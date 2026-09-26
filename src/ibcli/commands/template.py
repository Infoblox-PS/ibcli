# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

import re

from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict, format_extra_field, parse_extra_fields

# ---------------------------------------------------------------------------
# configure template network add <name> cidr <num>
# ---------------------------------------------------------------------------

register("configure", words="template", help="Create, modify or delete grid objects.")
register(
    "configure template",
    words="network",
    help="DHCP network/range/fixed templates (for provisioning).",
)
register("configure template network", words="add <name>", help="Network templates.")
register("configure template network add", words="<name>")

_TMPLADD_WORDS = "<cr> comment=<comment>|set"
_SET_NAME = "<name>"
_SET_VALUE = "<value>"

register("configure template network add <name>", words="cidr")
register("configure template network add <name> cidr", words="<num>")
register("configure template network add <name> cidr <num>", words=_TMPLADD_WORDS)

_TMPLADD_BASE = "configure template network add <name> cidr <num>"
for _depth in range(16):
    _pfx = _TMPLADD_BASE + (" set <name> <value>" * _depth)
    register(f"{_pfx} set", words=_SET_NAME)
    register(f"{_pfx} set <name>", words=_SET_VALUE)
    register(f"{_pfx} set <name> <value>", words=_TMPLADD_WORDS)


def _parse_kv(line: str, key: str) -> str | None:
    m = re.search(rf"\b{re.escape(key)}\s+(\S+)", line)
    return m.group(1) if m else None


def _parse_comment(line: str) -> str | None:
    m = re.search(r'\bcomment\s+"([^"]+)"', line)
    if m:
        return m.group(1)
    m = re.search(r"\bcomment\s+(\S+)", line)
    return m.group(1) if m else None


def _parse_extattrs(line: str) -> dict[str, dict[str, str]]:
    """Parse all `set key value` or `set key=value` pairs into WAPI extattrs."""
    result: dict[str, dict[str, str]] = {}
    # Form 1: tokenizer-expanded -> "set <key> <value>" (no '=' in key)
    for m in re.finditer(r"\bset\s+(\S+)\s+(\S+)", line):
        k, v = m.group(1), m.group(2)
        if "=" not in k:
            result[k] = {"value": v}
    # Form 2: raw -> "set key=value"
    for m in re.finditer(r"\bset\s+(\S+)=(\S+)", line):
        result[m.group(1)] = {"value": m.group(2)}
    return result


@command(
    "configure template network add <name> cidr <num>",
    words=_TMPLADD_WORDS,
    help="Create a network template.",
)
async def cli_add_network_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\btemplate network add\s+(\S+)", line)
    if not m:
        print("  Error: template name required")
        return
    name = m.group(1)

    cm = re.search(r"\bcidr\s+(\d+)", line)
    if not cm:
        print("  Error: cidr required")
        return
    cidr = int(cm.group(1))

    # WAPI's network template uses `netmask` (prefix length) with
    # `allow_any_netmask=False`; the CLI's user-facing `cidr <n>` is the same
    # value as `netmask`.
    body: dict = {"name": name, "netmask": cidr}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas

    await ctx.client.ipam.networktemplate.create(body)


# Bind handler to every static set-chain endpoint.
for _depth in range(1, 17):
    _ml = _TMPLADD_BASE + (" set <name> <value>" * _depth)
    command(_ml, words=_TMPLADD_WORDS)(cli_add_network_template)


# ---------------------------------------------------------------------------
# configure template network <name> delete
# ---------------------------------------------------------------------------

register("configure template network <name>", words="delete")
register("configure template network <name> delete", words="<cr>")


@command(
    "configure template network <name> delete",
    words="<cr>",
    help="Delete a network template by name.",
)
async def cli_delete_network_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\btemplate network\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: template name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.ipam.networktemplate.list(name=name)]
    if not results:
        print(f"  No template found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.ipam.networktemplate.delete(ref)


# ---------------------------------------------------------------------------
# show template network [<name>]
# ---------------------------------------------------------------------------

register("show", words="template", help="Read grid state without modifying anything.")
register(
    "show template", words="network", help="DHCP templates (network/range/fixed + IPv6 variants)."
)
register("show template network", words="<cr> <name>")
register("show template network <name>", words="<cr> fields=<field1,field2,...>")


def _print_template(t: dict) -> None:
    parts = [f"name={t.get('name', '')}"]
    if t.get("cidr") is not None:
        parts.append(f"cidr={t['cidr']}")
    if t.get("comment"):
        parts.append(f"comment={t['comment']}")
    print(" ".join(parts))


@command("show template network", words="<cr> <name>", help="List network templates.")
@command(
    "show template network <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific network template.",
)
async def cli_show_network_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    # "show template network [<name>]" → name at tokens[3] if present
    tmpl_name = None
    if len(tokens) >= 4 and "=" not in tokens[3]:
        tmpl_name = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields": ["name", "comment"] + extra}
    if tmpl_name:
        kwargs["name"] = tmpl_name

    results = [as_dict(r) async for r in ctx.client.ipam.networktemplate.list(**kwargs)]

    if not results:
        if tmpl_name:
            print(f"  No template found: {tmpl_name}")
        return

    for t in results:
        _print_template(t)
        for f in extra:
            val = t.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")
