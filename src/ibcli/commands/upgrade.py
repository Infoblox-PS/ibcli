# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Phase 9 - Upgrade + distribution scheduling commands.

WAPI access surface
--------------------
ctx.client.grid.upgradegroup        full CRUD (name, comment, policies, …)
ctx.client.grid.upgradeschedule     singleton - list+update only (1 per grid)
ctx.client.grid.distributionschedule singleton - list+update only (1 per grid)
ctx.client.grid.upgradestatus       read-only

Command vocabulary
-------------------
# Upgrade groups
show upgrade_group [<name>]
configure upgrade_group add <name> [comment=<text>] [upgrade_policy=<policy>]
                                   [distribution_policy=<policy>]
configure upgrade_group <name> delete
configure upgrade_group <name> set <key>=<value> ...

# Upgrade schedule (singleton - show + set only)
show upgrade_schedule
configure upgrade_schedule set <key>=<value> ...

# Distribution schedule (singleton - show + set only)
show distribution_schedule
configure distribution_schedule set <key>=<value> ...

# Upgrade status (read-only)
show upgrade_status [<member>]
"""

from __future__ import annotations

import re

from ibcli.coerce import coerce as _coerce_value  # noqa: F401
from ibcli.completions_keys import keys_completer_for_path
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict, format_extra_field, parse_extra_fields

_UPGRADE_GROUP_KEYS = keys_completer_for_path("grid", "upgradegroup")
_UPGRADE_SCHEDULE_KEYS = keys_completer_for_path("grid", "upgradeschedule")
_DIST_SCHEDULE_KEYS = keys_completer_for_path("grid", "distributionschedule")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_kv(line: str, key: str) -> str | None:
    """Extract value for *key* from 'key=value' or 'key value' forms."""
    m = re.search(rf"\b{re.escape(key)}\s*=\s*(\S+)", line)
    if m:
        return m.group(1)
    m = re.search(rf"\b{re.escape(key)}\s+(\S+)", line)
    return m.group(1) if m else None


def _parse_inline_kvs(line: str, marker: str) -> dict:
    """Parse key/value pairs appearing after *marker* in *line*.

    Handles both ``key=value`` and tokenised ``key value`` forms.
    Returns a dict with coerced values.
    """
    idx = line.find(marker)
    if idx == -1:
        return {}
    tail = line[idx + len(marker) :].strip()
    if not tail:
        return {}

    result: dict = {}
    tokens = tail.split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if "=" in tok:
            k, _, v = tok.partition("=")
            if k and v:
                result[k] = _coerce_value(v)
            i += 1
        elif i + 1 < len(tokens):
            result[tok] = _coerce_value(tokens[i + 1])
            i += 2
        else:
            i += 1
    return result


# ===========================================================================
# Registrations
# ===========================================================================

# --- upgrade_group ----------------------------------------------------------
register("show", words="upgrade_group", help="Read grid state without modifying anything.")
register("show upgrade_group", words="<cr> <name>", help="Upgrade-group membership.")
register("show upgrade_group <name>", words="<cr> fields=<field1,field2,...>")

register("configure", words="upgrade_group", help="Create, modify or delete grid objects.")
register(
    "configure upgrade_group",
    words="add <name>",
    help="Upgrade groups - ordered member cohorts for rolling upgrades.",
)
register("configure upgrade_group add", words="<name>")
register(
    "configure upgrade_group add <name>",
    words="<cr> comment=<comment>|upgrade_policy=<name>|distribution_policy=<name>",
)
register("configure upgrade_group <name>", words="delete set")
register("configure upgrade_group <name> delete", words="<cr>")
register("configure upgrade_group <name> set", words="<key>=<value>", dynamic=_UPGRADE_GROUP_KEYS)

# --- upgrade_schedule (singleton) ------------------------------------------
register("show", words="upgrade_schedule", help="Read grid state without modifying anything.")
register("show upgrade_schedule", words="<cr> fields=<field1,field2,...>")

register("configure", words="upgrade_schedule", help="Create, modify or delete grid objects.")
register(
    "configure upgrade_schedule",
    words="set",
    help="Grid-wide upgrade schedule (when the upgrade runs).",
)
register("configure upgrade_schedule set", words="<key>=<value>", dynamic=_UPGRADE_SCHEDULE_KEYS)

# --- distribution_schedule (singleton) -------------------------------------
register("show", words="distribution_schedule", help="Read grid state without modifying anything.")
register("show distribution_schedule", words="<cr>", help="Pre-upgrade distribution schedule.")

register("configure", words="distribution_schedule", help="Create, modify or delete grid objects.")
register(
    "configure distribution_schedule",
    words="set",
    help="Grid-wide distribution schedule (pre-upgrade staging).",
)
register("configure distribution_schedule set", words="<key>=<value>", dynamic=_DIST_SCHEDULE_KEYS)

# --- upgrade_status (read-only) --------------------------------------------
register("show", words="upgrade_status", help="Read grid state without modifying anything.")
register(
    "show upgrade_status",
    words="grid group vnode pnode",
    help="Upgrade status per grid/group/vnode/pnode.",
)
register("show upgrade_status grid", words="<cr>")
register("show upgrade_status group", words="<cr> <name>")
register("show upgrade_status group <name>", words="<cr> fields=<field1,field2,...>")
register("show upgrade_status vnode", words="<cr> <name>")
register("show upgrade_status vnode <name>", words="<cr> fields=<field1,field2,...>")
register("show upgrade_status pnode", words="<cr> <name>")
register("show upgrade_status pnode <name>", words="<cr> fields=<field1,field2,...>")


# ===========================================================================
# Handlers - upgrade_group
# ===========================================================================


@command("show upgrade_group", words="<cr> <name>", help="Show upgrade group(s).")
@command(
    "show upgrade_group <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific upgrade group.",
)
async def cli_show_upgrade_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    # "show upgrade_group" → 2 tokens; optional name at index 2
    name = None
    if len(tokens) >= 3 and "=" not in tokens[2]:
        name = tokens[2]

    extra = parse_extra_fields(line)
    filters: dict = {}
    if extra:
        filters["return_fields_plus"] = extra
    if name:
        filters["name"] = name

    results = [as_dict(r) async for r in ctx.client.grid.upgradegroup.list(**filters)]
    if not results:
        if name:
            print(f"  No upgrade group found: {name}")
        else:
            print("  No upgrade groups found")
        return

    for r in results:
        _print_upgrade_group(r)
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


def _print_upgrade_group(r: dict) -> None:
    parts = [f"name={r.get('name', '')}"]
    if r.get("comment"):
        parts.append(f"comment={r['comment']}")
    if r.get("upgrade_policy"):
        parts.append(f"upgrade_policy={r['upgrade_policy']}")
    if r.get("distribution_policy"):
        parts.append(f"distribution_policy={r['distribution_policy']}")
    if r.get("time_zone"):
        parts.append(f"time_zone={r['time_zone']}")
    print("  " + " ".join(parts))


@command(
    "configure upgrade_group add <name>",
    words="<cr> comment=<text>|upgrade_policy=<policy>|distribution_policy=<policy>",
    help="Add an upgrade group.",
)
async def cli_add_upgrade_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bupgrade_group add\s+(\S+)", line)
    if not m:
        print("  Error: upgrade_group name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_kv(line, "comment")
    if comment:
        body["comment"] = comment
    upgrade_policy = _parse_kv(line, "upgrade_policy")
    if upgrade_policy:
        body["upgrade_policy"] = upgrade_policy
    distribution_policy = _parse_kv(line, "distribution_policy")
    if distribution_policy:
        body["distribution_policy"] = distribution_policy

    result = await ctx.client.grid.upgradegroup.create(body)
    r = as_dict(result)
    print(f"  Created: {r.get('_ref', r.get('name', name))}")


@command(
    "configure upgrade_group <name> delete",
    words="<cr>",
    help="Delete an upgrade group.",
)
async def cli_del_upgrade_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bupgrade_group\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: upgrade_group name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.grid.upgradegroup.list(name=name)]
    if not results:
        print(f"  No upgrade group found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.upgradegroup.delete(ref)
    print(f"  Deleted: {name}")


@command(
    "configure upgrade_group <name> set",
    words="<key>=<value>",
    help="Set field(s) on an upgrade group.",
)
async def cli_set_upgrade_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bupgrade_group\s+(\S+)\s+set", line)
    if not m:
        print("  Error: upgrade_group name required")
        return
    name = m.group(1)

    kvs = _parse_inline_kvs(line, " set ")
    if not kvs:
        print("  Error: no key=value pairs provided")
        return

    results = [as_dict(r) async for r in ctx.client.grid.upgradegroup.list(name=name)]
    if not results:
        print(f"  No upgrade group found: {name}")
        return
    ref = results[0]["_ref"]
    result = await ctx.client.grid.upgradegroup.update(ref, kvs)
    r = as_dict(result)
    print(f"  Updated: {r.get('_ref', ref)}")


# ===========================================================================
# Handlers - upgrade_schedule (singleton)
# ===========================================================================


@command(
    "show upgrade_schedule",
    words="<cr> fields=<field1,field2,...>",
    help="Show the grid upgrade schedule.",
)
async def cli_show_upgrade_schedule(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    extra = parse_extra_fields(line)
    kwargs: dict = {}
    if extra:
        kwargs["return_fields_plus"] = extra
    results = [as_dict(r) async for r in ctx.client.grid.upgradeschedule.list(**kwargs)]
    if not results:
        print("  No upgrade schedule found")
        return

    r = results[0]
    parts = []
    if r.get("active") is not None:
        parts.append(f"active={r['active']}")
    if r.get("start_time") is not None:
        parts.append(f"start_time={r['start_time']}")
    if r.get("time_zone"):
        parts.append(f"time_zone={r['time_zone']}")
    print("  " + " ".join(parts) if parts else "  (no fields returned)")
    for f in extra:
        val = r.get(f)
        if val in (None, "", [], {}):
            continue
        print(f"  {f}: {format_extra_field(val)}")


@command(
    "configure upgrade_schedule set",
    words="<key>=<value>",
    help="Set field(s) on the grid upgrade schedule.",
)
async def cli_set_upgrade_schedule(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    kvs = _parse_inline_kvs(line, " set ")
    if not kvs:
        print("  Error: no key=value pairs provided")
        return

    results = [as_dict(r) async for r in ctx.client.grid.upgradeschedule.list()]
    if not results:
        print("  No upgrade schedule found")
        return
    ref = results[0]["_ref"]
    result = await ctx.client.grid.upgradeschedule.update(ref, kvs)
    r = as_dict(result)
    print(f"  Updated: {r.get('_ref', ref)}")


# ===========================================================================
# Handlers - distribution_schedule (singleton)
# ===========================================================================


@command(
    "show distribution_schedule",
    words="<cr> fields=<field1,field2,...>",
    help="Show the grid distribution schedule.",
)
async def cli_show_distribution_schedule(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    extra = parse_extra_fields(line)
    kwargs: dict = {}
    if extra:
        kwargs["return_fields_plus"] = extra
    results = [as_dict(r) async for r in ctx.client.grid.distributionschedule.list(**kwargs)]
    if not results:
        print("  No distribution schedule found")
        return

    r = results[0]
    parts = []
    if r.get("active") is not None:
        parts.append(f"active={r['active']}")
    if r.get("start_time") is not None:
        parts.append(f"start_time={r['start_time']}")
    if r.get("time_zone"):
        parts.append(f"time_zone={r['time_zone']}")
    print("  " + " ".join(parts) if parts else "  (no fields returned)")
    for f in extra:
        val = r.get(f)
        if val in (None, "", [], {}):
            continue
        print(f"  {f}: {format_extra_field(val)}")


@command(
    "configure distribution_schedule set",
    words="<key>=<value>",
    help="Set field(s) on the grid distribution schedule.",
)
async def cli_set_distribution_schedule(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    kvs = _parse_inline_kvs(line, " set ")
    if not kvs:
        print("  Error: no key=value pairs provided")
        return

    results = [as_dict(r) async for r in ctx.client.grid.distributionschedule.list()]
    if not results:
        print("  No distribution schedule found")
        return
    ref = results[0]["_ref"]
    result = await ctx.client.grid.distributionschedule.update(ref, kvs)
    r = as_dict(result)
    print(f"  Updated: {r.get('_ref', ref)}")


# ===========================================================================
# Handlers - upgrade_status (read-only)
# ===========================================================================


@command(
    "show upgrade_status grid",
    words="<cr>",
    help="Show grid-level upgrade status.",
)
@command(
    "show upgrade_status group",
    words="<cr> <name>",
    help="Show upgrade-group upgrade status.",
)
@command(
    "show upgrade_status group <name>",
    words="<cr>",
    help="Show a specific upgrade group's status.",
)
@command(
    "show upgrade_status vnode",
    words="<cr> <name>",
    help="Show virtual-member upgrade status.",
)
@command(
    "show upgrade_status vnode <name>",
    words="<cr>",
    help="Show a specific virtual member's upgrade status.",
)
@command(
    "show upgrade_status pnode",
    words="<cr> <name>",
    help="Show physical-member upgrade status.",
)
@command(
    "show upgrade_status pnode <name>",
    words="<cr>",
    help="Show a specific physical member's upgrade status.",
)
async def cli_show_upgrade_status(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    # tokens: show upgrade_status {grid|group|vnode|pnode} [<name>]
    type_arg = tokens[2].upper() if len(tokens) >= 3 else None
    if type_arg not in {"GRID", "GROUP", "VNODE", "PNODE"}:
        print(
            "  Error: type required (usage: show upgrade_status {grid|group|vnode|pnode} [<name>])"
        )
        return
    name = tokens[3] if len(tokens) >= 4 and not tokens[3].startswith("<") else None

    filters: dict = {
        "type": type_arg,
        "return_fields_plus": [
            "member",
            "upgrade_group",
            "type",
            "current_version",
            "alternate_version",
            "distribution_version",
            "upgrade_state",
            "distribution_state",
            "grid_state",
            "group_state",
            "element_status",
            "ha_status",
            "pnode_role",
            "subelement_type",
            "subelements_completed",
            "subelements_status",
            "subelements_total",
            "steps_completed",
            "steps_total",
            "status_value",
            "message",
            "comment",
            "upgrade_schedule_active",
            "distribution_schedule_active",
        ],
    }
    if name:
        if type_arg in ("VNODE", "PNODE"):
            filters["member"] = name
        elif type_arg == "GROUP":
            filters["upgrade_group"] = name

    results = [as_dict(r) async for r in ctx.client.grid.upgradestatus.list(**filters)]
    if not results:
        if name:
            print(f"  No upgrade status found for {type_arg.lower()}: {name}")
        else:
            print(f"  No upgrade status found for type {type_arg}")
        return

    for r in results:
        _print_upgrade_status(r)


def _print_upgrade_status(r: dict) -> None:
    t = r.get("type") or ""
    parts: list[str] = []

    # Identity varies by row type.
    if t == "GROUP" and r.get("upgrade_group"):
        parts.append(f"group={r['upgrade_group']}")
    elif r.get("member"):
        parts.append(f"member={r['member']}")
    if t:
        parts.append(f"type={t}")

    # Role / HA flags (nodes only).
    if r.get("pnode_role"):
        parts.append(f"role={r['pnode_role']}")
    if r.get("ha_status"):
        parts.append(f"ha={r['ha_status']}")

    # Versions.
    if r.get("current_version"):
        parts.append(f"version={r['current_version']}")
    if r.get("distribution_version"):
        parts.append(f"dist_version={r['distribution_version']}")
    if r.get("alternate_version"):
        parts.append(f"alt_version={r['alternate_version']}")

    # State/status.
    if r.get("element_status"):
        parts.append(f"status={r['element_status']}")
    elif r.get("status_value"):
        parts.append(f"status={r['status_value']}")
    if t == "GROUP" and r.get("group_state"):
        parts.append(f"group_state={r['group_state']}")
    if r.get("grid_state"):
        parts.append(f"grid_state={r['grid_state']}")
    if r.get("upgrade_state"):
        parts.append(f"upgrade_state={r['upgrade_state']}")
    if r.get("distribution_state"):
        parts.append(f"distribution_state={r['distribution_state']}")

    # Group progress - subelements + steps.
    if t == "GROUP":
        subs_done = r.get("subelements_completed")
        subs_total = r.get("subelements_total")
        if subs_total is not None:
            subtype = r.get("subelement_type") or "member"
            parts.append(f"{subtype.lower()}s={subs_done or 0}/{subs_total}")
        steps_done = r.get("steps_completed")
        steps_total = r.get("steps_total")
        if steps_total:
            parts.append(f"steps={steps_done or 0}/{steps_total}")

    # Scheduling flags - only surface when actively scheduled.
    if r.get("upgrade_schedule_active"):
        parts.append("upgrade_scheduled")
    if r.get("distribution_schedule_active"):
        parts.append("dist_scheduled")

    # Free-form fields last so they don't crowd the identity columns.
    if r.get("message"):
        parts.append(f"message={r['message']!r}")
    if r.get("comment"):
        parts.append(f"comment={r['comment']!r}")

    print("  " + " ".join(parts) if parts else "  (no fields returned)")
