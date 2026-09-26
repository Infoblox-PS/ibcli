# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

import inspect
import io
import re
import sys

from ibx_nios_sdk import ConflictError, NiosError, UnsupportedOperationError

from ibcli.context import Context
from ibcli.debug import debug_cli
from ibcli.parser import expand_line
from ibcli.registry import ALIASES, COMMANDS

# Verbs that mutate grid state - when a handler for one of these prints nothing
# we synthesize a "  OK" line so the operator sees confirmation. Read-only
# commands (show/list/etc.) are allowed to stay silent.
_MUTATING_VERBS = frozenset(
    {
        "add",
        "modify",
        "delete",
        "set",
        "move",
        "sign",
        "unsign",
        "clear",
        "dnssec",
        "rename",
        "copy",
        "rollover_ksk",
        "rollover_zsk",
    }
)


# NIOS wraps WAPI errors as e.g.:
#   "AdmConDataError: None (IBDataConflictError: IB.Data.Conflict:Server with name 'web1' already exists)"
# The useful payload is the last colon-delimited clause. Peel both wrappers.
_OUTER_WRAP = re.compile(r"^\w+Error:\s*\S+\s*\((.+)\)\s*$")
_INNER_WRAP = re.compile(r"^\w+Error:[\w.]+:\s*(.+)$")

# Signals that a failure is really "thing already exists" - NIOS returns these
# inconsistently as 400 BadRequest rather than 409 Conflict, so detect by text.
_EXISTS_SIGNALS = (
    "already exists",
    "duplicate object",
    "is already using name",
    # NIOS's wording when re-adding a fixed address whose MAC is already
    # bound to the same IP from a prior run.
    "used in two fixed addresses",
    # NIOS's wording when re-creating a network that still has live
    # leases/ranges/fixed addresses from a prior run.
    "must not have any active ip address",
)


# The SDK phrases its local refusal in library terms ("pass
# enforce_restrictions=False to NiosClient"), which is not something a CLI
# operator can act on. Point at the flag that does the same thing.
_SDK_OPTOUT = "pass enforce_restrictions=False to NiosClient to try anyway"
_CLI_OPTOUT = "re-run with --allow-restricted to send it anyway"

# Debug level from which an unexpected exception is re-raised with its
# traceback instead of being reported as a one-line error. Matches the
# `-d` table in docs/reference/cli-flags.md.
_TRACEBACK_LEVEL = 3


def _clean_nios_message(exc: NiosError) -> str:
    # Prefer wapi_text when present - it's the raw NIOS "text" field
    # (e.g. "IB.Data.Conflict:Server with name 'web1' already exists").
    msg = exc.wapi_text or exc.message or str(exc)
    m = _OUTER_WRAP.match(msg)
    if m:
        msg = m.group(1)
    m = _INNER_WRAP.match(msg)
    if m:
        msg = m.group(1)
    msg = msg.strip()
    if isinstance(exc, UnsupportedOperationError):
        msg = msg.replace(_SDK_OPTOUT, _CLI_OPTOUT)
    return msg


def _is_exists_conflict(exc: NiosError) -> bool:
    """True when a failure means "this object is already there".

    Only such failures may be demoted to `Skipped` under `-i`; anything else
    is a real error that must stay visible.

    NIOS's ``Conflict`` code is *not* sufficient evidence on its own. It also
    stamps unrelated hard failures - most notably

        Client.Ibap.Data.Conflict:
        The master does not have a valid Grid license installed for the
        member <ip>.

    which is a licensing wall, not an idempotent no-op. Treating every
    Conflict code as "already exists" made a 200-member pre-provision that
    created *nothing* report 200 skips and exit 0. So outside a real HTTP
    409 we require the message itself to say the object exists.
    """
    blob = " ".join(filter(None, (exc.wapi_text, exc.message))).lower()
    if any(sig in blob for sig in _EXISTS_SIGNALS):
        return True
    # A true 409 carries conflict semantics in the status code itself.
    return isinstance(exc, ConflictError)


# httpx timeout classes carry an empty str(), so a naive
# f"{type(e).__name__}: {e}" renders as a bare "ReadTimeout: " - accurate and
# useless. Name the remedy instead.
_TIMEOUT_NAMES = frozenset(
    {
        "ReadTimeout",
        "ConnectTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "TimeoutException",
    }
)


