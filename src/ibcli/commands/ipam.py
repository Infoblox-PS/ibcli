# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Phase 8 IPAM command module.

Decision: created as a separate ``ipam.py`` rather than extending ``network.py``
because network.py was already 1 042 lines and this phase adds ~400 more.  All
commands here are still IPAM-domain objects (ipv4address, vlan*, networkview,
superhost, bulkhost*, rir*, hostnamerewritepolicy, ipv6networktemplate) so a
single ``ipam.py`` keeps them co-located while keeping network.py manageable.

WAPI access attribute quick-reference
--------------------------------------
ctx.client.ipam.ipv4address          (read-only inventory)
ctx.client.ipam.ipv6address          (read-only inventory)
ctx.client.ipam.networkview          (full CRUD)
ctx.client.ipam.vlanview             (full CRUD)
ctx.client.ipam.vlanrange            (full CRUD)
ctx.client.ipam.vlan                 (full CRUD)
ctx.client.ipam.superhost            (full CRUD)
ctx.client.ipam.superhostchild       (read-only; children derived from parent)
ctx.client.ipam.bulkhost             (full CRUD)
ctx.client.ipam.bulkhostnametemplate (full CRUD)
ctx.client.ipam.network_discovery    (read-only)
ctx.client.ipam.rir                  (read-only; enum from NIOS)
ctx.client.ipam.rir_organization     (full CRUD)
ctx.client.ipam.hostnamerewritepolicy(full CRUD)
ctx.client.ipam.ipv6networktemplate  (full CRUD)
"""

from __future__ import annotations

import re

from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict, format_extra_field, parse_extra_fields

# ---------------------------------------------------------------------------
# Helpers shared across handlers in this module
# ---------------------------------------------------------------------------


def _parse_kv(line: str, key: str) -> str | None:
    m = re.search(rf"\b{re.escape(key)}\s*=\s*(\S+)", line)
    if m:
        return m.group(1)
    m = re.search(rf"\b{re.escape(key)}\s+(\S+)", line)
    return m.group(1) if m else None


def _parse_comment(line: str) -> str | None:
    m = re.search(r'\bcomment\s+"([^"]+)"', line)
    if m:
        return m.group(1)
    m = re.search(r"\bcomment\s+(\S+)", line)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Chunk A - Individual addresses (read-only inventory)
# ---------------------------------------------------------------------------

# show address <ip> [view=<view>]
register("show", words="address", help="Read grid state without modifying anything.")
register("show address", words="<ip> ipv6")
register("show address <ip>", words="<cr> view=<name>")
register("show address ipv6", words="<ipv6>")
register("show address ipv6 <ipv6>", words="<cr> view=<name>")


def _print_address(a: dict, *, v6: bool = False) -> None:
    ip_key = "ip_address"
    parts = [f"ip={a.get(ip_key, '')}"]
    if a.get("network"):
        parts.append(f"network={a['network']}")
    if a.get("network_view"):
        parts.append(f"view={a['network_view']}")
    if a.get("status"):
        parts.append(f"status={a['status']}")
    if a.get("types"):
        parts.append(f"types={','.join(a['types'])}")
    if a.get("usage"):
        parts.append(f"usage={','.join(a['usage'])}")
    if a.get("mac_address"):
        parts.append(f"mac={a['mac_address']}")
    if v6 and a.get("duid"):
        parts.append(f"duid={a['duid']}")
    if a.get("names"):
        parts.append(f"names={','.join(a['names'])}")
    print("  " + " ".join(parts))


@command(
    "show address <ip>",
    words="<cr> view=<name> fields=<field1,field2,...>",
    help="Show IPv4 address inventory record.",
)
async def cli_show_ipv4address(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    # "show address <ip>" => tokens[2]
    ip = tokens[2] if len(tokens) >= 3 and "=" not in tokens[2] else None
    view = _parse_kv(line, "view")
    extra = parse_extra_fields(line)
    filters: dict = {}
    if ip:
        filters["ip_address"] = ip
    if view:
        filters["network_view"] = view
    ret_fields = [
        "ip_address",
        "mac_address",
        "network",
        "network_view",
        "status",
        "types",
        "names",
        "usage",
    ]
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.ipv4address.list(return_fields=ret_fields + extra, **filters)
    ]
    if not results:
        print(f"  No IPv4 address found: {ip}")
        return
    for a in results:
        _print_address(a)
        for f in extra:
            val = a.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


@command(
    "show address ipv6 <ipv6>",
    words="<cr> view=<name> fields=<field1,field2,...>",
    help="Show IPv6 address inventory record.",
)
async def cli_show_ipv6address(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\baddress\s+ipv6\s+(\S+)", line)
    ip = m.group(1) if m else None
    view = _parse_kv(line, "view")
    extra = parse_extra_fields(line)
    filters: dict = {}
    if ip:
        filters["ip_address"] = ip
    if view:
        filters["network_view"] = view
    ret_fields = [
        "ip_address",
        "duid",
        "network",
        "network_view",
        "status",
        "types",
        "names",
        "usage",
    ]
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.ipv6address.list(return_fields=ret_fields + extra, **filters)
    ]
    if not results:
        print(f"  No IPv6 address found: {ip}")
        return
    for a in results:
        _print_address(a, v6=True)
        for f in extra:
            val = a.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Chunk B - Network views + VLAN views / ranges / VLANs
# ---------------------------------------------------------------------------

# --- Network view ---
register("configure", words="network_view", help="Create, modify or delete grid objects.")
register(
    "configure network_view",
    words="add <name>",
    help="Network views - split IPAM/DHCP by tenant/zone.",
)
register("configure network_view add", words="<name>")
register("configure network_view add <name>", words="<cr> comment=<comment>")
register("configure network_view <name>", words="delete")
register("configure network_view <name> delete", words="<cr>")
register("show", words="network_view", help="Read grid state without modifying anything.")
register("show network_view", words="<cr> <name>")
register("show network_view <name>", words="<cr> fields=<field1,field2,...>")


def _print_networkview(nv: dict) -> None:
    parts = [f"name={nv.get('name', '')}"]
    if nv.get("comment"):
        parts.append(f"comment={nv['comment']}")
    if nv.get("is_default"):
        parts.append("is_default=true")
    print("  " + " ".join(parts))


@command(
    "configure network_view add <name>",
    words="<cr> comment=<comment>",
    help="Create a new network view.",
)
async def cli_add_networkview(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bnetwork_view\s+add\s+(\S+)", line)
    if not m:
        print("  Error: network view name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    await ctx.client.ipam.networkview.create(body)


@command(
    "configure network_view <name> delete", words="<cr>", help="Delete a network view by name."
)
async def cli_delete_networkview(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bnetwork_view\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: network view name required")
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.ipam.networkview.list(name=name, max_results=1)]
    if not results:
        print(f"  No network view found: {name}")
        return
    await ctx.client.ipam.networkview.delete(results[0]["_ref"])


@command("show network_view", words="<cr> <name>", help="List network views.")
@command(
    "show network_view <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific network view.",
)
async def cli_show_networkview(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    nv_name = None
    if len(tokens) >= 3 and not tokens[2].startswith("view") and "=" not in tokens[2]:
        nv_name = tokens[2]
    extra = parse_extra_fields(line)
    filters: dict = {}
    if nv_name:
        filters["name"] = nv_name
    ret_fields = ["name", "comment", "is_default"]
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.networkview.list(return_fields=ret_fields + extra, **filters)
    ]
    if not results:
        if nv_name:
            print(f"  No network view found: {nv_name}")
        return
    for nv in results:
        _print_networkview(nv)
        for f in extra:
            val = nv.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# --- VLAN view ---
register("configure", words="vlan_view", help="Create, modify or delete grid objects.")
register(
    "configure vlan_view",
    words="add <name>",
    help="VLAN views (top-level containers for VLAN ranges/VLANs).",
)
register("configure vlan_view add", words="<name>")
register(
    "configure vlan_view add <name>",
    words="<cr> start_vlan_id=<num>|end_vlan_id=<num>|comment=<comment>",
)
register("configure vlan_view <name>", words="delete")
register("configure vlan_view <name> delete", words="<cr>")
register("show", words="vlan_view", help="Read grid state without modifying anything.")
register("show vlan_view", words="<cr> <name>")
register("show vlan_view <name>", words="<cr> fields=<field1,field2,...>")


def _print_vlanview(vv: dict) -> None:
    parts = [f"name={vv.get('name', '')}"]
    if vv.get("start_vlan_id") is not None:
        parts.append(f"start={vv['start_vlan_id']}")
    if vv.get("end_vlan_id") is not None:
        parts.append(f"end={vv['end_vlan_id']}")
    if vv.get("comment"):
        parts.append(f"comment={vv['comment']}")
    print("  " + " ".join(parts))


@command(
    "configure vlan_view add <name>",
    words="<cr> start_vlan_id=<num>|end_vlan_id=<num>|comment=<comment>",
    help="Create a VLAN view.",
)
async def cli_add_vlanview(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bvlan_view\s+add\s+(\S+)", line)
    if not m:
        print("  Error: VLAN view name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    sv = _parse_kv(line, "start_vlan_id")
    ev = _parse_kv(line, "end_vlan_id")
    if sv:
        body["start_vlan_id"] = int(sv)
    if ev:
        body["end_vlan_id"] = int(ev)
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    await ctx.client.ipam.vlanview.create(body)


@command("configure vlan_view <name> delete", words="<cr>", help="Delete a VLAN view by name.")
async def cli_delete_vlanview(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bvlan_view\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: VLAN view name required")
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.ipam.vlanview.list(name=name, max_results=1)]
    if not results:
        print(f"  No VLAN view found: {name}")
        return
    await ctx.client.ipam.vlanview.delete(results[0]["_ref"])


@command("show vlan_view", words="<cr> <name>", help="List VLAN views.")
@command(
    "show vlan_view <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific VLAN view.",
)
async def cli_show_vlanview(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    vv_name = None
    if len(tokens) >= 3 and "=" not in tokens[2]:
        vv_name = tokens[2]
    extra = parse_extra_fields(line)
    filters: dict = {}
    if vv_name:
        filters["name"] = vv_name
    ret_fields = ["name", "start_vlan_id", "end_vlan_id", "comment"]
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.vlanview.list(return_fields=ret_fields + extra, **filters)
    ]
    if not results:
        if vv_name:
            print(f"  No VLAN view found: {vv_name}")
        return
    for vv in results:
        _print_vlanview(vv)
        for f in extra:
            val = vv.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# --- VLAN range ---
register("configure", words="vlan_range", help="Create, modify or delete grid objects.")
register("configure vlan_range", words="add <name>", help="VLAN ranges for DDI VLAN management.")
register("configure vlan_range add", words="<name>")
register(
    "configure vlan_range add <name>",
    words="<cr> start_vlan_id=<num>|end_vlan_id=<num>|vlan_view=<name>|comment=<comment>",
)
register("configure vlan_range <name>", words="delete")
register("configure vlan_range <name> delete", words="<cr>")
register("show", words="vlan_range", help="Read grid state without modifying anything.")
register("show vlan_range", words="<cr> <name>")
register("show vlan_range <name>", words="<cr> fields=<field1,field2,...>")


def _print_vlanrange(vr: dict) -> None:
    parts = [f"name={vr.get('name', '')}"]
    if vr.get("vlan_view"):
        parts.append(f"vlan_view={vr['vlan_view']}")
    if vr.get("start_vlan_id") is not None:
        parts.append(f"start={vr['start_vlan_id']}")
    if vr.get("end_vlan_id") is not None:
        parts.append(f"end={vr['end_vlan_id']}")
    if vr.get("comment"):
        parts.append(f"comment={vr['comment']}")
    print("  " + " ".join(parts))


@command(
    "configure vlan_range add <name>",
    words="<cr> start_vlan_id=<num>|end_vlan_id=<num>|vlan_view=<name>|comment=<comment>",
    help="Create a VLAN range.",
)
async def cli_add_vlanrange(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bvlan_range\s+add\s+(\S+)", line)
    if not m:
        print("  Error: VLAN range name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    sv = _parse_kv(line, "start_vlan_id")
    ev = _parse_kv(line, "end_vlan_id")
    vv = _parse_kv(line, "vlan_view")
    if sv:
        body["start_vlan_id"] = int(sv)
    if ev:
        body["end_vlan_id"] = int(ev)
    if vv:
        body["vlan_view"] = vv
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    await ctx.client.ipam.vlanrange.create(body)


@command("configure vlan_range <name> delete", words="<cr>", help="Delete a VLAN range by name.")
async def cli_delete_vlanrange(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bvlan_range\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: VLAN range name required")
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.ipam.vlanrange.list(name=name, max_results=1)]
    if not results:
        print(f"  No VLAN range found: {name}")
        return
    await ctx.client.ipam.vlanrange.delete(results[0]["_ref"])


@command("show vlan_range", words="<cr> <name>", help="List VLAN ranges.")
@command(
    "show vlan_range <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific VLAN range.",
)
async def cli_show_vlanrange(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    vr_name = None
    if len(tokens) >= 3 and "=" not in tokens[2]:
        vr_name = tokens[2]
    extra = parse_extra_fields(line)
    filters: dict = {}
    if vr_name:
        filters["name"] = vr_name
    ret_fields = ["name", "vlan_view", "start_vlan_id", "end_vlan_id", "comment"]
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.vlanrange.list(return_fields=ret_fields + extra, **filters)
    ]
    if not results:
        if vr_name:
            print(f"  No VLAN range found: {vr_name}")
        return
    for vr in results:
        _print_vlanrange(vr)
        for f in extra:
            val = vr.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# --- VLAN ---
register("configure", words="vlan", help="Create, modify or delete grid objects.")
register(
    "configure vlan", words="add <num>", help="VLAN objects (used by discovery & DHCP options)."
)
register("configure vlan add", words="<num>")
register("configure vlan add <num>", words="<cr> name=<name>|parent=<name>|comment=<comment>")
register("configure vlan <num>", words="delete")
register("configure vlan <num> delete", words="<cr>")
register("show", words="vlan", help="Read grid state without modifying anything.")
register("show vlan", words="<cr> <num>", help="VLAN objects.")
register("show vlan <num>", words="<cr> fields=<field1,field2,...>")


def _print_vlan(v: dict) -> None:
    parts = [f"id={v.get('id', '')}"]
    if v.get("name"):
        parts.append(f"name={v['name']}")
    if v.get("parent"):
        parts.append(f"parent={v['parent']}")
    if v.get("comment"):
        parts.append(f"comment={v['comment']}")
    print("  " + " ".join(parts))


@command(
    "configure vlan add <num>",
    words="<cr> name=<name>|parent=<name>|comment=<comment>",
    help="Create a VLAN entry.",
)
async def cli_add_vlan(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bvlan\s+add\s+(\d+)", line)
    if not m:
        print("  Error: VLAN ID required")
        return
    vlan_id = int(m.group(1))
    body: dict = {"id": vlan_id}
    name = _parse_kv(line, "name")
    parent = _parse_kv(line, "parent")
    if name:
        body["name"] = name
    if parent:
        body["parent"] = parent
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    await ctx.client.ipam.vlan.create(body)


@command("configure vlan <num> delete", words="<cr>", help="Delete a VLAN entry by ID.")
async def cli_delete_vlan(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bvlan\s+(\d+)\s+delete", line)
    if not m:
        print("  Error: VLAN ID required")
        return
    vlan_id = int(m.group(1))
    results = [as_dict(r) async for r in ctx.client.ipam.vlan.list(id=vlan_id, max_results=1)]
    if not results:
        print(f"  No VLAN found: {vlan_id}")
        return
    await ctx.client.ipam.vlan.delete(results[0]["_ref"])


@command("show vlan", words="<cr> <num>", help="List VLANs.")
@command(
    "show vlan <num>", words="<cr> fields=<field1,field2,...>", help="Show a specific VLAN by ID."
)
async def cli_show_vlan(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    vlan_id = None
    if len(tokens) >= 3 and tokens[2].isdigit():
        vlan_id = int(tokens[2])
    extra = parse_extra_fields(line)
    filters: dict = {}
    if vlan_id is not None:
        filters["id"] = vlan_id
    ret_fields = ["id", "name", "parent", "comment"]
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.vlan.list(return_fields=ret_fields + extra, **filters)
    ]
    if not results:
        if vlan_id is not None:
            print(f"  No VLAN found: {vlan_id}")
        return
    for v in results:
        _print_vlan(v)
        for f in extra:
            val = v.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Chunk C - Superhosts, bulkhosts, bulkhostnametemplate
# ---------------------------------------------------------------------------

# --- Superhost ---
register("configure", words="superhost", help="Create, modify or delete grid objects.")
register(
    "configure superhost",
    words="add <name>",
    help="Superhosts - logical grouping of records that act as one host.",
)
register("configure superhost add", words="<name>")
register("configure superhost add <name>", words="<cr> comment=<comment>")
register("configure superhost <name>", words="delete")
register("configure superhost <name> delete", words="<cr>")
register("show", words="superhost", help="Read grid state without modifying anything.")
register(
    "show superhost",
    words="<cr> <name>",
    help="Superhost records (logical object bundling host instances).",
)
register("show superhost <name>", words="<cr> fields=<field1,field2,...>")


def _print_superhost(sh: dict) -> None:
    parts = [f"name={sh.get('name', '')}"]
    if sh.get("comment"):
        parts.append(f"comment={sh['comment']}")
    if sh.get("dhcp_associated_objects"):
        parts.append(f"dhcp_objects={len(sh['dhcp_associated_objects'])}")
    print("  " + " ".join(parts))


@command(
    "configure superhost add <name>", words="<cr> comment=<comment>", help="Create a superhost."
)
async def cli_add_superhost(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bsuperhost\s+add\s+(\S+)", line)
    if not m:
        print("  Error: superhost name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    await ctx.client.ipam.superhost.create(body)


@command("configure superhost <name> delete", words="<cr>", help="Delete a superhost by name.")
async def cli_delete_superhost(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bsuperhost\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: superhost name required")
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.ipam.superhost.list(name=name, max_results=1)]
    if not results:
        print(f"  No superhost found: {name}")
        return
    await ctx.client.ipam.superhost.delete(results[0]["_ref"])


@command("show superhost", words="<cr> <name>", help="List superhosts.")
@command(
    "show superhost <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific superhost.",
)
async def cli_show_superhost(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    sh_name = None
    if len(tokens) >= 3 and "=" not in tokens[2]:
        sh_name = tokens[2]
    extra = parse_extra_fields(line)
    filters: dict = {}
    if sh_name:
        filters["name"] = sh_name
    ret_fields = ["name", "comment", "dhcp_associated_objects"]
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.superhost.list(return_fields=ret_fields + extra, **filters)
    ]
    if not results:
        if sh_name:
            print(f"  No superhost found: {sh_name}")
        return
    for sh in results:
        _print_superhost(sh)
        for f in extra:
            val = sh.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# --- Superhostchild (read-only) ---
register("show", words="superhostchild", help="Read grid state without modifying anything.")
register(
    "show superhostchild",
    words="<cr> <name>",
    help="Superhost children (records bound to a superhost parent).",
)
register("show superhostchild <name>", words="<cr> fields=<field1,field2,...>")


def _print_superhostchild(c: dict) -> None:
    parts = [f"name={c.get('name', '')}"]
    if c.get("type"):
        parts.append(f"type={c['type']}")
    if c.get("parent"):
        parts.append(f"parent={c['parent']}")
    if c.get("record_parent"):
        parts.append(f"record_parent={c['record_parent']}")
    print("  " + " ".join(parts))


@command("show superhostchild", words="<cr> <name>", help="List superhost children (read-only).")
@command(
    "show superhostchild <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show superhost children for a named superhost.",
)
async def cli_show_superhostchild(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    parent_name = None
    if len(tokens) >= 3 and not tokens[2].startswith("<") and "=" not in tokens[2]:
        parent_name = tokens[2]
    if not parent_name:
        print("  Error: parent required (usage: show superhostchild <parent-superhost>)")
        return
    extra = parse_extra_fields(line)
    ret_fields = ["name", "type", "parent", "record_parent"]
    kwargs: dict = {"return_fields": ret_fields, "parent": parent_name}
    results = [as_dict(r) async for r in ctx.client.ipam.superhostchild.list(**kwargs)]
    if not results:
        if parent_name:
            print(f"  No superhostchild found for parent: {parent_name}")
        return
    for c in results:
        _print_superhostchild(c)
        for f in extra:
            val = c.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# --- Bulkhost ---
register("configure", words="bulkhost", help="Create, modify or delete grid objects.")
register(
    "configure bulkhost",
    words="add <name>",
    help="Bulk-host objects - auto-generated sequential host records.",
)
register("configure bulkhost add", words="<name>")
register(
    "configure bulkhost add <name>",
    words="<cr> zone=<zone>|start_addr=<ip>|end_addr=<ip>|comment=<comment>",
)
register("configure bulkhost <name>", words="delete")
register("configure bulkhost <name> delete", words="<cr>")
register("show", words="bulkhost", help="Read grid state without modifying anything.")
register("show bulkhost", words="<cr> <name>", help="List bulk-host objects.")
register("show bulkhost <name>", words="<cr> fields=<field1,field2,...>")


def _print_bulkhost(bh: dict) -> None:
    parts = [f"prefix={bh.get('prefix', '')}"]
    if bh.get("zone"):
        parts.append(f"zone={bh['zone']}")
    if bh.get("start_addr"):
        parts.append(f"start={bh['start_addr']}")
    if bh.get("end_addr"):
        parts.append(f"end={bh['end_addr']}")
    if bh.get("comment"):
        parts.append(f"comment={bh['comment']}")
    print("  " + " ".join(parts))


@command(
    "configure bulkhost add <name>",
    words="<cr> zone=<zone>|start_addr=<ip>|end_addr=<ip>|comment=<comment>",
    help="Create a bulk host record.",
)
async def cli_add_bulkhost(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bbulkhost\s+add\s+(\S+)", line)
    if not m:
        print("  Error: bulk host prefix required")
        return
    prefix = m.group(1)
    body: dict = {"prefix": prefix}
    zone = _parse_kv(line, "zone")
    start_addr = _parse_kv(line, "start_addr")
    end_addr = _parse_kv(line, "end_addr")
    if zone:
        body["zone"] = zone
    if start_addr:
        body["start_addr"] = start_addr
    if end_addr:
        body["end_addr"] = end_addr
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    await ctx.client.ipam.bulkhost.create(body)


@command("configure bulkhost <name> delete", words="<cr>", help="Delete a bulk host by prefix.")
async def cli_delete_bulkhost(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bbulkhost\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: bulk host prefix required")
        return
    prefix = m.group(1)
    results = [
        as_dict(r) async for r in ctx.client.ipam.bulkhost.list(prefix=prefix, max_results=1)
    ]
    if not results:
        print(f"  No bulk host found: {prefix}")
        return
    await ctx.client.ipam.bulkhost.delete(results[0]["_ref"])


@command("show bulkhost", words="<cr> <name>", help="List bulk hosts.")
@command(
    "show bulkhost <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific bulk host.",
)
async def cli_show_bulkhost(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    prefix = None
    if len(tokens) >= 3 and "=" not in tokens[2]:
        prefix = tokens[2]
    extra = parse_extra_fields(line)
    filters: dict = {}
    if prefix:
        filters["prefix"] = prefix
    ret_fields = ["prefix", "zone", "start_addr", "end_addr", "comment"]
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.bulkhost.list(return_fields=ret_fields + extra, **filters)
    ]
    if not results:
        if prefix:
            print(f"  No bulk host found: {prefix}")
        return
    for bh in results:
        _print_bulkhost(bh)
        for f in extra:
            val = bh.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# --- Bulkhostnametemplate ---
register("configure", words="bulkhost_template", help="Create, modify or delete grid objects.")
register(
    "configure bulkhost_template",
    words="add <name>",
    help="Bulk-host templates (name-format rules for bulk hosts).",
)
register("configure bulkhost_template add", words="<name>")
register(
    "configure bulkhost_template add <name>", words="<cr> template_format=<name>|comment=<comment>"
)
register("configure bulkhost_template <name>", words="delete")
register("configure bulkhost_template <name> delete", words="<cr>")
register("show", words="bulkhost_template", help="Read grid state without modifying anything.")
register("show bulkhost_template", words="<cr> <name>", help="List bulk-host templates.")
register("show bulkhost_template <name>", words="<cr> fields=<field1,field2,...>")


def _print_bulkhost_template(bt: dict) -> None:
    parts = [f"name={bt.get('template_name', '')}"]
    if bt.get("template_format"):
        parts.append(f"format={bt['template_format']}")
    print("  " + " ".join(parts))


@command(
    "configure bulkhost_template add <name>",
    words="<cr> template_format=<name>|comment=<comment>",
    help="Create a bulk host name template.",
)
async def cli_add_bulkhost_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bbulkhost_template\s+add\s+(\S+)", line)
    if not m:
        print("  Error: template name required")
        return
    name = m.group(1)
    body: dict = {"template_name": name}
    fmt = _parse_kv(line, "template_format")
    if fmt:
        body["template_format"] = fmt
    await ctx.client.ipam.bulkhostnametemplate.create(body)


@command(
    "configure bulkhost_template <name> delete",
    words="<cr>",
    help="Delete a bulk host name template by name.",
)
async def cli_delete_bulkhost_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bbulkhost_template\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: template name required")
        return
    name = m.group(1)
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.bulkhostnametemplate.list(template_name=name, max_results=1)
    ]
    if not results:
        print(f"  No bulk host template found: {name}")
        return
    await ctx.client.ipam.bulkhostnametemplate.delete(results[0]["_ref"])


@command("show bulkhost_template", words="<cr> <name>", help="List bulk host name templates.")
@command(
    "show bulkhost_template <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific bulk host name template.",
)
async def cli_show_bulkhost_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    tname = None
    if len(tokens) >= 3 and "=" not in tokens[2]:
        tname = tokens[2]
    extra = parse_extra_fields(line)
    filters: dict = {}
    if tname:
        filters["template_name"] = tname
    ret_fields = ["template_name", "template_format"]
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.bulkhostnametemplate.list(
            return_fields=ret_fields + extra, **filters
        )
    ]
    if not results:
        if tname:
            print(f"  No bulk host template found: {tname}")
        return
    for bt in results:
        _print_bulkhost_template(bt)
        for f in extra:
            val = bt.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Chunk D - RIR, rir_organization, hostname_policy, network_discovery,
#            ipv6networktemplate
# ---------------------------------------------------------------------------

# --- Network discovery (read-only) ---
register("show", words="network_discovery", help="Read grid state without modifying anything.")
register(
    "show network_discovery", words="<cr> <n.n.n.n/mm>", help="Network-discovery status / jobs."
)
register("show network_discovery <n.n.n.n/mm>", words="<cr>")


def _print_network_discovery(nd: dict) -> None:
    ref = nd.get("_ref", "")
    parts = [f"ref={ref}"]
    for k, v in nd.items():
        if k in ("_ref",):
            continue
        parts.append(f"{k}={v}")
    print("  " + " ".join(parts))


@command("show network_discovery", words="<cr> <n.n.n.n/mm>", help="List network discovery data.")
@command(
    "show network_discovery <n.n.n.n/mm>",
    words="<cr>",
    help="Show network discovery data for a specific CIDR.",
)
async def cli_show_network_discovery(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    cidr = None
    if len(tokens) >= 3 and "/" in tokens[2]:
        cidr = tokens[2]
    filters: dict = {}
    if cidr:
        filters["network"] = cidr
    results = [as_dict(r) async for r in ctx.client.ipam.network_discovery.list(**filters)]
    if not results:
        if cidr:
            print(f"  No network discovery data for: {cidr}")
        return
    for nd in results:
        _print_network_discovery(nd)


# --- RIR (read-only) ---
register("show", words="rir", help="Read grid state without modifying anything.")
register("show rir", words="<cr> <name>")
register("show rir <name>", words="<cr> fields=<field1,field2,...>")


def _print_rir(r: dict) -> None:
    parts = [f"name={r.get('name', '')}"]
    if r.get("communication_mode"):
        parts.append(f"mode={r['communication_mode']}")
    if r.get("email"):
        parts.append(f"email={r['email']}")
    if r.get("url"):
        parts.append(f"url={r['url']}")
    print("  " + " ".join(parts))


@command("show rir", words="<cr> <name>", help="List RIR configurations (read-only).")
@command("show rir <name>", words="<cr> fields=<field1,field2,...>", help="Show a specific RIR.")
async def cli_show_rir(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    rir_name = None
    if len(tokens) >= 3 and "=" not in tokens[2]:
        rir_name = tokens[2]
    extra = parse_extra_fields(line)
    filters: dict = {}
    if rir_name:
        filters["name"] = rir_name
    ret_fields = ["name", "communication_mode", "email", "url"]
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.rir.list(return_fields=ret_fields + extra, **filters)
    ]
    if not results:
        if rir_name:
            print(f"  No RIR found: {rir_name}")
        return
    for r in results:
        _print_rir(r)
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# --- RIR organization ---
register("configure", words="rir_organization", help="Create, modify or delete grid objects.")
register(
    "configure rir_organization", words="add <name>", help="RIR organization records for DDI IPAM."
)
register("configure rir_organization add", words="<name>")
register(
    "configure rir_organization add <name>",
    words="<cr> id=<name>|rir=<name>|maintainer=<name>|sender_email=<name>|comment=<comment>",
)
register("configure rir_organization <name>", words="delete")
register("configure rir_organization <name> delete", words="<cr>")
register("show", words="rir_organization", help="Read grid state without modifying anything.")
register(
    "show rir_organization",
    words="<cr> <name>",
    help="Registered Internet Registry (RIR) organizations.",
)
register("show rir_organization <name>", words="<cr> fields=<field1,field2,...>")


def _print_rir_organization(org: dict) -> None:
    parts = [f"name={org.get('name', '')}"]
    if org.get("id"):
        parts.append(f"id={org['id']}")
    if org.get("rir"):
        parts.append(f"rir={org['rir']}")
    if org.get("maintainer"):
        parts.append(f"maintainer={org['maintainer']}")
    if org.get("sender_email"):
        parts.append(f"sender_email={org['sender_email']}")
    print("  " + " ".join(parts))


@command(
    "configure rir_organization add <name>",
    words="<cr> id=<name>|rir=<name>|maintainer=<name>|sender_email=<name>|comment=<comment>",
    help="Create an RIR organization.",
)
async def cli_add_rir_organization(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brir_organization\s+add\s+(\S+)", line)
    if not m:
        print("  Error: RIR organization name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    org_id = _parse_kv(line, "id")
    rir = _parse_kv(line, "rir")
    maintainer = _parse_kv(line, "maintainer")
    sender_email = _parse_kv(line, "sender_email")
    if org_id:
        body["id"] = org_id
    if rir:
        body["rir"] = rir
    if maintainer:
        body["maintainer"] = maintainer
    if sender_email:
        body["sender_email"] = sender_email
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    await ctx.client.ipam.rir_organization.create(body)


@command(
    "configure rir_organization <name> delete",
    words="<cr>",
    help="Delete an RIR organization by name.",
)
async def cli_delete_rir_organization(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brir_organization\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: RIR organization name required")
        return
    name = m.group(1)
    results = [
        as_dict(r) async for r in ctx.client.ipam.rir_organization.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No RIR organization found: {name}")
        return
    await ctx.client.ipam.rir_organization.delete(results[0]["_ref"])


@command("show rir_organization", words="<cr> <name>", help="List RIR organizations.")
@command(
    "show rir_organization <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific RIR organization.",
)
async def cli_show_rir_organization(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    org_name = None
    if len(tokens) >= 3 and "=" not in tokens[2]:
        org_name = tokens[2]
    extra = parse_extra_fields(line)
    filters: dict = {}
    if org_name:
        filters["name"] = org_name
    ret_fields = ["name", "id", "rir", "maintainer", "sender_email"]
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.rir_organization.list(
            return_fields=ret_fields + extra, **filters
        )
    ]
    if not results:
        if org_name:
            print(f"  No RIR organization found: {org_name}")
        return
    for org in results:
        _print_rir_organization(org)
        for f in extra:
            val = org.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# --- Hostname rewrite policy ---
register("configure", words="hostname_policy", help="Create, modify or delete grid objects.")
register(
    "configure hostname_policy",
    words="add <name>",
    help="Hostname-validation policies applied to host names.",
)
register("configure hostname_policy add", words="<name>")
register(
    "configure hostname_policy add <name>",
    words="<cr> valid_characters=<name>|replacement_character=<name>|comment=<comment>",
)
register("configure hostname_policy <name>", words="delete")
register("configure hostname_policy <name> delete", words="<cr>")
register("show", words="hostname_policy", help="Read grid state without modifying anything.")
register("show hostname_policy", words="<cr> <name>", help="Hostname-validation policies.")
register("show hostname_policy <name>", words="<cr> fields=<field1,field2,...>")


def _print_hostname_policy(hp: dict) -> None:
    parts = [f"name={hp.get('name', '')}"]
    if hp.get("valid_characters"):
        parts.append(f"valid_characters={hp['valid_characters']}")
    if hp.get("replacement_character"):
        parts.append(f"replacement={hp['replacement_character']}")
    if hp.get("is_default"):
        parts.append("is_default=true")
    if hp.get("pre_defined"):
        parts.append("pre_defined=true")
    print("  " + " ".join(parts))


@command(
    "configure hostname_policy add <name>",
    words="<cr> valid_characters=<name>|replacement_character=<name>|comment=<comment>",
    help="Create a hostname rewrite policy.",
)
async def cli_add_hostname_policy(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bhostname_policy\s+add\s+(\S+)", line)
    if not m:
        print("  Error: hostname policy name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    valid_chars = _parse_kv(line, "valid_characters")
    replacement = _parse_kv(line, "replacement_character")
    if valid_chars:
        body["valid_characters"] = valid_chars
    if replacement:
        body["replacement_character"] = replacement
    await ctx.client.ipam.hostnamerewritepolicy.create(body)


@command(
    "configure hostname_policy <name> delete",
    words="<cr>",
    help="Delete a hostname rewrite policy by name.",
)
async def cli_delete_hostname_policy(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bhostname_policy\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: hostname policy name required")
        return
    name = m.group(1)
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.hostnamerewritepolicy.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No hostname policy found: {name}")
        return
    await ctx.client.ipam.hostnamerewritepolicy.delete(results[0]["_ref"])


@command("show hostname_policy", words="<cr> <name>", help="List hostname rewrite policies.")
@command(
    "show hostname_policy <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific hostname rewrite policy.",
)
async def cli_show_hostname_policy(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    hp_name = None
    if len(tokens) >= 3 and "=" not in tokens[2]:
        hp_name = tokens[2]
    extra = parse_extra_fields(line)
    filters: dict = {}
    if hp_name:
        filters["name"] = hp_name
    ret_fields = ["name", "valid_characters", "replacement_character", "is_default", "pre_defined"]
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.hostnamerewritepolicy.list(
            return_fields=ret_fields + extra, **filters
        )
    ]
    if not results:
        if hp_name:
            print(f"  No hostname policy found: {hp_name}")
        return
    for hp in results:
        _print_hostname_policy(hp)
        for f in extra:
            val = hp.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# --- IPv6 network template ---
register("configure", words="template", help="Create, modify or delete grid objects.")
register(
    "configure template",
    words="ipv6network network",
    help="DHCP network/range/fixed templates (for provisioning).",
)
register("configure template ipv6network", words="add <name>", help="IPv6 network templates.")
register("configure template ipv6network add", words="<name>")
register("configure template ipv6network add <name>", words="<cr> cidr=<num>|comment=<comment>")
register("configure template ipv6network <name>", words="delete")
register("configure template ipv6network <name> delete", words="<cr>")
register("show", words="template", help="Read grid state without modifying anything.")
register(
    "show template",
    words="ipv6network network",
    help="DHCP templates (network/range/fixed + IPv6 variants).",
)
register("show template ipv6network", words="<cr> <name>")
register("show template ipv6network <name>", words="<cr> fields=<field1,field2,...>")


def _print_ipv6networktemplate(t: dict) -> None:
    parts = [f"name={t.get('name', '')}"]
    if t.get("cidr") is not None:
        parts.append(f"cidr={t['cidr']}")
    if t.get("comment"):
        parts.append(f"comment={t['comment']}")
    print("  " + " ".join(parts))


@command(
    "configure template ipv6network add <name>",
    words="<cr> cidr=<num>|comment=<comment>",
    help="Create an IPv6 network template.",
)
async def cli_add_ipv6networktemplate(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\btemplate\s+ipv6network\s+add\s+(\S+)", line)
    if not m:
        print("  Error: IPv6 network template name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    cidr = _parse_kv(line, "cidr")
    if cidr:
        body["cidr"] = int(cidr)
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    await ctx.client.ipam.ipv6networktemplate.create(body)


@command(
    "configure template ipv6network <name> delete",
    words="<cr>",
    help="Delete an IPv6 network template by name.",
)
async def cli_delete_ipv6networktemplate(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\btemplate\s+ipv6network\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: IPv6 network template name required")
        return
    name = m.group(1)
    results = [
        as_dict(r) async for r in ctx.client.ipam.ipv6networktemplate.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No IPv6 network template found: {name}")
        return
    await ctx.client.ipam.ipv6networktemplate.delete(results[0]["_ref"])


@command("show template ipv6network", words="<cr> <name>", help="List IPv6 network templates.")
@command(
    "show template ipv6network <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific IPv6 network template.",
)
async def cli_show_ipv6networktemplate(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    tname = None
    if len(tokens) >= 4 and "=" not in tokens[3]:
        tname = tokens[3]
    extra = parse_extra_fields(line)
    filters: dict = {}
    if tname:
        filters["name"] = tname
    ret_fields = ["name", "cidr", "comment"]
    results = [
        as_dict(r)
        async for r in ctx.client.ipam.ipv6networktemplate.list(
            return_fields=ret_fields + extra, **filters
        )
    ]
    if not results:
        if tname:
            print(f"  No IPv6 network template found: {tname}")
        return
    for t in results:
        _print_ipv6networktemplate(t)
        for f in extra:
            val = t.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")
