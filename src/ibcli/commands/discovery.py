# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Discovery command handlers - Phase 16.

Exposes the full NIOS Discovery domain via ctx.client.discovery.*

SDK / WAPI surface notes
------------------------
- discovery          GET+PUT only (no POST/DELETE) - grid-level object, show only
- discovery_device   GET only (inventory) - show only
- discovery_deviceinterface   GET only - show only
- discovery_devicecomponent   GET only - show only
- discovery_deviceneighbor    GET only - show only
- discovery_devicesupportbundle  GET+DELETE - show only (no start in ibcli)
- discovery_sdnnetwork        GET only - show only
- discovery_vrf               GET only - show only
- discovery_credentialgroup   full CRUD (GET/POST/PUT/DELETE)
- discovery_gridproperties    GET+PUT - show + set
- discovery_memberproperties  GET+PUT - show + set
- discovery_status            GET only - show only
- discovery_diagnostictask    GET+POST (create starts task) - configure start + show
- vdiscoverytask              full CRUD + vdiscovery_control function (start)

Command vocabulary summary
--------------------------
# Device inventory (all read-only)
show discovery device [<name>]
show discovery device <name> interface
show discovery device <name> component
show discovery device <name> neighbor
show discovery device <name> support_bundle

# SDN networks / VRFs (read-only)
show discovery sdn_network [<name>]
show discovery vrf [<name>]

# Credential groups (full CRUD)
configure discovery credential_group add <name> [comment=<text>]
configure discovery credential_group <name> delete
configure discovery credential_group <name> set <key>=<value>
show discovery credential_group [<name>]

# Grid discovery properties (GET+PUT)
show discovery grid_properties
configure discovery grid_properties set <key>=<value>

# Member discovery properties (GET+PUT)
show discovery member_properties [<member>]
configure discovery member_properties <member> set <key>=<value>

# Status (read-only)
show discovery status [<member>]

# Diagnostic task (POST to start, GET to read)
configure discovery diagnostic start [member=<str>]
show discovery diagnostic

