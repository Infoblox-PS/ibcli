# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Extensible attribute definitions - slice 6a.

Command shapes:

  configure grid attribute add <name> type <type> [comment <text>] [list_value <v>...]
  configure grid attribute <name> delete
  show grid attribute [<name>]

The earlier `configure grid device_type` verb has been removed because
it duplicated `configure grid attribute add <name> type ENUM` with a
misleading name. Use the generic `attribute` verb to create ENUM-typed
EAs (including ones used to classify devices). The corresponding
register/handler blocks below are wrapped in `\"\"\" ... \"\"\"` and
can be un-hidden if the dedicated verb is ever reinstated.
"""

from __future__ import annotations

import re

from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict, format_extra_field, parse_extra_fields

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_kv(line: str, key: str) -> str | None:
    m = re.search(rf"\b{re.escape(key)}[= ](\S+)", line)
    return m.group(1) if m else None


def _parse_comment(line: str) -> str | None:
    m = re.search(r'\bcomment[= ]"([^"]+)"', line)
    if m:
        return m.group(1)
    m = re.search(r"\bcomment[= ](\S+)", line)
    return m.group(1) if m else None


def _parse_list_values(line: str) -> list[str]:
    """Return all values given as 'list_value <v>' tokens."""
    return re.findall(r"\blist_value\s+(\S+)", line)


# ---------------------------------------------------------------------------
# Waypoints - configure grid attribute
#
# The 'type' token accepts one of six literal values (STRING|INTEGER|…).
# Because <type> is not in SPECOPS, we use explicit literal words for the
# type sub-context. The @command decorators below attach the handler to every
# valid type-value node so the dispatcher can find it.
# ---------------------------------------------------------------------------

register("configure", words="grid", help="Create, modify or delete grid objects.")
register(
    "configure grid",
    words="attribute",
    help="Grid-level settings, members, schedules, and topology.",
)

register(
    "configure grid attribute",
    words="add <name>",
    help="Extensible Attribute (EA) definitions grid-wide.",
)
register("configure grid attribute add", words="<name>")
register(
    "configure grid attribute add <name>",
    words="<cr> type",
)
register(
    "configure grid attribute add <name> type",
    words="string integer email enum url date",
)
# Post-type: each type variant supports optional comment and list_value tokens.
# These contexts are also registered as @command targets below.
_POST_TYPE_WORDS = "<cr> comment list_value=<value>"
_EA_TYPES = ("string", "integer", "email", "enum", "url", "date")
for _t in _EA_TYPES:
    register(f"configure grid attribute add <name> type {_t}", words=_POST_TYPE_WORDS)
    register(f"configure grid attribute add <name> type {_t} comment", words="<comment>")
    register(
        f"configure grid attribute add <name> type {_t} comment <comment>", words=_POST_TYPE_WORDS
    )

register("configure grid attribute <name>", words="delete")
register("configure grid attribute <name> delete", words="<cr>")

register("show", words="grid", help="Read grid state without modifying anything.")
register("show grid", words="attribute", help="Grid-level configuration and metadata.")
register("show grid attribute", words="<cr> <name>")
register("show grid attribute <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Waypoints - configure grid device_type
# ---------------------------------------------------------------------------
# Hidden - device_type was a thin wrapper that created an ENUM-typed EA. It
# duplicated `configure grid attribute add <name> type ENUM` with a misleading
# verb name (the handler didn't restrict the name to "Device Type"). Users
# should use the generic `attribute` verb instead. Unhide by removing the
# surrounding `""" ... """` block.
"""
register("configure grid device_type", words="add <name>")
register("configure grid device_type add", words="<name>")
register(
    "configure grid device_type add <name>",
    words="<cr> list_value=<value>",
)
register("configure grid device_type <name>", words="delete")
register("configure grid device_type <name> delete", words="<cr>")

