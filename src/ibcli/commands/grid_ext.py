# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Grid extended commands - Phase 13.

Covers resources not yet exposed in grid.py:

  Chunk A - NAT groups (captive portal is hidden - see block below)
  Chunk B - Master grid + grid-wide licenses (GMC group + GMC schedule
            are hidden - see blocks below)
  Chunk D - Member DFP + cloud sync + parental control (show-only)
"""

from __future__ import annotations

import re

from ibcli.coerce import coerce as _coerce_value  # noqa: F401
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict, format_extra_field, parse_extra_fields

# ---------------------------------------------------------------------------
# Internal helpers (mirrors grid.py)
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


def _parse_inline_kvs(line: str, marker: str) -> dict:
    """Parse key=value pairs appearing after *marker* in *line*."""
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
            k, v = tok, tokens[i + 1]
            result[k] = _coerce_value(v)
            i += 2
        else:
            i += 1
    return result


def _print_fields(r: dict, *keys: str) -> None:
    """Print non-None fields from dict r."""
    parts = []
    for k in keys:
        if r.get(k) is not None:
            parts.append(f"{k}={r[k]}")
    if parts:
        print("  " + "  ".join(parts))


# ===========================================================================
# Chunk A - Captive Portal + NAT Groups
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - Captive Portal
# ---------------------------------------------------------------------------
# Hidden for now - captive portal is a niche DHCP feature and is not part of
# the current CLI surface.  Unhide by removing the surrounding `""" ... """`
# block.
r"""
register("configure", words="captive_portal",
         help="Create, modify or delete grid objects.")
register("configure captive_portal", words="add <name>",
         help="Captive-portal configuration per member.")
register("configure captive_portal add", words="<name>")
register(
    "configure captive_portal add <name>",
    words="<cr> authn_server_group=<svr>|comment=<comment>",
)
register("configure captive_portal <name>", words="delete set")
register("configure captive_portal <name> delete", words="<cr>")
register("configure captive_portal <name> set", words="<key>=<value>")

register("show", words="captive_portal",
         help="Read grid state without modifying anything.")
register("show captive_portal", words="<cr> <name>",
         help="Captive-portal member state.")
