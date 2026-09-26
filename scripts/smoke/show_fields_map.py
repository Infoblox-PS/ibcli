#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Derive a {show-command → SDK-model-fields} mapping for the --deep sweep.

Walks the COMMANDS registry for every ``show …`` entry, inspects the
handler's source for the ``ctx.client.<mod>.<res>.list(...)`` call it
dispatches, and pulls the field list from the matching SDK Pydantic
model at ``ibx_nios_sdk.<mod>.models.<res>``.

Prints a TSV to stdout:  ``<concrete-command>\\t<field1,field2,…>``

Only concrete commands (no ``<placeholder>`` tokens) are emitted - those
are the ones sweep-show.sh can actually run. Commands whose handler has
no recognisable ``.list()`` call, or whose model module can't be
imported, are skipped silently (no row emitted).
"""

from __future__ import annotations

import importlib
import inspect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import ibcli.commands  # noqa: F401 - registers handlers
from ibcli.registry import COMMANDS

_LIST_CALL_RE = re.compile(r"ctx\.client\.([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)\s*\.\s*list\s*\(")

# Some SDK model modules don't match the <mod>/<resource> shape 1:1 -
# record overrides here as they turn up.
_MODEL_MODULE_OVERRIDES: dict[tuple[str, str], str] = {}

# Fields NIOS accepts on write but refuses to return: asking for them yields
# "Field is not readable: <name>". They belong in the model (you can set
# them) but not in a read sweep, where they are noise rather than findings.
_WRITE_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "old_password",  # adminuser / user_profile password change
        "password",
        "secret",  # grid + auth-service shared secrets
        "execute_now",  # scheduledtask trigger
        "upload_token",
    }
)


def _load_model_fields(mod: str, res: str) -> list[str] | None:
    """Resolve ctx.client.<mod>.<res> to its SDK model's field list."""
    key = (mod, res)
    mod_path = _MODEL_MODULE_OVERRIDES.get(key, f"ibx_nios_sdk.{mod}.models.{res}")
    try:
        module = importlib.import_module(mod_path)
    except ModuleNotFoundError:
        return None
    for name in dir(module):
        obj = getattr(module, name)
        if hasattr(obj, "model_fields") and getattr(obj, "__module__", "") == mod_path:
            fields = []
            for field_name, field in obj.model_fields.items():
                if field_name == "ref":
                    continue  # WAPI returns _ref by default; no need to ask
                if field_name in _WRITE_ONLY_FIELDS:
                    continue
                if str(field.annotation) == "object | None":
                    # A WAPI function (upgrade, restartservices, …), which the
                    # SDK models as an untyped field. Asking for one in
                    # _return_fields makes NIOS error.
                    continue
                # Ask for the WAPI alias - pydantic escapes builtin
                # collisions, so the model's `type_` is `type` on the wire
                # and NIOS rejects the escaped spelling.
                fields.append(field.alias or field_name)
            return fields
    return None


def _extract_resource(handler) -> tuple[str, str] | None:
    try:
        source = inspect.getsource(handler)
    except (TypeError, OSError):
        return None
    m = _LIST_CALL_RE.search(source)
    if not m:
        return None
    return (m.group(1), m.group(2))


def main() -> int:
    for path, entry in sorted(COMMANDS.items()):
        if not path.startswith("show "):
            continue
        if "<" in path or ">" in path:
            # Only concrete commands - sweep-show.sh filters the same way.
            continue
        if not entry.func:
            continue
        res = _extract_resource(entry.func)
        if res is None:
            continue
        fields = _load_model_fields(*res)
        if not fields:
            continue
        print(f"{path}\t{','.join(fields)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