register("show grid device_type", words="<cr> <name>")
register("show grid device_type <name>", words="<cr> fields=<field1,field2,...>")
"""


# ===========================================================================
# Handlers - EA defs
# ===========================================================================


async def _do_add_attribute(line: str, ctx: Context) -> None:
    """Shared implementation for cli_add_attribute across all type variants."""
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r'\battribute add\s+(?:"([^"]+)"|(\S+))', line)
    if not m:
        print("  Error: attribute name required")
        return
    name = m.group(1) or m.group(2)

    ea_type = _parse_kv(line, "type")
    comment = _parse_comment(line)
    list_vals = _parse_list_values(line)

    body: dict = {"name": name}
    if ea_type:
        body["type"] = ea_type.upper()
    if comment:
        body["comment"] = comment
    if list_vals:
        body["list_values"] = [{"value": v} for v in list_vals]

    await ctx.client.grid.extensibleattributedef.create(body)


# Register handler at every valid terminal node for 'configure grid attribute add <name>'.
# Terminal nodes are: the type-value level itself and the post-comment/post-list_value levels.


@command(
    "configure grid attribute add <name> type string",
    words=_POST_TYPE_WORDS,
    help="Add an extensible attribute definition (STRING type).",
)
@command(
    "configure grid attribute add <name> type integer",
    words=_POST_TYPE_WORDS,
    help="Add an extensible attribute definition (INTEGER type).",
)
@command(
    "configure grid attribute add <name> type email",
    words=_POST_TYPE_WORDS,
    help="Add an extensible attribute definition (EMAIL type).",
)
@command(
    "configure grid attribute add <name> type enum",
    words=_POST_TYPE_WORDS,
    help="Add an extensible attribute definition (ENUM type).",
)
@command(
    "configure grid attribute add <name> type url",
    words=_POST_TYPE_WORDS,
    help="Add an extensible attribute definition (URL type).",
)
@command(
    "configure grid attribute add <name> type date",
    words=_POST_TYPE_WORDS,
    help="Add an extensible attribute definition (DATE type).",
)
# Also handle the post-comment and post-list_value nodes for each type.
# We register the handler at the comment/<comment> level so the dispatcher fires
# even when the user includes a comment after the type.
@command(
    "configure grid attribute add <name> type string comment <comment>",
    words=_POST_TYPE_WORDS,
    help="Add an extensible attribute definition.",
)
@command(
    "configure grid attribute add <name> type integer comment <comment>",
    words=_POST_TYPE_WORDS,
    help="Add an extensible attribute definition.",
)
@command(
    "configure grid attribute add <name> type email comment <comment>",
    words=_POST_TYPE_WORDS,
    help="Add an extensible attribute definition.",
)
@command(
    "configure grid attribute add <name> type enum comment <comment>",
    words=_POST_TYPE_WORDS,
    help="Add an extensible attribute definition.",
)
@command(
    "configure grid attribute add <name> type url comment <comment>",
    words=_POST_TYPE_WORDS,
    help="Add an extensible attribute definition.",
)
@command(
    "configure grid attribute add <name> type date comment <comment>",
    words=_POST_TYPE_WORDS,
    help="Add an extensible attribute definition.",
)
async def cli_add_attribute(line: str, ctx: Context) -> None:
    await _do_add_attribute(line, ctx)


@command(
    "configure grid attribute <name> delete",
    words="<cr>",
    help="Delete an extensible attribute definition.",
)
async def cli_del_attribute(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r'\battribute\s+(?:"([^"]+)"|(\S+))\s+delete', line)
    if not m:
        print("  Error: attribute name required")
        return
    name = m.group(1) or m.group(2)

    results = [as_dict(r) async for r in ctx.client.grid.extensibleattributedef.list(name=name)]
    if not results:
        print(f"  No attribute found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.extensibleattributedef.delete(ref)


@command("show grid attribute", words="<cr> <name>", help="List extensible attribute definitions.")
@command(
    "show grid attribute <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific EA definition.",
)
async def cli_show_attribute(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["name", "type", "comment", "list_values"] + extra}
    # "show grid attribute [<name>]" - tokens: show(0) grid(1) attribute(2) [name(3)]
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        kwargs["name"] = tokens[3]

    results = [as_dict(r) async for r in ctx.client.grid.extensibleattributedef.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("type"):
            parts.append(f"type={r['type']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        lv = r.get("list_values")
        if lv:
            vals = ",".join(v.get("value", "") for v in lv)
            parts.append(f"list_values={vals}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Handlers - Device types (thin wrappers over extensibleattributedef)
# ===========================================================================
# Hidden - see the note above the waypoints block.
r"""
@command(
    "configure grid device_type add <name>",
    words="<cr> list_value=<value>",
    help="Add a device-type EA definition (ENUM type).",
)
async def cli_add_device_type(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bdevice_type add\s+(\S+)", line)
    if not m:
        print("  Error: device_type name required")
        return
    name = m.group(1)

    list_vals = _parse_list_values(line)

    body: dict = {"name": name, "type": "ENUM"}
    if list_vals:
        body["list_values"] = [{"value": v} for v in list_vals]

    await ctx.client.grid.extensibleattributedef.create(body)


@command(
    "configure grid device_type <name> delete",
    words="<cr>",
    help="Delete a device-type EA definition.",
)
async def cli_del_device_type(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bdevice_type\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: device_type name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.grid.extensibleattributedef.list(name=name)]
    if not results:
        print(f"  No device_type found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.extensibleattributedef.delete(ref)


@command(
    "show grid device_type",
    words="<cr> <name>",
    help="List device-type EA definitions.",
)
@command(
    "show grid device_type <name>",
    words="<cr>",
    help="Show a specific device-type EA definition.",
)
async def cli_show_device_type(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    kwargs: dict = {"return_fields_plus": ["name", "type", "list_values"], "type": "ENUM"}
    # "show grid device_type [<name>]" - tokens: show(0) grid(1) device_type(2) [name(3)]
    if len(tokens) >= 4 and not tokens[3].startswith("<"):
        kwargs["name"] = tokens[3]

    results = [as_dict(r) async for r in ctx.client.grid.extensibleattributedef.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        lv = r.get("list_values")
        if lv:
            vals = ",".join(v.get("value", "") for v in lv)
            parts.append(f"list_values={vals}")
        print(" ".join(parts))
"""
