# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

from ibcli import __version__
from ibcli.context import Context
from ibcli.debug import configure_logging

# `ibcli.commands` (which builds the command tree by import side effect) and
# `ibcli.dispatcher` (which imports the SDK) are imported inside _async_main
# instead of here. --version and --license need neither, and -l needs only the
# tree, so loading them eagerly made every invocation pay for the heaviest
# path. See _load_command_tree below.

# GPLv3 section 5(d) asks an interactive program to show "Appropriate Legal
# Notices" - copyright, no-warranty, redistribution terms and how to read the
# licence. The short form goes in the REPL banner and `--version`; `--license`
# prints the full notice.
_COPYRIGHT = "Copyright (C) 2026 Infoblox Inc."

_LICENSE_NOTICE = f"""ibcli {__version__}
{_COPYRIGHT}

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option)
any later version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
more details.

You should have received a copy of the GNU General Public License along
with this program. If not, see <https://www.gnu.org/licenses/>."""


def _load_command_tree() -> dict:
    """Import every command module and return the populated registry.

    Importing `ibcli.commands` is what registers the ~1,063 handlers; the
    modules are imported purely for that side effect.
    """
    from ibcli import commands  # noqa: F401  triggers @command registration
    from ibcli.registry import COMMANDS

    return COMMANDS


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ibcli",
        description="Python port of the Infoblox CLI (ibcli) using the ibx-nios-sdk.",
    )
    p.add_argument("-s", dest="server", help="WAPI host")
    p.add_argument("-u", dest="user", help="username")
    p.add_argument("-p", dest="password", help="password")
    p.add_argument("-m", "--master", dest="master", help="grid master IP")
    p.add_argument("-e", dest="exec_cmd", help="run a single command and exit")
    p.add_argument("-d", dest="debug", type=int, default=0, help="debug level 0-5")
    p.add_argument(
        "-l", dest="list_commands", action="store_true", help="list all commands and exit"
    )
    p.add_argument(
        "-V",
        "--version",
        action="version",
        # Version only: argparse reflows the version string through its help
        # formatter, which collapses embedded newlines onto a single line.
        # The legal notice lives in --license and the REPL banner instead.
        version=f"ibcli {__version__}",
    )
    p.add_argument(
        "--license",
        dest="show_license",
        action="store_true",
        help="show licensing and warranty terms and exit",
    )
    p.add_argument("-k", "--insecure", action="store_true", help="skip TLS verification")
    p.add_argument(
        "-i",
        "--idempotent",
        action="store_true",
        help="treat 'already exists' conflicts as warnings (skip, keep going)",
    )
    p.add_argument("--wapi-version", dest="wapi_version", help="override WAPI version")
    p.add_argument(
        "--allow-restricted",
        dest="allow_restricted",
        action="store_true",
        help="send operations the SDK believes WAPI forbids for "
        "an object type, instead of refusing them locally. "
        "For grids whose restrictions differ from the "
        "NIOS 9.1 table the SDK ships.",
    )
    p.add_argument(
        "--timeout",
        dest="timeout",
        type=float,
        default=30.0,
        help="per-request WAPI timeout in seconds (default 30). "
        "Raise it for slow grid-wide aggregations.",
    )
    p.add_argument("-b", "-f", dest="backup_file", help=argparse.SUPPRESS)
    p.add_argument("files", nargs="*", help="batch files to process")
    return p


def main() -> None:
    asyncio.run(_async_main())


async def _async_main() -> None:
    args = _build_argparser().parse_args()

    if args.backup_file is not None:
        # The Perl ibcli read a Data::Dumper snapshot in-process. Browsing a
        # backup is an offline read of a local file, not a grid call, so it
        # is out of scope for a WAPI client.
        print(
            "  Error: -b/-f (backup file browsing) is not supported.\n"
            "  ibcli talks to a live grid over WAPI; reading a backup file is"
            " an offline operation.\n"
            "  To retrieve a backup from a grid:"
            " ibcli -e 'download database <file>'",
            file=sys.stderr,
        )
        sys.exit(2)

    if args.show_license:
        print(_LICENSE_NOTICE)
        return

    if args.list_commands:
        for key in sorted(_load_command_tree()):
            print(key)
        return

    # Past this point every path can reach the grid, so the SDK has to be
    # present. Checking here rather than at package import keeps the
    # argv-only paths above free of it while still reporting a missing or
    # outdated SDK as one actionable line.
    from ibcli._sdk_check import require_sdk

    require_sdk()

    _load_command_tree()
    from ibcli.dispatcher import process_line

    configure_logging(args.debug)

    ctx = Context(
        debug_level=args.debug,
        idempotent=args.idempotent,
        verify=not args.insecure,
        wapi_version=args.wapi_version,
        timeout=args.timeout,
        enforce_restrictions=not args.allow_restricted,
    )

    cf = Path.cwd() / ".ibcli.cf"
    if cf.is_file():
        for raw in cf.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            await process_line(line, ctx)

    if args.server and args.user:
        password = args.password
        if password is None:
            password = getpass.getpass("Password: ")
        parts = [f"configure server {args.server}", f"user {args.user}", f"password {password}"]
        if args.master:
            parts.append(f"master {args.master}")
        await process_line(" ".join(parts), ctx)

    try:
        if args.exec_cmd:
            await process_line(args.exec_cmd, ctx)
            return

        if args.files:
            await _run_batch(args.files, ctx)
            return

        await _run_repl(ctx)
    finally:
        await _close(ctx)


