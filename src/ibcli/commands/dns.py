# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Phase 11 DNS gap closures.

Covers:
  Chunk A: NS-group sub-types (delegation, forwarding, forward_stub, stub) + allnsgroup
  Chunk B: DDNS principal clusters + cluster groups
  Chunk C: Record name policy + DNS64
  Chunk D: Ordered RPZ + allrecords aggregator

Command vocabulary (all registered here):

  # NS group sub-types
  configure nsgroup delegation add <name> [delegate_to=<ns,ip>...] [comment=<text>]
  configure nsgroup delegation <name> delete
  show nsgroup delegation [<name>]

  configure nsgroup forwarding add <name> [forwarding_servers=<ip>...] [comment=<text>]
  configure nsgroup forwarding <name> delete
  show nsgroup forwarding [<name>]

  configure nsgroup forward_stub add <name> [comment=<text>]
  configure nsgroup forward_stub <name> delete
  show nsgroup forward_stub [<name>]

  configure nsgroup stub add <name> [comment=<text>]
  configure nsgroup stub <name> delete
  show nsgroup stub [<name>]

  show nsgroup all   # allnsgroup aggregate

  # DDNS principal clusters
  configure ddns cluster add <name> [principals=<str>,...] [comment=<text>]
  configure ddns cluster <name> delete
  configure ddns cluster <name> set <key>=<value>
  show ddns cluster [<name>]

  configure ddns cluster_group add <name> [comment=<text>]
  configure ddns cluster_group <name> delete
  show ddns cluster_group [<name>]

  # Record name policy
  configure record_name_policy add <name> regex=<pattern> [comment=<text>]
  configure record_name_policy <name> delete
  show record_name_policy [<name>]

  # DNS64
  configure dns64 add <name> prefix=<ipv6/cidr> [comment=<text>]
  configure dns64 <name> delete
  show dns64 [<name>]

  # Ordered RPZ (singleton-ish - one list per view)
  show rpz_order [view=<view>]
  configure rpz_order set rpz_list=<ref>,<ref>,...

  # All records aggregator
  show record all [<name>] [zone=<zone>]
