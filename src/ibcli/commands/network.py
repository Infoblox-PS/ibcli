# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

import ipaddress
import re

from ibcli import completions as _completions
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import (
    as_dict,
    cidr_family,
    format_extra_field,
    normalize_cidr,
    normalize_cidr_any,
    parse_extra_fields,
)


def _network_objtype(cidr: str, container: bool = False) -> str:
    """Return the WAPI objtype for a CIDR, choosing ipv6* variants for IPv6."""
    fam = cidr_family(cidr)
    if container:
        return "ipv6networkcontainer" if fam == "v6" else "networkcontainer"
    return "ipv6network" if fam == "v6" else "network"


def _ipam_resource(ctx: Context, objtype: str):
    """Return the SDK resource for the given IPAM objtype string."""
    return {
        "network": ctx.client.ipam.network,
        "ipv6network": ctx.client.ipam.ipv6network,
        "networkcontainer": ctx.client.ipam.networkcontainer,
        "ipv6networkcontainer": ctx.client.ipam.ipv6networkcontainer,
    }[objtype]


# Waypoints

register("configure", words="network", help="Create, modify or delete grid objects.")
register(
    "configure network",
    words="add <n.n.n.n/mm>",
    dynamic=_completions.networks,
    help="IPv4/IPv6 networks, ranges, fixed addresses, filters.",
)
register("configure network add", words="<n.n.n.n/mm>")

_NETADD_WORDS = "<cr> comment=<comment>|view=<name>|set|member"
_SET_NAME = "<name>"
_SET_VALUE = "<value>"

register("configure network add <n.n.n.n/mm>", words=_NETADD_WORDS)

# The tokenizer splits "set key=value" into tokens ["set", "key", "value"].
# Register a static chain so the parser can consume up to 16 set-pairs
# before falling back to the regex handler which scrapes all pairs from
# the line.
_SET_BASE = "configure network add <n.n.n.n/mm>"
for _depth in range(16):
    _pfx = _SET_BASE + (" set <name> <value>" * _depth)
    register(f"{_pfx} set", words=_SET_NAME)
    register(f"{_pfx} set <name>", words=_SET_VALUE)
    register(f"{_pfx} set <name> <value>", words=_NETADD_WORDS)

# Member chain: allow "member <ip> member <ip> ..." (up to 16 members).
# At each depth we register the `member` waypoint (words=<ip>) and the
# `member <ip>` endpoint (words=<cr> member|view=<name>) so the parser can keep
# consuming additional `member <ip>` pairs or accept a trailing view= keyword.
_NETADD_MEMBER_WORDS = "<cr> comment=<comment>|view=<name>|member"
_NETADD_MEMBER_BASE = "configure network add <n.n.n.n/mm> member <ip>"
register("configure network add <n.n.n.n/mm> member", words="<ip>")
register(_NETADD_MEMBER_BASE, words=_NETADD_MEMBER_WORDS)
for _depth in range(1, 17):
    _pfx = _NETADD_MEMBER_BASE + (" member <ip>" * _depth)
    _prev = _NETADD_MEMBER_BASE + (" member <ip>" * (_depth - 1))
    register(f"{_prev} member", words="<ip>")
    register(f"{_pfx}", words=_NETADD_MEMBER_WORDS)


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
    """Parse all `set key value` pairs into a WAPI extattrs dict.

    The tokenizer splits bare key=value into two tokens, so by the time the
    handler sees the expanded line, `set owner=alice` has become `set owner alice`.
    Quoted names (`set "DC Location" DC1`) and quoted values both round-trip
    through the tokenizer as single tokens with literal spaces, so the parser
    has to match quoted spans as well as bare \\S+ spans.
    """
    result: dict[str, dict[str, str]] = {}
    # word := "quoted text" | bare_run
    _word = r'(?:"[^"]+"|\S+)'
    # Form 1: already expanded by tokenizer -> "set <key> <value>"
    for m in re.finditer(rf"\bset\s+({_word})\s+({_word})", line):
        k, v = _unquote(m.group(1)), _unquote(m.group(2))
        if "=" not in k:  # skip if key still has '=' (Form 2 below)
            result[k] = {"value": v}
    # Form 2: raw/direct call -> "set key=value"
    for m in re.finditer(r"\bset\s+(\S+)=(\S+)", line):
        k, v = m.group(1), m.group(2)
        result[k] = {"value": v}
    return result


def _unquote(tok: str) -> str:
    if len(tok) >= 2 and tok[0] == '"' and tok[-1] == '"':
        return tok[1:-1]
    return tok


