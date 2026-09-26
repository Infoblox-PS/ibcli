# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Grid management slices 5a, 5b, 5c.

Command shapes:

  Slice 5a - Members + grid-level DNS/DHCP:
    configure grid <grid_name> member add <fqdn>
        [ipaddress <ip/cidr>] [gateway <gw>] [comment <text>]
        [platform <platform>] [hwtype <hwtype>] [model <hwmodel>] [serial <serial>]
        [license <name> ...] [node <hwtype>,<hwmodel>,<serial> ...]
    configure grid <grid_name> member <name> delete
    configure grid <grid_name> member <name> modify
        [ipaddress <ip/cidr>] [gateway <gw>] [comment <text>] [name <newname>]
    configure grid <grid_name> member <name> dns [enable|disable]
    configure grid <grid_name> member <name> dhcp [enable|disable]
    configure grid <grid_name> member <name> preprovision
        [platform <platform>] [hwtype <hwtype>] [model <hwmodel>] [serial <serial>]
        [license <name> ...] [node <hwtype>,<hwmodel>,<serial> ...]
    show grid <name> member [<name>]
    show grid <name> member <name> dns
    show grid <name> dns
    show grid <name> dhcp

  Slice 5b - NSGroups, Views, Shared Record Groups:
    configure nsgroup add <name> [primary <fqdn>] [secondary <fqdn> ...]
    configure nsgroup <name> delete
    show zone ns_group [<name>]
    configure view add <name> [comment <text>]
    configure view <name> delete
    configure shared_record_group add <name> [comment <text>]
    configure shared_record_group <name> delete
    show zone shared_record_group [<name>]

  Slice 5c - Service restart + scheduled tasks:
    restart dns [delay <num>]
    restart dhcp [delay <num>]
    restart discovery  [STUB]
    show schedule
    configure schedule <id> delete
"""

from __future__ import annotations

import ipaddress
import re

from ibcli import completions as _completions
from ibcli.coerce import coerce as _coerce_value  # noqa: F401
from ibcli.completions_keys import (
    keys_completer_for_path,
    lazy_keys_completer,
)
from ibcli.completions_keys import (
    list_settable_keys as _list_settable_keys,
)
from ibcli.completions_keys import (
    print_keys as _print_keys,
)
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict, format_extra_field, parse_extra_fields

_MEMBER_DNS_KEYS = keys_completer_for_path("grid", "member_dns")
_MEMBER_DHCP_KEYS = keys_completer_for_path("grid", "member_dhcpproperties")
_MEMBER_TI_KEYS = keys_completer_for_path("grid", "member_threatinsight")
_MEMBER_TP_KEYS = keys_completer_for_path("grid", "member_threatprotection")
_MEMBER_FD_KEYS = keys_completer_for_path("grid", "member_filedistribution")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_kv(line: str, key: str) -> str | None:
    """Extract value for key from 'key value' or 'key=value' form."""
    m = re.search(rf"\b{re.escape(key)}[= ](\S+)", line)
    return m.group(1) if m else None


def _parse_kv_all(line: str, key: str) -> list[str]:
    """Extract all values for a repeated key."""
    return re.findall(rf"\b{re.escape(key)}\s+(\S+)", line)


def _parse_int_kv(line: str, key: str) -> int | None:
    """Extract an integer-valued key. Returns None when absent.

    A non-numeric value raises ValueError, which the dispatcher renders as an
    error line - better than silently dropping a VLAN tag the operator asked
    for.
    """
    raw = _parse_kv(line, key)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be a number, got {raw!r}") from exc


_TRUE = frozenset({"true", "yes", "on", "1", "enabled"})
_FALSE = frozenset({"false", "no", "off", "0", "disabled"})


def _parse_bool_kv(line: str, key: str) -> bool | None:
    """Extract a boolean-valued key. Returns None when absent."""
    raw = _parse_kv(line, key)
    if raw is None:
        return None
    low = raw.lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    raise ValueError(f"{key} must be true or false, got {raw!r}")


def _parse_comment(line: str) -> str | None:
    """Extract comment value, supporting quoted or unquoted forms."""
    m = re.search(r'\bcomment[= ]"([^"]+)"', line)
    if m:
        return m.group(1)
    m = re.search(r"\bcomment[= ](\S+)", line)
    return m.group(1) if m else None


def _cidr_to_mask(cidr: str | int) -> str:
    """Convert a CIDR prefix length to dotted-decimal subnet mask."""
    return str(ipaddress.IPv4Network(f"0.0.0.0/{cidr}").netmask)


def _parse_ipaddress(line: str) -> tuple[str, str] | None:
    """Parse 'ipaddress <ip/cidr>' from line; return (address, subnet_mask) or None."""
    m = re.search(r"\bipaddress\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", line)
    if not m:
        return None
    return m.group(1), _cidr_to_mask(m.group(2))


def _parse_cidr_kv(line: str, key: str) -> tuple[str, str] | None:
    """Parse 'key <ipv4>/<prefix>' or 'key <ipv6>/<prefix>'; return (addr, mask_or_prefix)."""
    m = re.search(rf"\b{re.escape(key)}\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", line)
    if m:
        return m.group(1), _cidr_to_mask(m.group(2))
    m = re.search(rf"\b{re.escape(key)}\s+([0-9a-fA-F:]+)/(\d+)", line)
    if m:
        return m.group(1), m.group(2)  # prefix as-is for ipv6
    return None


def _parse_inline_kvs(line: str, marker: str) -> dict:
    """Parse key/value pairs appearing after *marker* in *line*.

    Handles two forms:
    - Original input form: "key=value key2=value2"  (before tokenizer splits =)
    - Expanded line form:  "key value key2 value2"   (after tokenizer splits = away)

    Returns a dict with coerced values (via _coerce_value).
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
            # Original form: key=value
            k, _, v = tok.partition("=")
            if k and v:
                result[k] = _coerce_value(v)
            i += 1
        elif i + 1 < len(tokens):
            # Expanded form: key value (two separate tokens)
            k, v = tok, tokens[i + 1]
            result[k] = _coerce_value(v)
            i += 2
        else:
            # Lone token with no value - skip
            i += 1
    return result


async def _supported_hw_fields(ctx: Context) -> set[str] | None:
    """Return the hardware_info fields this grid's WAPI actually accepts.

    NIOS versions disagree here: some accept ``hwtype``, ``hwmodel`` and
    ``serial_number``, others only ``hwtype`` and reject the rest outright
    with ``Unknown argument/field: 'hwmodel'`` - which aborts the whole
    pre-provisioning PUT and rolls the new member back.

    The grid tells us which it supports, so ask it once and cache the answer
    for the session. Returns None if the schema can't be read, in which case
    callers should send everything and let NIOS decide.

    Only a successful read is cached. A failed one - no client, a transport
    error, a grid that answers something unparseable - must not be, or one
    unlucky first call would disable the filter for the rest of the session
    and every later member add would go back to sending fields the grid
    rejects.
    """
    if "hw_fields" in ctx.caches:
        return ctx.caches["hw_fields"] or None
    try:
        # A schema read is `GET /member?_schema=1`, which no SDK resource
        # method models - `call_function` would POST. Go through the SDK's
        # HTTP client directly.
        schema = await ctx.client._http.get(
            "/member", params={"_schema": "1", "_schema_version": "2"}
        )
    except Exception:
        return None
    if not isinstance(schema, dict):
        return None
    fields: set[str] = set()
    for f in schema.get("fields", []):
        if f.get("name") != "pre_provisioning":
            continue
        for sf in f.get("schema", {}).get("fields", []):
            if sf.get("name") == "hardware_info":
                fields = {
                    x.get("name") for x in sf.get("schema", {}).get("fields", []) if x.get("name")
                }
    ctx.caches["hw_fields"] = fields
    return fields or None


def _filter_hardware_info(pre_prov: dict | None, supported: set[str] | None) -> list[str]:
    """Drop hardware_info keys the grid doesn't accept. Returns dropped names.

    Mutates *pre_prov* in place. Sending an unsupported key is not a partial
    failure - NIOS rejects the entire request - so dropping it is what lets
    the rest of the pre-provisioning succeed.
    """
    if not pre_prov or not supported:
        return []
    dropped: set[str] = set()
    for entry in pre_prov.get("hardware_info", []):
        for key in [k for k in entry if k not in supported]:
            dropped.add(key)
            del entry[key]
    return sorted(dropped)


def _warn_dropped_hw_fields(dropped: list[str], pre_prov: dict | None) -> None:
    """Report which hardware_info keys were dropped, and what still goes.

    Which keys survive depends on the grid, so name them rather than
    asserting a fixed outcome - dropping only ``serial_number`` still sends
    ``hwmodel``.
    """
    kept = sorted({k for entry in (pre_prov or {}).get("hardware_info", []) for k in entry})
    tail = f"sending {', '.join(kept)}" if kept else "nothing left to send"
    print(f"  Warning: grid does not accept {', '.join(dropped)} in hardware_info; {tail}")


def _build_pre_provisioning(line: str) -> dict | None:
    """Parse pre-provisioning keywords from line and return a dict or None.

    Keywords (top-level `platform` is handled separately in cli_add_member):
      hwtype <X>        - primary node hwtype (NIOS hardware SKU enum)
      model <X>         - primary node hwmodel
      serial <X>        - primary node serial number
      license <X>       - repeatable; each value added to licenses list
      node <t>,<m>,<s>  - repeatable; each adds a hardware_info entry (for HA)
    """
    hwtype = _parse_kv(line, "hwtype")
    model = _parse_kv(line, "model")
    serial = _parse_kv(line, "serial")
    licenses = _parse_kv_all(line, "license")
    nodes = _parse_kv_all(line, "node")

    if not any([hwtype, model, serial, licenses, nodes]):
        return None

    hardware_info: list[dict] = []
    if hwtype or model or serial:
        entry: dict = {}
        if hwtype:
            entry["hwtype"] = hwtype
        if model:
            entry["hwmodel"] = model
        if serial:
            entry["serial_number"] = serial
        hardware_info.append(entry)

    for node_raw in nodes:
        # <hwtype>[,<hwmodel>[,<serial>]] - trailing parts are optional so a
        # grid that only accepts hwtype can be driven with `node=IB-V1425`.
        parts = [x.strip() for x in node_raw.split(",")]
        if not parts or not parts[0]:
            continue  # skip malformed entries
        entry = {"hwtype": parts[0]}
        if len(parts) > 1 and parts[1]:
            entry["hwmodel"] = parts[1]
        if len(parts) > 2 and parts[2]:
            entry["serial_number"] = parts[2]
        hardware_info.append(entry)

    result: dict = {}
    if hardware_info:
        result["hardware_info"] = hardware_info
    if licenses:
        result["licenses"] = licenses
    return result


# ===========================================================================
# Slice 5a - Waypoints
# ===========================================================================