def _validation_error_summary(exc: Exception) -> str | None:
    """One-line summary of a pydantic ValidationError, or None if it isn't one.

    These mean the SDK's model disagrees with what this NIOS actually
    returned - e.g. `Grid.restart_status` is typed `str` but NIOS answers
    with a struct. Pydantic's default rendering is a multi-line dump with a
    docs URL, which buries the one fact that matters: which field, and that
    it is an SDK-side type mismatch rather than anything the operator did.
    """
    if type(exc).__name__ != "ValidationError":
        return None
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return None
    try:
        rows = errors()
    except Exception:
        return None
    fields = []
    for row in rows:
        loc = ".".join(str(x) for x in row.get("loc", ())) or "?"
        fields.append(f"{loc} ({row.get('type', 'invalid')})")
    if not fields:
        return None
    title = getattr(exc, "title", None) or "response"
    return (
        f"the SDK model for {title} does not match what this grid returned: "
        f"{', '.join(fields[:4])}"
        f"{' …' if len(fields) > 4 else ''}. "
        "This is an ibx-nios-sdk model/NIOS-version mismatch - drop the "
        "offending field from fields= to work around it."
    )


def _describe_exception(exc: Exception, ctx: Context) -> str:
    """Render an unexpected exception as something an operator can act on."""
    name = type(exc).__name__
    detail = str(exc).strip()
    if name in _TIMEOUT_NAMES:
        return (
            f"{name}: the grid did not respond within {ctx.timeout:g}s. "
            "Some grid-wide aggregations take longer on a populated grid - "
            "retry with a higher --timeout."
        )
    summary = _validation_error_summary(exc)
    if summary:
        return f"{name}: {summary}"
    return f"{name}: {detail}" if detail else name


class _Tee:
    """File-like proxy that mirrors writes to two sinks (stdout + capture buffer)."""

    def __init__(self, *sinks):
        self._sinks = sinks

    def write(self, data):
        for s in self._sinks:
            s.write(data)
        return len(data)

    def flush(self):
        for s in self._sinks:
            s.flush()

    def __getattr__(self, name):
        return getattr(self._sinks[0], name)


async def process_line(line: str, ctx: Context) -> None:
    """Parse and dispatch one line. Single entrypoint for REPL, -e, batch."""
    line = re.sub(r"\\\s+", " ", line)
    if line.endswith("\\"):
        line = line[:-1].rstrip()
    line = line.strip()
    if not line:
        return

    for alias, target in ALIASES.items():
        if line == alias or line.startswith(alias + " "):
            line = target + line[len(alias) :]
            break

    expanded, error, match_line = expand_line(line)
    if error:
        print(error)
        return

    debug_cli(ctx, 1, f"dispatch: {expanded!r} -> {match_line!r}")

    entry = COMMANDS.get(match_line)
    if entry and entry.func:
        tokens = set(expanded.split())
        is_mutating = bool(tokens & _MUTATING_VERBS)
        buf = io.StringIO()
        real_stdout = sys.stdout
        if is_mutating:
            sys.stdout = _Tee(real_stdout, buf)
        try:
            try:
                result = entry.func(expanded, ctx)
                if inspect.isawaitable(result):
                    await result
            except NiosError as e:
                msg = _clean_nios_message(e)
                if ctx.idempotent and _is_exists_conflict(e):
                    print(f"  Skipped: {msg}", file=real_stdout)
                else:
                    print(f"  Error: {msg}", file=real_stdout)
                return
            except Exception as e:  # noqa: BLE001 - a CLI must not traceback
                # Anything a handler didn't anticipate (a malformed ref the
                # SDK rejects with ValueError, a transport error, a bad
                # response shape) becomes an error line. Without this the
                # traceback escapes process_line and kills the REPL loop.
                # SystemExit/KeyboardInterrupt are BaseExceptions and still
                # propagate, so `exit` and Ctrl-C keep working.
                #
                # From -d 3 (the SDK-detail level) the traceback is more
                # useful than the one-liner, so re-raise there. Lower levels
                # are documented as tracing only - see
                # docs/reference/cli-flags.md - and must not turn a handler
                # bug into a dead REPL.
                if ctx.debug_level >= _TRACEBACK_LEVEL:
                    raise
                print(f"  Error: {_describe_exception(e, ctx)}", file=real_stdout)
                return
        finally:
            sys.stdout = real_stdout
        if is_mutating and not buf.getvalue().strip():
            print(f"  OK: {expanded}")
        return

    if entry and entry.words:
        print(f"  Incomplete : {expanded} ({entry.words.replace('=', ' ')})")
        return

    print(f"  Unknown command: {expanded}")