register("show captive_portal <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# configure captive_portal add <name>
# ---------------------------------------------------------------------------

@command(
    "configure captive_portal add <name>",
    words="<cr> authn_server_group=<svr>|comment=<comment>",
    help="Add a captive portal (tied to a member hostname).",
)
async def cli_add_captive_portal(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bcaptive_portal add\s+(\S+)", line)
    if not m:
        print("  Error: captive portal name (member hostname) required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    authn = _parse_kv(line, "authn_server_group")
    if authn:
        body["authn_server_group"] = authn
    comment = _parse_comment(line)
    if comment:
        body["company_name"] = comment  # closest writable string field

    result = as_dict(await ctx.client.grid.captiveportal.create(body))
    ref = result.get("_ref", "")
    print(f"  Added captive_portal {name}{' ref=' + ref if ref else ''}")


# ---------------------------------------------------------------------------
# configure captive_portal <name> delete
# ---------------------------------------------------------------------------

@command(
    "configure captive_portal <name> delete",
    words="<cr>",
    help="Delete a captive portal.",
)
async def cli_del_captive_portal(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bcaptive_portal\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: captive portal name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.grid.captiveportal.list(name=name, max_results=1)]
    if not results:
        print(f"  No captive_portal found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.captiveportal.delete(ref)
    print(f"  Deleted captive_portal {name}")


# ---------------------------------------------------------------------------
# configure captive_portal <name> set <key>=<value>
# ---------------------------------------------------------------------------

@command(
    "configure captive_portal <name> set",
    words="<key>=<value>",
    help="Set arbitrary captive portal fields via key=value pass-through.",
)
async def cli_set_captive_portal(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bcaptive_portal\s+(\S+)\s+set\b", line)
    if not m:
        print("  Error: captive portal name required")
        return
    name = m.group(1)

    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return

    results = [as_dict(r) async for r in ctx.client.grid.captiveportal.list(name=name, max_results=1)]
    if not results:
        print(f"  No captive_portal found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.captiveportal.update(ref, body)
    print(f"  Updated captive_portal {name}")


# ---------------------------------------------------------------------------
# show captive_portal [<name>]
# ---------------------------------------------------------------------------

@command("show captive_portal", words="<cr> <name>", help="List captive portals.")
@command("show captive_portal <name>", words="<cr>", help="Show a specific captive portal.")
async def cli_show_captive_portal(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    # tokens: show(0) captive_portal(1) [<name>(2)]
    kwargs: dict = {
        "return_fields_plus": ["name", "authn_server_group", "company_name", "service_enabled"],
    }
    if len(tokens) >= 3 and not tokens[2].startswith("<"):
        kwargs["name"] = tokens[2]

    results = [as_dict(r) async for r in ctx.client.grid.captiveportal.list(**kwargs)]
    if not results:
        print("  No captive portals found")
        return
    for r in results:
        parts = []
        if r.get("name"):
            parts.append(f"name={r['name']}")
        if r.get("authn_server_group"):
            parts.append(f"authn_server_group={r['authn_server_group']}")
        if r.get("company_name"):
            parts.append(f"company_name={r['company_name']}")
        if r.get("service_enabled") is not None:
            parts.append(f"service_enabled={r['service_enabled']}")
        print("  " + "  ".join(parts))
"""


# ---------------------------------------------------------------------------
# Waypoints - NAT Groups
# ---------------------------------------------------------------------------
register("configure", words="nat_group", help="Create, modify or delete grid objects.")
register(
    "configure nat_group",
    words="add <name>",
    help="DNS NAT groups (address translation for DNS queries).",
)
register("configure nat_group add", words="<name>")
register("configure nat_group add <name>", words="<cr> comment=<comment>")
register("configure nat_group <name>", words="delete set")
register("configure nat_group <name> delete", words="<cr>")
register("configure nat_group <name> set", words="<key>=<value>")

register("show", words="nat_group", help="Read grid state without modifying anything.")
register("show nat_group", words="<cr> <name>")
register("show nat_group <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# configure nat_group add <name>
# ---------------------------------------------------------------------------


@command(
    "configure nat_group add <name>",
    words="<cr> comment=<comment>",
    help="Add a NAT group.",
)
async def cli_add_nat_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnat_group add\s+(\S+)", line)
    if not m:
        print("  Error: NAT group name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    result = as_dict(await ctx.client.grid.natgroup.create(body))
    ref = result.get("_ref", "")
    print(f"  Added nat_group {name}{' ref=' + ref if ref else ''}")


# ---------------------------------------------------------------------------
# configure nat_group <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure nat_group <name> delete",
    words="<cr>",
    help="Delete a NAT group.",
)
async def cli_del_nat_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnat_group\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: NAT group name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.grid.natgroup.list(name=name, max_results=1)]
    if not results:
        print(f"  No nat_group found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.natgroup.delete(ref)
    print(f"  Deleted nat_group {name}")


# ---------------------------------------------------------------------------
# configure nat_group <name> set <key>=<value>
# ---------------------------------------------------------------------------


@command(
    "configure nat_group <name> set",
    words="<key>=<value>",
    help="Set arbitrary NAT group fields via key=value pass-through.",
)
async def cli_set_nat_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnat_group\s+(\S+)\s+set\b", line)
    if not m:
        print("  Error: NAT group name required")
        return
    name = m.group(1)

    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return

    results = [as_dict(r) async for r in ctx.client.grid.natgroup.list(name=name, max_results=1)]
    if not results:
        print(f"  No nat_group found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.natgroup.update(ref, body)
    print(f"  Updated nat_group {name}")


# ---------------------------------------------------------------------------
# show nat_group [<name>]
# ---------------------------------------------------------------------------


@command("show nat_group", words="<cr> <name>", help="List NAT groups.")
@command(
    "show nat_group <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific NAT group.",
)
async def cli_show_nat_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": ["name", "comment"] + extra,
    }
    if len(tokens) >= 3 and not tokens[2].startswith("<") and "=" not in tokens[2]:
        kwargs["name"] = tokens[2]

    results = [as_dict(r) async for r in ctx.client.grid.natgroup.list(**kwargs)]
    if not results:
        print("  No NAT groups found")
        return
    for r in results:
        parts = []
        if r.get("name"):
            parts.append(f"name={r['name']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print("  " + "  ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Chunk B - Master Grid + GMC Group + GMC Schedule
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - Master Grid
# ---------------------------------------------------------------------------
register("configure", words="master_grid", help="Create, modify or delete grid objects.")
register(
    "configure master_grid", words="add <name>", help="Grid-federation master-grid configuration."
)
register("configure master_grid add", words="<name>")
register(
    "configure master_grid add <name>",
    words="<cr> address=<ip>|comment=<comment>",
)
register("configure master_grid <name>", words="delete set")
register("configure master_grid <name> delete", words="<cr>")
register("configure master_grid <name> set", words="<key>=<value>")

register("show", words="master_grid", help="Read grid state without modifying anything.")
register("show master_grid", words="<cr> <name>")
register("show master_grid <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# configure master_grid add <name>
# ---------------------------------------------------------------------------


@command(
    "configure master_grid add <name>",
    words="<cr> address=<ip>|comment=<comment>",
    help="Add a master grid entry.",
)
async def cli_add_master_grid(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmaster_grid add\s+(\S+)", line)
    if not m:
        print("  Error: master grid name required")
        return
    name = m.group(1)

    address = _parse_kv(line, "address")
    if not address:
        print("  Error: address=<ip> is required")
        return

    body: dict = {"name": name, "address": address}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    result = as_dict(await ctx.client.grid.mastergrid.create(body))
    ref = result.get("_ref", "")
    print(f"  Added master_grid {name}{' ref=' + ref if ref else ''}")


# ---------------------------------------------------------------------------
# configure master_grid <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure master_grid <name> delete",
    words="<cr>",
    help="Delete a master grid entry.",
)
async def cli_del_master_grid(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmaster_grid\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: master grid name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.grid.mastergrid.list()]
    matches = [r for r in results if r.get("name") == name or r.get("address") == name]
    if not matches:
        print(f"  No master_grid found: {name}")
        return
    ref = matches[0]["_ref"]
    await ctx.client.grid.mastergrid.delete(ref)
    print(f"  Deleted master_grid {name}")


# ---------------------------------------------------------------------------
# configure master_grid <name> set <key>=<value>
# ---------------------------------------------------------------------------


@command(
    "configure master_grid <name> set",
    words="<key>=<value>",
    help="Set arbitrary master grid fields via key=value pass-through.",
)
async def cli_set_master_grid(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmaster_grid\s+(\S+)\s+set\b", line)
    if not m:
        print("  Error: master grid name required")
        return
    name = m.group(1)

    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return

    results = [as_dict(r) async for r in ctx.client.grid.mastergrid.list()]
    matches = [r for r in results if r.get("name") == name or r.get("address") == name]
    if not matches:
        print(f"  No master_grid found: {name}")
        return
    ref = matches[0]["_ref"]
    await ctx.client.grid.mastergrid.update(ref, body)
    print(f"  Updated master_grid {name}")


# ---------------------------------------------------------------------------
# show master_grid [<name>]
# ---------------------------------------------------------------------------


@command("show master_grid", words="<cr> <name>", help="List master grid entries.")
@command(
    "show master_grid <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific master grid entry.",
)
async def cli_show_master_grid(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    extra = parse_extra_fields(line)
    results = [
        as_dict(r)
        async for r in ctx.client.grid.mastergrid.list(
            return_fields_plus=["address", "enable", "join_status"] + extra,
        )
    ]

    # Optional name filter
    if len(tokens) >= 3 and not tokens[2].startswith("<") and "=" not in tokens[2]:
        name_filter = tokens[2]
        results = [
            r for r in results if r.get("name") == name_filter or r.get("address") == name_filter
        ]

    if not results:
        print("  No master grid entries found")
        return
    for r in results:
        parts = []
        if r.get("address"):
            parts.append(f"address={r['address']}")
        if r.get("enable") is not None:
            parts.append(f"enable={r['enable']}")
        if r.get("join_status"):
            parts.append(f"join_status={r['join_status']}")
        print("  " + "  ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Waypoints - GMC Group
# ---------------------------------------------------------------------------
# Hidden for now - Grid Master Candidate groups are an advanced DR operation
# and are not part of the current CLI surface.  Unhide by removing the
# surrounding `""" ... """` block.
r"""
register("configure", words="gmc_group",
         help="Create, modify or delete grid objects.")
register("configure gmc_group", words="add <name>",
         help="Grid Manager Cluster (GMC) group membership.")
register("configure gmc_group add", words="<name>")
register("configure gmc_group add <name>", words="<cr> comment=<comment>")
register("configure gmc_group <name>", words="delete")
register("configure gmc_group <name> delete", words="<cr>")

register("show", words="gmc_group",
         help="Read grid state without modifying anything.")
register("show gmc_group", words="<cr> <name>",
         help="GMC (Grid Manager Cluster) group info.")
register("show gmc_group <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# configure gmc_group add <name>
# ---------------------------------------------------------------------------

@command(
    "configure gmc_group add <name>",
    words="<cr> comment=<comment>",
    help="Add a Grid Master Candidate group.",
)
async def cli_add_gmc_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bgmc_group add\s+(\S+)", line)
    if not m:
        print("  Error: GMC group name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    result = as_dict(await ctx.client.grid.gmcgroup.create(body))
    ref = result.get("_ref", "")
    print(f"  Added gmc_group {name}{' ref=' + ref if ref else ''}")


# ---------------------------------------------------------------------------
# configure gmc_group <name> delete
# ---------------------------------------------------------------------------

@command(
    "configure gmc_group <name> delete",
    words="<cr>",
    help="Delete a GMC group.",
)
async def cli_del_gmc_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bgmc_group\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: GMC group name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.grid.gmcgroup.list(name=name)]
    if not results:
        print(f"  No gmc_group found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.gmcgroup.delete(ref)
    print(f"  Deleted gmc_group {name}")


# ---------------------------------------------------------------------------
# show gmc_group [<name>]
# ---------------------------------------------------------------------------

@command("show gmc_group", words="<cr> <name>", help="List GMC groups.")
@command("show gmc_group <name>", words="<cr>", help="Show a specific GMC group.")
async def cli_show_gmc_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    kwargs: dict = {
        "return_fields_plus": ["name", "comment", "gmc_promotion_policy"],
    }
    if len(tokens) >= 3 and not tokens[2].startswith("<"):
        kwargs["name"] = tokens[2]

    results = [as_dict(r) async for r in ctx.client.grid.gmcgroup.list(**kwargs)]
    if not results:
        print("  No GMC groups found")
        return
    for r in results:
        parts = []
        if r.get("name"):
            parts.append(f"name={r['name']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        if r.get("gmc_promotion_policy"):
            parts.append(f"gmc_promotion_policy={r['gmc_promotion_policy']}")
        print("  " + "  ".join(parts))
"""


# ---------------------------------------------------------------------------
# Waypoints - GMC Schedule
# ---------------------------------------------------------------------------
# Hidden for now - GMC failover scheduling is an advanced DR operation and is
# not part of the current CLI surface.  Unhide by removing the surrounding
# `""" ... """` block.
r"""
register("configure", words="gmc_schedule",
         help="Create, modify or delete grid objects.")
register("configure gmc_schedule", words="add <name>",
         help="GMC promotion schedule.")
register("configure gmc_schedule add", words="<cr> start_time=<num>|comment=<comment>")
register("configure gmc_schedule <name>", words="delete set")
register("configure gmc_schedule <name> delete", words="<cr>")
register("configure gmc_schedule <name> set", words="<key>=<value>")

register("show", words="gmc_schedule",
         help="Read grid state without modifying anything.")
register("show gmc_schedule", words="<cr>",
         help="GMC promotion schedule.")

# ---------------------------------------------------------------------------
# configure gmc_schedule add
# ---------------------------------------------------------------------------

@command(
    "configure gmc_schedule add",
    words="<cr> start_time=<num>|comment=<comment>",
    help="Add a GMC failover schedule.",
)
async def cli_add_gmc_schedule(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    body: dict = {}
    start_time = _parse_kv(line, "start_time")
    if start_time:
        body["activate_gmc_group_schedule"] = _coerce_value(start_time)

    result = as_dict(await ctx.client.grid.gmcschedule.create(body))
    ref = result.get("_ref", "")
    print(f"  Added gmc_schedule{' ref=' + ref if ref else ''}")


# ---------------------------------------------------------------------------
# configure gmc_schedule <ref> delete
# ---------------------------------------------------------------------------

@command(
    "configure gmc_schedule <name> delete",
    words="<cr>",
    help="Delete a GMC schedule by ref.",
)
async def cli_del_gmc_schedule(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bgmc_schedule\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: gmc_schedule ref required")
        return
    ref = m.group(1)
    await ctx.client.grid.gmcschedule.delete(ref)
    print(f"  Deleted gmc_schedule {ref}")


# ---------------------------------------------------------------------------
# configure gmc_schedule <name> set <key>=<value>
# ---------------------------------------------------------------------------

@command(
    "configure gmc_schedule <name> set",
    words="<key>=<value>",
    help="Set arbitrary GMC schedule fields via key=value pass-through.",
)
async def cli_set_gmc_schedule(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bgmc_schedule\s+(\S+)\s+set\b", line)
    if not m:
        print("  Error: gmc_schedule ref required")
        return
    ref = m.group(1)

    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    await ctx.client.grid.gmcschedule.update(ref, body)
    print(f"  Updated gmc_schedule {ref}")


# ---------------------------------------------------------------------------
# show gmc_schedule
# ---------------------------------------------------------------------------

@command("show gmc_schedule", words="<cr>", help="Show GMC schedule entries.")
async def cli_show_gmc_schedule(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    results = [
        as_dict(r)
        async for r in ctx.client.grid.gmcschedule.list(
            return_fields_plus=["activate_gmc_group_schedule"],
        )
    ]
    if not results:
        print("  No GMC schedules found")
        return
    for r in results:
        parts = []
        if r.get("_ref"):
            parts.append(f"ref={r['_ref']}")
        if r.get("activate_gmc_group_schedule") is not None:
            parts.append(f"activate_gmc_group_schedule={r['activate_gmc_group_schedule']}")
        print("  " + "  ".join(parts))
"""


# ===========================================================================
# Chunk C - Grid-wide Licenses
# ===========================================================================

register("show", words="license_gridwide", help="Read grid state without modifying anything.")
register("show license_gridwide", words="<cr> <name>")
register("show license_gridwide <name>", words="<cr> fields=<field1,field2,...>")

register("configure", words="license_gridwide", help="Create, modify or delete grid objects.")
register(
    "configure license_gridwide",
    words="add <name>",
    help="Grid-wide licenses (NIOS, DNS, DHCP, RPZ, DTC, etc.).",
)
register("configure license_gridwide add", words="<name>")
register("configure license_gridwide add <name>", words="<cr>")
register("configure license_gridwide <name>", words="delete")
register("configure license_gridwide <name> delete", words="<cr>")

# ---------------------------------------------------------------------------
# show license_gridwide [<type>]
# ---------------------------------------------------------------------------


@command("show license_gridwide", words="<cr> <name>", help="Show grid-wide licenses.")
@command(
    "show license_gridwide <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show grid-wide license by type.",
)
async def cli_show_license_gridwide(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": ["type", "key", "limit", "expiration_status", "expiry_date"] + extra,
    }
    if len(tokens) >= 3 and not tokens[2].startswith("<") and "=" not in tokens[2]:
        kwargs["type"] = tokens[2].upper()

    results = [as_dict(r) async for r in ctx.client.grid.license_gridwide.list(**kwargs)]
    if not results:
        print("  No grid-wide licenses found")
        return
    for r in results:
        parts = []
        if r.get("type"):
            parts.append(f"type={r['type']}")
        if r.get("key"):
            parts.append(f"key={r['key']}")
        if r.get("limit"):
            parts.append(f"limit={r['limit']}")
        if r.get("expiration_status"):
            parts.append(f"expiration_status={r['expiration_status']}")
        print("  " + "  ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# configure license_gridwide add <type>
# ---------------------------------------------------------------------------


@command(
    "configure license_gridwide add <name>",
    words="<cr>",
    help="Add a grid-wide license by type.",
)
async def cli_add_license_gridwide(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\blicense_gridwide add\s+(\S+)", line)
    if not m:
        print("  Error: license type required")
        return
    ltype = m.group(1).upper()

    body: dict = {"type": ltype}
    result = as_dict(await ctx.client.grid.license_gridwide.create(body))
    ref = result.get("_ref", "")
    print(f"  Added license_gridwide type={ltype}{' ref=' + ref if ref else ''}")


# ---------------------------------------------------------------------------
# configure license_gridwide <type> delete
# ---------------------------------------------------------------------------


@command(
    "configure license_gridwide <name> delete",
    words="<cr>",
    help="Delete a grid-wide license by type.",
)
async def cli_del_license_gridwide(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\blicense_gridwide\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: license type required")
        return
    ltype = m.group(1).upper()

    results = [as_dict(r) async for r in ctx.client.grid.license_gridwide.list(type=ltype)]
    if not results:
        print(f"  No license_gridwide found: {ltype}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.license_gridwide.delete(ref)
    print(f"  Deleted license_gridwide type={ltype}")


# ===========================================================================
# Chunk D - Member DFP + Cloud Sync + Parental Control
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - extend existing member paths
# ---------------------------------------------------------------------------
register("show grid <name> member <name>", words="dfp cloudsync parental_control")
register("show grid <name> member <name> dfp", words="<cr> fields=<field1,field2,...>")
register("show grid <name> member <name> cloudsync", words="<cr> fields=<field1,field2,...>")
register("show grid <name> member <name> parental_control", words="<cr> fields=<field1,field2,...>")

register("configure grid <name> member <name>", words="dfp cloudsync")
register("configure grid <name> member <name> dfp", words="set")
register("configure grid <name> member <name> dfp set", words="<key>=<value>")
register("configure grid <name> member <name> cloudsync", words="set")
register("configure grid <name> member <name> cloudsync set", words="<key>=<value>")

# ---------------------------------------------------------------------------
# show grid <name> member <name> dfp
# ---------------------------------------------------------------------------


@command(
    "show grid <name> member <name> dfp",
    words="<cr> fields=<field1,field2,...>",
    help="Show DFP settings for a member.",
)
async def cli_show_member_dfp(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    # tokens: show(0) grid(1) <grid>(2) member(3) <mname>(4) dfp(5)
    if len(tokens) < 5:
        print("  Error: member name required")
        return
    name = tokens[4]

    extra = parse_extra_fields(line)
    results = [
        as_dict(r)
        async for r in ctx.client.grid.memberdfp.list(
            host_name=name,
            return_fields_plus=["host_name", "dfp_forward_first", "is_dfp_override"] + extra,
        )
    ]
    if not results:
        print(f"  No memberdfp found: {name}")
        return
    for r in results:
        parts = []
        if r.get("host_name"):
            parts.append(f"host_name={r['host_name']}")
        if r.get("dfp_forward_first") is not None:
            parts.append(f"dfp_forward_first={r['dfp_forward_first']}")
        if r.get("is_dfp_override") is not None:
            parts.append(f"is_dfp_override={r['is_dfp_override']}")
        print("  " + "  ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# configure grid <name> member <name> dfp set <key>=<value>
# ---------------------------------------------------------------------------


@command(
    "configure grid <name> member <name> dfp set",
    words="<key>=<value>",
    help="Set DFP fields on a member via key=value pass-through.",
)
async def cli_set_member_dfp(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmember\s+(\S+)\s+dfp\s+set\b", line)
    if not m:
        print("  Error: member name required")
        return
    name = m.group(1)

    body = _parse_inline_kvs(line, " dfp set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return

    results = [as_dict(r) async for r in ctx.client.grid.memberdfp.list(host_name=name)]
    if not results:
        print(f"  No memberdfp found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.memberdfp.update(ref, body)
    print(f"  Updated memberdfp {name}")


# ---------------------------------------------------------------------------
# show grid <name> member <name> cloudsync
# ---------------------------------------------------------------------------


@command(
    "show grid <name> member <name> cloudsync",
    words="<cr> fields=<field1,field2,...>",
    help="Show cloud sync settings for a member.",
)
async def cli_show_member_cloudsync(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    # tokens: show(0) grid(1) <grid>(2) member(3) <mname>(4) cloudsync(5)
    if len(tokens) < 5:
        print("  Error: member name required")
        return
    name = tokens[4]

    extra = parse_extra_fields(line)
    results = [
        as_dict(r)
        async for r in ctx.client.grid.membercloudsync.list(
            host_name=name,
            return_fields_plus=["host_name", "cloud_sync_enabled"] + extra,
        )
    ]
    if not results:
        print(f"  No membercloudsync found: {name}")
        return
    for r in results:
        parts = []
        if r.get("host_name"):
            parts.append(f"host_name={r['host_name']}")
        if r.get("cloud_sync_enabled") is not None:
            parts.append(f"cloud_sync_enabled={r['cloud_sync_enabled']}")
        print("  " + "  ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# configure grid <name> member <name> cloudsync set <key>=<value>
# ---------------------------------------------------------------------------


@command(
    "configure grid <name> member <name> cloudsync set",
    words="<key>=<value>",
    help="Set cloud sync fields on a member via key=value pass-through.",
)
async def cli_set_member_cloudsync(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmember\s+(\S+)\s+cloudsync\s+set\b", line)
    if not m:
        print("  Error: member name required")
        return
    name = m.group(1)

    body = _parse_inline_kvs(line, " cloudsync set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return

    results = [as_dict(r) async for r in ctx.client.grid.membercloudsync.list(host_name=name)]
    if not results:
        print(f"  No membercloudsync found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.membercloudsync.update(ref, body)
    print(f"  Updated membercloudsync {name}")


# ---------------------------------------------------------------------------
# show grid <name> member <name> parental_control  (show-only)
# ---------------------------------------------------------------------------


@command(
    "show grid <name> member <name> parental_control",
    words="<cr> fields=<field1,field2,...>",
    help="Show parental control settings for a member (read-only).",
)
async def cli_show_member_parental_control(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    # tokens: show(0) grid(1) <grid>(2) member(3) <mname>(4) parental_control(5)
    if len(tokens) < 5:
        print("  Error: member name required")
        return
    name = tokens[4]

    extra = parse_extra_fields(line)
    results = [
        as_dict(r)
        async for r in ctx.client.grid.member_parentalcontrol.list(
            name=name,
            return_fields_plus=["name", "enable_service"] + extra,
        )
    ]
    if not results:
        print(f"  No member:parentalcontrol found: {name}")
        return
    for r in results:
        parts = []
        if r.get("name"):
            parts.append(f"name={r['name']}")
        if r.get("enable_service") is not None:
            parts.append(f"enable_service={r['enable_service']}")
        print("  " + "  ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")
