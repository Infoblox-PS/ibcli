# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

import re

# Waypoints for the zone command tree.
from ibcli import completions as _completions
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict, is_arpa, net_to_arpa

register("configure", words="zone", help="Create, modify or delete grid objects.")
register(
    "configure zone",
    words="add <zone>",
    dynamic=_completions.zones,
    help="Authoritative DNS zones + their records. 'zone add' accepts FQDNs or in-addr.arpa for reverse zones.",
)
register("configure zone add", words="<zone>")

_ZONE_ADD_WORDS = (
    "<cr> comment=<comment>|primary=<name>|secondary=<name>|"
    "ns_group=<name>|srg=<name>|view=<name>|forward_to=<name,ip>|"
    "delegate_to=<name,ip>|stub_from=<name,ip>|"
    "import_from=<ip>|do_host_abstraction=<value>|"
    "create_ptr_for_hosts=<value>|"
    "set"
)

register("configure zone add <zone>", words=_ZONE_ADD_WORDS)

# Register set <key> <value> chain up to 16 pairs deep for zone add.
_ZONE_ADD_BASE = "configure zone add <zone>"
for _depth in range(16):
    _pfx = _ZONE_ADD_BASE + (" set <name> <value>" * _depth)
    register(f"{_pfx} set", words="<name>")
    register(f"{_pfx} set <name>", words="<value>")
    register(f"{_pfx} set <name> <value>", words=_ZONE_ADD_WORDS)


def _parse_kv(line: str, key: str) -> str | None:
    m = re.search(rf"\b{re.escape(key)}\s+(\S+)", line)
    return m.group(1) if m else None


def _parse_kv_all(line: str, key: str) -> list[str]:
    return re.findall(rf"\b{re.escape(key)}\s+(\S+)", line)


def _parse_comment(line: str) -> str | None:
    m = re.search(r'\bcomment\s+"([^"]+)"', line)
    if m:
        return m.group(1)
    m = re.search(r"\bcomment\s+(\S+)", line)
    return m.group(1) if m else None


def _parse_extattrs(line: str) -> dict[str, dict[str, str]]:
    """Parse all `set key value` pairs into a WAPI extattrs dict.

    Mirrors the same helper in network.py - supports both the tokenizer-
    expanded form ``set key value`` and the raw ``set key=value`` form.
    """
    result: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"\bset\s+(\S+)\s+(\S+)", line):
        k, v = m.group(1), m.group(2)
        if "=" not in k:
            result[k] = {"value": v}
    for m in re.finditer(r"\bset\s+(\S+)=(\S+)", line):
        k, v = m.group(1), m.group(2)
        result[k] = {"value": v}
    return result


def _split_name_ip(raw: str) -> dict[str, str]:
    """'ns1,1.2.3.4' -> {'name': 'ns1', 'address': '1.2.3.4'}."""
    name, _, address = raw.partition(",")
    return {"name": name, "address": address}


def _zone_resource(ctx: Context, objtype: str):
    """Return the SDK resource for the given zone objtype string."""
    return {
        "zone_auth": ctx.client.dns.zone_auth,
        "zone_forward": ctx.client.dns.zone_forward,
        "zone_delegated": ctx.client.dns.zone_delegated,
        "zone_stub": ctx.client.dns.zone_stub,
    }[objtype]


def _record_resource(ctx: Context, objtype: str):
    """Return the SDK resource for the given record objtype string."""
    return {
        "record:host": ctx.client.dns.record_host,
        "record:a": ctx.client.dns.record_a,
        "record:aaaa": ctx.client.dns.record_aaaa,
        "record:cname": ctx.client.dns.record_cname,
        "record:mx": ctx.client.dns.record_mx,
        "record:txt": ctx.client.dns.record_txt,
        "record:srv": ctx.client.dns.record_srv,
        "record:ptr": ctx.client.dns.record_ptr,
    }[objtype]


