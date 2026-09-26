# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

import ipaddress
import re
from typing import Any


def is_arpa(name: str) -> bool:
    """Return True if *name* is a DNS reverse-zone FQDN.

    Covers both IPv4 (``.in-addr.arpa``) and IPv6 (``.ip6.arpa``) reverse
    zones. Bare ``in-addr.arpa`` / ``ip6.arpa`` also count - those are the
    top-level zones that RFC 6303 marks as locally-served.

    Callers rely on this to (a) skip CIDR-to-arpa rewriting on already-
    reversed names and (b) pick the correct ``zone_format`` on create.
    Before this returned True for only IPv4, every IPv6 reverse create
    tried to go in as a forward zone and NIOS rejected it with::

        Suffixes in-addr.arpa and ip6.arpa are forbidden for
        forward-mapping zone name.
    """
    lower = name.lower()
    return (
        lower.endswith(".in-addr.arpa")
        or lower.endswith(".ip6.arpa")
        or lower == "in-addr.arpa"
        or lower == "ip6.arpa"
    )


def arpa_to_net(arpa: str) -> str:
    """'3.2.1.in-addr.arpa' -> '1.2.3.0/24'. Matches Perl arpa_to_net().

    Only class-C boundaries (3-octet prefix) are handled - matches Perl.
    """
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)\.in-addr\.arpa$", arpa, re.IGNORECASE)
    if not m:
        raise ValueError(f"Not an arpa zone: {arpa!r}")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}.0/24"


def net_to_arpa(net: str) -> str:
    """'1.2.3.0/24' -> '3.2.1.in-addr.arpa'. For class-C boundaries."""
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)\.\d+/\d+$", net)
    if not m:
        raise ValueError(f"Not a network: {net!r}")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}.in-addr.arpa"


def normalize_cidr(value: str) -> str:
    """Accept '1.2.3/24', '1.2/16', etc.; return the zero-filled 4-octet CIDR.

    Raises ValueError for anything that's not a plausible CIDR.
    """
    if "/" not in value:
        raise ValueError(f"Not a CIDR: {value!r}")
    addr, _, mask = value.partition("/")
    if not mask.isdigit():
        raise ValueError(f"Bad mask: {value!r}")
    mask_int = int(mask)
    if mask_int < 0 or mask_int > 32:
        raise ValueError(f"Mask out of range: {value!r}")

    octets = addr.split(".")
    if len(octets) == 0 or any(o == "" for o in octets):
        raise ValueError(f"Empty address: {value!r}")
    if len(octets) > 4:
        raise ValueError(f"Too many octets: {value!r}")
    for o in octets:
        if not o.isdigit() or not (0 <= int(o) <= 255):
            raise ValueError(f"Bad octet in {value!r}")

    while len(octets) < 4:
        octets.append("0")
    return f"{'.'.join(octets)}/{mask_int}"


def cidr_family(value: str) -> str:
    """Return 'v4' or 'v6' depending on the CIDR family. Raises ValueError if neither."""
    try:
        net = ipaddress.ip_network(value, strict=False)
        return "v4" if net.version == 4 else "v6"
    except ValueError as exc:
        raise ValueError(f"Not a valid CIDR: {value!r}") from exc


def normalize_cidr_any(value: str) -> tuple[str, str]:
    """Return (normalized_cidr, family) where family is 'v4' or 'v6'.

    Accepts short IPv4 forms (e.g. '10.0.0/8') as well as full IPv4 and IPv6
    CIDRs.  Short IPv4 forms are normalized via normalize_cidr() before
    canonicalization so that ipaddress can parse them.
    """
    # Try direct parse first (handles full IPv4 and all IPv6).
    try:
        net = ipaddress.ip_network(value, strict=False)
        family = "v4" if net.version == 4 else "v6"
        return (str(net), family)
    except ValueError:
        pass
    # Fall back: try to normalize as a short-form IPv4 CIDR then re-parse.
    try:
        normalized = normalize_cidr(value)
        net = ipaddress.ip_network(normalized, strict=False)
        return (str(net), "v4")
    except ValueError as exc:
        raise ValueError(f"Not a valid CIDR: {value!r}") from exc


def as_dict(obj: Any) -> Any:
    """Convert a pydantic v2 model to a dict (alias keys, no None fields).

    Pass-through for dicts, None, and other primitives so formatters can call
    this unconditionally.
    """
    if hasattr(obj, "model_dump"):
        return obj.model_dump(by_alias=True, exclude_none=True)
    return obj


def parse_extra_fields(line: str) -> list[str]:
    """Extract comma-separated field names from a ``fields=a,b,c`` token.

    Used by ``show`` handlers to let a user request additional WAPI fields
    beyond the short default set the handler normally prints. Returns an
    empty list if the token isn't present. Field names are not validated -
    NIOS rejects bad ones with a clear error which bubbles up unchanged.

    Accepts both the raw-input form ``fields=a,b,c`` and the dispatcher's
    expanded form ``fields a,b,c`` (the tokenizer splits ``key=value`` into
    two tokens before the handler is called).
    """
    m = re.search(r"\bfields[= ]([A-Za-z_][\w,]*)", line)
    if not m:
        return []
    # Un-escape pydantic's builtin-collision suffix: the SDK models spell the
    # WAPI `type` field as `type_`, and NIOS rejects the trailing underscore
    # with "Unknown argument/field: 'type_'". No WAPI field name ends in an
    # underscore, so stripping the one pydantic added is unambiguous and lets
    # either spelling work. Exactly one, not `rstrip` - a name that really
    # ended in several underscores is not something pydantic produces, and
    # eating them all would rewrite it into a different field.
    fields = []
    for raw in m.group(1).split(","):
        name = raw[:-1] if raw.endswith("_") else raw
        if name:
            fields.append(name)
    return fields


def format_extra_field(value: Any) -> str:
    """Render an extra-field value for display under a ``show`` line.

    Scalars print as their string form; small member refs collapse to the
    IP; lists of dicts render one ``k=v`` line per entry; other dicts/lists
    fall back to ``str(value)``.
    """
    if isinstance(value, dict) and "ipv4addr" in value and len(value) <= 3:
        return str(value["ipv4addr"])
    if isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
        parts = []
        for item in value:
            clean = {k: v for k, v in item.items() if not k.startswith("_") and v not in (None, "")}
            # Unwrap extattrs-style {'value': X} wrappers.
            clean = {
                k: (
                    v["value"]
                    if isinstance(v, dict) and set(v) <= {"value", "inheritance_source"}
                    else v
                )
                for k, v in clean.items()
            }
            parts.append(", ".join(f"{k}={v}" for k, v in clean.items()))
        return " | ".join(parts)
    if isinstance(value, list):
        return ", ".join(str(x) for x in value)
    return str(value)