# Extend existing "show grid <name>" node (registered in server.py)
register(
    "show grid <name>",
    words="member dns dhcp threat_insight threat_protection file_distribution license_pool certificate restart",
)
register("show grid <name> member", words="<cr> <name>")
register("show grid <name> member <name>", words="<cr> dns")
register("show grid <name> member <name> dns", words="<cr> fields=<field1,field2,...>")
register("show grid <name> dns", words="<cr> fields=<field1,field2,...>")
register("show grid <name> dhcp", words="<cr> fields=<field1,field2,...>")

# Top-level "show member [<name>]" - shortcut that doesn't require typing
# the grid name (almost every deployment has a single grid).
register("show", words="member", help="Read grid state without modifying anything.")
register(
    "show member",
    words="<cr> <name>",
    help="List grid members (shortcut for 'show grid <g> member').",
)
register("show member <name>", words="<cr> fields=<field1,field2,...>")

# configure grid <name> member ...
register(
    "configure grid",
    words="<name>",
    dynamic=_completions.grid_name,
    help="Grid-level settings, members, schedules, and topology. "
    "Tab auto-fills the connected grid name.",
)
register(
    "configure grid <name>",
    words="member dns dhcp threat_insight threat_protection file_distribution certificate",
)
register("configure grid <name> member", words="add <name>")
register("configure grid <name> member add", words="<name>")
_MEMBER_ADD_WORDS = (
    "<cr> ipaddress=<cidr>|gateway=<ip>|comment=<comment>|"
    "platform=<name>|hwtype=<name>|model=<name>|serial=<name>|"
    "license=<name>|node=<name>|"
    "ipv6addr=<value>|ipv6gateway=<value>|"
    "mgmt_ipaddress=<cidr>|mgmt_gateway=<ip>|"
    "mgmt_ipv6addr=<value>|mgmt_ipv6gateway=<value>|"
    # VLAN tagging on the VIP / MGMT interfaces.
    "vlan_id=<num>|mgmt_vlan_id=<num>|"
    # HA pair: VRRP router id plus one
    # ha_node=<lan1_ip>,<ha_ip>[,<mgmt_ip>] per node.
    "ha=<value>|router_id=<num>|ha_node=<value>|master_candidate=<value>|"
    # LAN2 port.
    "lan2_ipaddress=<cidr>|lan2_gateway=<ip>|lan2_vlan_id=<num>|"
    "lan2_router_id=<num>|"
    # Port redundancy (LAN1/LAN2 failover), configured on the LAN2 port.
    # `nic_failover` is kept as an alias for the WAPI field name.
    "port_redundancy=<value>|port_redundancy_primary=<value>|"
    "nic_failover=<value>|nic_failover_primary=<value>|"
    "default_route_failover=<value>"
)
register("configure grid <name> member add <name>", words=_MEMBER_ADD_WORDS)
register("configure grid <name> member <name>", words="delete modify dns dhcp preprovision anycast")
register("configure grid <name> member <name> anycast", words="add delete")
register("configure grid <name> member <name> anycast add", words="<value>")
register("configure grid <name> member <name> anycast add <value>", words="<cr>")
register("configure grid <name> member <name> anycast delete", words="<value>")
register("configure grid <name> member <name> anycast delete <value>", words="<cr>")

_PREPROVISION_OPTS = (
    "<cr> platform=<name>|hwtype=<name>|model=<name>|serial=<name>|license=<name>|node=<name>"
)
register("configure grid <name> member <name> preprovision", words=_PREPROVISION_OPTS)
register("configure grid <name> member <name> delete", words="<cr>")
register(
    "configure grid <name> member <name> modify",
    words="<cr> ipaddress=<cidr>|gateway=<ip>|comment=<comment>|name=<name>",
)
register("configure grid <name> member <name> dns", words="<cr> enable disable set")
register("configure grid <name> member <name> dns enable", words="<cr>")
register("configure grid <name> member <name> dns disable", words="<cr>")
register(
    "configure grid <name> member <name> dns set", words="<key>=<value>", dynamic=_MEMBER_DNS_KEYS
)
register("configure grid <name> member <name> dhcp", words="<cr> enable disable set")
register("configure grid <name> member <name> dhcp enable", words="<cr> ipv4 ipv6 both")
register("configure grid <name> member <name> dhcp enable ipv4", words="<cr>")
register("configure grid <name> member <name> dhcp enable ipv6", words="<cr>")
register("configure grid <name> member <name> dhcp enable both", words="<cr>")
register("configure grid <name> member <name> dhcp disable", words="<cr> ipv4 ipv6 both")
register("configure grid <name> member <name> dhcp disable ipv4", words="<cr>")
register("configure grid <name> member <name> dhcp disable ipv6", words="<cr>")
register("configure grid <name> member <name> dhcp disable both", words="<cr>")
register(
    "configure grid <name> member <name> dhcp set", words="<key>=<value>", dynamic=_MEMBER_DHCP_KEYS
)
# member license
register("configure grid <name> member <name>", words="delete modify dns dhcp preprovision license")
register("configure grid <name> member <name> license", words="add remove")
register("configure grid <name> member <name> license add", words="<license_type>")
register("configure grid <name> member <name> license remove", words="<license_type>")
# member threat-insight, threat-protection, file-distribution
register(
    "show grid <name> member <name>",
    words="<cr> dns license threat_insight threat_protection file_distribution",
)
register("show grid <name> member <name> license", words="<cr> fields=<field1,field2,...>")
register("show grid <name> member <name> threat_insight", words="<cr> fields=<field1,field2,...>")
register(
    "show grid <name> member <name> threat_protection", words="<cr> fields=<field1,field2,...>"
)
register(
    "show grid <name> member <name> file_distribution", words="<cr> fields=<field1,field2,...>"
)
register(
    "configure grid <name> member <name>",
    words="threat_insight threat_protection file_distribution",
)
register("configure grid <name> member <name> threat_insight", words="set")
register(
    "configure grid <name> member <name> threat_insight set",
    words="<key>=<value>",
    dynamic=_MEMBER_TI_KEYS,
)
register("configure grid <name> member <name> threat_protection", words="set")
register(
    "configure grid <name> member <name> threat_protection set",
    words="<key>=<value>",
    dynamic=_MEMBER_TP_KEYS,
)
register("configure grid <name> member <name> file_distribution", words="set")
register(
    "configure grid <name> member <name> file_distribution set",
    words="<key>=<value>",
    dynamic=_MEMBER_FD_KEYS,
)
# Grid-level extensions (Chunk C)
register("show grid <name> dns", words="<cr> keys")
register("show grid <name> dns keys", words="<cr>")
register("show grid <name> dhcp", words="<cr> keys")
register("show grid <name> dhcp keys", words="<cr>")
register("show grid <name> threat_insight", words="<cr> keys")
register("show grid <name> threat_insight keys", words="<cr>")
register("show grid <name> threat_protection", words="<cr> keys")
register("show grid <name> threat_protection keys", words="<cr>")
register("show grid <name> file_distribution", words="<cr> keys")
register("show grid <name> file_distribution keys", words="<cr>")
register("configure grid <name> dns", words="set allow_recursion")
register("configure grid <name> dns set", words="<key>=<value>")
register(
    "configure grid <name> dns allow_recursion",
    words="<cr> any|acl=<name>|ace=<cidr>|deny_ace=<cidr>",
)
register("configure grid <name> dhcp", words="set")
register("configure grid <name> dhcp set", words="<key>=<value>")
register("configure grid <name> threat_insight", words="set")
register("configure grid <name> threat_insight set", words="<key>=<value>")
register("configure grid <name> threat_protection", words="set")
register("configure grid <name> threat_protection set", words="<key>=<value>")
register("configure grid <name> file_distribution", words="set")
register("configure grid <name> file_distribution set", words="<key>=<value>")
# Grid license pool + x509 cert + service-restart (Chunk D)
register("show grid <name> license_pool", words="<cr>")
register("show grid <name> certificate", words="<cr>")
register("configure grid <name> certificate", words="delete")
register("configure grid <name> certificate delete", words="<serial>")
register("show grid <name> restart", words="status group request")
register("show grid <name> restart status", words="<cr>")
register("show grid <name> restart group", words="<cr>")
register("show grid <name> restart request", words="<cr>")


# ===========================================================================
# Slice 5a - Handlers
# ===========================================================================

# ---------------------------------------------------------------------------
# configure grid <name> member add <fqdn>
# ---------------------------------------------------------------------------