# vdiscovery task (cloud/VM discovery - full CRUD + start)
configure vdiscovery task add <name> [service=<str>] [credentials=<str>] [comment=<text>]
configure vdiscovery task <name> delete
configure vdiscovery task <name> start
show vdiscovery task [<name>]
"""

from __future__ import annotations

import re

from ibcli.coerce import coerce as _coerce  # noqa: F401
from ibcli.completions_keys import keys_completer_for_path
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict

_DISC_CREDGROUP_KEYS = keys_completer_for_path("discovery", "credentialgroup")
_DISC_GRIDPROPS_KEYS = keys_completer_for_path("discovery", "gridproperties")
_DISC_MEMBERPROPS_KEYS = keys_completer_for_path("discovery", "memberproperties")

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _kv(line: str, key: str) -> str | None:
    """Extract value for *key* from 'key value' or 'key=value' forms."""
    m = re.search(rf"\b{re.escape(key)}[= ](\S+)", line)
    return m.group(1) if m else None


def _comment(line: str) -> str | None:
    """Extract a quoted or unquoted comment value."""
    m = re.search(r'\bcomment[= ]"([^"]+)"', line)
    if m:
        return m.group(1)
    m = re.search(r"\bcomment[= ](\S+)", line)
    return m.group(1) if m else None


def _parse_inline_kvs(line: str, marker: str) -> dict:
    """Parse key/value pairs appearing after *marker* in *line*."""
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
                result[k] = _coerce(v)
            i += 1
        elif i + 1 < len(tokens):
            k, v = tok, tokens[i + 1]
            result[k] = _coerce(v)
            i += 2
        else:
            i += 1
    return result


def _not_connected() -> None:
    print("  Not connected")


def _print_records(records: list, prefix: str) -> None:
    """Print a list of record dicts with a type= prefix."""
    for rec in records:
        parts = [f"type={prefix}"]
        for k, v in rec.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# ===========================================================================
# Chunk A: Device inventory (device + interface + component + neighbor +
#          support_bundle) - all read-only
# ===========================================================================

register("configure", words="discovery", help="Create, modify or delete grid objects.")
register("show", words="discovery", help="Read grid state without modifying anything.")
register(
    "show discovery",
    words="device sdn_network vrf credential_group grid_properties member_properties status diagnostic",
    help="Discovery (NetMRI-lite) state, devices, and properties.",
)
register(
    "configure discovery",
    words="grid_properties member_properties",
    help="Network-discovery (NetMRI-lite) credentials, devices, SDN.",
)

# ---------------------------------------------------------------------------
# A1: Device (show)
# ---------------------------------------------------------------------------

register("show discovery device", words="<cr> <name>")
register("show discovery device <name>", words="<cr> interface component neighbor support_bundle")
register("show discovery device <name> interface", words="<cr>")
register("show discovery device <name> component", words="<cr>")
register("show discovery device <name> neighbor", words="<cr>")
register("show discovery device <name> support_bundle", words="<cr>")


@command("show discovery device", words="<cr> <name>", help="Show discovered devices.")
@command(
    "show discovery device <name>",
    words="<cr> interface component neighbor support_bundle",
    help="Show a specific discovered device.",
)
async def cli_discovery_device_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show discovery device [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.discovery.device.list(**params)]
    if not records:
        if name:
            print(f"  No device found: {name}")
        return
    _print_records(records, "discovery:device")


@command(
    "show discovery device <name> interface",
    words="<cr>",
    help="Show interfaces for a discovered device.",
)
async def cli_discovery_device_interface_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdiscovery device (\S+) interface", line)
    if not m:
        print("  Error: device name required")
        return
    device = m.group(1)
    records = [as_dict(r) async for r in ctx.client.discovery.deviceinterface.list(device=device)]
    if not records:
        print(f"  No interfaces found for device: {device}")
        return
    _print_records(records, "discovery:deviceinterface")


@command(
    "show discovery device <name> component",
    words="<cr>",
    help="Show components for a discovered device.",
)
async def cli_discovery_device_component_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdiscovery device (\S+) component", line)
    if not m:
        print("  Error: device name required")
        return
    device = m.group(1)
    records = [as_dict(r) async for r in ctx.client.discovery.devicecomponent.list(device=device)]
    if not records:
        print(f"  No components found for device: {device}")
        return
    _print_records(records, "discovery:devicecomponent")


@command(
    "show discovery device <name> neighbor",
    words="<cr>",
    help="Show neighbors for a discovered device.",
)
async def cli_discovery_device_neighbor_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdiscovery device (\S+) neighbor", line)
    if not m:
        print("  Error: device name required")
        return
    device = m.group(1)
    records = [as_dict(r) async for r in ctx.client.discovery.deviceneighbor.list(device=device)]
    if not records:
        print(f"  No neighbors found for device: {device}")
        return
    _print_records(records, "discovery:deviceneighbor")


@command(
    "show discovery device <name> support_bundle",
    words="<cr>",
    help="Show support bundles for a discovered device.",
)
async def cli_discovery_device_support_bundle_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdiscovery device (\S+) support_bundle", line)
    if not m:
        print("  Error: device name required")
        return
    device = m.group(1)
    records = [as_dict(r) async for r in ctx.client.discovery.devicesupportbundle.list(name=device)]
    if not records:
        print(f"  No support bundles found for device: {device}")
        return
    _print_records(records, "discovery:devicesupportbundle")


# ===========================================================================
# Chunk B: SDN network + VRF + credential_group
# ===========================================================================

# ---------------------------------------------------------------------------
# B1: SDN network (read-only)
# ---------------------------------------------------------------------------

register("show discovery sdn_network", words="<cr> <name>")
register("show discovery sdn_network <name>", words="<cr>")


@command("show discovery sdn_network", words="<cr> <name>", help="Show SDN networks.")
@command("show discovery sdn_network <name>", words="<cr>", help="Show a specific SDN network.")
async def cli_discovery_sdn_network_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show discovery sdn_network [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.discovery.sdnnetwork.list(**params)]
    if not records:
        if name:
            print(f"  No SDN network found: {name}")
        return
    _print_records(records, "discovery:sdnnetwork")


# ---------------------------------------------------------------------------
# B2: VRF (read-only)
# ---------------------------------------------------------------------------

register("show discovery vrf", words="<cr> <name>")
register("show discovery vrf <name>", words="<cr>")


@command("show discovery vrf", words="<cr> <name>", help="Show discovery VRFs.")
@command("show discovery vrf <name>", words="<cr>", help="Show a specific discovery VRF.")
async def cli_discovery_vrf_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show discovery vrf [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.discovery.vrf.list(**params)]
    if not records:
        if name:
            print(f"  No VRF found: {name}")
        return
    _print_records(records, "discovery:vrf")


# ---------------------------------------------------------------------------
# B3: Credential group (full CRUD)
# ---------------------------------------------------------------------------

register(
    "configure discovery",
    words="credential_group",
    help="Network-discovery (NetMRI-lite) credentials, devices, SDN.",
)
register(
    "configure discovery credential_group",
    words="add <name>",
    help="Discovery credential groups (SSH/SNMP bundles).",
)
register("configure discovery credential_group add", words="<name>")
register("configure discovery credential_group add <name>", words="<cr> comment=<comment>")


@command(
    "configure discovery credential_group add <name>",
    words="<cr> comment=<comment>",
    help="Add a discovery credential group.",
)
async def cli_discovery_credentialgroup_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bcredential_group add (\S+)", line)
    if not m:
        print("  Error: credential group name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.discovery.credentialgroup.create(body)


register("configure discovery credential_group <name>", words="delete set")
register("configure discovery credential_group <name> delete", words="<cr>")


@command(
    "configure discovery credential_group <name> delete",
    words="<cr>",
    help="Delete a discovery credential group.",
)
async def cli_discovery_credentialgroup_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bcredential_group (\S+) delete", line)
    if not m:
        print("  Error: credential group name required")
        return
    name = m.group(1)
    results = [
        as_dict(r)
        async for r in ctx.client.discovery.credentialgroup.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No credential group found: {name}")
        return
    await ctx.client.discovery.credentialgroup.delete(results[0]["_ref"])


register(
    "configure discovery credential_group <name> set",
    words="<key>=<value>",
    dynamic=_DISC_CREDGROUP_KEYS,
)


@command(
    "configure discovery credential_group <name> set",
    words="<key>=<value>",
    help="Set fields on a discovery credential group.",
)
async def cli_discovery_credentialgroup_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bcredential_group (\S+) set\b", line)
    if not m:
        print("  Error: credential group name required")
        return
    name = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [
        as_dict(r)
        async for r in ctx.client.discovery.credentialgroup.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No credential group found: {name}")
        return
    await ctx.client.discovery.credentialgroup.update(results[0]["_ref"], body)


register("show discovery credential_group", words="<cr> <name>")
register("show discovery credential_group <name>", words="<cr>")


@command("show discovery credential_group", words="<cr> <name>", help="Show credential groups.")
@command(
    "show discovery credential_group <name>", words="<cr>", help="Show a specific credential group."
)
async def cli_discovery_credentialgroup_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show discovery credential_group [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.discovery.credentialgroup.list(**params)]
    if not records:
        if name:
            print(f"  No credential group found: {name}")
        return
    _print_records(records, "discovery:credentialgroup")


# ===========================================================================
# Chunk C: Grid + member discovery properties + status
# ===========================================================================

# ---------------------------------------------------------------------------
# C1: Grid properties (GET+PUT - singleton-ish)
# ---------------------------------------------------------------------------

register("show discovery grid_properties", words="<cr>")
register("configure discovery grid_properties", words="set")
register(
    "configure discovery grid_properties set", words="<key>=<value>", dynamic=_DISC_GRIDPROPS_KEYS
)


@command(
    "show discovery grid_properties", words="<cr>", help="Show grid-level discovery properties."
)
async def cli_discovery_gridproperties_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    records = [as_dict(r) async for r in ctx.client.discovery.gridproperties.list()]
    if not records:
        return
    _print_records(records, "discovery:gridproperties")


@command(
    "configure discovery grid_properties set",
    words="<key>=<value>",
    help="Set fields on grid-level discovery properties.",
)
async def cli_discovery_gridproperties_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [as_dict(r) async for r in ctx.client.discovery.gridproperties.list(max_results=1)]
    if not results:
        print("  No grid properties found")
        return
    await ctx.client.discovery.gridproperties.update(results[0]["_ref"], body)


# ---------------------------------------------------------------------------
# C2: Member properties (GET+PUT - per-member)
# ---------------------------------------------------------------------------

register("show discovery member_properties", words="<cr> <name>")
register("show discovery member_properties <name>", words="<cr>")
register("configure discovery member_properties", words="<name>")
register("configure discovery member_properties <name>", words="set")
register(
    "configure discovery member_properties <name> set",
    words="<key>=<value>",
    dynamic=_DISC_MEMBERPROPS_KEYS,
)


@command(
    "show discovery member_properties",
    words="<cr> <name>",
    help="Show member discovery properties.",
)
@command(
    "show discovery member_properties <name>",
    words="<cr>",
    help="Show discovery properties for a specific member.",
)
async def cli_discovery_memberproperties_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show discovery member_properties [<member>]
    member = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            member = candidate
    params: dict = {}
    if member:
        params["discovery_member"] = member
    records = [as_dict(r) async for r in ctx.client.discovery.memberproperties.list(**params)]
    if not records:
        if member:
            print(f"  No member properties found: {member}")
        return
    _print_records(records, "discovery:memberproperties")


@command(
    "configure discovery member_properties <name> set",
    words="<key>=<value>",
    help="Set fields on a member's discovery properties.",
)
async def cli_discovery_memberproperties_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bmember_properties (\S+) set\b", line)
    if not m:
        print("  Error: member name required")
        return
    member = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [
        as_dict(r)
        async for r in ctx.client.discovery.memberproperties.list(
            discovery_member=member, max_results=1
        )
    ]
    if not results:
        print(f"  No member properties found: {member}")
        return
    await ctx.client.discovery.memberproperties.update(results[0]["_ref"], body)


# ---------------------------------------------------------------------------
# C3: Discovery status (read-only)
# ---------------------------------------------------------------------------

register("show discovery status", words="<cr> <name>")
register("show discovery status <name>", words="<cr>")


@command("show discovery status", words="<cr> <name>", help="Show discovery status.")
@command(
    "show discovery status <name>",
    words="<cr>",
    help="Show discovery status for a specific member.",
)
async def cli_discovery_status_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show discovery status [<member>]
    address = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            address = candidate
    params: dict = {}
    if address:
        params["address"] = address
    records = [as_dict(r) async for r in ctx.client.discovery.status.list(**params)]
    if not records:
        if address:
            print(f"  No discovery status found: {address}")
        return
    _print_records(records, "discovery:status")


# ===========================================================================
# Chunk D: Diagnostic task + vdiscovery task
# ===========================================================================

# ---------------------------------------------------------------------------
# D1: Diagnostic task (POST to start, GET to poll)
# ---------------------------------------------------------------------------

register(
    "configure discovery",
    words="diagnostic",
    help="Network-discovery (NetMRI-lite) credentials, devices, SDN.",
)
register("configure discovery diagnostic", words="start")
register("configure discovery diagnostic start", words="<cr> member=<name>")
register("show discovery diagnostic", words="<cr>")


@command(
    "configure discovery diagnostic start",
    words="<cr> member=<name>",
    help="Start a discovery diagnostic task.",
)
async def cli_discovery_diagnostic_start(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    body: dict = {}
    member = _kv(line, "member")
    if member:
        body["network_view"] = member
    await ctx.client.discovery.diagnostictask.create(body)


@command("show discovery diagnostic", words="<cr>", help="Show discovery diagnostic tasks.")
async def cli_discovery_diagnostic_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    records = [as_dict(r) async for r in ctx.client.discovery.diagnostictask.list()]
    if not records:
        return
    _print_records(records, "discovery:diagnostictask")


# ---------------------------------------------------------------------------
# D2: vdiscovery task (cloud/VM discovery - full CRUD + start)
# ---------------------------------------------------------------------------

register("configure", words="vdiscovery", help="Create, modify or delete grid objects.")
register("show", words="vdiscovery", help="Read grid state without modifying anything.")
register(
    "configure vdiscovery", words="task", help="vDiscovery jobs (cloud-adaptor network discovery)."
)
register("show vdiscovery", words="task")
register("configure vdiscovery task", words="add <name>")
register("configure vdiscovery task add", words="<name>")
register(
    "configure vdiscovery task add <name>",
    words="<cr> service=<name>|credentials=<name>|comment=<comment>",
)


@command(
    "configure vdiscovery task add <name>",
    words="<cr> service=<name>|credentials=<name>|comment=<comment>",
    help="Add a vDiscovery task.",
)
async def cli_vdiscovery_task_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bvdiscovery task add (\S+)", line)
    if not m:
        print("  Error: vDiscovery task name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    service = _kv(line, "service")
    if service:
        body["driver_type"] = service
    credentials = _kv(line, "credentials")
    if credentials:
        body["credentials_type"] = credentials
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.discovery.vdiscoverytask.create(body)


register("configure vdiscovery task <name>", words="delete start")
register("configure vdiscovery task <name> delete", words="<cr>")


@command(
    "configure vdiscovery task <name> delete",
    words="<cr>",
    help="Delete a vDiscovery task.",
)
async def cli_vdiscovery_task_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bvdiscovery task (\S+) delete", line)
    if not m:
        print("  Error: vDiscovery task name required")
        return
    name = m.group(1)
    results = [
        as_dict(r) async for r in ctx.client.discovery.vdiscoverytask.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No vDiscovery task found: {name}")
        return
    await ctx.client.discovery.vdiscoverytask.delete(results[0]["_ref"])


register("configure vdiscovery task <name> start", words="<cr>")


@command(
    "configure vdiscovery task <name> start",
    words="<cr>",
    help="Start a vDiscovery task.",
)
async def cli_vdiscovery_task_start(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bvdiscovery task (\S+) start", line)
    if not m:
        print("  Error: vDiscovery task name required")
        return
    name = m.group(1)
    results = [
        as_dict(r) async for r in ctx.client.discovery.vdiscoverytask.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No vDiscovery task found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.discovery.vdiscoverytask.call_function(
        ref, "vdiscovery_control", action="START"
    )


register("show vdiscovery task", words="<cr> <name>")
register("show vdiscovery task <name>", words="<cr>")


@command("show vdiscovery task", words="<cr> <name>", help="Show vDiscovery tasks.")
@command("show vdiscovery task <name>", words="<cr>", help="Show a specific vDiscovery task.")
async def cli_vdiscovery_task_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show vdiscovery task [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.discovery.vdiscoverytask.list(**params)]
    if not records:
        if name:
            print(f"  No vDiscovery task found: {name}")
        return
    _print_records(records, "vdiscoverytask")
