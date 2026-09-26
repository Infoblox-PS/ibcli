# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Shared value coercion for `configure ... set <key>=<value>` pass-throughs.

Rules, in order:

1. ``true`` / ``false`` (case-insensitive) → Python bool
2. All-digit string → int
3. Starts with ``{`` or ``[`` → JSON-decoded (for struct / struct-list fields)
4. ACL shortcut - comma-separated ``<PERM>:<cidr>`` entries expand to a
   list of ``addressac`` structs the NIOS WAPI expects for fields like
   ``allow_query`` / ``allow_transfer`` / ``allow_update``. Example::

       ALLOW:10.0.0.0/8,DENY:192.168.0.0/16
       ALLOW:10.0.0.0/8         # single entry
       10.0.0.0/8               # bare CIDR → ALLOWed

   Permissions are case-insensitive. Mixed with named ACL refs via the
   ``acl:<ref>`` form::

       ALLOW:10.0.0.0/8,acl:namedacl/Li5hY2w..:trusted

5. Otherwise → the original string
"""

from __future__ import annotations

import json
import re
from typing import Any

_CIDR_V4 = r"\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?"
_CIDR_V6 = r"[0-9a-fA-F:]+(?:/\d{1,3})?"
_CIDR = rf"(?:{_CIDR_V4}|{_CIDR_V6})"
_ACL_ENTRY = re.compile(
    rf"^(?:(ALLOW|DENY):)?({_CIDR})$|^acl:(\S+)$",
    re.IGNORECASE,
)


def _maybe_acl_list(v: str) -> list[dict[str, Any]] | None:
    """If *v* looks like an ACL shortcut, return the expanded struct list.

    Returns None when the string doesn't match, letting coerce() fall
    through to the next rule.
    """
    parts = [p.strip() for p in v.split(",") if p.strip()]
    if not parts:
        return None
    out: list[dict[str, Any]] = []
    for p in parts:
        m = _ACL_ENTRY.match(p)
        if not m:
            return None
        perm, cidr, ref = m.group(1), m.group(2), m.group(3)
        if ref is not None:
            out.append({"_ref": ref})
        else:
            out.append(
                {
                    "address": cidr,
                    "permission": (perm or "ALLOW").upper(),
                    "_struct": "addressac",
                }
            )
    return out


def coerce(v: str) -> Any:
    """Coerce a CLI string value to a Python value suitable for WAPI PUT."""
    if not isinstance(v, str):
        return v
    lower = v.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if v.lstrip("-").isdigit():
        return int(v)
    if v and v[0] in "[{":
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            pass
    acl = _maybe_acl_list(v)
    if acl is not None:
        return acl
    return v