@command(
    "configure grid <name> member add <name>",
    words=_MEMBER_ADD_WORDS,
    help=(
        "Add a grid member. Supports IPv4 VIP (ipaddress/gateway), IPv6 "
        "VIP (ipv6addr=<addr/prefix>/ipv6gateway), MGMT v4 "
        "(mgmt_ipaddress/mgmt_gateway), and MGMT v6 "
        "(mgmt_ipv6addr/mgmt_ipv6gateway). Note: IPv6 VIP won't persist on "
        "a member that hasn't actually booted yet - NIOS applies it once "
        "the member comes online."
    ),
)
async def cli_add_member(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmember add\s+(\S+)", line)
    if not m:
        print("  Error: member FQDN required")
        return
    fqdn = m.group(1)

    addr_info = _parse_ipaddress(line)
    gateway = _parse_kv(line, "gateway")
    comment = _parse_comment(line)
    platform = _parse_kv(line, "platform")
    pre_prov = _build_pre_provisioning(line)
    dropped = _filter_hardware_info(pre_prov, await _supported_hw_fields(ctx))
    if dropped:
        _warn_dropped_hw_fields(dropped, pre_prov)

    # IPv6 VIP + MGMT (v4 and v6). Each key= value pair is optional; when
    # any are present we include the corresponding struct in the create body.
    v6 = _parse_cidr_kv(line, "ipv6addr")
    v6gw = _parse_kv(line, "ipv6gateway")
    mgmt4 = _parse_cidr_kv(line, "mgmt_ipaddress")
    mgmt4gw = _parse_kv(line, "mgmt_gateway")
    mgmt6 = _parse_cidr_kv(line, "mgmt_ipv6addr")
    mgmt6gw = _parse_kv(line, "mgmt_ipv6gateway")

    # VLAN tags (802.1Q) on the VIP and MGMT interfaces.
    vlan_id = _parse_int_kv(line, "vlan_id")
    mgmt_vlan_id = _parse_int_kv(line, "mgmt_vlan_id")

    # HA pair. `ha_node` is repeatable - one per physical node, each giving
    # that node's LAN1 address and its HA-port address as `<lan1>,<ha>`.
    # NIOS needs both: "Send HA and Grid communication requires valid LAN1
    # IPv4 addresses." `router_id` is the VRRP VRID the pair shares, which
    # NIOS requires whenever enable_ha is true.
    ha_flag = _parse_bool_kv(line, "ha")
    router_id = _parse_int_kv(line, "router_id")
    ha_nodes_raw = _parse_kv_all(line, "ha_node")
    master_candidate = _parse_bool_kv(line, "master_candidate")

    # LAN2 port, with its own VLAN tag and VRRP id.
    lan2 = _parse_cidr_kv(line, "lan2_ipaddress")
    lan2gw = _parse_kv(line, "lan2_gateway")
    lan2_vlan_id = _parse_int_kv(line, "lan2_vlan_id")
    lan2_router_id = _parse_int_kv(line, "lan2_router_id")

    # Port redundancy - what the NIOS UI calls LAN1/LAN2 failover, and what
    # WAPI spells `nic_failover_*` on the LAN2 port. Accept both spellings;
    # these turn the LAN2 port on even with no LAN2 address, because the
    # redundant port is a standby for LAN1 and carries no IP of its own.
    nic_failover = _parse_bool_kv(line, "port_redundancy")
    if nic_failover is None:
        nic_failover = _parse_bool_kv(line, "nic_failover")
    nic_failover_primary = _parse_bool_kv(line, "port_redundancy_primary")
    if nic_failover_primary is None:
        nic_failover_primary = _parse_bool_kv(line, "nic_failover_primary")
    default_route_failover = _parse_bool_kv(line, "default_route_failover")
    want_lan2 = bool(
        lan2
        or nic_failover is not None
        or nic_failover_primary is not None
        or default_route_failover is not None
    )
    # NIOS rejects this pair outright ("Cannot enable default route redundancy
    # and NIC failover together"). Catch it before the round trip.
    if nic_failover and default_route_failover:
        print(
            "  Error: port_redundancy and default_route_failover are "
            "mutually exclusive - NIOS allows only one"
        )
        return
    # With NIC failover on, LAN2 is a standby for LAN1 and carries no address
    # of its own. NIOS accepts the request and drops network_setting silently,
    # so say so rather than letting it look like it applied.
    if nic_failover and lan2:
        print(
            "  Warning: port redundancy makes LAN2 a standby interface; "
            "NIOS will ignore lan2_ipaddress"
        )

    want_ha = bool(ha_flag or router_id is not None or ha_nodes_raw)
    ha_nodes: list[tuple[str, str, str | None]] = []
    if want_ha:
        if router_id is None:
            print("  Error: HA needs router_id=<1-255> (the VRRP virtual router id)")
            return
        if not 1 <= router_id <= 255:
            print(f"  Error: router_id must be 1-255, got {router_id}")
            return
        if _parse_cidr_kv(line, "mgmt_ipaddress") and not any(
            len(r.split(",")) == 3 for r in ha_nodes_raw
        ):
            print(
                "  Warning: HA member with MGMT but no per-node MGMT address; "
                "add a third field to each ha_node=<lan1>,<ha>,<mgmt>"
            )
        if len(ha_nodes_raw) != 2:
            print(
                "  Error: HA needs exactly two ha_node=<lan1_ip>,<ha_ip> values"
                f" (one per node), got {len(ha_nodes_raw)}"
            )
            return
        for raw in ha_nodes_raw:
            parts = [x.strip() for x in raw.split(",")]
            if len(parts) not in (2, 3) or not all(parts[:2]):
                print(f"  Error: ha_node must be <lan1_ip>,<ha_ip>[,<mgmt_ip>] - got {raw!r}")
                return
            ha_nodes.append((parts[0], parts[1], parts[2] if len(parts) == 3 else None))

    # Warn if ipaddress is set but no gateway - the member will boot with no
    # default route and won't be able to phone the grid master to get joined.
    if addr_info and not gateway:
        print(f"  Warning: no gateway specified; {fqdn} will have no default route")

    # Step 1: POST - basic fields only.
    create_body: dict = {"host_name": fqdn}
    if addr_info or gateway:
        vip: dict = {}
        if addr_info:
            vip["address"] = addr_info[0]
            vip["subnet_mask"] = addr_info[1]
        if gateway:
            vip["gateway"] = gateway
        if vlan_id is not None:
            vip["vlan_id"] = vlan_id
        create_body["vip_setting"] = vip
    if v6:
        ipv6: dict = {"enabled": True, "virtual_ip": v6[0], "cidr_prefix": int(v6[1])}
        if v6gw:
            ipv6["gateway"] = v6gw
        create_body["ipv6_setting"] = ipv6
        # NIOS silently drops ipv6_setting unless the member is flagged
        # dual-stack. "BOTH" for v4+v6, "IPV6" for v6-only.
        create_body["config_addr_type"] = "BOTH" if addr_info else "IPV6"
    if mgmt4 or mgmt6 or want_ha:
        if mgmt4 or mgmt6:
            create_body["mgmt_port_setting"] = {
                "enabled": True,
                "security_access_enabled": True,
            }
        node_info: dict = {}
        if mgmt4:
            mgmt_net: dict = {
                "address": mgmt4[0],
                "subnet_mask": mgmt4[1],
            }
            if mgmt4gw:
                mgmt_net["gateway"] = mgmt4gw
            if mgmt_vlan_id is not None:
                mgmt_net["vlan_id"] = mgmt_vlan_id
            node_info["mgmt_network_setting"] = mgmt_net
        if mgmt6:
            v6_mgmt: dict = {
                "enabled": True,
                "virtual_ip": mgmt6[0],
                "cidr_prefix": int(mgmt6[1]),
            }
            if mgmt6gw:
                v6_mgmt["gateway"] = mgmt6gw
            node_info["v6_mgmt_network_setting"] = v6_mgmt
        if want_ha:
            # One node_info per physical node, each carrying that node's LAN1
            # address (mgmt_lan) and HA-port address. NIOS pairs them by
            # position: first entry is node 1, second is node 2.
            #
            # MGMT must differ per node - sharing one address fails with "The
            # node 2 address <ip> is already in use by node 1" - so each
            # node's MGMT address comes from its own ha_node entry, while the
            # mask and gateway come from mgmt_ipaddress/mgmt_gateway.
            ha_node_info = []
            for lan1, ha_ip, node_mgmt in ha_nodes:
                entry = {k: v for k, v in node_info.items() if k != "mgmt_network_setting"}
                entry["lan_ha_port_setting"] = {
                    "mgmt_lan": lan1,
                    "ha_ip_address": ha_ip,
                }
                if node_mgmt and mgmt4:
                    per_node = {"address": node_mgmt, "subnet_mask": mgmt4[1]}
                    if mgmt4gw:
                        per_node["gateway"] = mgmt4gw
                    if mgmt_vlan_id is not None:
                        per_node["vlan_id"] = mgmt_vlan_id
                    entry["mgmt_network_setting"] = per_node
                ha_node_info.append(entry)
            create_body["node_info"] = ha_node_info
            create_body["enable_ha"] = True
            create_body["router_id"] = router_id
        else:
            create_body["node_info"] = [node_info]
    if want_lan2:
        lan2_setting: dict = {"enabled": True}
        if lan2:
            lan2_net: dict = {"address": lan2[0], "subnet_mask": lan2[1]}
            if lan2gw:
                lan2_net["gateway"] = lan2gw
            if lan2_vlan_id is not None:
                lan2_net["vlan_id"] = lan2_vlan_id
            lan2_setting["network_setting"] = lan2_net
        if lan2_router_id is not None:
            lan2_setting["virtual_router_id"] = lan2_router_id
        if nic_failover is not None:
            lan2_setting["nic_failover_enabled"] = nic_failover
        if nic_failover_primary is not None:
            lan2_setting["nic_failover_enable_primary"] = nic_failover_primary
        if default_route_failover is not None:
            lan2_setting["default_route_failover_enabled"] = default_route_failover
        create_body["lan2_port_setting"] = lan2_setting
    if master_candidate is not None:
        create_body["master_candidate"] = master_candidate
    if comment:
        create_body["comment"] = comment

    result = as_dict(await ctx.client.grid.member.create(create_body))
    ref = result.get("_ref", "") if isinstance(result, dict) else ""
    print(f"  Added member {fqdn}")

    if not ref:
        print("  Error: server returned no ref for new member; cannot pre-provision")
        print(f"  Member {fqdn} was created but is unprovisioned. Configure via:")
        print(f"  configure grid <grid> member {fqdn} preprovision ...")
        return

    # Step 2: PUT - pre-provisioning and platform (if any).
    if pre_prov is None and not platform:
        return

    put_body: dict = {}
    if pre_prov is not None:
        put_body["pre_provisioning"] = pre_prov
        if len(pre_prov.get("hardware_info", [])) >= 2:
            put_body["enable_ha"] = True
    if platform:
        put_body["platform"] = platform  # verbatim, no uppercasing

    try:
        await ctx.client.grid.member.update(ref, put_body)
    except Exception as e:
        # Rollback: delete the member we just created.
        msg = str(e)
        print(f"  Pre-provisioning failed: {msg}")
        try:
            await ctx.client.grid.member.delete(ref)
            print(f"  Rolled back: deleted {fqdn}")
        except Exception as del_err:
            print(f"  WARNING: rollback also failed - member {fqdn} exists in the grid")
            print(f"  Delete manually: configure grid <grid> member {fqdn} delete")
            print(f"  Delete error: {del_err}")
        return
    print(f"  Pre-provisioned {fqdn}")


# ---------------------------------------------------------------------------
# configure grid <name> member <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure grid <name> member <name> delete",
    words="<cr>",
    help="Delete a grid member.",
)
async def cli_del_member(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmember\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: member name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.grid.member.list(host_name=name)]
    if not results:
        print(f"  No member found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.member.delete(ref)


# ---------------------------------------------------------------------------
# configure grid <name> member <name> modify
# ---------------------------------------------------------------------------


def _parse_anycast_target(line: str, verb: str) -> tuple[str, int, bool] | None:
    """Extract the anycast add|delete target as (address, prefix, is_ipv6).

    Accepts bare `192.0.2.53`, `192.0.2.53/32`, `2001:db8::53`, `2001:db8::53/128`.
    Defaults to /32 for IPv4 and /128 for IPv6 when no prefix is given.
    """
    tail_pat = rf"\banycast\s+{verb}\s+(\S+)"
    m = re.search(tail_pat, line)
    if not m:
        return None
    tok = m.group(1)
    addr, _, prefix_str = tok.partition("/")
    is_v6 = ":" in addr
    default_prefix = 128 if is_v6 else 32
    try:
        prefix = int(prefix_str) if prefix_str else default_prefix
    except ValueError:
        return None
    return addr, prefix, is_v6


async def _get_member_ref_and_additional(ctx: Context, name: str) -> tuple[str, list] | None:
    results = [
        as_dict(r)
        async for r in ctx.client.grid.member.list(
            host_name=name, return_fields_plus=["additional_ip_list"]
        )
    ]
    if not results:
        print(f"  No member found: {name}")
        return None
    return results[0]["_ref"], list(results[0].get("additional_ip_list") or [])


@command(
    "configure grid <name> member <name> anycast add <value>",
    words="<cr>",
    help=(
        "Attach an anycast loopback to a member. IPv4 defaults to /32, "
        "IPv6 to /128. Pre-provisioned (offline) members may silently drop "
        "v6 loopback until the member boots."
    ),
)
async def cli_member_anycast_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bmember\s+(\S+)\s+anycast\s+add", line)
    if not m:
        return
    member_name = m.group(1)
    tgt = _parse_anycast_target(line, "add")
    if not tgt:
        print("  Error: anycast address required (v4 or v6, optional /prefix)")
        return
    addr, prefix, is_v6 = tgt

    found = await _get_member_ref_and_additional(ctx, member_name)
    if not found:
        return
    ref, additional = found

    # Skip if this exact address already present.
    for entry in additional:
        if is_v6:
            if entry.get("ipv6_network_setting", {}).get("virtual_ip") == addr:
                print(f"  Skipped: anycast {addr} already on {member_name}")
                return
        else:
            if entry.get("ipv4_network_setting", {}).get("address") == addr:
                print(f"  Skipped: anycast {addr} already on {member_name}")
                return

    entry: dict = {"interface": "LOOPBACK", "anycast": True}
    if is_v6:
        entry["ipv6_network_setting"] = {
            "virtual_ip": addr,
            "cidr_prefix": prefix,
        }
    else:
        entry["ipv4_network_setting"] = {
            "address": addr,
            "subnet_mask": _cidr_to_mask(str(prefix)),
        }
    additional.append(entry)
    try:
        await ctx.client.grid.member.update(ref, {"additional_ip_list": additional})
    except Exception as e:
        # NIOS refuses v6 loopbacks until the member has a live LAN IPv6 VIP,
        # which pre-provisioned members don't have until first boot. Surface
        # this as a deferred rather than an error so batch scripts stay green.
        msg = str(e)
        if "IPv6 loopback address requires" in msg:
            print(
                f"  Deferred: v6 anycast {addr} on {member_name} "
                "(waiting for member to come online with IPv6 LAN)"
            )
            return
        raise


@command(
    "configure grid <name> member <name> anycast delete <value>",
    words="<cr>",
    help="Remove an anycast loopback from a member.",
)
async def cli_member_anycast_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bmember\s+(\S+)\s+anycast\s+delete", line)
    if not m:
        return
    member_name = m.group(1)
    tgt = _parse_anycast_target(line, "delete")
    if not tgt:
        print("  Error: anycast address required")
        return
    addr, _, is_v6 = tgt

    found = await _get_member_ref_and_additional(ctx, member_name)
    if not found:
        return
    ref, additional = found

    def _matches(e: dict) -> bool:
        if is_v6:
            return e.get("ipv6_network_setting", {}).get("virtual_ip") == addr
        return e.get("ipv4_network_setting", {}).get("address") == addr

    filtered = [e for e in additional if not _matches(e)]
    if len(filtered) == len(additional):
        print(f"  Skipped: anycast {addr} not present on {member_name}")
        return
    await ctx.client.grid.member.update(ref, {"additional_ip_list": filtered})


@command(
    "configure grid <name> member <name> modify",
    words="<cr> ipaddress=<cidr>|gateway=<ip>|comment=<comment>|name=<name>",
    help="Modify a grid member.",
)
async def cli_mod_member(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmember\s+(\S+)\s+modify", line)
    if not m:
        print("  Error: member name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.grid.member.list(host_name=name)]
    if not results:
        print(f"  No member found: {name}")
        return
    ref = results[0]["_ref"]

    body: dict = {}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    new_name = _parse_kv(line, "name")
    if new_name:
        body["host_name"] = new_name

    gateway = _parse_kv(line, "gateway")
    addr_info = _parse_ipaddress(line)

    if addr_info or gateway:
        vip: dict = {}
        if addr_info:
            vip["address"] = addr_info[0]
            vip["subnet_mask"] = addr_info[1]
        if gateway:
            vip["gateway"] = gateway
        body["vip_setting"] = vip

    if not body:
        print("  Error: no fields to modify")
        return

    await ctx.client.grid.member.update(ref, body)


# ---------------------------------------------------------------------------
# configure grid <name> member <name> dns [enable|disable]
# ---------------------------------------------------------------------------


@command(
    "configure grid <name> member <name> dns",
    words="<cr> enable disable",
    help="Configure DNS service on a member.",
)
@command(
    "configure grid <name> member <name> dns enable",
    words="<cr>",
    help="Enable DNS on a member.",
)
@command(
    "configure grid <name> member <name> dns disable",
    words="<cr>",
    help="Disable DNS on a member.",
)
async def cli_mod_member_dns(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmember\s+(\S+)\s+dns", line)
    if not m:
        print("  Error: member name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.grid.member_dns.list(host_name=name)]
    if not results:
        print(f"  No member:dns found: {name}")
        return
    ref = results[0]["_ref"]

    enable: bool | None = None
    if re.search(r"\bdns\s+enable\b", line):
        enable = True
    elif re.search(r"\bdns\s+disable\b", line):
        enable = False

    body: dict = {}
    if enable is not None:
        body["enable_dns"] = enable

    if body:
        await ctx.client.grid.member_dns.update(ref, body)


# ---------------------------------------------------------------------------
# configure grid <name> member <name> dhcp [enable|disable]
# ---------------------------------------------------------------------------


@command(
    "configure grid <name> member <name> dhcp",
    words="<cr> enable disable",
    help="Configure DHCP service on a member.",
)
@command(
    "configure grid <name> member <name> dhcp enable",
    words="<cr> ipv4 ipv6 both",
    help=(
        "Enable DHCP on a member. Bare form toggles IPv4 (backward compat); "
        "append ipv4/ipv6/both to target explicitly."
    ),
)
@command(
    "configure grid <name> member <name> dhcp enable ipv4",
    words="<cr>",
    help="Enable IPv4 DHCP (enable_dhcp) on a member.",
)
@command(
    "configure grid <name> member <name> dhcp enable ipv6",
    words="<cr>",
    help="Enable IPv6 DHCP (enable_dhcpv6_service) on a member.",
)
@command(
    "configure grid <name> member <name> dhcp enable both",
    words="<cr>",
    help="Enable both IPv4 and IPv6 DHCP services on a member.",
)
@command(
    "configure grid <name> member <name> dhcp disable",
    words="<cr> ipv4 ipv6 both",
    help="Disable DHCP on a member (defaults to IPv4).",
)
@command(
    "configure grid <name> member <name> dhcp disable ipv4",
    words="<cr>",
    help="Disable IPv4 DHCP on a member.",
)
@command(
    "configure grid <name> member <name> dhcp disable ipv6",
    words="<cr>",
    help="Disable IPv6 DHCP on a member.",
)
@command(
    "configure grid <name> member <name> dhcp disable both",
    words="<cr>",
    help="Disable both IPv4 and IPv6 DHCP on a member.",
)
async def cli_mod_member_dhcp(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmember\s+(\S+)\s+dhcp", line)
    if not m:
        print("  Error: member name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.grid.member_dhcpproperties.list(host_name=name)]
    if not results:
        print(f"  No member:dhcpproperties found: {name}")
        return
    ref = results[0]["_ref"]

    verb_m = re.search(r"\bdhcp\s+(enable|disable)(?:\s+(ipv4|ipv6|both))?\b", line)
    if not verb_m:
        return
    enable = verb_m.group(1) == "enable"
    proto = verb_m.group(2) or "ipv4"  # default preserves existing behavior

    body: dict = {}
    if proto in ("ipv4", "both"):
        body["enable_dhcp"] = enable
    if proto in ("ipv6", "both"):
        body["enable_dhcpv6_service"] = enable

    if body:
        await ctx.client.grid.member_dhcpproperties.update(ref, body)


# ---------------------------------------------------------------------------
# configure grid <name> member <name> dns set <key>=<value>
# ---------------------------------------------------------------------------


@command(
    "configure grid <name> member <name> dns set",
    words="<key>=<value>",
    help="Set arbitrary DNS config fields on a member via key=value pass-through.",
)
async def cli_set_member_dns(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmember\s+(\S+)\s+dns\s+set\b", line)
    if not m:
        print("  Error: member name required")
        return
    name = m.group(1)

    body = _parse_inline_kvs(line, " dns set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return

    results = [as_dict(r) async for r in ctx.client.grid.member_dns.list(host_name=name)]
    if not results:
        print(f"  No member:dns found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.member_dns.update(ref, body)


# ---------------------------------------------------------------------------
# configure grid <name> member <name> dhcp set <key>=<value>
# ---------------------------------------------------------------------------


@command(
    "configure grid <name> member <name> dhcp set",
    words="<key>=<value>",
    help="Set arbitrary DHCP config fields on a member via key=value pass-through.",
)
async def cli_set_member_dhcp(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmember\s+(\S+)\s+dhcp\s+set\b", line)
    if not m:
        print("  Error: member name required")
        return
    name = m.group(1)

    body = _parse_inline_kvs(line, " dhcp set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return

    results = [as_dict(r) async for r in ctx.client.grid.member_dhcpproperties.list(host_name=name)]
    if not results:
        print(f"  No member:dhcpproperties found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.member_dhcpproperties.update(ref, body)


# ---------------------------------------------------------------------------
# show grid <name> member <name> license
# configure grid <name> member <name> license add <license_type>
# configure grid <name> member <name> license remove <license_type>
# ---------------------------------------------------------------------------


@command(
    "show grid <name> member <name> license",
    words="<cr> fields=<field1,field2,...>",
    help="Show licenses installed on a member.",
)
async def cli_show_member_license(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    # tokens: show(0) grid(1) <grid>(2) member(3) <mname>(4) license(5)
    tokens = line.split()
    if len(tokens) < 5:
        print("  Error: member name required")
        return
    name = tokens[4]

    extra = parse_extra_fields(line)
    results = [
        as_dict(r)
        async for r in ctx.client.grid.member_license.list(
            host_name=name,
            return_fields_plus=["hwid", "key", "kind", "type"] + extra,
        )
    ]

    for r in results:
        parts = []
        if r.get("type"):
            parts.append(f"type={r['type']}")
        if r.get("kind"):
            parts.append(f"kind={r['kind']}")
        if r.get("hwid"):
            parts.append(f"hwid={r['hwid']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


@command(
    "configure grid <name> member <name> license add <license_type>",
    words="<cr>",
    help="Add a license to a member.",
)
async def cli_add_member_license(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\blicense\s+add\s+(\S+)", line)
    if not m:
        print("  Error: license type required")
        return
    license_type = m.group(1).upper()

    # Extract member name: "member <mname> license"
    mm = re.search(r"\bmember\s+(\S+)\s+license", line)
    if not mm:
        print("  Error: member name required")
        return
    member_name = mm.group(1)

    await ctx.client.grid.member_license.create({"host_name": member_name, "type": license_type})
    print(f"  Added license {license_type} to {member_name}")


@command(
    "configure grid <name> member <name> license remove <license_type>",
    words="<cr>",
    help="Remove a license from a member.",
)
async def cli_remove_member_license(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\blicense\s+remove\s+(\S+)", line)
    if not m:
        print("  Error: license type required")
        return
    license_type = m.group(1).upper()

    mm = re.search(r"\bmember\s+(\S+)\s+license", line)
    if not mm:
        print("  Error: member name required")
        return
    member_name = mm.group(1)

    results = [
        as_dict(r)
        async for r in ctx.client.grid.member_license.list(
            host_name=member_name,
        )
    ]
    # Filter to the matching type (WAPI returns all licenses for the member)
    matches = [r for r in results if str(r.get("type", "")).upper() == license_type]
    if not matches:
        print(f"  No license of type {license_type} found on {member_name}")
        return
    ref = matches[0]["_ref"]
    await ctx.client.grid.member_license.delete(ref)
    print(f"  Removed license {license_type} from {member_name}")


# ---------------------------------------------------------------------------
# configure grid <name> member <name> preprovision
# ---------------------------------------------------------------------------


@command(
    "configure grid <name> member <name> preprovision",
    words=_PREPROVISION_OPTS,
    help="Set pre-provisioning (hardware_info + licenses) on an existing member.",
)
async def cli_preprovision_member(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmember\s+(\S+)\s+preprovision", line)
    if not m:
        print("  Error: member name required")
        return
    name = m.group(1)

    pre_prov = _build_pre_provisioning(line)
    if pre_prov is None:
        print("  Error: specify at least one of hwtype/model/serial/license/node")
        return
    dropped = _filter_hardware_info(pre_prov, await _supported_hw_fields(ctx))
    if dropped:
        _warn_dropped_hw_fields(dropped, pre_prov)

    results = [as_dict(r) async for r in ctx.client.grid.member.list(host_name=name)]
    if not results:
        print(f"  No member found: {name}")
        return
    ref = results[0]["_ref"]

    update_body: dict = {"pre_provisioning": pre_prov}
    platform = _parse_kv(line, "platform")
    if platform:
        update_body["platform"] = platform
    if len(pre_prov.get("hardware_info", [])) >= 2:
        update_body["enable_ha"] = True

    await ctx.client.grid.member.update(ref, update_body)


# ---------------------------------------------------------------------------
# show grid <name> member [<member_name>]
# ---------------------------------------------------------------------------


@command("show grid <name> member", words="<cr> <name>", help="List grid members.")
@command(
    "show grid <name> member <name>",
    words="<cr> dns fields=<field1,field2,...>",
    help="Show a specific member.",
)
@command("show member", words="<cr> <name>", help="List grid members (shortcut).")
@command(
    "show member <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific member (shortcut).",
)
async def cli_show_member(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    # Parse both forms:
    #   "show grid <grid> member [<mname>]"  - tokens[4] is the member name
    #   "show member [<mname>]"               - tokens[2] is the member name
    tokens = line.split()
    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": [
            "host_name",
            "vip_setting",
            "comment",
            "pre_provisioning",
            "platform",
            "node_info",
        ]
        + extra,
    }
    if tokens[1] == "member":
        if len(tokens) >= 3 and not tokens[2].startswith("<") and "=" not in tokens[2]:
            kwargs["host_name"] = tokens[2]
    elif len(tokens) >= 5 and not tokens[4].startswith("<") and "=" not in tokens[4]:
        kwargs["host_name"] = tokens[4]

    results = [as_dict(r) async for r in ctx.client.grid.member.list(**kwargs)]

    for r in results:
        parts = [f"host_name={r.get('host_name', '')}"]
        vip = r.get("vip_setting")
        if vip and isinstance(vip, dict):
            parts.append(f"address={vip.get('address', '')}")
        if r.get("platform"):
            parts.append(f"platform={r['platform']}")
        # node_info[0].hwmodel surfaces the actual appliance model for
        # booted members (pre-provisioned ones use pre_provisioning below).
        ni = r.get("node_info") or []
        if ni and isinstance(ni, list):
            hwmodel = ni[0].get("hwmodel") if isinstance(ni[0], dict) else None
            if hwmodel:
                parts.append(f"hwmodel={hwmodel}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        pp = r.get("pre_provisioning")
        if pp and isinstance(pp, dict):
            print("  pre_provisioning:")
            for hw in pp.get("hardware_info", []):
                hwtype = hw.get("hwtype", "")
                hwmodel = hw.get("hwmodel", "")
                sn = hw.get("serial_number", "")
                print(f"    hardware: {hwtype} / {hwmodel} / {sn}")
            lics = pp.get("licenses", [])
            if lics:
                print(f"    licenses: {' '.join(lics)}")
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# show grid <name> member <name> dns
# ---------------------------------------------------------------------------


@command(
    "show grid <name> member <name> dns",
    words="<cr> fields=<field1,field2,...>",
    help="Show DNS settings for a member.",
)
async def cli_show_member_dns(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    # tokens: show(0) grid(1) <grid>(2) member(3) <mname>(4) dns(5)
    tokens = line.split()
    if len(tokens) < 5:
        print("  Error: member name required")
        return
    name = tokens[4]

    extra = parse_extra_fields(line)
    results = [
        as_dict(r)
        async for r in ctx.client.grid.member_dns.list(
            host_name=name,
            return_fields_plus=["host_name", "enable_dns"] + extra,
        )
    ]

    for r in results:
        parts = [f"host_name={r.get('host_name', '')}"]
        if "enable_dns" in r:
            parts.append(f"enable_dns={r['enable_dns']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# show grid <name> dns
# ---------------------------------------------------------------------------


@command(
    "show grid <name> dns",
    words="<cr> fields=<field1,field2,...>",
    help="Show grid-level DNS settings.",
)
async def cli_show_grid_dns(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    extra = parse_extra_fields(line)
    results = [
        as_dict(r)
        async for r in ctx.client.grid.grid_dns.list(
            return_fields_plus=["allow_recursive_query", "default_ttl", "dnssec_enabled"] + extra,
        )
    ]

    for r in results:
        parts = []
        if "allow_recursive_query" in r:
            parts.append(f"allow_recursive_query={r['allow_recursive_query']}")
        if "default_ttl" in r:
            parts.append(f"default_ttl={r['default_ttl']}")
        if "dnssec_enabled" in r:
            parts.append(f"dnssec_enabled={r['dnssec_enabled']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# show grid <name> dhcp
# ---------------------------------------------------------------------------


@command(
    "show grid <name> dhcp",
    words="<cr> fields=<field1,field2,...>",
    help="Show grid-level DHCP settings.",
)
async def cli_show_grid_dhcp(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    extra = parse_extra_fields(line)
    # `domain_name`, `domain_name_servers`, and `lease_time` are not fields
    # on grid:dhcpproperties (the WAPI object uses `ddns_domainname`,
    # `ipv6_domain_name`, `lease_scavenge_time`, etc.). Ask only for
    # `authority` in the summary; users can surface anything else via
    # `fields=`.
    results = [
        as_dict(r)
        async for r in ctx.client.grid.grid_dhcpproperties.list(
            return_fields_plus=["authority"] + extra,
        )
    ]

    for r in results:
        parts = []
        if "authority" in r:
            parts.append(f"authority={r['authority']}")
        print(" ".join(parts) if parts else "  (no summary fields returned)")
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Chunk B - Member threat-insight / threat-protection / file-distribution
# ===========================================================================


@command(
    "show grid <name> member <name> threat_insight",
    words="<cr> fields=<field1,field2,...>",
    help="Show Threat Insight settings for a member.",
)
async def cli_show_member_threatinsight(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    if len(tokens) < 5:
        print("  Error: member name required")
        return
    name = tokens[4]

    extra = parse_extra_fields(line)
    results = [
        as_dict(r)
        async for r in ctx.client.grid.member_threatinsight.list(
            host_name=name,
            return_fields_plus=["host_name", "enable_service", "status"] + extra,
        )
    ]

    for r in results:
        parts = [f"host_name={r.get('host_name', name)}"]
        if "enable_service" in r:
            parts.append(f"enable_service={r['enable_service']}")
        if r.get("status"):
            parts.append(f"status={r['status']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


@command(
    "configure grid <name> member <name> threat_insight set",
    words="<key>=<value>",
    help="Set Threat Insight fields on a member via key=value pass-through.",
)
async def cli_set_member_threatinsight(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmember\s+(\S+)\s+threat_insight\s+set\b", line)
    if not m:
        print("  Error: member name required")
        return
    name = m.group(1)

    body = _parse_inline_kvs(line, " threat_insight set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return

    results = [as_dict(r) async for r in ctx.client.grid.member_threatinsight.list(host_name=name)]
    if not results:
        print(f"  No member:threatinsight found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.member_threatinsight.update(ref, body)


@command(
    "show grid <name> member <name> threat_protection",
    words="<cr> fields=<field1,field2,...>",
    help="Show Threat Protection settings for a member.",
)
async def cli_show_member_threatprotection(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    if len(tokens) < 5:
        print("  Error: member name required")
        return
    name = tokens[4]

    extra = parse_extra_fields(line)
    results = [
        as_dict(r)
        async for r in ctx.client.grid.member_threatprotection.list(
            host_name=name,
            return_fields_plus=["host_name", "comment", "enable_service"] + extra,
        )
    ]

    for r in results:
        parts = [f"host_name={r.get('host_name', name)}"]
        if "enable_service" in r:
            parts.append(f"enable_service={r['enable_service']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


@command(
    "configure grid <name> member <name> threat_protection set",
    words="<key>=<value>",
    help="Set Threat Protection fields on a member via key=value pass-through.",
)
async def cli_set_member_threatprotection(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmember\s+(\S+)\s+threat_protection\s+set\b", line)
    if not m:
        print("  Error: member name required")
        return
    name = m.group(1)

    body = _parse_inline_kvs(line, " threat_protection set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return

    results = [
        as_dict(r) async for r in ctx.client.grid.member_threatprotection.list(host_name=name)
    ]
    if not results:
        print(f"  No member:threatprotection found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.member_threatprotection.update(ref, body)


@command(
    "show grid <name> member <name> file_distribution",
    words="<cr> fields=<field1,field2,...>",
    help="Show file distribution settings for a member.",
)
async def cli_show_member_filedistribution(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    if len(tokens) < 5:
        print("  Error: member name required")
        return
    name = tokens[4]

    extra = parse_extra_fields(line)
    results = [
        as_dict(r)
        async for r in ctx.client.grid.member_filedistribution.list(
            host_name=name,
            return_fields_plus=["host_name", "comment", "status"] + extra,
        )
    ]

    for r in results:
        parts = [f"host_name={r.get('host_name', name)}"]
        if r.get("status"):
            parts.append(f"status={r['status']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


@command(
    "configure grid <name> member <name> file_distribution set",
    words="<key>=<value>",
    help="Set file distribution fields on a member via key=value pass-through.",
)
async def cli_set_member_filedistribution(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmember\s+(\S+)\s+file_distribution\s+set\b", line)
    if not m:
        print("  Error: member name required")
        return
    name = m.group(1)

    body = _parse_inline_kvs(line, " file_distribution set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return

    results = [
        as_dict(r) async for r in ctx.client.grid.member_filedistribution.list(host_name=name)
    ]
    if not results:
        print(f"  No member:filedistribution found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.member_filedistribution.update(ref, body)


# ===========================================================================
# Slice 5b - Waypoints
# ===========================================================================

register(
    "configure",
    words="grid nsgroup view shared_record_group",
    help="Create, modify or delete grid objects.",
)

# nsgroup
register(
    "configure nsgroup",
    words="add <name>",
    help="NS groups - named sets of DNS name-servers used on zones.",
)
register("configure nsgroup add", words="<name>")
register(
    "configure nsgroup add <name>",
    words="<cr> primary=<name>|secondary=<name>",
)
register("configure nsgroup <name>", words="delete modify")
register("configure nsgroup <name> delete", words="<cr>")
register(
    "configure nsgroup <name> modify",
    words="<cr> primary=<name>|secondary=<name>",
)

# view
register(
    "configure view",
    words="add <name>",
    dynamic=_completions.views,
    help="DNS views - split-brain separation of zones and records.",
)
register("configure view add", words="<name>")
register("configure view add <name>", words="<cr> comment=<comment>")
register("configure view <name>", words="delete")
register("configure view <name> delete", words="<cr>")

# shared_record_group
register(
    "configure shared_record_group",
    words="add <name>",
    help="Shared-record groups - container for shared records.",
)
register("configure shared_record_group add", words="<name>")
register("configure shared_record_group add <name>", words="<cr> comment=<comment>")
register("configure shared_record_group <name>", words="delete")
register("configure shared_record_group <name> delete", words="<cr>")

# show zone ns_group / shared_record_group (extend existing "show zone" node)
register(
    "show zone",
    words="ns_group shared_record_group",
    help="Authoritative zones (forward + reverse).",
)
register("show zone ns_group", words="<cr> <name>")
register("show zone ns_group <name>", words="<cr> fields=<field1,field2,...>")
register("show zone shared_record_group", words="<cr> <name>")
register("show zone shared_record_group <name>", words="<cr> fields=<field1,field2,...>")


# ===========================================================================
# Slice 5b - Handlers
# ===========================================================================

# ---------------------------------------------------------------------------
# configure nsgroup add <name>
# ---------------------------------------------------------------------------


@command(
    "configure nsgroup add <name>",
    words="<cr> primary=<name>|secondary=<name>",
    help="Add a DNS NS group.",
)
async def cli_add_nsgroup(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnsgroup add\s+(\S+)", line)
    if not m:
        print("  Error: nsgroup name required")
        return
    name = m.group(1)

    primary = _parse_kv(line, "primary")
    secondaries = _parse_kv_all(line, "secondary")

    body: dict = {"name": name}
    if primary:
        body["grid_primary"] = [{"name": primary}]
    if secondaries:
        body["grid_secondaries"] = [{"name": s} for s in secondaries]

    await ctx.client.dns.nsgroup.create(body)


# ---------------------------------------------------------------------------
# configure nsgroup <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure nsgroup <name> delete",
    words="<cr>",
    help="Delete a DNS NS group.",
)
async def cli_del_nsgroup(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnsgroup\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: nsgroup name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dns.nsgroup.list(name=name)]
    if not results:
        print(f"  No nsgroup found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.dns.nsgroup.delete(ref)


# ---------------------------------------------------------------------------
# configure nsgroup <name> modify [primary <fqdn>] [secondary <fqdn>...]
# ---------------------------------------------------------------------------


@command(
    "configure nsgroup <name> modify",
    words="<cr> primary=<name>|secondary=<name>",
    help="Modify an NS group's primary/secondary members.",
)
async def cli_mod_nsgroup(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnsgroup\s+(\S+)\s+modify", line)
    if not m:
        print("  Error: nsgroup name required")
        return
    name = m.group(1)

    primary = _parse_kv(line, "primary")
    secondaries = _parse_kv_all(line, "secondary")

    if not primary and not secondaries:
        print("  Error: specify at least one of primary= or secondary=")
        return

    results = [as_dict(r) async for r in ctx.client.dns.nsgroup.list(name=name)]
    if not results:
        print(f"  No nsgroup found: {name}")
        return
    ref = results[0]["_ref"]

    body: dict = {}
    if primary:
        body["grid_primary"] = [{"name": primary}]
    if secondaries:
        body["grid_secondaries"] = [{"name": s} for s in secondaries]

    await ctx.client.dns.nsgroup.update(ref, body)


# ---------------------------------------------------------------------------
# show zone ns_group [<name>]
# ---------------------------------------------------------------------------


@command("show zone ns_group", words="<cr> <name>", help="List NS groups.")
@command(
    "show zone ns_group <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific NS group.",
)
async def cli_show_nsgroup(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": ["name", "grid_primary", "grid_secondaries", "comment"] + extra
    }
    # "show zone ns_group [<name>]" - tokens: show(0) zone(1) ns_group(2) [name(3)]
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        kwargs["name"] = tokens[3]

    results = [as_dict(r) async for r in ctx.client.dns.nsgroup.list(**kwargs)]

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


# ---------------------------------------------------------------------------
# configure view add <name>
# ---------------------------------------------------------------------------


@command(
    "configure view add <name>",
    words="<cr> comment=<comment>",
    help="Add a DNS view.",
)
async def cli_add_view(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bview add\s+(\S+)", line)
    if not m:
        print("  Error: view name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.dns.view.create(body)


# ---------------------------------------------------------------------------
# configure view <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure view <name> delete",
    words="<cr>",
    help="Delete a DNS view.",
)
async def cli_del_view(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bview\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: view name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dns.view.list(name=name)]
    if not results:
        print(f"  No view found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.dns.view.delete(ref)


# ---------------------------------------------------------------------------
# configure shared_record_group add <name>
# ---------------------------------------------------------------------------


@command(
    "configure shared_record_group add <name>",
    words="<cr> comment=<comment>",
    help="Add a DNS shared record group.",
)
async def cli_add_shared_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bshared_record_group add\s+(\S+)", line)
    if not m:
        print("  Error: shared record group name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.dns.sharedrecordgroup.create(body)


# ---------------------------------------------------------------------------
# configure shared_record_group <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure shared_record_group <name> delete",
    words="<cr>",
    help="Delete a DNS shared record group.",
)
async def cli_del_shared_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bshared_record_group\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: shared record group name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dns.sharedrecordgroup.list(name=name)]
    if not results:
        print(f"  No shared record group found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.dns.sharedrecordgroup.delete(ref)


# ---------------------------------------------------------------------------
# show zone shared_record_group [<name>]
# ---------------------------------------------------------------------------


@command(
    "show zone shared_record_group",
    words="<cr> <name>",
    help="List DNS shared record groups.",
)
@command(
    "show zone shared_record_group <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific DNS shared record group.",
)
async def cli_show_shared_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["name", "comment"] + extra}
    # "show zone shared_record_group [<name>]" - tokens: show(0) zone(1) shared_record_group(2) [name(3)]
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        kwargs["name"] = tokens[3]

    results = [as_dict(r) async for r in ctx.client.dns.sharedrecordgroup.list(**kwargs)]

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
# Slice 5c - Waypoints
# ===========================================================================

register(
    "restart",
    words="dns dhcp dhcpv4 dhcpv6 all discovery status",
    help="Restart grid services (DNS, DHCP, reporting, etc.).",
)
_RESTART_OPTS = "<cr> delay=<num>|at=<value>|mode=<name>|option=<name>|member=<name>"
register("restart dns", words=_RESTART_OPTS)
register("restart dhcp", words=_RESTART_OPTS)
register("restart dhcpv4", words=_RESTART_OPTS)
register("restart dhcpv6", words=_RESTART_OPTS)
register("restart all", words=_RESTART_OPTS)
register("restart discovery", words="<cr>")
register(
    "restart status",
    words="<cr> refresh",
    help="Show or refresh service-restart status across members.",
)
register("restart status refresh", words="<cr>")

register("show", words="schedule restart", help="Read grid state without modifying anything.")
register("show schedule", words="<cr> fields=<field1,field2,...>")
register("show restart", words="<cr>", help="Current service-restart status on each member.")

register("configure", words="schedule", help="Create, modify or delete grid objects.")
register(
    "configure schedule",
    words="<num>",
    help="Scheduled tasks (apply an object change at a future time).",
)
register("configure schedule <num>", words="delete")
register("configure schedule <num> delete", words="<cr>")


# ===========================================================================
# Slice 5c - Handlers
# ===========================================================================


async def _get_grid_ref(ctx: Context) -> str | None:
    """Fetch the grid object ref. Returns None and prints error on failure."""
    grids = [as_dict(r) async for r in ctx.client.grid.grid.list()]
    if not grids:
        print("  Error: no grid found")
        return None
    return grids[0]["_ref"]


_VALID_MODES = frozenset({"GROUPED", "SEQUENTIAL", "SIMULTANEOUS"})
_VALID_OPTIONS = frozenset({"FORCE_RESTART", "RESTART_IF_NEEDED"})


async def _do_restart(line: str, ctx: Context, service: str) -> None:
    """Shared logic for restart dns/dhcp/dhcpv4/dhcpv6/all.

    Accepted keywords (all optional):
      delay <num>   - integer delay in seconds
      mode <M>      - GROUPED | SEQUENTIAL | SIMULTANEOUS
      option <O>    - FORCE_RESTART | RESTART_IF_NEEDED
      member <name> - one or more member names (repeatable)
    """
    if ctx.client is None:
        print("  Not connected")
        return

    ref = await _get_grid_ref(ctx)
    if ref is None:
        return

    body: dict = {"services": [service]}

    delay_str = _parse_kv(line, "delay")
    at_str = _parse_kv(line, "at")
    if delay_str is not None and at_str is not None:
        print("  Error: specify either delay= or at=, not both")
        return
    if delay_str is not None:
        try:
            body["delay"] = int(delay_str)
        except ValueError:
            print(f"  Error: delay must be an integer, got: {delay_str}")
            return
    elif at_str is not None:
        # Absolute time → delay relative to now. Accepts epoch seconds or
        # ISO-8601 (e.g. "2026-05-01T02:00:00" - local TZ).
        import datetime
        import time

        try:
            if at_str.isdigit():
                target = int(at_str)
            else:
                target = int(datetime.datetime.fromisoformat(at_str).timestamp())
        except ValueError:
            print(f"  Error: at= must be epoch seconds or ISO-8601 timestamp, got: {at_str}")
            return
        now = int(time.time())
        delay = target - now
        if delay <= 0:
            print(f"  Error: at= is in the past (now={now}, target={target})")
            return
        body["delay"] = delay

    mode = _parse_kv(line, "mode")
    if mode is not None:
        mode_upper = mode.upper()
        if mode_upper not in _VALID_MODES:
            print(f"  Error: mode must be one of {sorted(_VALID_MODES)}, got: {mode}")
            return
        body["mode"] = mode_upper

    restart_option = _parse_kv(line, "option")
    if restart_option is not None:
        opt_upper = restart_option.upper()
        if opt_upper not in _VALID_OPTIONS:
            print(f"  Error: option must be one of {sorted(_VALID_OPTIONS)}, got: {restart_option}")
            return
        body["restart_option"] = opt_upper

    members = _parse_kv_all(line, "member")
    if members:
        body["members"] = members

    await ctx.client.grid.grid.call_function(ref, "restartservices", **body)


# ---------------------------------------------------------------------------
# restart dns/dhcp/dhcpv4/dhcpv6/all [mode <M>] [option <O>] [member <n>] [delay <num>]
# ---------------------------------------------------------------------------


@command(
    "restart dns",
    words=_RESTART_OPTS,
    help="Restart DNS service on the grid.",
)
async def cli_restart_dns(line: str, ctx: Context) -> None:
    await _do_restart(line, ctx, "DNS")


@command(
    "restart dhcpv4",
    words=_RESTART_OPTS,
    help="Restart DHCPv4 service on the grid.",
)
async def cli_restart_dhcpv4(line: str, ctx: Context) -> None:
    await _do_restart(line, ctx, "DHCPV4")


@command(
    "restart dhcpv6",
    words=_RESTART_OPTS,
    help="Restart DHCPv6 service on the grid.",
)
async def cli_restart_dhcpv6(line: str, ctx: Context) -> None:
    await _do_restart(line, ctx, "DHCPV6")


@command(
    "restart all",
    words=_RESTART_OPTS,
    help="Restart all services on the grid.",
)
async def cli_restart_all(line: str, ctx: Context) -> None:
    await _do_restart(line, ctx, "ALL")


# ---------------------------------------------------------------------------
# restart dhcp [delay <num>]
# ---------------------------------------------------------------------------


@command(
    "restart dhcp",
    words=_RESTART_OPTS,
    help="Restart DHCP service on the grid.",
)
async def cli_restart_dhcp(line: str, ctx: Context) -> None:
    await _do_restart(line, ctx, "DHCP")


# ---------------------------------------------------------------------------
# restart discovery  [STUB]
# ---------------------------------------------------------------------------


@command(
    "restart discovery",
    words="<cr>",
    help="Start/restart a network discovery task.",
)
async def cli_restart_discovery(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    result = await ctx.client.ipam.discovery_discoverytask.create({"action": "START"})
    if result:
        print(f"  Discovery started: {result}")


# ---------------------------------------------------------------------------
# show schedule
# ---------------------------------------------------------------------------


@command("show schedule", words="<cr> fields=<field1,field2,...>", help="Show scheduled tasks.")
async def cli_show_schedule(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    extra = parse_extra_fields(line)
    results = [
        as_dict(r)
        async for r in ctx.client.misc.scheduledtask.list(
            return_fields_plus=[
                "task_id",
                "submitter",
                "scheduled_time",
                "submit_time",
                "task_type",
                "execution_status",
            ]
            + extra,
        )
    ]

    for r in results:
        parts = []
        if "task_id" in r:
            parts.append(f"task_id={r['task_id']}")
        if "submitter" in r:
            parts.append(f"submitter={r['submitter']}")
        if "task_type" in r:
            parts.append(f"task_type={r['task_type']}")
        if "execution_status" in r:
            parts.append(f"status={r['execution_status']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# configure schedule <id> delete
# ---------------------------------------------------------------------------


@command(
    "configure schedule <num> delete",
    words="<cr>",
    help="Delete a scheduled task by task ID.",
)
async def cli_del_schedule(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bschedule\s+(\d+)\s+delete", line)
    if not m:
        print("  Error: schedule task ID required")
        return
    task_id = int(m.group(1))

    results = [as_dict(r) async for r in ctx.client.misc.scheduledtask.list(task_id=task_id)]
    if not results:
        print(f"  No scheduled task found: {task_id}")
        return
    ref = results[0]["_ref"]
    await ctx.client.misc.scheduledtask.delete(ref)


# ===========================================================================
# Gap 5 - restart status / show restart
# ===========================================================================


async def _get_restart_status(ctx: Context) -> list[dict]:
    """GET restartservicestatus. NiosError propagates to the dispatcher."""
    return [
        as_dict(r)
        async for r in ctx.client.grid.restartservicestatus.list(
            return_fields_plus=[
                "member",
                "dhcp_status",
                "dns_status",
                "reporting_status",
            ],
        )
    ]


def _print_restart_status(statuses: list[dict]) -> None:
    if not statuses:
        print("  (no restart status available)")
        return
    for s in statuses:
        parts = []
        if s.get("member"):
            parts.append(f"member={s['member']}")
        for svc in ("dns_status", "dhcp_status", "reporting_status"):
            if s.get(svc):
                parts.append(f"{svc}={s[svc]}")
        if parts:
            print(" ".join(parts))


# ---------------------------------------------------------------------------
# restart status [refresh]
# ---------------------------------------------------------------------------


@command(
    "restart status",
    words="<cr> refresh",
    help="Show (and optionally refresh) grid service restart status.",
)
@command(
    "restart status refresh",
    words="<cr>",
    help="Refresh and show grid service restart status.",
)
async def cli_restart_status(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    refresh = "refresh" in line.split()

    if refresh:
        # Trigger a status refresh on the grid first
        ref = await _get_grid_ref(ctx)
        if ref is None:
            return
        await ctx.client.grid.grid.call_function(
            ref,
            "requestrestartservicestatus",
            service_option="ALL",
        )

    _print_restart_status(await _get_restart_status(ctx))


# ---------------------------------------------------------------------------
# show restart
# ---------------------------------------------------------------------------


@command(
    "show restart",
    words="<cr>",
    help="Show grid service restart status (alias for restart status).",
)
async def cli_show_restart(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    _print_restart_status(await _get_restart_status(ctx))


# ===========================================================================
# Chunk C - Grid-level extensions: dns/dhcp/threat-insight/threat-protection/
#            file-distribution set <key>=<value>
# ===========================================================================


def _require_connected(ctx: Context) -> bool:
    """Print error and return False when client is not connected."""
    if ctx.client is None:
        print("  Not connected")
        return False
    return True


async def _grid_set(ctx: Context, resource_attr: str, marker: str, line: str) -> None:
    """Generic helper for 'configure grid <name> <domain> set <kv...>'.

    Args:
        resource_attr: attribute name on ctx.client.grid (e.g. "grid_dns")
        marker:        substring used to locate the kv pairs in *line*
        line:          the full CLI input line
    """
    body = _parse_inline_kvs(line, marker)
    if not body:
        print("  Error: specify at least one key=value pair")
        return

    resource = getattr(ctx.client.grid, resource_attr)
    results = [as_dict(r) async for r in resource.list()]
    if not results:
        print(f"  Error: no {resource_attr} object found")
        return
    ref = results[0]["_ref"]
    await resource.update(ref, body)


# ---------------------------------------------------------------------------
# show grid <name> {dns,dhcp,threat_insight,threat_protection,file_distribution} keys
#
# Lists the writable fields accepted by the matching `... set <key>=<value>`
# pass-through, with their Python-level types. Resolved from the SDK pydantic
# model, so it tracks whichever WAPI version the SDK is pinned against.
# ---------------------------------------------------------------------------


def _grid_dns_model():
    from ibx_nios_sdk.grid.models.grid_dns import READONLY_FIELDS, GridDns

    return GridDns, READONLY_FIELDS


_grid_dns_keys_completer = lazy_keys_completer(_grid_dns_model)


def _grid_dhcp_model():
    from ibx_nios_sdk.grid.models.grid_dhcpproperties import READONLY_FIELDS, GridDhcpproperties

    return GridDhcpproperties, READONLY_FIELDS


_grid_dhcp_keys_completer = lazy_keys_completer(_grid_dhcp_model)


def _grid_ti_model():
    from ibx_nios_sdk.grid.models.grid_threatinsight import READONLY_FIELDS, GridThreatinsight

    return GridThreatinsight, READONLY_FIELDS


_grid_ti_keys_completer = lazy_keys_completer(_grid_ti_model)


def _grid_tp_model():
    from ibx_nios_sdk.grid.models.grid_threatprotection import READONLY_FIELDS, GridThreatprotection

    return GridThreatprotection, READONLY_FIELDS


_grid_tp_keys_completer = lazy_keys_completer(_grid_tp_model)


def _grid_fd_model():
    from ibx_nios_sdk.grid.models.grid_filedistribution import READONLY_FIELDS, GridFiledistribution

    return GridFiledistribution, READONLY_FIELDS


_grid_fd_keys_completer = lazy_keys_completer(_grid_fd_model)

register("configure grid <name> dns set", words="<key>=<value>", dynamic=_grid_dns_keys_completer)
register("configure grid <name> dhcp set", words="<key>=<value>", dynamic=_grid_dhcp_keys_completer)
register(
    "configure grid <name> threat_insight set",
    words="<key>=<value>",
    dynamic=_grid_ti_keys_completer,
)
register(
    "configure grid <name> threat_protection set",
    words="<key>=<value>",
    dynamic=_grid_tp_keys_completer,
)
register(
    "configure grid <name> file_distribution set",
    words="<key>=<value>",
    dynamic=_grid_fd_keys_completer,
)


@command(
    "show grid <name> dns keys",
    words="<cr>",
    help="List writable fields accepted by `configure grid <name> dns set`.",
)
async def cli_show_grid_dns_keys(line: str, ctx: Context) -> None:
    _print_keys(_list_settable_keys(*_grid_dns_model()))


@command(
    "show grid <name> dhcp keys",
    words="<cr>",
    help="List writable fields accepted by `configure grid <name> dhcp set`.",
)
async def cli_show_grid_dhcp_keys(line: str, ctx: Context) -> None:
    _print_keys(_list_settable_keys(*_grid_dhcp_model()))


@command(
    "show grid <name> threat_insight keys",
    words="<cr>",
    help="List writable fields accepted by `configure grid <name> threat_insight set`.",
)
async def cli_show_grid_ti_keys(line: str, ctx: Context) -> None:
    _print_keys(_list_settable_keys(*_grid_ti_model()))


@command(
    "show grid <name> threat_protection keys",
    words="<cr>",
    help="List writable fields accepted by `configure grid <name> threat_protection set`.",
)
async def cli_show_grid_tp_keys(line: str, ctx: Context) -> None:
    _print_keys(_list_settable_keys(*_grid_tp_model()))


@command(
    "show grid <name> file_distribution keys",
    words="<cr>",
    help="List writable fields accepted by `configure grid <name> file_distribution set`.",
)
async def cli_show_grid_fd_keys(line: str, ctx: Context) -> None:
    _print_keys(_list_settable_keys(*_grid_fd_model()))


# ---------------------------------------------------------------------------
# configure grid <name> dns set <key>=<value>
# ---------------------------------------------------------------------------


@command(
    "configure grid <name> dns set",
    words="<key>=<value>",
    help="Set arbitrary grid DNS config fields via key=value pass-through.",
)
async def cli_set_grid_dns(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return
    await _grid_set(ctx, "grid_dns", " dns set ", line)


@command(
    "configure grid <name> dns allow_recursion",
    words="<cr> any|acl=<name>|ace=<cidr>|deny_ace=<cidr>",
    help="Configure the grid's Allow Recursion ACL. Modes mirror the UI: "
    "`any` (radio: Any), `acl=<name>` (Named ACL), or one-or-more "
    "`ace=<cidr>` / `deny_ace=<cidr>` entries (Set of ACEs). Modes are "
    "mutually exclusive; acl takes precedence over ACEs over any.",
)
async def cli_grid_dns_allow_recursion(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return

    acl_name = _parse_kv(line, "acl")
    allow_aces = _parse_kv_all(line, "ace")
    deny_aces = _parse_kv_all(line, "deny_ace")
    use_any = re.search(r"\ballow_recursion\b.*\bany\b", line) is not None

    grid_dns_list = [as_dict(g) async for g in ctx.client.grid.grid_dns.list()]
    if not grid_dns_list:
        print("  Error: no grid:dns object found")
        return
    ref = grid_dns_list[0]["_ref"]

    body: dict = {"allow_recursive_query": True}
    if acl_name:
        # Undocumented but valid: an entry with only `_ref` pointing at a
        # namedacl object makes grid:dns.recursive_query_list behave as the
        # UI's 'Named ACL' radio (verified by capturing the UI's WAPI PUT).
        acls = [as_dict(a) async for a in ctx.client.acl.namedacl.list(name=acl_name)]
        if not acls:
            print(f"  No named ACL found: {acl_name}")
            return
        body["recursive_query_list"] = [{"_ref": acls[0]["_ref"]}]
        summary = f"named ACL: {acl_name}"
    elif allow_aces or deny_aces:
        entries = [
            {"_struct": "addressac", "address": a, "permission": "ALLOW"} for a in allow_aces
        ]
        entries += [{"_struct": "addressac", "address": a, "permission": "DENY"} for a in deny_aces]
        body["recursive_query_list"] = entries
        summary = f"{len(entries)} ACE(s)"
    elif use_any:
        body["recursive_query_list"] = [
            {"_struct": "addressac", "address": "Any", "permission": "ALLOW"}
        ]
        summary = "Any"
    else:
        print("  Error: specify one of: any, acl=<name>, ace=<cidr>, deny_ace=<cidr>")
        return

    await ctx.client.grid.grid_dns.update(ref, body)
    print(f"  grid:dns Allow Recursion set to {summary}")


# ---------------------------------------------------------------------------
# configure grid <name> dhcp set <key>=<value>
# ---------------------------------------------------------------------------


@command(
    "configure grid <name> dhcp set",
    words="<key>=<value>",
    help="Set arbitrary grid DHCP config fields via key=value pass-through.",
)
async def cli_set_grid_dhcp(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return
    await _grid_set(ctx, "grid_dhcpproperties", " dhcp set ", line)


# ---------------------------------------------------------------------------
# show grid <name> threat_insight
# configure grid <name> threat_insight set <key>=<value>
# ---------------------------------------------------------------------------


@command(
    "show grid <name> threat_insight",
    words="<cr>",
    help="Show grid-level Threat Insight settings.",
)
async def cli_show_grid_threatinsight(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return

    results = [
        as_dict(r)
        async for r in ctx.client.grid.grid_threatinsight.list(
            return_fields_plus=["name"],
        )
    ]

    for r in results:
        parts = []
        if r.get("name"):
            parts.append(f"name={r['name']}")
        print(" ".join(parts) if parts else "  (no threat insight data)")


@command(
    "configure grid <name> threat_insight set",
    words="<key>=<value>",
    help="Set grid Threat Insight fields via key=value pass-through.",
)
async def cli_set_grid_threatinsight(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return
    await _grid_set(ctx, "grid_threatinsight", " threat_insight set ", line)


# ---------------------------------------------------------------------------
# show grid <name> threat_protection
# configure grid <name> threat_protection set <key>=<value>
# ---------------------------------------------------------------------------


@command(
    "show grid <name> threat_protection",
    words="<cr>",
    help="Show grid-level Threat Protection settings.",
)
async def cli_show_grid_threatprotection(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return

    results = [
        as_dict(r)
        async for r in ctx.client.grid.grid_threatprotection.list(
            return_fields_plus=["current_ruleset", "disable_multiple_dns_tcp_request"],
        )
    ]

    for r in results:
        parts = []
        if r.get("current_ruleset"):
            parts.append(f"current_ruleset={r['current_ruleset']}")
        if "disable_multiple_dns_tcp_request" in r:
            parts.append(
                f"disable_multiple_dns_tcp_request={r['disable_multiple_dns_tcp_request']}"
            )
        print(" ".join(parts) if parts else "  (no threat protection data)")


@command(
    "configure grid <name> threat_protection set",
    words="<key>=<value>",
    help="Set grid Threat Protection fields via key=value pass-through.",
)
async def cli_set_grid_threatprotection(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return
    await _grid_set(ctx, "grid_threatprotection", " threat_protection set ", line)


# ---------------------------------------------------------------------------
# show grid <name> file_distribution
# configure grid <name> file_distribution set <key>=<value>
# ---------------------------------------------------------------------------


@command(
    "show grid <name> file_distribution",
    words="<cr>",
    help="Show grid-level file distribution settings.",
)
async def cli_show_grid_filedistribution(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return

    results = [
        as_dict(r)
        async for r in ctx.client.grid.grid_filedistribution.list(
            return_fields_plus=["name"],
        )
    ]

    for r in results:
        parts = []
        if r.get("name"):
            parts.append(f"name={r['name']}")
        print(" ".join(parts) if parts else "  (no file distribution data)")


@command(
    "configure grid <name> file_distribution set",
    words="<key>=<value>",
    help="Set grid file distribution fields via key=value pass-through.",
)
async def cli_set_grid_filedistribution(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return
    await _grid_set(ctx, "grid_filedistribution", " file_distribution set ", line)


# ===========================================================================
# Chunk D - Grid license pool + x509 certificate + service-restart observability
# ===========================================================================

# ---------------------------------------------------------------------------
# show grid <name> license_pool
# ---------------------------------------------------------------------------


@command(
    "show grid <name> license_pool",
    words="<cr>",
    help="Show grid license pool container.",
)
async def cli_show_grid_license_pool(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return

    results = [
        as_dict(r)
        async for r in ctx.client.grid.grid_license_pool_container.list(
            return_fields_plus=["lpc_uid", "last_entitlement_update"],
        )
    ]

    for r in results:
        parts = []
        if r.get("lpc_uid"):
            parts.append(f"lpc_uid={r['lpc_uid']}")
        if r.get("last_entitlement_update"):
            parts.append(f"last_entitlement_update={r['last_entitlement_update']}")
        print(" ".join(parts) if parts else "  (no license pool data)")


# ---------------------------------------------------------------------------
# show grid <name> certificate
# configure grid <name> certificate delete <serial>
# ---------------------------------------------------------------------------


@command(
    "show grid <name> certificate",
    words="<cr>",
    help="Show grid X.509 certificates.",
)
async def cli_show_grid_certificate(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return

    results = [
        as_dict(r)
        async for r in ctx.client.grid.grid_x509certificate.list(
            return_fields_plus=[
                "subject",
                "issuer",
                "serial",
                "valid_not_before",
                "valid_not_after",
            ],
        )
    ]

    for r in results:
        parts = []
        if r.get("serial"):
            parts.append(f"serial={r['serial']}")
        if r.get("subject"):
            parts.append(f"subject={r['subject']}")
        if r.get("issuer"):
            parts.append(f"issuer={r['issuer']}")
        if r.get("valid_not_after"):
            parts.append(f"valid_not_after={r['valid_not_after']}")
        print(" ".join(parts))


@command(
    "configure grid <name> certificate delete <serial>",
    words="<cr>",
    help="Delete a grid X.509 certificate by serial number.",
)
async def cli_delete_grid_certificate(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return

    m = re.search(r"\bcertificate\s+delete\s+(\S+)", line)
    if not m:
        print("  Error: certificate serial required")
        return
    serial = m.group(1)

    results = [as_dict(r) async for r in ctx.client.grid.grid_x509certificate.list(serial=serial)]
    if not results:
        print(f"  No certificate found with serial: {serial}")
        return
    ref = results[0]["_ref"]
    await ctx.client.grid.grid_x509certificate.delete(ref)
    print(f"  Deleted certificate {serial}")


# ---------------------------------------------------------------------------
# show grid <name> restart status / group / request
# ---------------------------------------------------------------------------


@command(
    "show grid <name> restart status",
    words="<cr>",
    help="Show grid service-restart status summary.",
)
async def cli_show_grid_restart_status(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return

    results = [
        as_dict(r)
        async for r in ctx.client.grid.grid_servicerestart_status.list(
            return_fields_plus=["parent", "pending", "success", "failures"],
        )
    ]

    for r in results:
        parts = []
        if r.get("parent"):
            parts.append(f"parent={r['parent']}")
        if r.get("pending") is not None:
            parts.append(f"pending={r['pending']}")
        if r.get("success") is not None:
            parts.append(f"success={r['success']}")
        if r.get("failures") is not None:
            parts.append(f"failures={r['failures']}")
        print(" ".join(parts) if parts else "  (no restart status)")


@command(
    "show grid <name> restart group",
    words="<cr>",
    help="Show grid service-restart groups.",
)
async def cli_show_grid_restart_group(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return

    results = [
        as_dict(r)
        async for r in ctx.client.grid.grid_servicerestart_group.list(
            return_fields_plus=["name", "comment", "service", "mode"],
        )
    ]

    for r in results:
        parts = []
        if r.get("name"):
            parts.append(f"name={r['name']}")
        if r.get("service"):
            parts.append(f"service={r['service']}")
        if r.get("mode"):
            parts.append(f"mode={r['mode']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))


@command(
    "show grid <name> restart request",
    words="<cr>",
    help="Show pending/recent grid service-restart requests.",
)
async def cli_show_grid_restart_request(line: str, ctx: Context) -> None:
    if not _require_connected(ctx):
        return

    results = [
        as_dict(r)
        async for r in ctx.client.grid.grid_servicerestart_request.list(
            return_fields_plus=["member", "service", "state", "result"],
        )
    ]

    for r in results:
        parts = []
        if r.get("member"):
            parts.append(f"member={r['member']}")
        if r.get("service"):
            parts.append(f"service={r['service']}")
        if r.get("state"):
            parts.append(f"state={r['state']}")
        if r.get("result"):
            parts.append(f"result={r['result']}")
        print(" ".join(parts))