async def _close(ctx: Context) -> None:
    """Release the SDK client, if one is open, on the way out."""
    if ctx.client is None:
        return
    try:
        await ctx.client.aclose()
    except Exception:
        pass
    ctx.client = None
    ctx.online = False


async def _run_batch(files: list[str], ctx: Context) -> None:
    # Imported here rather than at module scope so --version, --license
    # and -l never pull in the SDK. See the import note at the top of
    # this module.
    from ibcli.dispatcher import process_line

    for path in files:
        with open(path) as fh:
            buffered = ""
            for i, raw in enumerate(fh, 1):
                stripped = raw.rstrip("\n")
                if stripped.rstrip().endswith("\\"):
                    buffered += stripped.rstrip()[:-1] + " "
                    continue
                line = buffered + stripped
                buffered = ""
                if line.strip().startswith("#"):
                    sys.stdout.write(line + "\n" if not line.endswith("\n") else line)
                    continue
                if not line.strip():
                    continue
                print(f"read line {i}: {line}")
                await process_line(line, ctx)
            if buffered.strip():
                await process_line(buffered, ctx)


def _make_prompt_session(ctx: Context):  # pragma: no cover - interactive prompt_toolkit wiring
    from prompt_toolkit import PromptSession
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.shortcuts import CompleteStyle
    from prompt_toolkit.styles import Style

    from ibcli.completer import IbcliCompleter

    kb = KeyBindings()

    @kb.add("?")
    def _show_help(event):
        event.app.output.write(
            "\n  press <tab> for options; '\\' at end of line to continue; Ctrl-D to exit\n"
        )
        event.app.invalidate()

    @kb.add("\\")
    def _backslash(event):
        buf = event.app.current_buffer
        if buf.cursor_position == len(buf.text):
            buf.insert_text("\\")
        else:
            buf.reset()

    @kb.add("c-c")
    def _ignore_ctrl_c(event):
        event.app.current_buffer.reset()

    def _line_ends_with_backslash() -> bool:
        try:
            from prompt_toolkit.application.current import get_app

            app = get_app()
            return app.current_buffer.text.rstrip(" \t").endswith("\\")
        except Exception:
            return False

    # Polished completion menu styling: indigo selection bar, dim meta
    # column for help text, subtle scrollbar. Prompt itself stays default so
    # the user's terminal palette still drives colors.
    menu_style = Style.from_dict(
        {
            "completion-menu": "bg:#1e1b4b fg:#e0e7ff",
            "completion-menu.completion": "bg:#1e1b4b fg:#e0e7ff",
            "completion-menu.completion.current": "bg:#6366f1 fg:#ffffff bold",
            "completion-menu.meta": "bg:#1e1b4b fg:#a5b4fc italic",
            "completion-menu.meta.completion": "bg:#1e1b4b fg:#a5b4fc italic",
            "completion-menu.meta.completion.current": "bg:#6366f1 fg:#e0e7ff italic",
            "completion-menu.multi-column-meta": "bg:#1e1b4b fg:#a5b4fc italic",
            "scrollbar.background": "bg:#312e81",
            "scrollbar.button": "bg:#6366f1",
            "prompt": "fg:#a78bfa bold",
        }
    )

    return PromptSession(
        message=lambda: [("class:prompt", ctx.prompt)],
        completer=IbcliCompleter(ctx),
        complete_while_typing=False,
        complete_style=CompleteStyle.COLUMN,
        reserve_space_for_menu=6,
        mouse_support=False,
        style=menu_style,
        history=FileHistory(str(Path.home() / ".ibcli_history")),
        enable_history_search=True,
        key_bindings=kb,
        multiline=Condition(_line_ends_with_backslash),
    )


async def _run_repl(ctx: Context) -> None:  # pragma: no cover - interactive REPL loop
    # Imported here rather than at module scope so --version, --license
    # and -l never pull in the SDK. See the import note at the top of
    # this module.
    from ibcli.dispatcher import process_line

    print(f"""
#####################################################################
#
# the Infoblox CLI (Python port, beta)  v{__version__}
#
#####################################################################

ibcli comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it under
the terms of the GNU GPL v3 or later; run `ibcli --license`.

( press <tab> for help )
""")
    session = _make_prompt_session(ctx)
    while True:
        try:
            line = await session.prompt_async()
        except (EOFError, KeyboardInterrupt):
            break
        await process_line(line, ctx)


if __name__ == "__main__":  # pragma: no cover
    main()