"""

from __future__ import annotations

import re

from ibcli import completions as _completions
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict, format_extra_field, parse_extra_fields

# ---------------------------------------------------------------------------
# Shared helpers (mirrors zone.py - no import to avoid coupling)
# ---------------------------------------------------------------------------


def _parse_kv(line: str, key: str) -> str | None:
    m = re.search(rf"\b{re.escape(key)}[= ](\S+)", line)
    return m.group(1) if m else None


def _parse_comment(line: str) -> str | None:
    m = re.search(r'\bcomment\s+"([^"]+)"', line)
    if m:
        return m.group(1)
    m = re.search(r"\bcomment\s+(\S+)", line)
    return m.group(1) if m else None


def _split_name_ip(raw: str) -> dict[str, str]:
    """'ns1,1.2.3.4' -> {'name': 'ns1', 'address': '1.2.3.4'}."""
    name, _, address = raw.partition(",")
    return {"name": name, "address": address}


# ===========================================================================
# Top-level keyword registrations (additive to the shared "configure"/"show" tables)
# ===========================================================================

# Add new sub-trees to the shared "configure" and "show" dispatch tables.
# These are additive: each call merges words into the existing entry.
register(
    "configure",
    words="ddns dns64 rpz_order record_name_policy",
    help="Create, modify or delete grid objects.",
)
register(
    "show",
    words="nsgroup ddns dns64 rpz_order record_name_policy",
    help="Read grid state without modifying anything.",
)


# ===========================================================================
# Chunk A: NS group sub-types + allnsgroup
# ===========================================================================

# ---------------------------------------------------------------------------
# Extend the "nsgroup" subtree already started in grid.py (slug5b)
# grid.py registers: configure nsgroup add <name> / configure nsgroup <name> delete
# We add: configure nsgroup delegation/forwarding/forward_stub/stub sub-trees.
# ---------------------------------------------------------------------------

register(
    "configure nsgroup",
    words="delegation forwarding forward_stub stub",
    help="NS groups - named sets of DNS name-servers used on zones.",
)
register("configure nsgroup delegation", words="add <name>")
register("configure nsgroup delegation add", words="<name>")
register(
    "configure nsgroup delegation add <name>", words="<cr> delegate_to=<name>|comment=<comment>"
)
register("configure nsgroup delegation <name>", words="delete")
register("configure nsgroup forwarding", words="add <name>")
register("configure nsgroup forwarding add", words="<name>")
register(
    "configure nsgroup forwarding add <name>",
    words="<cr> forwarding_servers=<name>|comment=<comment>",
)
register("configure nsgroup forwarding <name>", words="delete")
register("configure nsgroup forward_stub", words="add <name>")
register("configure nsgroup forward_stub add", words="<name>")
register("configure nsgroup forward_stub add <name>", words="<cr> comment=<comment>")
register("configure nsgroup forward_stub <name>", words="delete")
register("configure nsgroup stub", words="add <name>")
register("configure nsgroup stub add", words="<name>")
register("configure nsgroup stub add <name>", words="<cr> comment=<comment>")
register("configure nsgroup stub <name>", words="delete")

register(
    "show nsgroup",
    words="authoritative delegation forwarding forward_stub stub all",
    help="NS groups (authoritative, forward_stub, delegation, etc.).",
)
register("show nsgroup authoritative", words="<cr> <name>", dynamic=_completions.nsgroups)
register("show nsgroup authoritative <name>", words="<cr> fields=<field1,field2,...>")
register("show nsgroup delegation", words="<cr> <name>")
register("show nsgroup forwarding", words="<cr> <name>")
register("show nsgroup forward_stub", words="<cr> <name>")
register("show nsgroup stub", words="<cr> <name>")


# ---- delegation ----


@command(
    "configure nsgroup delegation add <name>",
    words="<cr> delegate_to=<name>|comment=<comment>",
    help="Add a delegation NS group.",
)
async def cli_add_nsgroup_delegation(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bdelegation add (\S+)", line)
    if not m:
        print("  Error: name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    delegates = re.findall(r"\bdelegate_to\s+(\S+)", line)
    if delegates:
        body["delegate_to"] = [_split_name_ip(x) for x in delegates]
    await ctx.client.dns.nsgroup_delegation.create(body)


@command("configure nsgroup delegation <name> delete", help="Delete a delegation NS group.")
async def cli_delete_nsgroup_delegation(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bdelegation (\S+) delete", line)
    if not m:
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.dns.nsgroup_delegation.list(name=name)]
    if not results:
        print(f"  No delegation NS group found: {name}")
        return
    await ctx.client.dns.nsgroup_delegation.delete(results[0]["_ref"])


@command("show nsgroup delegation", words="<cr> <name>", help="Show delegation NS groups.")
@command(
    "show nsgroup delegation <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific delegation NS group.",
)
async def cli_show_nsgroup_delegation(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    name = None
    if len(tokens) >= 4 and tokens[3] not in ("<cr>",) and "=" not in tokens[3]:
        name = tokens[3]
    extra = parse_extra_fields(line)
    params: dict = {}
    if extra:
        params["return_fields_plus"] = extra
    if name:
        params["name"] = name
    results = [as_dict(r) async for r in ctx.client.dns.nsgroup_delegation.list(**params)]
    if not results:
        if name:
            print(f"  No delegation NS group found: {name}")
        return
    for r in results:
        _print_nsgroup(r, "delegation")
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---- forwarding member ----


@command(
    "configure nsgroup forwarding add <name>",
    words="<cr> forwarding_servers=<name>|comment=<comment>",
    help="Add a forwarding-member NS group.",
)
async def cli_add_nsgroup_forwarding(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bforwarding add (\S+)", line)
    if not m:
        print("  Error: name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    servers = re.findall(r"\bforwarding_servers\s+(\S+)", line)
    if servers:
        body["forwarding_servers"] = [{"name": s} for s in servers]
    await ctx.client.dns.nsgroup_forwardingmember.create(body)


@command("configure nsgroup forwarding <name> delete", help="Delete a forwarding-member NS group.")
async def cli_delete_nsgroup_forwarding(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bforwarding (\S+) delete", line)
    if not m:
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.dns.nsgroup_forwardingmember.list(name=name)]
    if not results:
        print(f"  No forwarding NS group found: {name}")
        return
    await ctx.client.dns.nsgroup_forwardingmember.delete(results[0]["_ref"])


@command("show nsgroup forwarding", words="<cr> <name>", help="Show forwarding-member NS groups.")
@command(
    "show nsgroup forwarding <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific forwarding NS group.",
)
async def cli_show_nsgroup_forwarding(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    name = None
    if len(tokens) >= 4 and tokens[3] not in ("<cr>",) and "=" not in tokens[3]:
        name = tokens[3]
    extra = parse_extra_fields(line)
    params: dict = {}
    if extra:
        params["return_fields_plus"] = extra
    if name:
        params["name"] = name
    results = [as_dict(r) async for r in ctx.client.dns.nsgroup_forwardingmember.list(**params)]
    if not results:
        if name:
            print(f"  No forwarding NS group found: {name}")
        return
    for r in results:
        _print_nsgroup(r, "forwarding")
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---- forward_stub server ----


@command(
    "configure nsgroup forward_stub add <name>",
    words="<cr> comment=<comment>",
    help="Add a forward/stub-server NS group.",
)
async def cli_add_nsgroup_forward_stub(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bforward_stub add (\S+)", line)
    if not m:
        print("  Error: name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    await ctx.client.dns.nsgroup_forwardstubserver.create(body)


@command(
    "configure nsgroup forward_stub <name> delete", help="Delete a forward/stub-server NS group."
)
async def cli_delete_nsgroup_forward_stub(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bforward_stub (\S+) delete", line)
    if not m:
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.dns.nsgroup_forwardstubserver.list(name=name)]
    if not results:
        print(f"  No forward_stub NS group found: {name}")
        return
    await ctx.client.dns.nsgroup_forwardstubserver.delete(results[0]["_ref"])


@command(
    "show nsgroup forward_stub", words="<cr> <name>", help="Show forward/stub-server NS groups."
)
@command(
    "show nsgroup forward_stub <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific forward_stub NS group.",
)
async def cli_show_nsgroup_forward_stub(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    name = None
    if len(tokens) >= 4 and tokens[3] not in ("<cr>",) and "=" not in tokens[3]:
        name = tokens[3]
    extra = parse_extra_fields(line)
    params: dict = {}
    if extra:
        params["return_fields_plus"] = extra
    if name:
        params["name"] = name
    results = [as_dict(r) async for r in ctx.client.dns.nsgroup_forwardstubserver.list(**params)]
    if not results:
        if name:
            print(f"  No forward_stub NS group found: {name}")
        return
    for r in results:
        _print_nsgroup(r, "forward_stub")
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---- stub member ----


@command(
    "configure nsgroup stub add <name>",
    words="<cr> comment=<comment>",
    help="Add a stub-member NS group.",
)
async def cli_add_nsgroup_stub(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bnsgroup stub add (\S+)", line)
    if not m:
        print("  Error: name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    await ctx.client.dns.nsgroup_stubmember.create(body)


@command("configure nsgroup stub <name> delete", help="Delete a stub-member NS group.")
async def cli_delete_nsgroup_stub(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bnsgroup stub (\S+) delete", line)
    if not m:
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.dns.nsgroup_stubmember.list(name=name)]
    if not results:
        print(f"  No stub NS group found: {name}")
        return
    await ctx.client.dns.nsgroup_stubmember.delete(results[0]["_ref"])


@command("show nsgroup stub", words="<cr> <name>", help="Show stub-member NS groups.")
@command(
    "show nsgroup stub <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific stub NS group.",
)
async def cli_show_nsgroup_stub(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    name = None
    if len(tokens) >= 4 and tokens[3] not in ("<cr>",) and "=" not in tokens[3]:
        name = tokens[3]
    extra = parse_extra_fields(line)
    params: dict = {}
    if extra:
        params["return_fields_plus"] = extra
    if name:
        params["name"] = name
    results = [as_dict(r) async for r in ctx.client.dns.nsgroup_stubmember.list(**params)]
    if not results:
        if name:
            print(f"  No stub NS group found: {name}")
        return
    for r in results:
        _print_nsgroup(r, "stub")
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---- authoritative (plain nsgroup) ----


@command("show nsgroup authoritative", words="<cr> <name>", help="Show authoritative NS groups.")
@command(
    "show nsgroup authoritative <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific authoritative NS group.",
)
async def cli_show_nsgroup_authoritative(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    name = None
    if len(tokens) >= 4 and tokens[3] not in ("<cr>",) and "=" not in tokens[3]:
        name = tokens[3]
    extra = parse_extra_fields(line)
    params: dict = {"return_fields_plus": ["comment"] + extra}
    if name:
        params["name"] = name
    results = [as_dict(r) async for r in ctx.client.dns.nsgroup.list(**params)]
    if not results:
        if name:
            print(f"  No authoritative NS group found: {name}")
        return
    for r in results:
        _print_nsgroup(r, "authoritative")
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---- allnsgroup aggregate ----


@command(
    "show nsgroup all",
    words="<cr> fields=<field1,field2,...>",
    help="Show all NS groups (aggregate across all types).",
)
async def cli_show_allnsgroup(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    extra = parse_extra_fields(line)
    kwargs: dict = {}
    if extra:
        kwargs["return_fields_plus"] = extra
    results = [as_dict(r) async for r in ctx.client.dns.allnsgroup.list(**kwargs)]
    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("type"):
            parts.append(f"type={r['type']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


def _print_nsgroup(r: dict, subtype: str) -> None:
    parts = [f"type={subtype}", f"name={r.get('name', '')}"]
    if r.get("comment"):
        parts.append(f"comment={r['comment']}")
    print(" ".join(parts))


# ===========================================================================
# Chunk B: DDNS principal clusters + cluster groups
# ===========================================================================

# DDNS principal clusters manage the Kerberos (GSS-TSIG) principals that are
# allowed to perform AUTHENTICATED dynamic DNS updates against NIOS zones.
# Typical example: Active Directory DCs or DHCP relays that push DDNS updates
# signed with a Kerberos ticket.
#
# This is NOT:
#   - grid-level DHCP DDNS behaviour (see `configure grid <g> dhcp set ddns_*`)
#   - zone update-policy ACLs (see `configure zone <z> set allow_update=...`)
#   - anything cloud-related
#
# "Cluster" here is Infoblox terminology for "a named allowlist of principals"
# - not a cluster of servers. A "cluster_group" is an ordered bundle of such
# allowlists that a zone can reference as its update policy.
register(
    "configure ddns",
    words="cluster cluster_group",
    help="Manage Kerberos principal allowlists for authenticated DDNS "
    "updates (GSS-TSIG). See `configure grid ... dhcp` for grid "
    "DHCP DDNS settings, or `configure zone <z> set allow_update` "
    "for per-zone update ACLs.",
)
register(
    "configure ddns cluster",
    words="add <name>",
    help="Principal allowlist (Infoblox calls this a 'cluster').",
)
register("configure ddns cluster add", words="<name>")
register("configure ddns cluster add <name>", words="<cr> principals=<name>|comment=<comment>")
register("configure ddns cluster <name>", words="delete set")
register("configure ddns cluster <name> set", words="<key>")
register("configure ddns cluster <name> set <key>", words="<value>")
register(
    "configure ddns cluster_group",
    words="add <name>",
    help="Ordered bundle of principal allowlists.",
)
register("configure ddns cluster_group add", words="<name>")
register("configure ddns cluster_group add <name>", words="<cr> comment=<comment>")
register("configure ddns cluster_group <name>", words="delete")

register(
    "show ddns", words="cluster cluster_group", help="Show DDNS principal allowlists (GSS-TSIG)."
)
register("show ddns cluster", words="<cr> <name>")
register("show ddns cluster_group", words="<cr> <name>")


# ---- ddns cluster ----


@command(
    "configure ddns cluster add <name>",
    words="<cr> principals=<name>|comment=<comment>",
    help="Add a GSS-TSIG principal allowlist (aka DDNS 'cluster'). "
    "principals=<p1,p2,...> lists Kerberos principals "
    "(e.g. dhcp$@CORP.EXAMPLE.COM) authorized for authenticated "
    "DDNS updates against zones that reference this cluster.",
)
async def cli_add_ddns_cluster(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bcluster add (\S+)", line)
    if not m:
        print("  Error: name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    # principals=a,b,c → split on comma
    pm = re.search(r"\bprincipals\s+(\S+)", line)
    if pm:
        body["principals"] = [p for p in pm.group(1).split(",") if p]
    await ctx.client.dns.ddns_principalcluster.create(body)


@command(
    "configure ddns cluster <name> delete",
    help="Delete a GSS-TSIG principal allowlist. Fails if any zone's "
    "update policy still references it.",
)
async def cli_delete_ddns_cluster(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bcluster (\S+) delete", line)
    if not m:
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.dns.ddns_principalcluster.list(name=name)]
    if not results:
        print(f"  No DDNS cluster found: {name}")
        return
    await ctx.client.dns.ddns_principalcluster.delete(results[0]["_ref"])


@command(
    "configure ddns cluster <name> set <key> <value>",
    help="Update a field on the principal allowlist. Common keys: "
    "principals (comma-list of Kerberos principals), comment.",
)
async def cli_set_ddns_cluster(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bcluster (\S+) set (\S+) (\S+)", line)
    if not m:
        print("  Error: cluster <name> set <key> <value> required")
        return
    name, key, value = m.group(1), m.group(2), m.group(3)
    results = [as_dict(r) async for r in ctx.client.dns.ddns_principalcluster.list(name=name)]
    if not results:
        print(f"  No DDNS cluster found: {name}")
        return
    await ctx.client.dns.ddns_principalcluster.update(results[0]["_ref"], {key: value})


@command(
    "show ddns cluster",
    words="<cr> <name>",
    help="List GSS-TSIG principal allowlists (DDNS clusters).",
)
@command(
    "show ddns cluster <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show one principal allowlist, including its member principals.",
)
async def cli_show_ddns_cluster(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    name = None
    if len(tokens) >= 4 and tokens[3] not in ("<cr>",) and "=" not in tokens[3]:
        name = tokens[3]
    extra = parse_extra_fields(line)
    params: dict = {}
    if extra:
        params["return_fields_plus"] = extra
    if name:
        params["name"] = name
    results = [as_dict(r) async for r in ctx.client.dns.ddns_principalcluster.list(**params)]
    if not results:
        if name:
            print(f"  No DDNS cluster found: {name}")
        return
    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        if r.get("principals"):
            parts.append(f"principals={','.join(r['principals'])}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---- ddns cluster_group ----


@command(
    "configure ddns cluster_group add <name>",
    words="<cr> comment=<comment>",
    help="Add a cluster_group - an ordered bundle of DDNS principal "
    "allowlists. A zone's update policy can point at a group to "
    "evaluate multiple allowlists in sequence.",
)
async def cli_add_ddns_cluster_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bcluster_group add (\S+)", line)
    if not m:
        print("  Error: name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    await ctx.client.dns.ddns_principalcluster_group.create(body)


@command(
    "configure ddns cluster_group <name> delete",
    help="Delete a principal-allowlist group. Fails if a zone's update policy still references it.",
)
async def cli_delete_ddns_cluster_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bcluster_group (\S+) delete", line)
    if not m:
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.dns.ddns_principalcluster_group.list(name=name)]
    if not results:
        print(f"  No DDNS cluster group found: {name}")
        return
    await ctx.client.dns.ddns_principalcluster_group.delete(results[0]["_ref"])


@command(
    "show ddns cluster_group", words="<cr> <name>", help="List DDNS principal-allowlist groups."
)
@command(
    "show ddns cluster_group <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show one principal-allowlist group and its contained clusters.",
)
async def cli_show_ddns_cluster_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    name = None
    if len(tokens) >= 4 and tokens[3] not in ("<cr>",) and "=" not in tokens[3]:
        name = tokens[3]
    extra = parse_extra_fields(line)
    params: dict = {}
    if extra:
        params["return_fields_plus"] = extra
    if name:
        params["name"] = name
    results = [as_dict(r) async for r in ctx.client.dns.ddns_principalcluster_group.list(**params)]
    if not results:
        if name:
            print(f"  No DDNS cluster group found: {name}")
        return
    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Chunk C: Record name policy + DNS64
# ===========================================================================

register(
    "configure record_name_policy",
    words="add <name>",
    help="Hostname regex policies used by zones on record add.",
)
register("configure record_name_policy add", words="<name>")
register("configure record_name_policy add <name>", words="<cr> regex=<value>|comment=<comment>")
register("configure record_name_policy <name>", words="delete")

register("show record_name_policy", words="<cr> <name>")

register(
    "configure dns64",
    words="add <name>",
    help="DNS64 synthesis groups (IPv6-only clients → IPv4 hosts).",
)
register("configure dns64 add", words="<name>")
register("configure dns64 add <name>", words="<cr> prefix=<name>|comment=<comment>")
register("configure dns64 <name>", words="delete")

register("show dns64", words="<cr> <name>", help="DNS64 synthesis groups.")


# ---- record_name_policy ----


@command(
    "configure record_name_policy add <name>",
    words="<cr> regex=<value>|comment=<comment>",
    help="Add a DNS record name policy.",
)
async def cli_add_record_name_policy(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brecord_name_policy add (\S+)", line)
    if not m:
        print("  Error: name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    regex = _parse_kv(line, "regex")
    if regex:
        body["regex"] = regex
    await ctx.client.dns.recordnamepolicy.create(body)


@command("configure record_name_policy <name> delete", help="Delete a DNS record name policy.")
async def cli_delete_record_name_policy(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brecord_name_policy (\S+) delete", line)
    if not m:
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.dns.recordnamepolicy.list(name=name)]
    if not results:
        print(f"  No record name policy found: {name}")
        return
    await ctx.client.dns.recordnamepolicy.delete(results[0]["_ref"])


@command("show record_name_policy", words="<cr> <name>", help="Show DNS record name policies.")
@command(
    "show record_name_policy <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific record name policy.",
)
async def cli_show_record_name_policy(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    name = None
    if len(tokens) >= 3 and tokens[2] not in ("<cr>",) and "=" not in tokens[2]:
        name = tokens[2]
    extra = parse_extra_fields(line)
    params: dict = {}
    if extra:
        params["return_fields_plus"] = extra
    if name:
        params["name"] = name
    results = [as_dict(r) async for r in ctx.client.dns.recordnamepolicy.list(**params)]
    if not results:
        if name:
            print(f"  No record name policy found: {name}")
        return
    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("regex"):
            parts.append(f"regex={r['regex']}")
        if r.get("is_default"):
            parts.append("is_default=true")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---- dns64 ----


@command(
    "configure dns64 add <name>",
    words="<cr> prefix=<name>|comment=<comment>",
    help="Add a DNS64 synthesis group.",
)
async def cli_add_dns64(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bdns64 add (\S+)", line)
    if not m:
        print("  Error: name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    prefix = _parse_kv(line, "prefix")
    if prefix:
        body["prefix"] = prefix
    await ctx.client.dns.dns64group.create(body)


@command("configure dns64 <name> delete", help="Delete a DNS64 synthesis group.")
async def cli_delete_dns64(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bdns64 (\S+) delete", line)
    if not m:
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.dns.dns64group.list(name=name)]
    if not results:
        print(f"  No DNS64 group found: {name}")
        return
    await ctx.client.dns.dns64group.delete(results[0]["_ref"])


@command("show dns64", words="<cr> <name>", help="Show DNS64 synthesis groups.")
@command(
    "show dns64 <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific DNS64 group.",
)
async def cli_show_dns64(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    name = None
    if len(tokens) >= 3 and tokens[2] not in ("<cr>",) and "=" not in tokens[2]:
        name = tokens[2]
    extra = parse_extra_fields(line)
    params: dict = {}
    if extra:
        params["return_fields_plus"] = extra
    if name:
        params["name"] = name
    results = [as_dict(r) async for r in ctx.client.dns.dns64group.list(**params)]
    if not results:
        if name:
            print(f"  No DNS64 group found: {name}")
        return
    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("prefix"):
            parts.append(f"prefix={r['prefix']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Chunk D: Ordered RPZ (GET+PUT) + allrecords aggregator
# ===========================================================================

register(
    "configure rpz_order", words="set", help="Evaluation order of RPZ zones within a DNS view."
)
register("configure rpz_order set", words="rpz_list=<name>")

register("show rpz_order", words="<cr> view=<name>", help="RPZ evaluation order (per view).")
register(
    "show record", words="all", help="DNS records - all modern types (CAA, HTTPS, SVCB, NAPTR…)."
)
register("show record all", words="<cr> <name>|zone=<name>")


# ---- show rpz_order ----


@command(
    "show rpz_order",
    words="<cr> view=<name> fields=<field1,field2,...>",
    help="Show ordered RPZ list (one per view).",
)
async def cli_show_rpz_order(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    view = _parse_kv(line, "view")
    if not view:
        print("  Error: view required (usage: show rpz_order view=<view>)")
        return
    extra = parse_extra_fields(line)
    params: dict = {"view": view}
    if extra:
        params["return_fields_plus"] = extra
    results = [as_dict(r) async for r in ctx.client.dns.orderedresponsepolicyzones.list(**params)]
    if not results:
        print("  No ordered RPZ configuration found")
        return
    for r in results:
        parts = []
        if r.get("view"):
            parts.append(f"view={r['view']}")
        zones = r.get("rp_zones") or []
        for i, z in enumerate(zones):
            parts.append(f"[{i}] {z}")
        print("  " + "  ".join(parts) if parts else "  (empty)")
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---- configure rpz_order set ----


@command(
    "configure rpz_order set rpz_list <name>",
    help="Re-order RPZ list for a view (comma-separated zone_rp refs).",
)
async def cli_set_rpz_order(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    # Accepts: configure rpz_order set rpz_list=<ref1,ref2,...> [view=<name>]
    m = re.search(r"\brpz_list[= ](\S+)", line)
    if not m:
        print("  Error: rpz_list=<ref,...> required")
        return
    rpz_list = [r for r in m.group(1).split(",") if r]
    view = _parse_kv(line, "view")
    # Find existing orderedresponsepolicyzones object to PUT
    params: dict = {}
    if view:
        params["view"] = view
    results = [as_dict(r) async for r in ctx.client.dns.orderedresponsepolicyzones.list(**params)]
    if not results:
        print("  No ordered RPZ configuration found")
        return
    await ctx.client.dns.orderedresponsepolicyzones.update(
        results[0]["_ref"], {"rp_zones": rpz_list}
    )


# ---- show record all ----


@command(
    "show record all",
    words="<cr> <name>|zone=<name>",
    help="Show all DNS records (aggregate view).",
)
@command(
    "show record all <name>", words="<cr> zone=<name>", help="Show all DNS records matching a name."
)
async def cli_show_allrecords(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    name = None
    # tokens: ['show', 'record', 'all', <name?>]
    if len(tokens) >= 4 and tokens[3] not in ("<cr>",) and "=" not in tokens[3]:
        name = tokens[3]
    zone = _parse_kv(line, "zone")
    if not zone:
        print("  Error: zone required (usage: show record all [<name>] zone=<zone>)")
        return
    params: dict = {"zone": zone}
    if name:
        params["name"] = name
    results = [as_dict(r) async for r in ctx.client.dns.allrecords.list(**params)]
    if not results:
        if name:
            print(f"  No records found: {name}")
        return
    for r in results:
        parts = []
        if r.get("type"):
            parts.append(f"type={r['type']}")
        if r.get("name"):
            parts.append(f"name={r['name']}")
        if r.get("zone"):
            parts.append(f"zone={r['zone']}")
        if r.get("view"):
            parts.append(f"view={r['view']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