@command(
    "configure network add <n.n.n.n/mm>",
    words="<cr> comment=<comment>|view=<name>|set|member",
    help="Add a DHCP network.",
)
async def cli_add_network(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnetwork add (\S+)", line)
    if not m:
        print("  Error: CIDR required")
        return
    try:
        cidr, _ = normalize_cidr_any(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return

    objtype = _network_objtype(cidr)
    body: dict = {"network": cidr}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    view = _parse_kv(line, "view")
    if view:
        body["network_view"] = view
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    member_ips = re.findall(r"\bmember\s+(\d+\.\d+\.\d+\.\d+)", line)
    if member_ips:
        body["members"] = [{"_struct": "dhcpmember", "ipv4addr": ip} for ip in member_ips]

    await _ipam_resource(ctx, objtype).create(body)


# Bind handler to every static set-chain endpoint so the dispatcher dispatches
# cli_add_network no matter how many "set key value" pairs are on the line.
for _depth in range(1, 17):
    _ml = _SET_BASE + (" set <name> <value>" * _depth)
    command(_ml, words=_NETADD_WORDS)(cli_add_network)

# Bind cli_add_network to every member-chain endpoint (depths 1..16).
command(_NETADD_MEMBER_BASE, words=_NETADD_MEMBER_WORDS)(cli_add_network)
for _depth in range(1, 17):
    _ml = _NETADD_MEMBER_BASE + (" member <ip>" * _depth)
    command(_ml, words=_NETADD_MEMBER_WORDS)(cli_add_network)


# ---------------------------------------------------------------------------
# configure network <n.n.n.n/mm> delete / modify
# ---------------------------------------------------------------------------

register("configure network <n.n.n.n/mm>", words="delete modify extattrs")

# Dedicated extattrs subcommand - discoverable sibling of `modify set`. Both
# write to the same extattrs field; this one just lets users tab-complete to
# `extattrs` instead of needing to know about `modify set`.
register("configure network <n.n.n.n/mm> extattrs", words="set delete")
register("configure network <n.n.n.n/mm> extattrs set", words="<name>")
register("configure network <n.n.n.n/mm> extattrs set <name>", words="<value>")
register("configure network <n.n.n.n/mm> extattrs set <name> <value>", words="<cr> view=<name>")
register("configure network <n.n.n.n/mm> extattrs delete", words="<name>")
register("configure network <n.n.n.n/mm> extattrs delete <name>", words="<cr> view=<name>")
register("configure network <n.n.n.n/mm> delete", words="<cr> view=<name>")
_NETMOD_WORDS = "<cr> comment=<comment>|view=<name>|option=<name>|set"
register("configure network <n.n.n.n/mm> modify", words=_NETMOD_WORDS)
_NETMOD_BASE = "configure network <n.n.n.n/mm> modify"

# Register static set-chain for modify (same pattern as add).
for _depth in range(16):
    _pfx = _NETMOD_BASE + (" set <name> <value>" * _depth)
    register(f"{_pfx} set", words=_SET_NAME)
    register(f"{_pfx} set <name>", words=_SET_VALUE)
    register(f"{_pfx} set <name> <value>", words=_NETMOD_WORDS)


async def _find_network_ref(
    ctx: Context,
    cidr: str,
    view: str | None,
    objtype: str = "network",
) -> tuple[str, dict] | None:
    """Return (_ref, raw_record) for the matching network/container, or None."""
    params: dict[str, str] = {"network": cidr}
    if view:
        params["network_view"] = view
    results = [as_dict(r) async for r in _ipam_resource(ctx, objtype).list(**params)]
    if not results:
        return None
    return (results[0]["_ref"], results[0])


@command(
    "configure network <n.n.n.n/mm> delete", words="<cr> view=<name>", help="Delete a network."
)
async def cli_delete_network(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bnetwork (\S+) delete", line)
    if not m:
        print("  Error: CIDR required")
        return
    try:
        cidr, _ = normalize_cidr_any(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return
    view = _parse_kv(line, "view")
    objtype = _network_objtype(cidr)
    found = await _find_network_ref(ctx, cidr, view, objtype=objtype)
    if found is None:
        print(f"  No network found: {cidr}")
        return
    ref, _ = found
    await _ipam_resource(ctx, objtype).delete(ref)


@command(
    "configure network <n.n.n.n/mm> modify", words=_NETMOD_WORDS, help="Modify an existing network."
)
async def cli_modify_network(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bnetwork (\S+) modify", line)
    if not m:
        print("  Error: CIDR required")
        return
    try:
        cidr, _ = normalize_cidr_any(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return
    view = _parse_kv(line, "view")
    objtype = _network_objtype(cidr)
    found = await _find_network_ref(ctx, cidr, view, objtype=objtype)
    if found is None:
        print(f"  No network found: {cidr}")
        return
    ref, _ = found

    body: dict = {}
    comment = _parse_comment(line)
    if comment is not None:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    opts = _parse_dhcp_options(line)
    if opts is not None:
        body["options"] = opts
    if not body:
        print("  Nothing to modify (no fields specified)")
        return

    await _ipam_resource(ctx, objtype).update(ref, body)


@command(
    "configure network <n.n.n.n/mm> extattrs set <name> <value>",
    words="<cr> view=<name>",
    help=(
        "Set an Extensible Attribute on a network. Merges with "
        "existing extattrs; does not replace them."
    ),
)
async def cli_network_extattrs_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r'\bnetwork (\S+) extattrs set\s+("[^"]+"|\S+)\s+("[^"]+"|\S+)', line)
    if not m:
        print("  Error: EA name and value required")
        return
    try:
        cidr, _ = normalize_cidr_any(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return
    ea_name = _unquote(m.group(2))
    ea_value = _unquote(m.group(3))
    view = _parse_kv(line, "view")
    objtype = _network_objtype(cidr)
    found = await _find_network_ref(ctx, cidr, view, objtype=objtype)
    if found is None:
        print(f"  No network found: {cidr}")
        return
    ref, _record = found
    record = as_dict(await _ipam_resource(ctx, objtype).get(ref, return_fields_plus=["extattrs"]))
    existing = dict(record.get("extattrs") or {})
    existing[ea_name] = {"value": ea_value}
    await _ipam_resource(ctx, objtype).update(ref, {"extattrs": existing})


@command(
    "configure network <n.n.n.n/mm> extattrs delete <name>",
    words="<cr> view=<name>",
    help="Remove an Extensible Attribute from a network.",
)
async def cli_network_extattrs_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r'\bnetwork (\S+) extattrs delete\s+("[^"]+"|\S+)', line)
    if not m:
        print("  Error: EA name required")
        return
    try:
        cidr, _ = normalize_cidr_any(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return
    ea_name = _unquote(m.group(2))
    view = _parse_kv(line, "view")
    objtype = _network_objtype(cidr)
    found = await _find_network_ref(ctx, cidr, view, objtype=objtype)
    if found is None:
        print(f"  No network found: {cidr}")
        return
    ref, _record = found
    record = as_dict(await _ipam_resource(ctx, objtype).get(ref, return_fields_plus=["extattrs"]))
    existing = dict(record.get("extattrs") or {})
    existing.pop(ea_name, None)
    await _ipam_resource(ctx, objtype).update(ref, {"extattrs": existing})


def _parse_dhcp_options(line: str) -> list[dict] | None:
    """Parse repeatable `option=<spec>` tokens into WAPI dhcpoption structs.

    Spec forms:
      name=value           DHCP option in default space
      space:name=value     DHCP option in a named (vendor) option space

    Returns None if no option= token present so the caller can leave the
    existing options list untouched. An explicit `option=clear` wipes the
    list.
    """
    # After tokenization `option=foo=bar` becomes `option foo=bar`, so match
    # either form here.
    specs = re.findall(r"\boption[=\s]+(\S+)", line)
    if not specs:
        return None
    if len(specs) == 1 and specs[0].lower() == "clear":
        return []
    out: list[dict] = []
    for spec in specs:
        space = None
        if ":" in spec and "=" in spec and spec.index(":") < spec.index("="):
            space, _, rest = spec.partition(":")
        else:
            rest = spec
        name, _, value = rest.partition("=")
        if not name or not value:
            continue
        entry: dict = {"name": name, "value": value}
        if space:
            entry["vendor_class"] = space
        out.append(entry)
    return out


# Bind cli_modify_network to every static set-chain endpoint.
for _depth in range(1, 17):
    _ml = _NETMOD_BASE + (" set <name> <value>" * _depth)
    command(_ml, words=_NETMOD_WORDS)(cli_modify_network)


# ---------------------------------------------------------------------------
# show network
# ---------------------------------------------------------------------------

register("show", words="network", help="Read grid state without modifying anything.")
register(
    "show network",
    words="<cr> <n.n.n.n/mm>|view=<name>|ea=<name>",
    help="Networks, network containers, shared networks (IPv4/IPv6).",
)
register("show network <n.n.n.n/mm>", words="<cr> view=<name>|fields=<field1,field2,...>")


def _print_network(n: dict) -> None:
    parts = [f"network={n.get('network', '')}"]
    if n.get("network_view"):
        parts.append(f"view={n['network_view']}")
    if n.get("comment"):
        parts.append(f"comment={n['comment']}")
    print(" ".join(parts))


@command(
    "show network",
    words="<cr> <n.n.n.n/mm>|view=<name>|ea=<name> fields=<field1,field2,...>",
    help="List networks. ea=<NAME>:<VALUE> filters by extensible "
    'attribute (repeatable). Example: ea="DC Location:DC1".',
)
@command(
    "show network <n.n.n.n/mm>",
    words="<cr> view=<name> fields=<field1,field2,...>",
    help="Show a specific network.",
)
async def cli_show_network(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    cidr = None
    if len(tokens) >= 3 and "/" in tokens[2]:
        try:
            cidr, _ = normalize_cidr_any(tokens[2])
        except ValueError as e:
            print(f"  Error: {e}")
            return

    view = _parse_kv(line, "view")
    extra = parse_extra_fields(line)
    ret_fields = ["network", "comment", "network_view"] + extra
    filters: dict = {}
    if cidr:
        filters["network"] = cidr
    if view:
        filters["network_view"] = view

    # ea=<NAME>:<VALUE> -> WAPI filter `*<NAME>=<VALUE>`. Repeatable.
    for m in re.finditer(r'\bea[= ]+(?:"([^"]+)"|(\S+))', line):
        spec = m.group(1) or m.group(2)
        if ":" not in spec:
            continue
        ea_name, _, ea_value = spec.partition(":")
        filters[f"*{ea_name}"] = ea_value

    def _emit_extra(n: dict) -> None:
        for f in extra:
            val = n.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")

    if cidr:
        # CIDR given - single-record lookup, no pagination
        objtype = _network_objtype(cidr)
        nets = [
            as_dict(r)
            async for r in _ipam_resource(ctx, objtype).list(return_fields=ret_fields, **filters)
        ]
        if not nets:
            print(f"  No network found: {cidr}")
            return
        for n in nets:
            _print_network(n)
            _emit_extra(n)
    else:
        # No CIDR - list-all query, paginate both IPv4 and IPv6 networks
        all_nets: list[dict] = []
        for objtype in ("network", "ipv6network"):
            results = [
                as_dict(r)
                async for r in _ipam_resource(ctx, objtype).list(
                    return_fields=ret_fields, **filters
                )
            ]
            all_nets.extend(results)
        for n in all_nets:
            _print_network(n)
            _emit_extra(n)


# ---------------------------------------------------------------------------
# configure network add shared
# ---------------------------------------------------------------------------

register("configure network add", words="shared")
register("configure network add shared", words="<name>")

_SHAREDADD_WORDS = "<cr> comment=<comment>|view=<name>|network=<n.n.n.n/mm>|set"
register("configure network add shared <name>", words=_SHAREDADD_WORDS)

_SHAREDADD_BASE = "configure network add shared <name>"
for _depth in range(16):
    _pfx = _SHAREDADD_BASE + (" set <name> <value>" * _depth)
    register(f"{_pfx} set", words=_SET_NAME)
    register(f"{_pfx} set <name>", words=_SET_VALUE)
    register(f"{_pfx} set <name> <value>", words=_SHAREDADD_WORDS)


def _parse_member_networks(line: str) -> list[str]:
    """Return list of member CIDRs from 'network <cidr>' tokens in the line.

    The command prefix 'configure network add shared <name>' contains the
    word 'network' but never followed immediately by a CIDR, so the regex
    naturally captures only the member-network CIDRs.
    """
    return re.findall(r"\bnetwork\s+(\d+\.\d+\.\d+\.\d+/\d+)", line)


@command(
    "configure network add shared <name>",
    words=_SHAREDADD_WORDS,
    help="Create a shared network (optionally with member networks).",
)
async def cli_add_shared_network(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnetwork add shared\s+(\S+)", line)
    if not m:
        print("  Error: shared network name required")
        return
    name = m.group(1)

    view = _parse_kv(line, "view")
    comment = _parse_comment(line)
    eas = _parse_extattrs(line)

    member_cidrs = _parse_member_networks(line)
    networks_list: list[dict] = []
    for cidr in member_cidrs:
        params: dict = {"network": cidr}
        if view:
            params["network_view"] = view
        results = [as_dict(r) async for r in ctx.client.ipam.network.list(**params)]
        if not results:
            print(f"  No network found: {cidr}")
            return
        networks_list.append({"_ref": results[0]["_ref"]})

    body: dict = {"name": name}
    if networks_list:
        body["networks"] = networks_list
    if comment:
        body["comment"] = comment
    if view:
        body["network_view"] = view
    if eas:
        body["extattrs"] = eas

    await ctx.client.dhcp.sharednetwork.create(body)


# Bind handler to every static set-chain endpoint.
for _depth in range(1, 17):
    _ml = _SHAREDADD_BASE + (" set <name> <value>" * _depth)
    command(_ml, words=_SHAREDADD_WORDS)(cli_add_shared_network)


# ---------------------------------------------------------------------------
# configure network container add
# ---------------------------------------------------------------------------

register(
    "configure network",
    words="container",
    help="IPv4/IPv6 networks, ranges, fixed addresses, filters.",
)
register("configure network container", words="add <n.n.n.n/mm>")
register("configure network container add", words="<n.n.n.n/mm>")

_CNTADD_WORDS = "<cr> comment=<comment>|view=<name>|set"
register("configure network container add <n.n.n.n/mm>", words=_CNTADD_WORDS)

_CNTADD_BASE = "configure network container add <n.n.n.n/mm>"
for _depth in range(16):
    _pfx = _CNTADD_BASE + (" set <name> <value>" * _depth)
    register(f"{_pfx} set", words=_SET_NAME)
    register(f"{_pfx} set <name>", words=_SET_VALUE)
    register(f"{_pfx} set <name> <value>", words=_CNTADD_WORDS)


@command(
    "configure network container add <n.n.n.n/mm>",
    words=_CNTADD_WORDS,
    help="Add a network container.",
)
async def cli_add_network_container(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bcontainer add (\S+)", line)
    if not m:
        print("  Error: CIDR required")
        return
    try:
        cidr, _ = normalize_cidr_any(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return

    objtype = _network_objtype(cidr, container=True)
    body: dict = {"network": cidr}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    view = _parse_kv(line, "view")
    if view:
        body["network_view"] = view
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas

    await _ipam_resource(ctx, objtype).create(body)


# Bind handler to every static set-chain endpoint.
for _depth in range(1, 17):
    _ml = _CNTADD_BASE + (" set <name> <value>" * _depth)
    command(_ml, words=_CNTADD_WORDS)(cli_add_network_container)


# ---------------------------------------------------------------------------
# configure network container <cidr> delete / modify
# ---------------------------------------------------------------------------

register("configure network container <n.n.n.n/mm>", words="delete modify")
register("configure network container <n.n.n.n/mm> delete", words="<cr> view=<name>")
register(
    "configure network container <n.n.n.n/mm> modify",
    words="<cr> comment=<comment>|view=<name>|set",
)

_CNTMOD_WORDS = "<cr> comment=<comment>|view=<name>|set"
_CNTMOD_BASE = "configure network container <n.n.n.n/mm> modify"

for _depth in range(16):
    _pfx = _CNTMOD_BASE + (" set <name> <value>" * _depth)
    register(f"{_pfx} set", words=_SET_NAME)
    register(f"{_pfx} set <name>", words=_SET_VALUE)
    register(f"{_pfx} set <name> <value>", words=_CNTMOD_WORDS)


@command(
    "configure network container <n.n.n.n/mm> delete",
    words="<cr> view=<name>",
    help="Delete a network container.",
)
async def cli_delete_network_container(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bcontainer (\S+) delete", line)
    if not m:
        print("  Error: CIDR required")
        return
    try:
        cidr, _ = normalize_cidr_any(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return
    view = _parse_kv(line, "view")
    objtype = _network_objtype(cidr, container=True)
    found = await _find_network_ref(ctx, cidr, view, objtype=objtype)
    if found is None:
        print(f"  No network container found: {cidr}")
        return
    ref, _ = found
    await _ipam_resource(ctx, objtype).delete(ref)


@command(
    "configure network container <n.n.n.n/mm> modify",
    words="<cr> comment=<comment>|view=<name>|set",
    help="Modify an existing network container.",
)
async def cli_modify_network_container(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bcontainer (\S+) modify", line)
    if not m:
        print("  Error: CIDR required")
        return
    try:
        cidr, _ = normalize_cidr_any(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return
    view = _parse_kv(line, "view")
    objtype = _network_objtype(cidr, container=True)
    found = await _find_network_ref(ctx, cidr, view, objtype=objtype)
    if found is None:
        print(f"  No network container found: {cidr}")
        return
    ref, _ = found

    body: dict = {}
    comment = _parse_comment(line)
    if comment is not None:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    if not body:
        print("  Nothing to modify (no fields specified)")
        return

    await _ipam_resource(ctx, objtype).update(ref, body)


# Bind cli_modify_network_container to every static set-chain endpoint.
for _depth in range(1, 17):
    _ml = _CNTMOD_BASE + (" set <name> <value>" * _depth)
    command(_ml, words=_CNTMOD_WORDS)(cli_modify_network_container)


# ---------------------------------------------------------------------------
# show network container
# ---------------------------------------------------------------------------

register(
    "show network",
    words="container",
    help="Networks, network containers, shared networks (IPv4/IPv6).",
)
register("show network container", words="<cr> <n.n.n.n/mm>|view=<name>")
register("show network container <n.n.n.n/mm>", words="<cr> view=<name>|fields=<field1,field2,...>")


@command(
    "show network container",
    words="<cr> <n.n.n.n/mm>|view=<name> fields=<field1,field2,...>",
    help="List network containers.",
)
@command(
    "show network container <n.n.n.n/mm>",
    words="<cr> view=<name> fields=<field1,field2,...>",
    help="Show a specific network container.",
)
async def cli_show_network_container(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    cidr = None
    # "show network container <cidr>" → tokens[3]
    if len(tokens) >= 4 and "/" in tokens[3]:
        try:
            cidr, _ = normalize_cidr_any(tokens[3])
        except ValueError as e:
            print(f"  Error: {e}")
            return

    view = _parse_kv(line, "view")
    extra = parse_extra_fields(line)
    ret_fields = ["network", "comment", "network_view"] + extra
    filters: dict = {}
    if cidr:
        filters["network"] = cidr
    if view:
        filters["network_view"] = view

    def _emit_extra(n: dict) -> None:
        for f in extra:
            val = n.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")

    if cidr:
        # CIDR given - single-record lookup, no pagination
        objtype = _network_objtype(cidr, container=True)
        nets = [
            as_dict(r)
            async for r in _ipam_resource(ctx, objtype).list(return_fields=ret_fields, **filters)
        ]
        if not nets:
            print(f"  No network container found: {cidr}")
            return
        for n in nets:
            _print_network(n)
            _emit_extra(n)
    else:
        # No CIDR - list-all query, paginate both IPv4 and IPv6 network containers
        all_nets: list[dict] = []
        for objtype in ("networkcontainer", "ipv6networkcontainer"):
            results = [
                as_dict(r)
                async for r in _ipam_resource(ctx, objtype).list(
                    return_fields=ret_fields, **filters
                )
            ]
            all_nets.extend(results)
        for n in all_nets:
            _print_network(n)
            _emit_extra(n)


# ---------------------------------------------------------------------------
# configure shared_network <name> delete
# ---------------------------------------------------------------------------

register("configure", words="shared_network", help="Create, modify or delete grid objects.")
register(
    "configure shared_network",
    words="<name>",
    help="Shared networks - one DHCP pool spanning multiple subnets.",
)
register("configure shared_network <name>", words="delete")
register("configure shared_network <name> delete", words="<cr> view=<name>")


@command(
    "configure shared_network <name> delete",
    words="<cr> view=<name>",
    help="Delete a shared network by name.",
)
async def cli_delete_shared_network(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bshared_network\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: shared network name required")
        return
    name = m.group(1)
    view = _parse_kv(line, "view")

    params: dict = {"name": name}
    if view:
        params["network_view"] = view

    results = [as_dict(r) async for r in ctx.client.dhcp.sharednetwork.list(**params)]
    if not results:
        print(f"  No shared network found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.dhcp.sharednetwork.delete(ref)


# ---------------------------------------------------------------------------
# show network shared
# ---------------------------------------------------------------------------

register(
    "show network",
    words="shared",
    help="Networks, network containers, shared networks (IPv4/IPv6).",
)
register("show network shared", words="<cr> <name>|view=<name>")
register("show network shared <name>", words="<cr> view=<name>")


def _print_shared_network(sn: dict) -> None:
    parts = [f"name={sn.get('name', '')}"]
    if sn.get("network_view"):
        parts.append(f"view={sn['network_view']}")
    if sn.get("comment"):
        parts.append(f"comment={sn['comment']}")
    print(" ".join(parts))


@command("show network shared", words="<cr> <name>|view=<name>", help="List shared networks.")
@command(
    "show network shared <name>",
    words="<cr> view=<name> fields=<field1,field2,...>",
    help="Show a specific shared network.",
)
async def cli_show_shared_network(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    # "show network shared [<name>]" → name at tokens[3] if present and not "view"/"fields"
    sn_name = None
    if len(tokens) >= 4 and not tokens[3].startswith("view") and "=" not in tokens[3]:
        sn_name = tokens[3]

    view = _parse_kv(line, "view")
    extra = parse_extra_fields(line)
    ret_fields = ["name", "networks", "comment", "network_view"] + extra
    filters: dict = {}
    if sn_name:
        filters["name"] = sn_name
    if view:
        filters["network_view"] = view

    results = [
        as_dict(r)
        async for r in ctx.client.dhcp.sharednetwork.list(return_fields=ret_fields, **filters)
    ]

    if not results:
        if sn_name:
            print(f"  No shared network found: {sn_name}")
        return

    for sn in results:
        _print_shared_network(sn)
        for f in extra:
            val = sn.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# configure network <n.n.n.n/mm> split / join / move  (2e)
# ---------------------------------------------------------------------------

register("configure network <n.n.n.n/mm>", words="split join move")
register("configure network <n.n.n.n/mm> split", words="<num>")
register("configure network <n.n.n.n/mm> split <num>", words="<cr>")
register("configure network <n.n.n.n/mm> join", words="<n.n.n.n/mm>")
register("configure network <n.n.n.n/mm> join <n.n.n.n/mm>", words="<cr>")
register("configure network <n.n.n.n/mm> move", words="member failover")
register("configure network <n.n.n.n/mm> move member", words="<ip>")
register("configure network <n.n.n.n/mm> move member <ip>", words="<cr> member")
register("configure network <n.n.n.n/mm> move failover", words="<name>")
register("configure network <n.n.n.n/mm> move failover <name>", words="<cr>")

# Multi-member chain: allow "member <ip> member <ip> ..." (depths 1-4).
# At each depth we register the `member` waypoint (words=<ip>) and the
# `member <ip>` endpoint (words=<cr> member) so the parser can keep consuming
# additional `member <ip>` pairs.
_MOVE_BASE = "configure network <n.n.n.n/mm> move member <ip>"
for _depth in range(1, 17):
    _pfx = _MOVE_BASE + (" member <ip>" * (_depth - 1))
    register(f"{_pfx} member", words="<ip>")
    register(f"{_pfx} member <ip>", words="<cr> member")


@command(
    "configure network <n.n.n.n/mm> split <num>",
    words="<cr>",
    help="Split a network into two halves with the new prefix length.",
)
async def cli_split_network(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bnetwork (\S+) split (\d+)", line)
    if not m:
        print("  Error: CIDR and prefix required")
        return
    try:
        cidr = normalize_cidr(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return
    new_prefix = int(m.group(2))

    found = await _find_network_ref(ctx, cidr, view=None)
    if found is None:
        print(f"  No network found: {cidr}")
        return
    ref, _ = found

    await ctx.client.ipam.network.call_function(ref, "split_network", cidr=new_prefix)


def _are_adjacent_siblings(cidr_a: str, cidr_b: str) -> tuple[bool, str]:
    """Check if two CIDRs are adjacent siblings that share the same parent.

    Returns (True, parent_cidr) if they are siblings, (False, "") otherwise.
    Two networks are siblings if they have the same prefix length and their
    addresses differ only in the last bit of the prefix (the bit at position
    prefix_len - 1 from the high end), i.e. one is the even/lower sibling
    and the other is the odd/upper sibling of a supernet one bit shorter.
    """
    try:
        net_a = ipaddress.ip_network(cidr_a, strict=True)
        net_b = ipaddress.ip_network(cidr_b, strict=True)
    except ValueError as e:
        return False, str(e)

    if net_a.version != net_b.version:
        return False, "address families differ"
    if net_a.prefixlen != net_b.prefixlen:
        return False, "prefix lengths differ"
    if net_a.prefixlen == 0:
        return False, "cannot join a /0 network"

    # Compute the supernet (parent) of each and check they are the same.
    parent_a = net_a.supernet()
    parent_b = net_b.supernet()
    if parent_a != parent_b:
        return False, "not siblings of the same parent"

    return True, str(parent_a)


@command(
    "configure network <n.n.n.n/mm> join <n.n.n.n/mm>",
    words="<cr>",
    help="Join two adjacent sibling networks into their parent CIDR.",
)
async def cli_join_network(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnetwork (\S+) join (\S+)", line)
    if not m:
        print("  Error: two CIDRs required")
        return

    raw_a, raw_b = m.group(1), m.group(2)
    try:
        cidr_a, _ = normalize_cidr_any(raw_a)
        cidr_b, _ = normalize_cidr_any(raw_b)
    except ValueError as e:
        print(f"  Error: {e}")
        return

    ok, parent_or_err = _are_adjacent_siblings(cidr_a, cidr_b)
    if not ok:
        print(f"  Error: {cidr_a} and {cidr_b} are not adjacent siblings - {parent_or_err}")
        return

    parent_cidr = parent_or_err
    objtype = _network_objtype(cidr_a)

    # Verify both networks exist in WAPI.
    ref_a_found = await _find_network_ref(ctx, cidr_a, view=None, objtype=objtype)
    if ref_a_found is None:
        print(f"  Error: network not found: {cidr_a}")
        return
    ref_a = ref_a_found[0]

    ref_b_found = await _find_network_ref(ctx, cidr_b, view=None, objtype=objtype)
    if ref_b_found is None:
        print(f"  Error: network not found: {cidr_b}")
        return
    ref_b = ref_b_found[0]

    # Delete both children.  If deletion of B fails after A is deleted,
    # report a partial-rollback error with both refs.
    from ibx_nios_sdk import NiosError

    try:
        await _ipam_resource(ctx, objtype).delete(ref_a)
    except NiosError as e:
        print(f"  Error deleting {cidr_a} ({ref_a}): {e}")
        return

    try:
        await _ipam_resource(ctx, objtype).delete(ref_b)
    except NiosError as e:
        print(
            f"  Error deleting {cidr_b} ({ref_b}): {e}\n"
            f"  PARTIAL STATE: {cidr_a} was already deleted.\n"
            f"  Recover manually: re-create {cidr_a} or complete deletion of {cidr_b}"
        )
        return

    # Create the parent network.
    try:
        await _ipam_resource(ctx, objtype).create({"network": parent_cidr})
    except NiosError as e:
        print(
            f"  Error creating parent {parent_cidr}: {e}\n"
            f"  PARTIAL STATE: {cidr_a} and {cidr_b} were deleted but {parent_cidr} was NOT created.\n"
            f"  Recover manually: re-create {parent_cidr} (or {cidr_a} and {cidr_b})"
        )


@command(
    "configure network <n.n.n.n/mm> move member <ip>",
    words="<cr> member",
    help="Reassign the DHCP member(s) responsible for serving this network.",
)
@command(
    "configure network <n.n.n.n/mm> move failover <name>",
    words="<cr>",
    help="Retarget the failover association on every DHCP range in this network.",
)
async def cli_move_network(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnetwork (\S+) move", line)
    if not m:
        print("  Error: CIDR required")
        return
    try:
        cidr = normalize_cidr(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return

    # Failover lives on the `range` object, not `network`. A full move to a
    # new failover group also needs both peers to be members of the network,
    # otherwise the range PUT fails ("Member X is functioning as the DHCP
    # failover primary peer, but is not assigned to the network"). So:
    #   1. Look up the dhcpfailover to get the peer FQDNs.
    #   2. Ensure both peers are in network.members (merge, don't replace).
    #   3. PUT failover_association on every range in the network.
    fo_m = re.search(r"\bmove\s+failover\s+(\S+)", line)
    if fo_m:
        fo_name = fo_m.group(1)

        fo_list = [
            as_dict(f)
            async for f in ctx.client.dhcp.dhcpfailover.list(
                name=fo_name, return_fields_plus=["primary", "secondary"]
            )
        ]
        if not fo_list:
            print(f"  No failover association found: {fo_name}")
            return
        peers = [p for p in (fo_list[0].get("primary"), fo_list[0].get("secondary")) if p]

        found = await _find_network_ref(ctx, cidr, view=None)
        if found is None:
            print(f"  No network found: {cidr}")
            return
        net_ref, _ = found
        net_list = [
            as_dict(n)
            async for n in ctx.client.ipam.network.list(
                network=cidr, return_fields_plus=["members"]
            )
        ]
        existing = net_list[0].get("members", []) if net_list else []

        def _peer_label(m: dict) -> str:
            return m.get("name") or m.get("ipv4addr") or ""

        existing_labels = {_peer_label(m) for m in existing}
        added = [p for p in peers if p not in existing_labels]
        if added:
            # Strip null/empty fields from existing members - WAPI round-trips
            # ipv6addr=null which it then rejects on PUT.
            cleaned = [{k: v for k, v in m.items() if v not in (None, "")} for m in existing]
            new_members = cleaned + [{"_struct": "dhcpmember", "name": p} for p in added]
            await ctx.client.ipam.network.update(net_ref, {"members": new_members})

        ranges = [as_dict(r) async for r in ctx.client.dhcp.range.list(network=cidr)]
        if not ranges:
            print(f"  No ranges in {cidr} to retarget")
            return
        for r in ranges:
            await ctx.client.dhcp.range.update(r["_ref"], {"failover_association": fo_name})
        if added:
            print(f"  Added {len(added)} peer(s) to {cidr}: {', '.join(added)}")
        print(f"  Moved {len(ranges)} range(s) in {cidr} to failover {fo_name}")
        return

    # Member reassignment: update network.members.
    found = await _find_network_ref(ctx, cidr, view=None)
    if found is None:
        print(f"  No network found: {cidr}")
        return
    ref, _ = found

    member_ips = re.findall(r"\bmember\s+(\d+\.\d+\.\d+\.\d+)", line)
    if not member_ips:
        print("  Error: member IP required")
        return
    body = {"members": [{"_struct": "dhcpmember", "ipv4addr": ip} for ip in member_ips]}
    await ctx.client.ipam.network.update(ref, body)


# Bind cli_move_network to every multi-member chain endpoint.
for _depth in range(1, 4):
    _ml = _MOVE_BASE + (" member <ip>" * _depth)
    command(_ml, words="<cr> member")(cli_move_network)


# ---------------------------------------------------------------------------
# show network <n.n.n.n/mm> ipam next_available / next_network  (2e)
# ---------------------------------------------------------------------------

register("show network <n.n.n.n/mm>", words="ipam")
register("show network <n.n.n.n/mm> ipam", words="next_available next_network")
register("show network <n.n.n.n/mm> ipam next_available", words="<cr> <num>")
register("show network <n.n.n.n/mm> ipam next_available <num>", words="<cr>")
register("show network <n.n.n.n/mm> ipam next_network", words="</cidr>")
register("show network <n.n.n.n/mm> ipam next_network </cidr>", words="<cr>")


@command(
    "show network <n.n.n.n/mm> ipam next_available",
    words="<cr> <num>",
    help="Return next available IP(s) in a network.",
)
@command(
    "show network <n.n.n.n/mm> ipam next_available <num>",
    words="<cr>",
    help="Return N next available IPs in a network.",
)
async def cli_next_available_ip(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bnetwork (\S+) ipam next_available(?:\s+(\d+))?", line)
    if not m:
        print("  Error: CIDR required")
        return
    try:
        cidr = normalize_cidr(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return
    num = int(m.group(2)) if m.group(2) else 1

    found = await _find_network_ref(ctx, cidr, view=None)
    if found is None:
        print(f"  No network found: {cidr}")
        return
    ref, _ = found

    result = await ctx.client.ipam.network.next_available_ip(ref, num=num)
    for ip in (result or {}).get("ips", []):
        print(f"  {ip}")


@command(
    "show network <n.n.n.n/mm> ipam next_network </cidr>",
    words="<cr>",
    help="Return next available sub-network from a network container.",
)
async def cli_next_available_network(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bnetwork (\S+) ipam next_network /(\d+)", line)
    if not m:
        print("  Error: CIDR and /prefix required")
        return
    try:
        cidr = normalize_cidr(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return
    prefix = int(m.group(2))

    found = await _find_network_ref(ctx, cidr, view=None, objtype="networkcontainer")
    if found is None:
        print(f"  No network container found: {cidr}")
        return
    ref, _ = found

    result = await ctx.client.ipam.networkcontainer.next_available_network(ref, cidr=prefix, num=1)
    for net in (result or {}).get("networks", []):
        print(f"  {net}")


# ---------------------------------------------------------------------------
# show network <n.n.n.n/mm> statistics  (2e)
# ---------------------------------------------------------------------------

register("show network <n.n.n.n/mm>", words="statistics")
register("show network <n.n.n.n/mm> statistics", words="<cr>")
# Also expose "show network statistics [<cidr>]" as an alias waypoint
register(
    "show network",
    words="statistics",
    help="Networks, network containers, shared networks (IPv4/IPv6).",
)
register("show network statistics", words="<cr> <n.n.n.n/mm>")
register("show network statistics <n.n.n.n/mm>", words="<cr>")


@command(
    "show network <n.n.n.n/mm> statistics",
    words="<cr>",
    help="Show IPAM utilization statistics for a network.",
)
async def cli_show_network_statistics(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bnetwork (\S+) statistics", line)
    if not m:
        print("  Error: CIDR required")
        return
    try:
        cidr = normalize_cidr(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return

    results = [as_dict(r) async for r in ctx.client.ipam.ipam_statistics.list(network=cidr)]

    if not results:
        print(f"  No statistics found for: {cidr}")
        return

    stats = results[0] if isinstance(results, list) else results
    for key, val in stats.items():
        if key == "_ref":
            continue
        print(f"  {key}={val}")