@command("configure zone add <zone>", words=_ZONE_ADD_WORDS, help="Add a DNS zone.")
async def cli_add_zone(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bzone add (\S+)", line)
    if not m:
        print("  Error: zone name required")
        return
    zone = m.group(1)

    # Reverse-zone rewrite: CIDR -> arpa form.
    if "/" in zone and not is_arpa(zone):
        zone = net_to_arpa(zone)

    forwards = _parse_kv_all(line, "forward_to")
    delegates = _parse_kv_all(line, "delegate_to")
    stubs = _parse_kv_all(line, "stub_from")

    if forwards:
        objtype = "zone_forward"
        body: dict = {"fqdn": zone, "forward_to": [_split_name_ip(x) for x in forwards]}
    elif delegates:
        objtype = "zone_delegated"
        body = {"fqdn": zone, "delegate_to": [_split_name_ip(x) for x in delegates]}
    elif stubs:
        objtype = "zone_stub"
        body = {"fqdn": zone, "stub_from": [_split_name_ip(x) for x in stubs]}
    else:
        objtype = "zone_auth"
        body = {"fqdn": zone}
        if is_arpa(zone):
            body["zone_format"] = "IPV6" if zone.lower().endswith(".ip6.arpa") else "IPV4"

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    ns_group = _parse_kv(line, "ns_group")
    if ns_group:
        body["ns_group"] = ns_group
    primary = _parse_kv(line, "primary")
    if primary:
        body["grid_primary"] = [{"name": primary}]
    secondaries = _parse_kv_all(line, "secondary")
    if secondaries:
        body["grid_secondaries"] = [{"name": s} for s in secondaries]
    srgs = _parse_kv_all(line, "srg")
    if srgs:
        body["srgs"] = srgs
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas

    # AXFR-based zone import - NIOS will pull zone data from `import_from`
    # via a DNS zone transfer after the create. Only meaningful on auth zones.
    if objtype == "zone_auth":
        import_from = _parse_kv(line, "import_from")
        if import_from:
            body["import_from"] = import_from
            body["use_import_from"] = True
            host_abs = _parse_kv(line, "do_host_abstraction")
            if host_abs is not None:
                body["do_host_abstraction"] = host_abs.lower() == "true"
            create_ptr = _parse_kv(line, "create_ptr_for_hosts")
            if create_ptr is not None:
                body["create_ptr_for_hosts"] = create_ptr.lower() == "true"

    await _zone_resource(ctx, objtype).create(body)


# Bind handler to every static set-chain endpoint for zone add.
for _depth in range(1, 17):
    _ml = _ZONE_ADD_BASE + (" set <name> <value>" * _depth)
    command(_ml, words=_ZONE_ADD_WORDS)(cli_add_zone)


register(
    "show",
    words="time debug server grid zone network record views",
    help="Read grid state without modifying anything.",
)
register(
    "show zone", words="<cr> <zone>|view=<name>", help="Authoritative zones (forward + reverse)."
)


_ZONE_TYPES_FALLBACK = ("zone_auth", "zone_forward", "zone_delegated", "zone_stub")


@command(
    "show zone",
    words="<cr> <zone>|view=<name>|forward|secondary|detailed",
    help="Show one or more zones.",
)
@command("show zone <zone>", words="<cr> view=<name>|detailed", help="Show a specific zone.")
async def cli_show_zone(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    fqdn = None
    if len(tokens) >= 3 and not tokens[2].startswith("<"):
        candidate = tokens[2]
        if not candidate.endswith("=") and "=" not in candidate:
            if candidate not in ("forward", "secondary", "detailed", "view"):
                fqdn = candidate

    view = _parse_kv(line, "view")
    params: dict[str, str] = {}
    if fqdn:
        if "/" in fqdn and not is_arpa(fqdn):
            fqdn = net_to_arpa(fqdn)
        params["fqdn"] = fqdn
    if view:
        params["view"] = view

    wanted_types = _ZONE_TYPES_FALLBACK
    if "forward" in tokens:
        wanted_types = ("zone_forward",)
    elif "secondary" in tokens:
        wanted_types = ("zone_auth",)  # secondaries are auth zones with a secondary member

    _rfields = ["fqdn", "comment", "view", "zone_format"]
    for objtype in wanted_types:
        resource = _zone_resource(ctx, objtype)
        zones = [
            as_dict(r)
            async for r in resource.list(
                return_fields_plus=_rfields,
                **params,
            )
        ]
        if zones:
            for z in zones:
                _print_zone(z, objtype)
            return

    if fqdn:
        print(f"  No zone found: {fqdn}")


def _print_zone(z: dict, objtype: str) -> None:
    parts = [f"type={objtype.replace('zone_', '')}", f"fqdn={z.get('fqdn', '')}"]
    if z.get("view"):
        parts.append(f"view={z['view']}")
    if z.get("comment"):
        parts.append(f"comment={z['comment']}")
    print(" ".join(parts))


register("configure zone <zone>", words="add modify delete rename dnssec")

_ZONE_MODIFY_WORDS = (
    "<cr> comment=<comment>|primary=<name>|secondary=<name>|"
    "ns_group=<name>|srg=<name>|view=<name>|set"
)

register("configure zone <zone> modify", words=_ZONE_MODIFY_WORDS)

# Register set chain for zone modify.
_ZONE_MOD_BASE = "configure zone <zone> modify"
for _depth in range(16):
    _pfx = _ZONE_MOD_BASE + (" set <name> <value>" * _depth)
    register(f"{_pfx} set", words="<name>")
    register(f"{_pfx} set <name>", words="<value>")
    register(f"{_pfx} set <name> <value>", words=_ZONE_MODIFY_WORDS)


async def _find_zone_ref(ctx: Context, zone: str, view: str | None) -> tuple[str, str] | None:
    """Return (objtype, _ref) or None. Searches zone types in fallback order."""
    if "/" in zone and not is_arpa(zone):
        zone = net_to_arpa(zone)
    params: dict[str, str] = {"fqdn": zone}
    if view:
        params["view"] = view
    for objtype in _ZONE_TYPES_FALLBACK:
        resource = _zone_resource(ctx, objtype)
        results = [as_dict(r) async for r in resource.list(max_results=1, **params)]
        if results:
            return (objtype, results[0]["_ref"])
    return None


@command("configure zone <zone> modify", words=_ZONE_MODIFY_WORDS, help="Modify an existing zone.")
async def cli_modify_zone(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bzone (\S+) modify", line)
    if not m:
        print("  Error: zone name required")
        return
    zone = m.group(1)
    view = _parse_kv(line, "view")
    ref_info = await _find_zone_ref(ctx, zone, view)
    if ref_info is None:
        print(f"  No zone found: {zone}")
        return
    _objtype, ref = ref_info

    body: dict = {}
    comment = _parse_comment(line)
    if comment is not None:
        body["comment"] = comment
    ns_group = _parse_kv(line, "ns_group")
    if ns_group:
        body["ns_group"] = ns_group
    primary = _parse_kv(line, "primary")
    if primary:
        body["grid_primary"] = [{"name": primary}]
    secondaries = _parse_kv_all(line, "secondary")
    if secondaries:
        body["grid_secondaries"] = [{"name": s} for s in secondaries]
    srgs = _parse_kv_all(line, "srg")
    if srgs:
        body["srgs"] = srgs
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    if not body:
        print("  Nothing to modify (no fields specified)")
        return

    await _zone_resource(ctx, _objtype).update(ref, body)


# Bind handler to every static set-chain endpoint for zone modify.
for _depth in range(1, 17):
    _ml = _ZONE_MOD_BASE + (" set <name> <value>" * _depth)
    command(_ml, words=_ZONE_MODIFY_WORDS)(cli_modify_zone)


register("configure zone <zone> add", words="host a aaaa cname mx txt ptr")
register("configure zone <zone> add host", words="<name>")
register("configure zone <zone> add host <name>", words="<ip>")

_HOST_ADD_WORDS = (
    "<cr> mac=<mac>|fixed|ip=<ip>|ipv6=<name>|alias=<name>|comment=<comment>|view=<name>|set"
)

# Register set chain for host add.
_HOST_ADD_BASE = "configure zone <zone> add host <name> <ip>"
for _depth in range(16):
    _pfx = _HOST_ADD_BASE + (" set <name> <value>" * _depth)
    register(f"{_pfx} set", words="<name>")
    register(f"{_pfx} set <name>", words="<value>")
    register(f"{_pfx} set <name> <value>", words=_HOST_ADD_WORDS)
register("configure zone <zone> delete", words="<cr> host a aaaa cname mx txt ptr view=<name>")


def _fqdn(zone: str, name: str) -> str:
    if name.endswith("." + zone) or name == zone:
        return name
    return f"{name}.{zone}"


@command(
    "configure zone <zone> add host <name> <ip>", words=_HOST_ADD_WORDS, help="Add a host record."
)
async def cli_add_host(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bzone (\S+) add host (\S+) (\S+)", line)
    if not m:
        return
    zone, name, ip = m.group(1), m.group(2), m.group(3)
    ipv4addr: dict = {"ipv4addr": ip}
    mac = _parse_kv(line, "mac")
    if mac:
        ipv4addr["mac"] = mac
    fixed = re.search(r"\bfixed\b", line) is not None
    if fixed and mac:
        ipv4addr["configure_for_dhcp"] = True

    ipv4s = [ipv4addr]
    for extra in _parse_kv_all(line, "ip"):
        ipv4s.append({"ipv4addr": extra})

    ipv6s = [{"ipv6addr": v} for v in _parse_kv_all(line, "ipv6")]

    aliases = _parse_kv_all(line, "alias")
    alias_fqdns = [_fqdn(zone, a) for a in aliases]

    body: dict = {"name": _fqdn(zone, name), "ipv4addrs": ipv4s}
    if ipv6s:
        body["ipv6addrs"] = ipv6s
    if alias_fqdns:
        body["aliases"] = alias_fqdns
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas

    await ctx.client.dns.record_host.create(body)


# Bind handler to every static set-chain endpoint for host add.
for _depth in range(1, 17):
    _ml = _HOST_ADD_BASE + (" set <name> <value>" * _depth)
    command(_ml, words=_HOST_ADD_WORDS)(cli_add_host)


register("configure zone <zone> modify", words="host")
register("configure zone <zone> modify host", words="<name>")

# Zone copy - clones records from an existing zone into another zone on
# the same grid via WAPI's copy_zone_records function.
register("configure zone <zone>", words="copy")
register("configure zone <zone> copy", words="from")
register("configure zone <zone> copy from", words="<zone>")
register("configure zone <zone> copy from <zone>", words="<cr> view=<name>|source_view=<name>")


@command(
    "configure zone <zone> copy from <zone>",
    words="<cr> view=<name>|source_view=<name>",
    help=(
        "Clone records from a source zone into this zone. Calls "
        "zone_auth?_function=copyzonerecords on the source, passing "
        "destination_zone=<dst-ref>. Both zones must already exist; "
        "target and source can live in different views (source_view=)."
    ),
)
async def cli_zone_copy(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bzone (\S+) copy from (\S+)", line)
    if not m:
        print("  Error: destination and source zones required")
        return
    dst, src = m.group(1), m.group(2)
    view = _parse_kv(line, "view")
    src_view = _parse_kv(line, "source_view") or view
    # Resolve the destination zone ref.
    dst_params: dict[str, str] = {"fqdn": dst}
    if view:
        dst_params["view"] = view
    dst_zones = [as_dict(r) async for r in ctx.client.dns.zone_auth.list(**dst_params)]
    if not dst_zones:
        print(f"  No destination zone found: {dst}")
        return
    dst_ref = dst_zones[0]["_ref"]

    # Resolve the source zone ref.
    src_params: dict[str, str] = {"fqdn": src}
    if src_view:
        src_params["view"] = src_view
    src_zones = [as_dict(r) async for r in ctx.client.dns.zone_auth.list(**src_params)]
    if not src_zones:
        print(f"  No source zone found: {src}")
        return
    src_ref = src_zones[0]["_ref"]

    # WAPI semantics: copyzonerecords is called on the SOURCE zone, with
    # destination_zone pointing at where the records should go.
    await ctx.client.dns.zone_auth.call_function(
        src_ref,
        "copyzonerecords",
        destination_zone=dst_ref,
    )


# Host rename - separate verb because `name` is part of the _ref and NIOS
# treats the PUT as a rename rather than a field update.
register("configure zone <zone> rename", words="host")
register("configure zone <zone> rename host", words="<name>")
register("configure zone <zone> rename host <name>", words="<name>")
register("configure zone <zone> rename host <name> <name>", words="<cr> view=<name>")

# DNSSEC zone operations - POST <zone_auth>?_function=dnssec_operation
_DNSSEC_OPS = "sign unsign rollover_ksk rollover_zsk"
register("configure zone <zone> dnssec", words=_DNSSEC_OPS)
for _op in _DNSSEC_OPS.split():
    register(f"configure zone <zone> dnssec {_op}", words="<cr> view=<name>")
_HOST_MOD_WORDS = (
    "<cr> add-alias=<name>|remove-alias=<name>|"
    "add-ip=<ip>|remove-ip=<ip>|"
    "add-ipv6=<name>|remove-ipv6=<name>|"
    "comment=<comment>|view=<name>|disable=<value>"
)
register("configure zone <zone> modify host <name>", words=_HOST_MOD_WORDS)


async def _find_host_ref(
    ctx: Context, zone: str, name: str, view: str | None
) -> tuple[str, dict] | None:
    params: dict[str, str] = {"name": _fqdn(zone, name)}
    if view:
        params["view"] = view
    hosts = [
        as_dict(r)
        async for r in ctx.client.dns.record_host.list(
            return_fields_plus=["ipv4addrs", "ipv6addrs", "aliases", "comment", "disable", "view"],
            **params,
        )
    ]
    if not hosts:
        return None
    return hosts[0]["_ref"], hosts[0]


@command(
    "configure zone <zone> modify host <name>",
    words=_HOST_MOD_WORDS,
    help=(
        "Modify an existing host record. Supports incremental "
        "add-alias/remove-alias, add-ip/remove-ip, "
        "add-ipv6/remove-ipv6, plus comment/disable changes. "
        "Reads the record, mutates the lists, then PUTs the result."
    ),
)
async def cli_modify_host(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bzone (\S+) modify host (\S+)", line)
    if not m:
        return
    zone, name = m.group(1), m.group(2)
    view = _parse_kv(line, "view")

    found = await _find_host_ref(ctx, zone, name, view)
    if not found:
        print(f"  No host record found: {_fqdn(zone, name)}")
        return
    ref, record = found

    update: dict = {}

    # Aliases - incremental add/remove, preserving existing entries.
    aliases = list(record.get("aliases") or [])
    changed_aliases = False
    for a in _parse_kv_all(line, "add-alias"):
        fqdn = _fqdn(zone, a)
        if fqdn not in aliases:
            aliases.append(fqdn)
            changed_aliases = True
    for a in _parse_kv_all(line, "remove-alias"):
        fqdn = _fqdn(zone, a)
        if fqdn in aliases:
            aliases.remove(fqdn)
            changed_aliases = True
    if changed_aliases:
        update["aliases"] = aliases

    # Strip server-computed fields from host_ipv4addr / host_ipv6addr structs
    # before PUT. NIOS rejects writes to `_ref`, `host`, `uuid`, etc. Use an
    # allow-list to keep only fields the user might have set.
    _V4_WRITABLE = {
        "ipv4addr",
        "mac",
        "configure_for_dhcp",
        "bootfile",
        "bootserver",
        "nextserver",
        "use_bootfile",
        "use_bootserver",
        "use_nextserver",
        "match_client",
        "options",
        "comment",
    }
    _V6_WRITABLE = {"ipv6addr", "configure_for_dhcp", "duid", "options", "comment"}

    def _strip_ip(e: dict, writable: set[str]) -> dict:
        return {k: v for k, v in e.items() if k in writable}

    # IPv4s - list of {ipv4addr: …, configure_for_dhcp: …, mac: …} structs.
    v4s = [_strip_ip(e, _V4_WRITABLE) for e in (record.get("ipv4addrs") or [])]
    v4set = {e.get("ipv4addr") for e in v4s}
    changed_v4 = False
    for ip in _parse_kv_all(line, "add-ip"):
        if ip not in v4set:
            v4s.append({"ipv4addr": ip})
            v4set.add(ip)
            changed_v4 = True
    for ip in _parse_kv_all(line, "remove-ip"):
        if ip in v4set:
            v4s = [e for e in v4s if e.get("ipv4addr") != ip]
            v4set.discard(ip)
            changed_v4 = True
    if changed_v4:
        update["ipv4addrs"] = v4s

    # IPv6s.
    v6s = [_strip_ip(e, _V6_WRITABLE) for e in (record.get("ipv6addrs") or [])]
    v6set = {e.get("ipv6addr") for e in v6s}
    changed_v6 = False
    for ip in _parse_kv_all(line, "add-ipv6"):
        if ip not in v6set:
            v6s.append({"ipv6addr": ip})
            v6set.add(ip)
            changed_v6 = True
    for ip in _parse_kv_all(line, "remove-ipv6"):
        if ip in v6set:
            v6s = [e for e in v6s if e.get("ipv6addr") != ip]
            v6set.discard(ip)
            changed_v6 = True
    if changed_v6:
        update["ipv6addrs"] = v6s

    comment = _parse_comment(line)
    if comment is not None:
        update["comment"] = comment
    disable = _parse_kv(line, "disable")
    if disable is not None:
        update["disable"] = disable.lower() == "true"

    if not update:
        print("  Nothing to modify (no fields specified)")
        return

    await ctx.client.dns.record_host.update(ref, update)


@command(
    "configure zone <zone> rename host <name> <name>",
    words="<cr> view=<name>",
    help=(
        "Rename a host record. The old name is relative to the zone; "
        "the new name may be relative or a fully-qualified FQDN. "
        "NIOS preserves IPs, aliases, EAs, and comment across the "
        "rename - only the record's name changes."
    ),
)
async def cli_rename_host(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bzone (\S+) rename host (\S+) (\S+)", line)
    if not m:
        print("  Error: old and new names required")
        return
    zone, old, new = m.group(1), m.group(2), m.group(3)
    view = _parse_kv(line, "view")

    found = await _find_host_ref(ctx, zone, old, view)
    if not found:
        print(f"  No host record found: {_fqdn(zone, old)}")
        return
    ref, _ = found

    new_fqdn = (
        _fqdn(zone, new)
        if "." not in new or not new.endswith(zone)
        else (new if new.endswith(zone) else f"{new}.{zone}")
    )
    if new_fqdn == _fqdn(zone, old):
        print("  Nothing to rename (new name equals old name)")
        return

    await ctx.client.dns.record_host.update(ref, {"name": new_fqdn})


@command(
    "configure zone <zone> dnssec sign",
    words="<cr> view=<name>",
    help="Sign an auth zone (POST <zone_auth>?_function=dnssec_operation SIGN).",
)
@command(
    "configure zone <zone> dnssec unsign", words="<cr> view=<name>", help="Unsign an auth zone."
)
@command(
    "configure zone <zone> dnssec rollover_ksk",
    words="<cr> view=<name>",
    help="Roll the KSK on an auth zone.",
)
@command(
    "configure zone <zone> dnssec rollover_zsk",
    words="<cr> view=<name>",
    help="Roll the ZSK on an auth zone.",
)
async def cli_zone_dnssec(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bzone (\S+) dnssec (\S+)", line)
    if not m:
        print("  Error: dnssec operation required")
        return
    zone, op = m.group(1), m.group(2).lower()
    wapi_op = {
        "sign": "SIGN",
        "unsign": "UNSIGN",
        "rollover_ksk": "ROLLOVER_KSK",
        "rollover_zsk": "ROLLOVER_ZSK",
    }.get(op)
    if wapi_op is None:
        print(f"  Error: unknown dnssec operation '{op}'")
        return
    view = _parse_kv(line, "view")

    params: dict[str, str] = {"fqdn": zone}
    if view:
        params["view"] = view
    zones = [as_dict(r) async for r in ctx.client.dns.zone_auth.list(**params)]
    if not zones:
        print(f"  No auth zone found: {zone}")
        return
    ref = zones[0]["_ref"]
    await ctx.client.dns.zone_auth.call_function(
        ref,
        "dnssec_operation",
        operation=wapi_op,
    )


register("configure zone <zone> delete host", words="<name>")


@command(
    "configure zone <zone> delete host <name>",
    words="<cr> view=<name>",
    help="Delete a host record.",
)
async def cli_delete_host(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bzone (\S+) delete host (\S+)", line)
    if not m:
        return
    zone, name = m.group(1), m.group(2)
    view = _parse_kv(line, "view")
    params: dict[str, str] = {"name": _fqdn(zone, name)}
    if view:
        params["view"] = view
    records = [as_dict(r) async for r in ctx.client.dns.record_host.list(**params)]
    if not records:
        print(f"  No host found: {params['name']}")
        return
    await ctx.client.dns.record_host.delete(records[0]["_ref"])


# Record-type metadata: (WAPI objtype, ip-field-name)
_SIMPLE_RECORDS = {
    "a": ("record:a", "ipv4addr"),
    "aaaa": ("record:aaaa", "ipv6addr"),
    "cname": ("record:cname", "canonical"),
    "txt": ("record:txt", "text"),
}


for _rec, (_obj, _field) in _SIMPLE_RECORDS.items():
    register(f"configure zone <zone> add {_rec}", words="<name>")
    register(f"configure zone <zone> add {_rec} <name>", words="<value>")
    register(f"configure zone <zone> delete {_rec}", words="<name>")


async def _add_simple_record(rec: str, line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    objtype, field = _SIMPLE_RECORDS[rec]
    # Capture: zone, name, then value (which may be quoted or a plain token)
    m = re.search(rf'\bzone (\S+) add {rec} (\S+) (".+?"|\S+)', line)
    if not m:
        print(f"  Error: zone, name, and {field} required")
        return
    zone, name, value = m.group(1), m.group(2), m.group(3).strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    body: dict = {"name": _fqdn(zone, name), field: value}
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    await _record_resource(ctx, objtype).create(body)


async def _delete_simple_record(rec: str, line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    objtype, _field = _SIMPLE_RECORDS[rec]
    m = re.search(rf"\bzone (\S+) delete {rec} (\S+)", line)
    if not m:
        return
    zone, name = m.group(1), m.group(2)
    view = _parse_kv(line, "view")
    params: dict[str, str] = {"name": _fqdn(zone, name)}
    if view:
        params["view"] = view
    resource = _record_resource(ctx, objtype)
    records = [as_dict(r) async for r in resource.list(**params)]
    if not records:
        print(f"  No {rec} record found: {params['name']}")
        return
    await resource.delete(records[0]["_ref"])


# Bind handlers for each simple-record type.
for _rec in _SIMPLE_RECORDS:

    def _make_add(rec=_rec):
        async def _h(line: str, ctx: Context) -> None:
            await _add_simple_record(rec, line, ctx)

        return _h

    def _make_del(rec=_rec):
        async def _h(line: str, ctx: Context) -> None:
            await _delete_simple_record(rec, line, ctx)

        return _h

    command(
        f"configure zone <zone> add {_rec} <name> <value>",
        words="<cr> view=<name>|comment=<comment>",
    )(_make_add())
    command(f"configure zone <zone> delete {_rec} <name>", words="<cr> view=<name>")(_make_del())


register("configure zone <zone> add mx", words="<name>")
register("configure zone <zone> add mx <name>", words="<canonical>")
register("configure zone <zone> add mx <name> <canonical>", words="<priority>")
register("configure zone <zone> add ptr", words="<ipany>")
register("configure zone <zone> add ptr <ipany>", words="<name>")
register("configure zone <zone> delete mx", words="<name>")
register("configure zone <zone> delete ptr", words="<ipany>")


@command(
    "configure zone <zone> add mx <name> <canonical> <priority>",
    words="<cr> view=<name>",
    help="Add an MX record.",
)
async def cli_add_mx(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bzone (\S+) add mx (\S+) (\S+) (\d+)", line)
    if not m:
        print("  Error: zone, name, mail_exchanger, preference required")
        return
    zone, name, mx, pref = m.group(1), m.group(2), m.group(3), int(m.group(4))
    body: dict = {"name": _fqdn(zone, name), "mail_exchanger": mx, "preference": pref}
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    await ctx.client.dns.record_mx.create(body)


@command(
    "configure zone <zone> add ptr <ipany> <name>",
    words="<cr> view=<name>",
    help="Add a PTR record. Accepts either an IPv4 or an IPv6 address; "
    "the handler picks ipv4addr / ipv6addr based on which family "
    "the literal parses as.",
)
async def cli_add_ptr(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bzone (\S+) add ptr (\S+) (\S+)", line)
    if not m:
        print("  Error: zone, ip, ptrdname required")
        return
    _zone, ip, ptrdname = m.group(1), m.group(2), m.group(3)
    body: dict = {"ptrdname": ptrdname}
    # Pick the right WAPI key based on the address family. The strict
    # parse happens here (not in the grammar) so the CLI errors out with
    # a clear message rather than a NIOS 400 later.
    import ipaddress

    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        print(f"  Error: {ip!r} is not a valid IP address")
        return
    if parsed.version == 6:
        body["ipv6addr"] = ip
    else:
        body["ipv4addr"] = ip
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    await ctx.client.dns.record_ptr.create(body)


@command("configure zone <zone> delete mx <name>", help="Delete an MX record.")
async def cli_delete_mx(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bzone (\S+) delete mx (\S+)", line)
    if not m:
        return
    zone, name = m.group(1), m.group(2)
    records = [as_dict(r) async for r in ctx.client.dns.record_mx.list(name=_fqdn(zone, name))]
    if not records:
        print(f"  No mx record found: {_fqdn(zone, name)}")
        return
    await ctx.client.dns.record_mx.delete(records[0]["_ref"])


@command("configure zone <zone> delete ptr <ipany>", help="Delete a PTR record (v4 or v6).")
async def cli_delete_ptr(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bzone (\S+) delete ptr (\S+)", line)
    if not m:
        return
    _zone, ip = m.group(1), m.group(2)
    import ipaddress

    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        print(f"  Error: {ip!r} is not a valid IP address")
        return
    key = "ipv6addr" if parsed.version == 6 else "ipv4addr"
    records = [as_dict(r) async for r in ctx.client.dns.record_ptr.list(**{key: ip})]
    if not records:
        print(f"  No ptr record found: {ip}")
        return
    await ctx.client.dns.record_ptr.delete(records[0]["_ref"])


register(
    "show record",
    words="info=<name>|a_record=<name>|aaaa=<name>|cname=<name>|"
    "mx=<name>|txt=<name>|ptr=<value>|srv=<name>|view=<name>",
    help="DNS records - all modern types (CAA, HTTPS, SVCB, NAPTR…).",
)


_SHOW_RECORD_MAP = {
    "a_record": "record:a",
    "aaaa": "record:aaaa",
    "cname": "record:cname",
    "mx": "record:mx",
    "txt": "record:txt",
    "srv": "record:srv",
    "ptr": "record:ptr",
}


async def _show_record(
    objtype: str, param: str, value: str, view: str | None, ctx: Context
) -> None:
    params: dict[str, str] = {param: value}
    if view:
        params["view"] = view
    resource = _record_resource(ctx, objtype)
    records = [as_dict(r) async for r in resource.list(**params)]
    for r in records:
        parts = [f"type={objtype.replace('record:', '')}"]
        for k, v in r.items():
            if k.startswith("_"):
                continue
            parts.append(f"{k}={v}")
        print(" ".join(parts))


for _key in _SHOW_RECORD_MAP:
    register(
        f"show record {_key}=<name>" if _key != "ptr" else "show record ptr=<value>",
        words="<cr> view=<name>",
    )
register("show record info=<name>", words="<cr> view=<name>")


def _bind_show_record(key: str, objtype: str):
    @command(f"show record {key} <name>" if key != "ptr" else "show record ptr <value>")
    async def _h(line: str, ctx: Context) -> None:
        if ctx.client is None:
            print("  Not connected")
            return
        m = re.search(rf"\b{key}\s+(\S+)", line)
        if not m:
            return
        value = m.group(1)
        param = "ipv4addr" if key == "ptr" else "name"
        view = _parse_kv(line, "view")
        await _show_record(objtype, param, value, view, ctx)


for _k, _obj in _SHOW_RECORD_MAP.items():
    _bind_show_record(_k, _obj)


@command("show record info <name>", help="Find any record (host or A) by name.")
async def cli_show_record_info(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\binfo\s+(\S+)", line)
    if not m:
        return
    name = m.group(1)
    view = _parse_kv(line, "view")
    for objtype in ("record:host", "record:a", "record:aaaa", "record:cname"):
        await _show_record(objtype, "name", name, view, ctx)


@command("configure zone <zone> delete", words="<cr> view=<name>", help="Delete a zone.")
async def cli_delete_zone(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bzone (\S+) delete", line)
    if not m:
        print("  Error: zone name required")
        return
    zone = m.group(1)
    view = _parse_kv(line, "view")
    ref_info = await _find_zone_ref(ctx, zone, view)
    if ref_info is None:
        print(f"  No zone found: {zone}")
        return
    _objtype, ref = ref_info

    await _zone_resource(ctx, _objtype).delete(ref)
