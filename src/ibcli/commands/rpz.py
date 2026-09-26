# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""RPZ command handlers - Phase 6.

Provides ``configure rpz`` and ``show rpz`` command trees for managing
Response Policy Zones and RPZ records via the Infoblox WAPI.

Command vocabulary summary
--------------------------
# Zone (RPZ container - lives in ctx.client.dns.zone_rp)
configure rpz zone add <name> [view <name>] [policy <name>] [comment <text>]
configure rpz zone <name> delete [view <name>]
show rpz zone [<name>]

# Records (all under ctx.client.rpz.*)
configure rpz record <type> add <name> <value> zone <zone> [view <name>]
configure rpz record <type> <name> delete zone <zone> [view <name>]
show rpz record <type> [<name>] zone <zone>

# All-records aggregator (read-only)
show rpz records [<name>]
"""

from __future__ import annotations

import re

from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict

# ---------------------------------------------------------------------------
# Shared parser helpers
# ---------------------------------------------------------------------------


def _kv(line: str, key: str) -> str | None:
    """Extract the first occurrence of `key <token>` from *line*."""
    m = re.search(rf"\b{re.escape(key)}\s+(\S+)", line)
    return m.group(1) if m else None


def _comment(line: str) -> str | None:
    """Extract a quoted or unquoted comment value."""
    m = re.search(r'\bcomment\s+"([^"]+)"', line)
    if m:
        return m.group(1)
    m = re.search(r"\bcomment\s+(\S+)", line)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Chunk A: RPZ zone (configure rpz zone / show rpz zone)
# ---------------------------------------------------------------------------

register("configure", words="rpz", help="Create, modify or delete grid objects.")
register("show", words="rpz", help="Read grid state without modifying anything.")
register(
    "configure rpz",
    words="zone record",
    help="Response Policy Zones - DNS firewalling / threat blocking.",
)
register(
    "configure rpz zone", words="add <name>", help="RPZ authoritative zones (policy containers)."
)
register("configure rpz zone add", words="<name>")

# view=<name>  policy=<name>  comment=<name>  are key=<special> pairs handled
# by the parser's _append_alt; <name> is in SPECOPS.
_RPZ_ZONE_ADD_WORDS = "<cr> view=<name>|policy=<name>|comment=<comment>"
register("configure rpz zone add <name>", words=_RPZ_ZONE_ADD_WORDS)


@command(
    "configure rpz zone add <name>",
    words=_RPZ_ZONE_ADD_WORDS,
    help="Add an RPZ zone.",
)
async def cli_rpz_zone_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brpz zone add (\S+)", line)
    if not m:
        print("  Error: zone name required")
        return
    fqdn = m.group(1)
    body: dict = {"fqdn": fqdn}
    view = _kv(line, "view")
    if view:
        body["view"] = view
    policy = _kv(line, "policy")
    if policy:
        body["rpz_policy"] = policy.upper()
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.dns.zone_rp.create(body)


register("configure rpz zone <name>", words="delete")
register("configure rpz zone <name> delete", words="<cr> view=<name>")


@command(
    "configure rpz zone <name> delete",
    words="<cr> view=<name>",
    help="Delete an RPZ zone.",
)
async def cli_rpz_zone_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brpz zone (\S+) delete", line)
    if not m:
        print("  Error: zone name required")
        return
    fqdn = m.group(1)
    view = _kv(line, "view")
    params: dict = {"fqdn": fqdn}
    if view:
        params["view"] = view
    results = [as_dict(r) async for r in ctx.client.dns.zone_rp.list(max_results=1, **params)]
    if not results:
        print(f"  No RPZ zone found: {fqdn}")
        return
    await ctx.client.dns.zone_rp.delete(results[0]["_ref"])


register("show rpz", words="zone record records", help="RPZ zones and records.")
register("show rpz zone", words="<cr> <name>", help="RPZ zones.")
register("show rpz zone <name>", words="<cr>")


@command("show rpz zone", words="<cr> <name>", help="Show RPZ zones.")
@command("show rpz zone <name>", words="<cr>", help="Show a specific RPZ zone.")
async def cli_rpz_zone_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    # tokens: show rpz zone [<name>]
    fqdn = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            fqdn = candidate
    params: dict = {}
    if fqdn:
        params["fqdn"] = fqdn
    zones = [
        as_dict(r)
        async for r in ctx.client.dns.zone_rp.list(
            return_fields_plus=["fqdn", "view", "comment", "rpz_policy", "rpz_severity"],
            **params,
        )
    ]
    if not zones:
        if fqdn:
            print(f"  No RPZ zone found: {fqdn}")
        return
    for z in zones:
        parts = ["type=rpz", f"fqdn={z.get('fqdn', '')}"]
        if z.get("view"):
            parts.append(f"view={z['view']}")
        if z.get("rpz_policy"):
            parts.append(f"policy={z['rpz_policy']}")
        if z.get("comment"):
            parts.append(f"comment={z['comment']}")
        print(" ".join(parts))


# ---------------------------------------------------------------------------
# Chunk B: Simple RPZ records - cname, a, aaaa, txt
#
# Token conventions (must all be in SPECOPS):
#   value field position  -> <value>  (matches _RE_COMM - quoted or non-ws)
#   rpz zone position     -> <zone>   (matches r'^\S+$')
#   name position         -> <name>   (matches r'^\S+$')
# ---------------------------------------------------------------------------

register(
    "configure rpz record",
    words="cname a aaaa txt mx srv ptr naptr https svcb "
    "a_ipaddress aaaa_ipaddress "
    "cname_clientipaddress cname_clientipaddressdn "
    "cname_ipaddress cname_ipaddressdn",
    help="RPZ override records (A, CNAME, IP, client-IP, NAPTR, …).",
)

_SIMPLE_RPZ_RECORDS: dict[str, tuple[str, str]] = {
    # cli_key -> (sdk_attr_on_ctx.client.rpz, value_field)
    "cname": ("record_rpz_cname", "canonical"),
    "a": ("record_rpz_a", "ipv4addr"),
    "aaaa": ("record_rpz_aaaa", "ipv6addr"),
    "txt": ("record_rpz_txt", "text"),
}

_SIMPLE_RPZ_ADD_WORDS = "<cr> view=<name>"

for _rec in _SIMPLE_RPZ_RECORDS:
    register(f"configure rpz record {_rec}", words="add <name>")
    register(f"configure rpz record {_rec} add", words="<name>")
    register(f"configure rpz record {_rec} add <name>", words="<value>")
    register(f"configure rpz record {_rec} add <name> <value>", words="zone")
    register(f"configure rpz record {_rec} add <name> <value> zone", words="<zone>")
    register(
        f"configure rpz record {_rec} add <name> <value> zone <zone>",
        words=_SIMPLE_RPZ_ADD_WORDS,
    )
    register(f"configure rpz record {_rec} <name>", words="delete")
    register(f"configure rpz record {_rec} <name> delete", words="zone")
    register(f"configure rpz record {_rec} <name> delete zone", words="<zone>")
    register(
        f"configure rpz record {_rec} <name> delete zone <zone>",
        words="<cr> view=<name>",
    )


def _rpz_resource(ctx: Context, sdk_attr: str):
    """Return the RPZ resource object by attribute name."""
    return getattr(ctx.client.rpz, sdk_attr)


async def _rpz_record_add_simple(rec: str, line: str, ctx: Context) -> None:
    sdk_attr, field = _SIMPLE_RPZ_RECORDS[rec]
    # Pattern: "rpz record cname add <name> <value> zone <zone>"
    m = re.search(
        rf'\brpz record {re.escape(rec)} add (\S+) ("(?:[^"]*)+"|\S+) zone (\S+)',
        line,
    )
    if not m:
        print("  Error: name, value, and zone required")
        return
    name, value, rpz_zone = m.group(1), m.group(2).strip('"'), m.group(3)
    body: dict = {"name": name, field: value, "rp_zone": rpz_zone}
    view = _kv(line, "view")
    if view:
        body["view"] = view
    await _rpz_resource(ctx, sdk_attr).create(body)


async def _rpz_record_delete_simple(rec: str, line: str, ctx: Context) -> None:
    sdk_attr, _field = _SIMPLE_RPZ_RECORDS[rec]
    m = re.search(
        rf"\brpz record {re.escape(rec)} (\S+) delete zone (\S+)",
        line,
    )
    if not m:
        return
    name, rpz_zone = m.group(1), m.group(2)
    view = _kv(line, "view")
    params: dict = {"name": name, "zone": rpz_zone}
    if view:
        params["view"] = view
    resource = _rpz_resource(ctx, sdk_attr)
    records = [as_dict(r) async for r in resource.list(**params)]
    if not records:
        print(f"  No rpz {rec} record found: {name}")
        return
    await resource.delete(records[0]["_ref"])


def _bind_simple_rpz(rec: str) -> None:
    """Close over rec so each handler captures its own rec value."""

    def make_add(r=rec):
        async def _h(line: str, ctx: Context) -> None:
            if ctx.client is None:
                print("  Not connected")
                return
            await _rpz_record_add_simple(r, line, ctx)

        return _h

    def make_del(r=rec):
        async def _h(line: str, ctx: Context) -> None:
            if ctx.client is None:
                print("  Not connected")
                return
            await _rpz_record_delete_simple(r, line, ctx)

        return _h

    command(
        f"configure rpz record {rec} add <name> <value> zone <zone>",
        words=_SIMPLE_RPZ_ADD_WORDS,
        help=f"Add an RPZ {rec} record.",
    )(make_add())
    command(
        f"configure rpz record {rec} <name> delete zone <zone>",
        words="<cr> view=<name>",
        help=f"Delete an RPZ {rec} record.",
    )(make_del())


for _rec in _SIMPLE_RPZ_RECORDS:
    _bind_simple_rpz(_rec)


# show rpz record <type>
register(
    "show rpz record",
    words=" ".join(_SIMPLE_RPZ_RECORDS.keys()) + " mx srv ptr naptr https svcb "
    "a_ipaddress aaaa_ipaddress "
    "cname_clientipaddress cname_clientipaddressdn "
    "cname_ipaddress cname_ipaddressdn",
    help="RPZ records by type (A, CNAME, IP, client-IP, …).",
)

for _rec in _SIMPLE_RPZ_RECORDS:
    register(f"show rpz record {_rec}", words="<cr> <name> zone")
    register(f"show rpz record {_rec} zone", words="<zone>")
    register(f"show rpz record {_rec} zone <zone>", words="<cr>")
    register(f"show rpz record {_rec} <name>", words="zone")
    register(f"show rpz record {_rec} <name> zone", words="<zone>")
    register(f"show rpz record {_rec} <name> zone <zone>", words="<cr>")


def _bind_simple_rpz_show(rec: str) -> None:
    sdk_attr, _field = _SIMPLE_RPZ_RECORDS[rec]

    @command(
        f"show rpz record {rec}",
        words="<cr> <name> zone",
        help=f"Show RPZ {rec} records.",
    )
    @command(
        f"show rpz record {rec} zone <zone>",
        words="<cr>",
        help=f"Show RPZ {rec} records for a zone.",
    )
    @command(
        f"show rpz record {rec} <name> zone <zone>",
        words="<cr>",
        help=f"Show a specific RPZ {rec} record.",
    )
    async def _show(line: str, ctx: Context) -> None:
        if ctx.client is None:
            print("  Not connected")
            return
        # Try named match first, then zone-only
        m_named = re.search(rf"\bshow rpz record {re.escape(rec)} (\S+) zone (\S+)", line)
        m_zone_only = re.search(rf"\bshow rpz record {re.escape(rec)} zone (\S+)", line)
        params: dict = {}
        if m_named:
            params["name"] = m_named.group(1)
            params["zone"] = m_named.group(2)
        elif m_zone_only:
            params["zone"] = m_zone_only.group(1)
        resource = _rpz_resource(ctx, sdk_attr)
        records = [as_dict(r) async for r in resource.list(**params)]
        for r in records:
            parts = [f"type=rpz:{rec}"]
            for k, v in r.items():
                if not k.startswith("_"):
                    parts.append(f"{k}={v}")
            print(" ".join(parts))


for _rec in _SIMPLE_RPZ_RECORDS:
    _bind_simple_rpz_show(_rec)


# ---------------------------------------------------------------------------
# Chunk C: IP-address / client-IP variants
#
#   a_ipaddress         -> record_rpz_a_ipaddress    (name=CIDR, ipv4addr=<ip>)
#   aaaa_ipaddress      -> record_rpz_aaaa_ipaddress  (name=CIDR, ipv6addr=<ip>)
#   cname_clientipaddress    -> record_rpz_cname_clientipaddress  (name=CIDR, canonical)
#   cname_clientipaddressdn  -> record_rpz_cname_clientipaddressdn (name=CIDR, canonical)
#   cname_ipaddress          -> record_rpz_cname_ipaddress        (name=CIDR, canonical)
#   cname_ipaddressdn        -> record_rpz_cname_ipaddressdn      (name=CIDR, canonical)
# ---------------------------------------------------------------------------

_IP_VARIANT_RECORDS: dict[str, tuple[str, str]] = {
    "a_ipaddress": ("record_rpz_a_ipaddress", "ipv4addr"),
    "aaaa_ipaddress": ("record_rpz_aaaa_ipaddress", "ipv6addr"),
    "cname_clientipaddress": ("record_rpz_cname_clientipaddress", "canonical"),
    "cname_clientipaddressdn": ("record_rpz_cname_clientipaddressdn", "canonical"),
    "cname_ipaddress": ("record_rpz_cname_ipaddress", "canonical"),
    "cname_ipaddressdn": ("record_rpz_cname_ipaddressdn", "canonical"),
}

for _rec in _IP_VARIANT_RECORDS:
    register(f"configure rpz record {_rec}", words="add <name>")
    register(f"configure rpz record {_rec} add", words="<name>")
    register(f"configure rpz record {_rec} add <name>", words="<name>")
    register(f"configure rpz record {_rec} add <name> <name>", words="zone")
    register(f"configure rpz record {_rec} add <name> <name> zone", words="<zone>")
    register(
        f"configure rpz record {_rec} add <name> <name> zone <zone>",
        words="<cr> view=<name>",
    )
    register(f"configure rpz record {_rec} <name>", words="delete")
    register(f"configure rpz record {_rec} <name> delete", words="zone")
    register(f"configure rpz record {_rec} <name> delete zone", words="<zone>")
    register(
        f"configure rpz record {_rec} <name> delete zone <zone>",
        words="<cr> view=<name>",
    )
    register(f"show rpz record {_rec}", words="<cr> <name> zone")
    register(f"show rpz record {_rec} zone", words="<zone>")
    register(f"show rpz record {_rec} zone <zone>", words="<cr>")
    register(f"show rpz record {_rec} <name>", words="zone")
    register(f"show rpz record {_rec} <name> zone", words="<zone>")
    register(f"show rpz record {_rec} <name> zone <zone>", words="<cr>")


def _bind_ip_variant(rec: str) -> None:
    sdk_attr, field = _IP_VARIANT_RECORDS[rec]

    def make_add(r=rec, sa=sdk_attr, f=field):
        async def _h(line: str, ctx: Context) -> None:
            if ctx.client is None:
                print("  Not connected")
                return
            m = re.search(
                rf"\brpz record {re.escape(r)} add (\S+) (\S+) zone (\S+)",
                line,
            )
            if not m:
                print("  Error: name, value, and zone required")
                return
            name, value, rpz_zone = m.group(1), m.group(2), m.group(3)
            body: dict = {"name": name, f: value, "rp_zone": rpz_zone}
            view = _kv(line, "view")
            if view:
                body["view"] = view
            await _rpz_resource(ctx, sa).create(body)

        return _h

    def make_del(r=rec, sa=sdk_attr):
        async def _h(line: str, ctx: Context) -> None:
            if ctx.client is None:
                print("  Not connected")
                return
            m = re.search(
                rf"\brpz record {re.escape(r)} (\S+) delete zone (\S+)",
                line,
            )
            if not m:
                return
            name, rpz_zone = m.group(1), m.group(2)
            view = _kv(line, "view")
            params: dict = {"name": name, "zone": rpz_zone}
            if view:
                params["view"] = view
            resource = _rpz_resource(ctx, sa)
            records = [as_dict(x) async for x in resource.list(**params)]
            if not records:
                print(f"  No rpz {r} record found: {name}")
                return
            await resource.delete(records[0]["_ref"])

        return _h

    def make_show(r=rec, sa=sdk_attr):
        async def _h(line: str, ctx: Context) -> None:
            if ctx.client is None:
                print("  Not connected")
                return
            m_named = re.search(rf"\bshow rpz record {re.escape(r)} (\S+) zone (\S+)", line)
            m_zone_only = re.search(rf"\bshow rpz record {re.escape(r)} zone (\S+)", line)
            params: dict = {}
            if m_named:
                params["name"] = m_named.group(1)
                params["zone"] = m_named.group(2)
            elif m_zone_only:
                params["zone"] = m_zone_only.group(1)
            resource = _rpz_resource(ctx, sa)
            records = [as_dict(x) async for x in resource.list(**params)]
            for rec_obj in records:
                parts = [f"type=rpz:{r}"]
                for k, v in rec_obj.items():
                    if not k.startswith("_"):
                        parts.append(f"{k}={v}")
                print(" ".join(parts))

        return _h

    command(
        f"configure rpz record {rec} add <name> <name> zone <zone>",
        words="<cr> view=<name>",
        help=f"Add an RPZ {rec} record.",
    )(make_add())
    command(
        f"configure rpz record {rec} <name> delete zone <zone>",
        words="<cr> view=<name>",
        help=f"Delete an RPZ {rec} record.",
    )(make_del())
    command(
        f"show rpz record {rec}",
        words="<cr> <name> zone",
        help=f"Show RPZ {rec} records.",
    )(make_show())
    command(
        f"show rpz record {rec} zone <zone>",
        words="<cr>",
        help=f"Show RPZ {rec} records for a zone.",
    )(make_show())
    command(
        f"show rpz record {rec} <name> zone <zone>",
        words="<cr>",
        help=f"Show a specific RPZ {rec} record.",
    )(make_show())


for _rec in _IP_VARIANT_RECORDS:
    _bind_ip_variant(_rec)


# ---------------------------------------------------------------------------
# Chunk D: Other record rewrites - mx, srv, ptr, naptr, https, svcb
# ---------------------------------------------------------------------------

# --- MX ---
# configure rpz record mx add <name> <name:mx_host> <priority> zone <zone>
register("configure rpz record mx", words="add <name>")
register("configure rpz record mx add", words="<name>")
register("configure rpz record mx add <name>", words="<name>")
register("configure rpz record mx add <name> <name>", words="<priority>")
register("configure rpz record mx add <name> <name> <priority>", words="zone")
register("configure rpz record mx add <name> <name> <priority> zone", words="<zone>")
register(
    "configure rpz record mx add <name> <name> <priority> zone <zone>", words="<cr> view=<name>"
)
register("configure rpz record mx <name>", words="delete")
register("configure rpz record mx <name> delete", words="zone")
register("configure rpz record mx <name> delete zone", words="<zone>")
register("configure rpz record mx <name> delete zone <zone>", words="<cr> view=<name>")
register("show rpz record mx", words="<cr> <name> zone")
register("show rpz record mx zone", words="<zone>")
register("show rpz record mx zone <zone>", words="<cr>")
register("show rpz record mx <name>", words="zone")
register("show rpz record mx <name> zone", words="<zone>")
register("show rpz record mx <name> zone <zone>", words="<cr>")


@command(
    "configure rpz record mx add <name> <name> <priority> zone <zone>",
    words="<cr> view=<name>",
    help="Add an RPZ MX record.",
)
async def cli_rpz_mx_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brpz record mx add (\S+) (\S+) (\d+) zone (\S+)", line)
    if not m:
        print("  Error: name, mail_exchanger, preference, and zone required")
        return
    name, mx_host, pref, rpz_zone = m.group(1), m.group(2), int(m.group(3)), m.group(4)
    body: dict = {
        "name": name,
        "mail_exchanger": mx_host,
        "preference": pref,
        "rp_zone": rpz_zone,
    }
    view = _kv(line, "view")
    if view:
        body["view"] = view
    await ctx.client.rpz.record_rpz_mx.create(body)


@command(
    "configure rpz record mx <name> delete zone <zone>",
    words="<cr> view=<name>",
    help="Delete an RPZ MX record.",
)
async def cli_rpz_mx_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brpz record mx (\S+) delete zone (\S+)", line)
    if not m:
        return
    name, rpz_zone = m.group(1), m.group(2)
    view = _kv(line, "view")
    params: dict = {"name": name, "zone": rpz_zone}
    if view:
        params["view"] = view
    records = [as_dict(r) async for r in ctx.client.rpz.record_rpz_mx.list(**params)]
    if not records:
        print(f"  No rpz mx record found: {name}")
        return
    await ctx.client.rpz.record_rpz_mx.delete(records[0]["_ref"])


@command("show rpz record mx", words="<cr> <name> zone", help="Show RPZ MX records.")
@command("show rpz record mx zone <zone>", words="<cr>")
@command("show rpz record mx <name> zone <zone>", words="<cr>")
async def cli_rpz_mx_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m_named = re.search(r"\bshow rpz record mx (\S+) zone (\S+)", line)
    m_zone = re.search(r"\bshow rpz record mx zone (\S+)", line)
    params: dict = {}
    if m_named:
        params["name"] = m_named.group(1)
        params["zone"] = m_named.group(2)
    elif m_zone:
        params["zone"] = m_zone.group(1)
    records = [as_dict(r) async for r in ctx.client.rpz.record_rpz_mx.list(**params)]
    for r in records:
        parts = ["type=rpz:mx"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# --- SRV ---
# configure rpz record srv add <name> <name:target> <priority> <weight> <port> zone <zone>
register("configure rpz record srv", words="add <name>")
register("configure rpz record srv add", words="<name>")
register("configure rpz record srv add <name>", words="<name>")
register("configure rpz record srv add <name> <name>", words="<priority>")
register("configure rpz record srv add <name> <name> <priority>", words="<weight>")
register("configure rpz record srv add <name> <name> <priority> <weight>", words="<port>")
register("configure rpz record srv add <name> <name> <priority> <weight> <port>", words="zone")
register(
    "configure rpz record srv add <name> <name> <priority> <weight> <port> zone", words="<zone>"
)
register(
    "configure rpz record srv add <name> <name> <priority> <weight> <port> zone <zone>",
    words="<cr> view=<name>",
)
register("configure rpz record srv <name>", words="delete")
register("configure rpz record srv <name> delete", words="zone")
register("configure rpz record srv <name> delete zone", words="<zone>")
register("configure rpz record srv <name> delete zone <zone>", words="<cr> view=<name>")
register("show rpz record srv", words="<cr> <name> zone")
register("show rpz record srv zone", words="<zone>")
register("show rpz record srv zone <zone>", words="<cr>")
register("show rpz record srv <name>", words="zone")
register("show rpz record srv <name> zone", words="<zone>")
register("show rpz record srv <name> zone <zone>", words="<cr>")


@command(
    "configure rpz record srv add <name> <name> <priority> <weight> <port> zone <zone>",
    words="<cr> view=<name>",
    help="Add an RPZ SRV record.",
)
async def cli_rpz_srv_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brpz record srv add (\S+) (\S+) (\d+) (\d+) (\d+) zone (\S+)", line)
    if not m:
        print("  Error: name, target, priority, weight, port, and zone required")
        return
    name, target, priority, weight, port, rpz_zone = (
        m.group(1),
        m.group(2),
        int(m.group(3)),
        int(m.group(4)),
        int(m.group(5)),
        m.group(6),
    )
    body: dict = {
        "name": name,
        "target": target,
        "priority": priority,
        "weight": weight,
        "port": port,
        "rp_zone": rpz_zone,
    }
    view = _kv(line, "view")
    if view:
        body["view"] = view
    await ctx.client.rpz.record_rpz_srv.create(body)


@command(
    "configure rpz record srv <name> delete zone <zone>",
    words="<cr> view=<name>",
    help="Delete an RPZ SRV record.",
)
async def cli_rpz_srv_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brpz record srv (\S+) delete zone (\S+)", line)
    if not m:
        return
    name, rpz_zone = m.group(1), m.group(2)
    view = _kv(line, "view")
    params: dict = {"name": name, "zone": rpz_zone}
    if view:
        params["view"] = view
    records = [as_dict(r) async for r in ctx.client.rpz.record_rpz_srv.list(**params)]
    if not records:
        print(f"  No rpz srv record found: {name}")
        return
    await ctx.client.rpz.record_rpz_srv.delete(records[0]["_ref"])


@command("show rpz record srv", words="<cr> <name> zone", help="Show RPZ SRV records.")
@command("show rpz record srv zone <zone>", words="<cr>")
@command("show rpz record srv <name> zone <zone>", words="<cr>")
async def cli_rpz_srv_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m_named = re.search(r"\bshow rpz record srv (\S+) zone (\S+)", line)
    m_zone = re.search(r"\bshow rpz record srv zone (\S+)", line)
    params: dict = {}
    if m_named:
        params["name"] = m_named.group(1)
        params["zone"] = m_named.group(2)
    elif m_zone:
        params["zone"] = m_zone.group(1)
    records = [as_dict(r) async for r in ctx.client.rpz.record_rpz_srv.list(**params)]
    for r in records:
        parts = ["type=rpz:srv"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# --- PTR ---
# configure rpz record ptr add <name:fqdn> <name:ptrdname> zone <zone>
register("configure rpz record ptr", words="add <name>")
register("configure rpz record ptr add", words="<name>")
register("configure rpz record ptr add <name>", words="<name>")
register("configure rpz record ptr add <name> <name>", words="zone")
register("configure rpz record ptr add <name> <name> zone", words="<zone>")
register("configure rpz record ptr add <name> <name> zone <zone>", words="<cr> view=<name>")
register("configure rpz record ptr <name>", words="delete")
register("configure rpz record ptr <name> delete", words="zone")
register("configure rpz record ptr <name> delete zone", words="<zone>")
register("configure rpz record ptr <name> delete zone <zone>", words="<cr> view=<name>")
register("show rpz record ptr", words="<cr> <name> zone")
register("show rpz record ptr zone", words="<zone>")
register("show rpz record ptr zone <zone>", words="<cr>")
register("show rpz record ptr <name>", words="zone")
register("show rpz record ptr <name> zone", words="<zone>")
register("show rpz record ptr <name> zone <zone>", words="<cr>")


@command(
    "configure rpz record ptr add <name> <name> zone <zone>",
    words="<cr> view=<name>",
    help="Add an RPZ PTR record.",
)
async def cli_rpz_ptr_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brpz record ptr add (\S+) (\S+) zone (\S+)", line)
    if not m:
        print("  Error: name, ptrdname, and zone required")
        return
    name, ptrdname, rpz_zone = m.group(1), m.group(2), m.group(3)
    body: dict = {"name": name, "ptrdname": ptrdname, "rp_zone": rpz_zone}
    view = _kv(line, "view")
    if view:
        body["view"] = view
    await ctx.client.rpz.record_rpz_ptr.create(body)


@command(
    "configure rpz record ptr <name> delete zone <zone>",
    words="<cr> view=<name>",
    help="Delete an RPZ PTR record.",
)
async def cli_rpz_ptr_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brpz record ptr (\S+) delete zone (\S+)", line)
    if not m:
        return
    name, rpz_zone = m.group(1), m.group(2)
    view = _kv(line, "view")
    params: dict = {"name": name, "zone": rpz_zone}
    if view:
        params["view"] = view
    records = [as_dict(r) async for r in ctx.client.rpz.record_rpz_ptr.list(**params)]
    if not records:
        print(f"  No rpz ptr record found: {name}")
        return
    await ctx.client.rpz.record_rpz_ptr.delete(records[0]["_ref"])


@command("show rpz record ptr", words="<cr> <name> zone", help="Show RPZ PTR records.")
@command("show rpz record ptr zone <zone>", words="<cr>")
@command("show rpz record ptr <name> zone <zone>", words="<cr>")
async def cli_rpz_ptr_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m_named = re.search(r"\bshow rpz record ptr (\S+) zone (\S+)", line)
    m_zone = re.search(r"\bshow rpz record ptr zone (\S+)", line)
    params: dict = {}
    if m_named:
        params["name"] = m_named.group(1)
        params["zone"] = m_named.group(2)
    elif m_zone:
        params["zone"] = m_zone.group(1)
    records = [as_dict(r) async for r in ctx.client.rpz.record_rpz_ptr.list(**params)]
    for r in records:
        parts = ["type=rpz:ptr"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# --- NAPTR ---
# configure rpz record naptr add <name> <order:priority> <preference:priority> <name:replacement> zone <zone>
register("configure rpz record naptr", words="add <name>")
register("configure rpz record naptr add", words="<name>")
register("configure rpz record naptr add <name>", words="<priority>")
register("configure rpz record naptr add <name> <priority>", words="<priority>")
register("configure rpz record naptr add <name> <priority> <priority>", words="<name>")
register("configure rpz record naptr add <name> <priority> <priority> <name>", words="zone")
register("configure rpz record naptr add <name> <priority> <priority> <name> zone", words="<zone>")
register(
    "configure rpz record naptr add <name> <priority> <priority> <name> zone <zone>",
    words="<cr> view=<name>",
)
register("configure rpz record naptr <name>", words="delete")
register("configure rpz record naptr <name> delete", words="zone")
register("configure rpz record naptr <name> delete zone", words="<zone>")
register("configure rpz record naptr <name> delete zone <zone>", words="<cr> view=<name>")
register("show rpz record naptr", words="<cr> <name> zone")
register("show rpz record naptr zone", words="<zone>")
register("show rpz record naptr zone <zone>", words="<cr>")
register("show rpz record naptr <name>", words="zone")
register("show rpz record naptr <name> zone", words="<zone>")
register("show rpz record naptr <name> zone <zone>", words="<cr>")


@command(
    "configure rpz record naptr add <name> <priority> <priority> <name> zone <zone>",
    words="<cr> view=<name>",
    help="Add an RPZ NAPTR record.",
)
async def cli_rpz_naptr_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brpz record naptr add (\S+) (\d+) (\d+) (\S+) zone (\S+)", line)
    if not m:
        print("  Error: name, order, preference, replacement, and zone required")
        return
    name, order, preference, replacement, rpz_zone = (
        m.group(1),
        int(m.group(2)),
        int(m.group(3)),
        m.group(4),
        m.group(5),
    )
    body: dict = {
        "name": name,
        "order": order,
        "preference": preference,
        "replacement": replacement,
        "rp_zone": rpz_zone,
    }
    view = _kv(line, "view")
    if view:
        body["view"] = view
    await ctx.client.rpz.record_rpz_naptr.create(body)


@command(
    "configure rpz record naptr <name> delete zone <zone>",
    words="<cr> view=<name>",
    help="Delete an RPZ NAPTR record.",
)
async def cli_rpz_naptr_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brpz record naptr (\S+) delete zone (\S+)", line)
    if not m:
        return
    name, rpz_zone = m.group(1), m.group(2)
    view = _kv(line, "view")
    params: dict = {"name": name, "zone": rpz_zone}
    if view:
        params["view"] = view
    records = [as_dict(r) async for r in ctx.client.rpz.record_rpz_naptr.list(**params)]
    if not records:
        print(f"  No rpz naptr record found: {name}")
        return
    await ctx.client.rpz.record_rpz_naptr.delete(records[0]["_ref"])


@command("show rpz record naptr", words="<cr> <name> zone", help="Show RPZ NAPTR records.")
@command("show rpz record naptr zone <zone>", words="<cr>")
@command("show rpz record naptr <name> zone <zone>", words="<cr>")
async def cli_rpz_naptr_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m_named = re.search(r"\bshow rpz record naptr (\S+) zone (\S+)", line)
    m_zone = re.search(r"\bshow rpz record naptr zone (\S+)", line)
    params: dict = {}
    if m_named:
        params["name"] = m_named.group(1)
        params["zone"] = m_named.group(2)
    elif m_zone:
        params["zone"] = m_zone.group(1)
    records = [as_dict(r) async for r in ctx.client.rpz.record_rpz_naptr.list(**params)]
    for r in records:
        parts = ["type=rpz:naptr"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# --- HTTPS ---
# configure rpz record https add <name> <name:target_name> <priority> zone <zone>
register("configure rpz record https", words="add <name>")
register("configure rpz record https add", words="<name>")
register("configure rpz record https add <name>", words="<name>")
register("configure rpz record https add <name> <name>", words="<priority>")
register("configure rpz record https add <name> <name> <priority>", words="zone")
register("configure rpz record https add <name> <name> <priority> zone", words="<zone>")
register(
    "configure rpz record https add <name> <name> <priority> zone <zone>", words="<cr> view=<name>"
)
register("configure rpz record https <name>", words="delete")
register("configure rpz record https <name> delete", words="zone")
register("configure rpz record https <name> delete zone", words="<zone>")
register("configure rpz record https <name> delete zone <zone>", words="<cr> view=<name>")
register("show rpz record https", words="<cr> <name> zone")
register("show rpz record https zone", words="<zone>")
register("show rpz record https zone <zone>", words="<cr>")
register("show rpz record https <name>", words="zone")
register("show rpz record https <name> zone", words="<zone>")
register("show rpz record https <name> zone <zone>", words="<cr>")


@command(
    "configure rpz record https add <name> <name> <priority> zone <zone>",
    words="<cr> view=<name>",
    help="Add an RPZ HTTPS record.",
)
async def cli_rpz_https_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brpz record https add (\S+) (\S+) (\d+) zone (\S+)", line)
    if not m:
        print("  Error: name, target_name, priority, and zone required")
        return
    name, target_name, priority, rpz_zone = (m.group(1), m.group(2), int(m.group(3)), m.group(4))
    body: dict = {
        "name": name,
        "target_name": target_name,
        "priority": priority,
        "rp_zone": rpz_zone,
    }
    view = _kv(line, "view")
    if view:
        body["view"] = view
    await ctx.client.rpz.record_rpz_https.create(body)


@command(
    "configure rpz record https <name> delete zone <zone>",
    words="<cr> view=<name>",
    help="Delete an RPZ HTTPS record.",
)
async def cli_rpz_https_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brpz record https (\S+) delete zone (\S+)", line)
    if not m:
        return
    name, rpz_zone = m.group(1), m.group(2)
    view = _kv(line, "view")
    params: dict = {"name": name, "zone": rpz_zone}
    if view:
        params["view"] = view
    records = [as_dict(r) async for r in ctx.client.rpz.record_rpz_https.list(**params)]
    if not records:
        print(f"  No rpz https record found: {name}")
        return
    await ctx.client.rpz.record_rpz_https.delete(records[0]["_ref"])


@command("show rpz record https", words="<cr> <name> zone", help="Show RPZ HTTPS records.")
@command("show rpz record https zone <zone>", words="<cr>")
@command("show rpz record https <name> zone <zone>", words="<cr>")
async def cli_rpz_https_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m_named = re.search(r"\bshow rpz record https (\S+) zone (\S+)", line)
    m_zone = re.search(r"\bshow rpz record https zone (\S+)", line)
    params: dict = {}
    if m_named:
        params["name"] = m_named.group(1)
        params["zone"] = m_named.group(2)
    elif m_zone:
        params["zone"] = m_zone.group(1)
    records = [as_dict(r) async for r in ctx.client.rpz.record_rpz_https.list(**params)]
    for r in records:
        parts = ["type=rpz:https"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# --- SVCB ---
# configure rpz record svcb add <name> <name:target_name> <priority> zone <zone>
register("configure rpz record svcb", words="add <name>")
register("configure rpz record svcb add", words="<name>")
register("configure rpz record svcb add <name>", words="<name>")
register("configure rpz record svcb add <name> <name>", words="<priority>")
register("configure rpz record svcb add <name> <name> <priority>", words="zone")
register("configure rpz record svcb add <name> <name> <priority> zone", words="<zone>")
register(
    "configure rpz record svcb add <name> <name> <priority> zone <zone>", words="<cr> view=<name>"
)
register("configure rpz record svcb <name>", words="delete")
register("configure rpz record svcb <name> delete", words="zone")
register("configure rpz record svcb <name> delete zone", words="<zone>")
register("configure rpz record svcb <name> delete zone <zone>", words="<cr> view=<name>")
register("show rpz record svcb", words="<cr> <name> zone")
register("show rpz record svcb zone", words="<zone>")
register("show rpz record svcb zone <zone>", words="<cr>")
register("show rpz record svcb <name>", words="zone")
register("show rpz record svcb <name> zone", words="<zone>")
register("show rpz record svcb <name> zone <zone>", words="<cr>")


@command(
    "configure rpz record svcb add <name> <name> <priority> zone <zone>",
    words="<cr> view=<name>",
    help="Add an RPZ SVCB record.",
)
async def cli_rpz_svcb_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brpz record svcb add (\S+) (\S+) (\d+) zone (\S+)", line)
    if not m:
        print("  Error: name, target_name, priority, and zone required")
        return
    name, target_name, priority, rpz_zone = (m.group(1), m.group(2), int(m.group(3)), m.group(4))
    body: dict = {
        "name": name,
        "target_name": target_name,
        "priority": priority,
        "rp_zone": rpz_zone,
    }
    view = _kv(line, "view")
    if view:
        body["view"] = view
    await ctx.client.rpz.record_rpz_svcb.create(body)


@command(
    "configure rpz record svcb <name> delete zone <zone>",
    words="<cr> view=<name>",
    help="Delete an RPZ SVCB record.",
)
async def cli_rpz_svcb_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\brpz record svcb (\S+) delete zone (\S+)", line)
    if not m:
        return
    name, rpz_zone = m.group(1), m.group(2)
    view = _kv(line, "view")
    params: dict = {"name": name, "zone": rpz_zone}
    if view:
        params["view"] = view
    records = [as_dict(r) async for r in ctx.client.rpz.record_rpz_svcb.list(**params)]
    if not records:
        print(f"  No rpz svcb record found: {name}")
        return
    await ctx.client.rpz.record_rpz_svcb.delete(records[0]["_ref"])


@command("show rpz record svcb", words="<cr> <name> zone", help="Show RPZ SVCB records.")
@command("show rpz record svcb zone <zone>", words="<cr>")
@command("show rpz record svcb <name> zone <zone>", words="<cr>")
async def cli_rpz_svcb_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m_named = re.search(r"\bshow rpz record svcb (\S+) zone (\S+)", line)
    m_zone = re.search(r"\bshow rpz record svcb zone (\S+)", line)
    params: dict = {}
    if m_named:
        params["name"] = m_named.group(1)
        params["zone"] = m_named.group(2)
    elif m_zone:
        params["zone"] = m_zone.group(1)
    records = [as_dict(r) async for r in ctx.client.rpz.record_rpz_svcb.list(**params)]
    for r in records:
        parts = ["type=rpz:svcb"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# ---------------------------------------------------------------------------
# Chunk E: allrpzrecords aggregator (read-only)
# ---------------------------------------------------------------------------

register("show rpz records", words="zone=<name>")
register("show rpz records zone=<name>", words="<cr>")


@command(
    "show rpz records", words="zone=<name>", help="Show all RPZ records in a zone (aggregate)."
)
async def cli_rpz_allrecords_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bzone[= ](\S+)", line)
    if not m:
        print("  Error: zone required (usage: show rpz records zone=<zone>)")
        return
    params: dict = {"zone": m.group(1)}
    records = [as_dict(r) async for r in ctx.client.rpz.allrpzrecords.list(**params)]
    for r in records:
        parts = []
        rtype = r.get("type") or r.get("type_")
        if rtype:
            parts.append(f"type={rtype}")
        for k, v in r.items():
            if not k.startswith("_") and k not in ("type", "type_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))
