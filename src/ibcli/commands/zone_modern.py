# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""zone_modern.py - Phase 3 DNS record commands.

Adds add/delete/show for modern RRtypes, DNSSEC (show-only), and shared records.
All handlers follow the same pattern as zone.py.

Chunks:
  A - CAA, DNAME, ALIAS, NS  (simple field shapes)
  B - NAPTR, TLSA, HTTPS, SVCB  (complex field shapes)
  C - DNSKEY, DS, RRSIG, NSEC, NSEC3, NSEC3PARAM, DHCID  (show-only DNSSEC)
  D - sharedrecord A, AAAA, CNAME, MX, TXT, SRV  (full CRUD)
"""

from __future__ import annotations

import re

# Re-use private helpers from zone.py directly.
from ibcli.commands.zone import (
    _parse_comment,
    _parse_extattrs,
    _parse_kv,
)
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict

# ---------------------------------------------------------------------------
# Top-level waypoints - extend "configure" and "show" with new sub-commands.
# Multiple modules can call register() on the same key; words are merged.
# ---------------------------------------------------------------------------

register("configure", words="record shared_record", help="Create, modify or delete grid objects.")
register(
    "configure record",
    words="caa dname alias ns naptr tlsa https svcb",
    help="Create DNS records by type: CAA, DNAME, ALIAS, NS, NAPTR, TLSA, HTTPS, SVCB. For zone-scoped A/AAAA/CNAME/MX/TXT/PTR use 'configure zone <z> add <type>' instead.",
)
register(
    "show record",
    words="caa dname alias ns naptr tlsa https svcb dnskey ds rrsig nsec nsec3 nsec3param dhcid",
    help="DNS records - all modern types (CAA, HTTPS, SVCB, NAPTR…).",
)
register("show", words="shared_record", help="Read grid state without modifying anything.")
register("show shared_record", words="a aaaa cname mx txt srv", help="Shared DNS records.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _modern_resource(ctx: Context, objtype: str):
    """Return the SDK resource for a modern/DNSSEC record objtype."""
    return {
        "record:caa": ctx.client.dns.record_caa,
        "record:dname": ctx.client.dns.record_dname,
        "record:alias": ctx.client.dns.record_alias,
        "record:ns": ctx.client.dns.record_ns,
        "record:naptr": ctx.client.dns.record_naptr,
        "record:tlsa": ctx.client.dns.record_tlsa,
        "record:https": ctx.client.dns.record_https,
        "record:svcb": ctx.client.dns.record_svcb,
        # DNSSEC - read-only
        "record:dnskey": ctx.client.dns.record_dnskey,
        "record:ds": ctx.client.dns.record_ds,
        "record:rrsig": ctx.client.dns.record_rrsig,
        "record:nsec": ctx.client.dns.record_nsec,
        "record:nsec3": ctx.client.dns.record_nsec3,
        "record:nsec3param": ctx.client.dns.record_nsec3param,
        "record:dhcid": ctx.client.dns.record_dhcid,
    }[objtype]


def _shared_resource(ctx: Context, objtype: str):
    """Return the SDK resource for a sharedrecord objtype."""
    return {
        "sharedrecord:a": ctx.client.dns.sharedrecord_a,
        "sharedrecord:aaaa": ctx.client.dns.sharedrecord_aaaa,
        "sharedrecord:cname": ctx.client.dns.sharedrecord_cname,
        "sharedrecord:mx": ctx.client.dns.sharedrecord_mx,
        "sharedrecord:txt": ctx.client.dns.sharedrecord_txt,
        "sharedrecord:srv": ctx.client.dns.sharedrecord_srv,
    }[objtype]


async def _delete_by_name(resource, name: str, view: str | None) -> None:
    """Generic list-then-delete for records keyed by 'name'."""
    params: dict[str, str] = {"name": name}
    if view:
        params["view"] = view
    records = [as_dict(r) async for r in resource.list(**params)]
    if not records:
        print(f"  No record found: {name}")
        return
    await resource.delete(records[0]["_ref"])


async def _show_modern(objtype: str, name: str | None, view: str | None, ctx: Context) -> None:
    """Generic show for modern records, optionally filtered by name."""
    resource = _modern_resource(ctx, objtype)
    params: dict[str, str] = {}
    if name:
        params["name"] = name
    if view:
        params["view"] = view
    records = [as_dict(r) async for r in resource.list(**params)]
    short = objtype.replace("record:", "")
    for r in records:
        parts = [f"type={short}"]
        for k, v in r.items():
            if k.startswith("_"):
                continue
            parts.append(f"{k}={v}")
        print(" ".join(parts))


# ===========================================================================
# CHUNK A - CAA, DNAME, ALIAS, NS
# ===========================================================================

# ---------------------------------------------------------------------------
# CAA  (ca_flag ca_tag ca_value)
# ---------------------------------------------------------------------------

register("configure record caa", words="add delete")
register("configure record caa add", words="<name>")
register("configure record caa add <name>", words="<num>")
register("configure record caa add <name> <num>", words="<name>")
register("configure record caa add <name> <num> <name>", words="<value>")
register("configure record caa delete", words="<name>")
register("show record caa", words="<cr> <name>")


@command(
    "configure record caa add <name> <num> <name> <value>",
    words="<cr> view=<name> comment=<text>",
    help="Add a CAA record.",
)
async def cli_add_caa(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bcaa add (\S+) (\d+) (\S+) (\S+)", line)
    if not m:
        print("  Error: name, ca_flag, ca_tag, ca_value required")
        return
    name, ca_flag, ca_tag, ca_value = m.group(1), int(m.group(2)), m.group(3), m.group(4)
    body: dict = {"name": name, "ca_flag": ca_flag, "ca_tag": ca_tag, "ca_value": ca_value}
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    await ctx.client.dns.record_caa.create(body)


@command(
    "configure record caa delete <name>",
    words="<cr> view=<name>",
    help="Delete a CAA record by name.",
)
async def cli_delete_caa(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bcaa delete (\S+)", line)
    if not m:
        return
    name = m.group(1)
    view = _parse_kv(line, "view")
    await _delete_by_name(ctx.client.dns.record_caa, name, view)


@command("show record caa", words="<cr> <name> view=<name>", help="Show CAA records.")
@command("show record caa <name>", words="<cr> view=<name>", help="Show CAA record by name.")
async def cli_show_caa(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bcaa\s+(\S+)", line)
    name = m.group(1) if m else None
    view = _parse_kv(line, "view")
    await _show_modern("record:caa", name, view, ctx)


# ---------------------------------------------------------------------------
# DNAME  (name → target)
# ---------------------------------------------------------------------------

register("configure record dname", words="add delete")
register("configure record dname add", words="<name>")
register("configure record dname add <name>", words="<target>")
register("configure record dname delete", words="<name>")
register("show record dname", words="<cr> <name>")


@command(
    "configure record dname add <name> <target>",
    words="<cr> view=<name> comment=<text>",
    help="Add a DNAME record.",
)
async def cli_add_dname(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bdname add (\S+) (\S+)", line)
    if not m:
        print("  Error: name and target required")
        return
    name, target = m.group(1), m.group(2)
    body: dict = {"name": name, "target": target}
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    await ctx.client.dns.record_dname.create(body)


@command(
    "configure record dname delete <name>",
    words="<cr> view=<name>",
    help="Delete a DNAME record.",
)
async def cli_delete_dname(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bdname delete (\S+)", line)
    if not m:
        return
    name = m.group(1)
    view = _parse_kv(line, "view")
    await _delete_by_name(ctx.client.dns.record_dname, name, view)


@command("show record dname", words="<cr> <name> view=<name>", help="Show DNAME records.")
@command("show record dname <name>", words="<cr> view=<name>", help="Show DNAME record by name.")
async def cli_show_dname(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bdname\s+(\S+)", line)
    name = m.group(1) if m else None
    view = _parse_kv(line, "view")
    await _show_modern("record:dname", name, view, ctx)


# ---------------------------------------------------------------------------
# ALIAS  (name → target_name)
# ---------------------------------------------------------------------------

register("configure record alias", words="add delete")
register("configure record alias add", words="<name>")
register("configure record alias add <name>", words="<target>")
register("configure record alias delete", words="<name>")
register("show record alias", words="<cr> <name>")


@command(
    "configure record alias add <name> <target>",
    words="<cr> view=<name> comment=<text>",
    help="Add an ALIAS record.",
)
async def cli_add_alias(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\balias add (\S+) (\S+)", line)
    if not m:
        print("  Error: name and target_name required")
        return
    name, target_name = m.group(1), m.group(2)
    body: dict = {"name": name, "target_name": target_name}
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    await ctx.client.dns.record_alias.create(body)


@command(
    "configure record alias delete <name>",
    words="<cr> view=<name>",
    help="Delete an ALIAS record.",
)
async def cli_delete_alias(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\balias delete (\S+)", line)
    if not m:
        return
    name = m.group(1)
    view = _parse_kv(line, "view")
    await _delete_by_name(ctx.client.dns.record_alias, name, view)


@command("show record alias", words="<cr> <name> view=<name>", help="Show ALIAS records.")
@command("show record alias <name>", words="<cr> view=<name>", help="Show ALIAS record by name.")
async def cli_show_alias(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\balias\s+(\S+)", line)
    name = m.group(1) if m else None
    view = _parse_kv(line, "view")
    await _show_modern("record:alias", name, view, ctx)


# ---------------------------------------------------------------------------
# NS  (authoritative NS: name → nameserver)
# ---------------------------------------------------------------------------

register("configure record ns", words="add delete")
register("configure record ns add", words="<name>")
register("configure record ns add <name>", words="<target>")
register("configure record ns delete", words="<name>")
register("show record ns", words="<cr> <name>")


@command(
    "configure record ns add <name> <target>",
    words="<cr> view=<name> comment=<text>",
    help="Add an NS record.",
)
async def cli_add_ns(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bns add (\S+) (\S+)", line)
    if not m:
        print("  Error: name and nameserver required")
        return
    name, nameserver = m.group(1), m.group(2)
    body: dict = {"name": name, "nameserver": nameserver}
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    await ctx.client.dns.record_ns.create(body)


@command(
    "configure record ns delete <name>",
    words="<cr> view=<name>",
    help="Delete an NS record.",
)
async def cli_delete_ns(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bns delete (\S+)", line)
    if not m:
        return
    name = m.group(1)
    view = _parse_kv(line, "view")
    await _delete_by_name(ctx.client.dns.record_ns, name, view)


@command("show record ns", words="<cr> <name> view=<name>", help="Show NS records.")
@command("show record ns <name>", words="<cr> view=<name>", help="Show NS record by name.")
async def cli_show_ns(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bns\s+(\S+)", line)
    name = m.group(1) if m else None
    view = _parse_kv(line, "view")
    await _show_modern("record:ns", name, view, ctx)


# ===========================================================================
# CHUNK B - NAPTR, TLSA, HTTPS, SVCB
# ===========================================================================

# ---------------------------------------------------------------------------
# NAPTR  (name order preference flags services regexp replacement)
# ---------------------------------------------------------------------------

register("configure record naptr", words="add delete")
register("configure record naptr add", words="<name>")
register("configure record naptr add <name>", words="<num>")
register("configure record naptr add <name> <num>", words="<priority>")
register("configure record naptr add <name> <num> <priority>", words="<name>")
register("configure record naptr add <name> <num> <priority> <name>", words="<svr>")
register(
    "configure record naptr add <name> <num> <priority> <name> <svr>",
    words="<value>",
)
register(
    "configure record naptr add <name> <num> <priority> <name> <svr> <value>",
    words="<target>",
)
register("configure record naptr delete", words="<name>")
register("show record naptr", words="<cr> <name>")


@command(
    "configure record naptr add <name> <num> <priority> <name> <svr> <value> <target>",
    words="<cr> view=<name> comment=<text>",
    help="Add a NAPTR record.",
)
async def cli_add_naptr(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bnaptr add (\S+) (\d+) (\d+) (\S+) (\S+) (\S+) (\S+)", line)
    if not m:
        print("  Error: name, order, preference, flags, services, regexp, replacement required")
        return
    name = m.group(1)
    order = int(m.group(2))
    preference = int(m.group(3))
    flags = m.group(4)
    services = m.group(5)
    regexp = m.group(6)
    replacement = m.group(7)
    body: dict = {
        "name": name,
        "order": order,
        "preference": preference,
        "flags": flags,
        "services": services,
        "regexp": regexp,
        "replacement": replacement,
    }
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    await ctx.client.dns.record_naptr.create(body)


@command(
    "configure record naptr delete <name>",
    words="<cr> view=<name>",
    help="Delete a NAPTR record.",
)
async def cli_delete_naptr(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bnaptr delete (\S+)", line)
    if not m:
        return
    name = m.group(1)
    view = _parse_kv(line, "view")
    await _delete_by_name(ctx.client.dns.record_naptr, name, view)


@command("show record naptr", words="<cr> <name> view=<name>", help="Show NAPTR records.")
@command("show record naptr <name>", words="<cr> view=<name>", help="Show NAPTR record by name.")
async def cli_show_naptr(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bnaptr\s+(\S+)", line)
    name = m.group(1) if m else None
    view = _parse_kv(line, "view")
    await _show_modern("record:naptr", name, view, ctx)


# ---------------------------------------------------------------------------
# TLSA  (name certificate_usage selector matching_type certificate_data)
# NOTE: swagger field is matched_type; alias matching_type is accepted by SDK.
# ---------------------------------------------------------------------------

register("configure record tlsa", words="add delete")
register("configure record tlsa add", words="<name>")
register("configure record tlsa add <name>", words="<num>")
register("configure record tlsa add <name> <num>", words="<priority>")
register("configure record tlsa add <name> <num> <priority>", words="<weight>")
register(
    "configure record tlsa add <name> <num> <priority> <weight>",
    words="<value>",
)
register("configure record tlsa delete", words="<name>")
register("show record tlsa", words="<cr> <name>")


@command(
    "configure record tlsa add <name> <num> <priority> <weight> <value>",
    words="<cr> view=<name> comment=<text>",
    help="Add a TLSA record.",
)
async def cli_add_tlsa(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\btlsa add (\S+) (\d+) (\d+) (\d+) (\S+)", line)
    if not m:
        print(
            "  Error: name, certificate_usage, selector, matching_type, certificate_data required"
        )
        return
    name = m.group(1)
    certificate_usage = int(m.group(2))
    selector = int(m.group(3))
    matching_type = int(m.group(4))
    certificate_data = m.group(5)
    body: dict = {
        "name": name,
        "certificate_usage": certificate_usage,
        "selector": selector,
        "matching_type": matching_type,
        "certificate_data": certificate_data,
    }
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    await ctx.client.dns.record_tlsa.create(body)


@command(
    "configure record tlsa delete <name>",
    words="<cr> view=<name>",
    help="Delete a TLSA record.",
)
async def cli_delete_tlsa(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\btlsa delete (\S+)", line)
    if not m:
        return
    name = m.group(1)
    view = _parse_kv(line, "view")
    await _delete_by_name(ctx.client.dns.record_tlsa, name, view)


@command("show record tlsa", words="<cr> <name> view=<name>", help="Show TLSA records.")
@command("show record tlsa <name>", words="<cr> view=<name>", help="Show TLSA record by name.")
async def cli_show_tlsa(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\btlsa\s+(\S+)", line)
    name = m.group(1) if m else None
    view = _parse_kv(line, "view")
    await _show_modern("record:tlsa", name, view, ctx)


# ---------------------------------------------------------------------------
# HTTPS  (name priority target_name)
# svc_parameters are optional; pass via set key=value if needed in future.
# ---------------------------------------------------------------------------

register("configure record https", words="add delete")
register("configure record https add", words="<name>")
register("configure record https add <name>", words="<priority>")
register("configure record https add <name> <priority>", words="<target>")
register("configure record https delete", words="<name>")
register("show record https", words="<cr> <name>")


@command(
    "configure record https add <name> <priority> <target>",
    words="<cr> view=<name> comment=<text>",
    help="Add an HTTPS record.",
)
async def cli_add_https(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bhttps add (\S+) (\d+) (\S+)", line)
    if not m:
        print("  Error: name, priority, target_name required")
        return
    name, priority, target_name = m.group(1), int(m.group(2)), m.group(3)
    body: dict = {"name": name, "priority": priority, "target_name": target_name}
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    await ctx.client.dns.record_https.create(body)


@command(
    "configure record https delete <name>",
    words="<cr> view=<name>",
    help="Delete an HTTPS record.",
)
async def cli_delete_https(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bhttps delete (\S+)", line)
    if not m:
        return
    name = m.group(1)
    view = _parse_kv(line, "view")
    await _delete_by_name(ctx.client.dns.record_https, name, view)


@command("show record https", words="<cr> <name> view=<name>", help="Show HTTPS records.")
@command("show record https <name>", words="<cr> view=<name>", help="Show HTTPS record by name.")
async def cli_show_https(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bhttps\s+(\S+)", line)
    name = m.group(1) if m else None
    view = _parse_kv(line, "view")
    await _show_modern("record:https", name, view, ctx)


# ---------------------------------------------------------------------------
# SVCB  (name priority target_name)
# ---------------------------------------------------------------------------

register("configure record svcb", words="add delete")
register("configure record svcb add", words="<name>")
register("configure record svcb add <name>", words="<priority>")
register("configure record svcb add <name> <priority>", words="<target>")
register("configure record svcb delete", words="<name>")
register("show record svcb", words="<cr> <name>")


@command(
    "configure record svcb add <name> <priority> <target>",
    words="<cr> view=<name> comment=<text>",
    help="Add a SVCB record.",
)
async def cli_add_svcb(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bsvcb add (\S+) (\d+) (\S+)", line)
    if not m:
        print("  Error: name, priority, target_name required")
        return
    name, priority, target_name = m.group(1), int(m.group(2)), m.group(3)
    body: dict = {"name": name, "priority": priority, "target_name": target_name}
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    await ctx.client.dns.record_svcb.create(body)


@command(
    "configure record svcb delete <name>",
    words="<cr> view=<name>",
    help="Delete a SVCB record.",
)
async def cli_delete_svcb(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bsvcb delete (\S+)", line)
    if not m:
        return
    name = m.group(1)
    view = _parse_kv(line, "view")
    await _delete_by_name(ctx.client.dns.record_svcb, name, view)


@command("show record svcb", words="<cr> <name> view=<name>", help="Show SVCB records.")
@command("show record svcb <name>", words="<cr> view=<name>", help="Show SVCB record by name.")
async def cli_show_svcb(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bsvcb\s+(\S+)", line)
    name = m.group(1) if m else None
    view = _parse_kv(line, "view")
    await _show_modern("record:svcb", name, view, ctx)


# ===========================================================================
# CHUNK C - DNSSEC show-only records
# ===========================================================================

_DNSSEC_TYPES = {
    "dnskey": "record:dnskey",
    "ds": "record:ds",
    "rrsig": "record:rrsig",
    "nsec": "record:nsec",
    "nsec3": "record:nsec3",
    "nsec3param": "record:nsec3param",
    "dhcid": "record:dhcid",
}

for _dn in _DNSSEC_TYPES:
    register(f"show record {_dn}", words="<cr> <name> view=<name>")
    register(f"show record {_dn} <name>", words="<cr> view=<name>")


def _bind_dnssec_show(cli_key: str, objtype: str) -> None:
    @command(
        f"show record {cli_key}",
        words="<cr> <name> view=<name>",
        help=f"Show {cli_key.upper()} records (read-only, DNSSEC-generated).",
    )
    @command(
        f"show record {cli_key} <name>",
        words="<cr> view=<name>",
        help=f"Show {cli_key.upper()} record by name.",
    )
    async def _h(line: str, ctx: Context) -> None:
        if ctx.client is None:
            print("  Not connected")
            return
        m = re.search(rf"\b{cli_key}\s+(\S+)", line)
        name = m.group(1) if m else None
        view = _parse_kv(line, "view")
        await _show_modern(objtype, name, view, ctx)


for _dn_key, _dn_obj in _DNSSEC_TYPES.items():
    _bind_dnssec_show(_dn_key, _dn_obj)


# ===========================================================================
# CHUNK D - Shared records (A, AAAA, CNAME, MX, TXT, SRV)
# ===========================================================================
#
# Command form:
#   configure shared_record <rrtype> add <name> <value> group <group_name> [view ...] [comment ...]
#   configure shared_record <rrtype> delete <name> group <group_name>
#   show shared_record <rrtype> [group <group_name>]
#
# The ``group`` parameter maps to ``shared_record_group`` in WAPI.
# ---------------------------------------------------------------------------

register(
    "configure shared_record",
    words="a aaaa cname mx txt srv",
    help="Shared DNS records (replicated across multiple zones).",
)
register("show shared_record", words="a aaaa cname mx txt srv", help="Shared DNS records.")

# ---- A ----

register("configure shared_record a", words="add delete")
register("configure shared_record a add", words="<name>")
register("configure shared_record a add <name>", words="<value>")
register("configure shared_record a delete", words="<name>")
register("show shared_record a", words="<cr> group")
register("show shared_record a group", words="<name>")


@command(
    "configure shared_record a add <name> <value>",
    words="<cr> group=<name> view=<name> comment=<text>",
    help="Add a shared A record.",
)
async def cli_add_shared_a(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bshared_record a add (\S+) (\S+)", line)
    if not m:
        print("  Error: name and ipv4addr required")
        return
    name, ipv4addr = m.group(1), m.group(2)
    group = _parse_kv(line, "group")
    if not group:
        print("  Error: group required")
        return
    body: dict = {"name": name, "ipv4addr": ipv4addr, "shared_record_group": group}
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    await ctx.client.dns.sharedrecord_a.create(body)


@command(
    "configure shared_record a delete <name>",
    words="<cr> group=<name>",
    help="Delete a shared A record.",
)
async def cli_delete_shared_a(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bshared_record a delete (\S+)", line)
    if not m:
        return
    name = m.group(1)
    group = _parse_kv(line, "group")
    params: dict[str, str] = {"name": name}
    if group:
        params["shared_record_group"] = group
    records = [as_dict(r) async for r in ctx.client.dns.sharedrecord_a.list(**params)]
    if not records:
        print(f"  No shared A record found: {name}")
        return
    await ctx.client.dns.sharedrecord_a.delete(records[0]["_ref"])


@command("show shared_record a", words="<cr> group=<name>", help="Show shared A records.")
@command("show shared_record a group <name>", words="<cr>", help="Show shared A records by group.")
async def cli_show_shared_a(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    group = _parse_kv(line, "group")
    m_g = re.search(r"\bgroup\s+(\S+)", line)
    if not group and m_g:
        group = m_g.group(1)
    params: dict[str, str] = {}
    if group:
        params["shared_record_group"] = group
    records = [as_dict(r) async for r in ctx.client.dns.sharedrecord_a.list(**params)]
    for r in records:
        parts = ["type=sharedrecord:a"]
        for k, v in r.items():
            if k.startswith("_"):
                continue
            parts.append(f"{k}={v}")
        print(" ".join(parts))


# ---- AAAA ----

register("configure shared_record aaaa", words="add delete")
register("configure shared_record aaaa add", words="<name>")
register("configure shared_record aaaa add <name>", words="<value>")
register("configure shared_record aaaa delete", words="<name>")
register("show shared_record aaaa", words="<cr> group")
register("show shared_record aaaa group", words="<name>")


@command(
    "configure shared_record aaaa add <name> <value>",
    words="<cr> group=<name> view=<name> comment=<text>",
    help="Add a shared AAAA record.",
)
async def cli_add_shared_aaaa(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bshared_record aaaa add (\S+) (\S+)", line)
    if not m:
        print("  Error: name and ipv6addr required")
        return
    name, ipv6addr = m.group(1), m.group(2)
    group = _parse_kv(line, "group")
    if not group:
        print("  Error: group required")
        return
    body: dict = {"name": name, "ipv6addr": ipv6addr, "shared_record_group": group}
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    await ctx.client.dns.sharedrecord_aaaa.create(body)


@command(
    "configure shared_record aaaa delete <name>",
    words="<cr> group=<name>",
    help="Delete a shared AAAA record.",
)
async def cli_delete_shared_aaaa(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bshared_record aaaa delete (\S+)", line)
    if not m:
        return
    name = m.group(1)
    group = _parse_kv(line, "group")
    params: dict[str, str] = {"name": name}
    if group:
        params["shared_record_group"] = group
    records = [as_dict(r) async for r in ctx.client.dns.sharedrecord_aaaa.list(**params)]
    if not records:
        print(f"  No shared AAAA record found: {name}")
        return
    await ctx.client.dns.sharedrecord_aaaa.delete(records[0]["_ref"])


@command("show shared_record aaaa", words="<cr> group=<name>", help="Show shared AAAA records.")
@command("show shared_record aaaa group <name>", words="<cr>", help="Show shared AAAA by group.")
async def cli_show_shared_aaaa(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    group = _parse_kv(line, "group")
    m_g = re.search(r"\bgroup\s+(\S+)", line)
    if not group and m_g:
        group = m_g.group(1)
    params: dict[str, str] = {}
    if group:
        params["shared_record_group"] = group
    records = [as_dict(r) async for r in ctx.client.dns.sharedrecord_aaaa.list(**params)]
    for r in records:
        parts = ["type=sharedrecord:aaaa"]
        for k, v in r.items():
            if k.startswith("_"):
                continue
            parts.append(f"{k}={v}")
        print(" ".join(parts))


# ---- CNAME ----

register("configure shared_record cname", words="add delete")
register("configure shared_record cname add", words="<name>")
register("configure shared_record cname add <name>", words="<canonical>")
register("configure shared_record cname delete", words="<name>")
register("show shared_record cname", words="<cr> group")
register("show shared_record cname group", words="<name>")


@command(
    "configure shared_record cname add <name> <canonical>",
    words="<cr> group=<name> view=<name> comment=<text>",
    help="Add a shared CNAME record.",
)
async def cli_add_shared_cname(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bshared_record cname add (\S+) (\S+)", line)
    if not m:
        print("  Error: name and canonical required")
        return
    name, canonical = m.group(1), m.group(2)
    group = _parse_kv(line, "group")
    if not group:
        print("  Error: group required")
        return
    body: dict = {"name": name, "canonical": canonical, "shared_record_group": group}
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    await ctx.client.dns.sharedrecord_cname.create(body)


@command(
    "configure shared_record cname delete <name>",
    words="<cr> group=<name>",
    help="Delete a shared CNAME record.",
)
async def cli_delete_shared_cname(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bshared_record cname delete (\S+)", line)
    if not m:
        return
    name = m.group(1)
    group = _parse_kv(line, "group")
    params: dict[str, str] = {"name": name}
    if group:
        params["shared_record_group"] = group
    records = [as_dict(r) async for r in ctx.client.dns.sharedrecord_cname.list(**params)]
    if not records:
        print(f"  No shared CNAME record found: {name}")
        return
    await ctx.client.dns.sharedrecord_cname.delete(records[0]["_ref"])


@command("show shared_record cname", words="<cr> group=<name>", help="Show shared CNAME records.")
@command("show shared_record cname group <name>", words="<cr>", help="Show shared CNAME by group.")
async def cli_show_shared_cname(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    group = _parse_kv(line, "group")
    m_g = re.search(r"\bgroup\s+(\S+)", line)
    if not group and m_g:
        group = m_g.group(1)
    params: dict[str, str] = {}
    if group:
        params["shared_record_group"] = group
    records = [as_dict(r) async for r in ctx.client.dns.sharedrecord_cname.list(**params)]
    for r in records:
        parts = ["type=sharedrecord:cname"]
        for k, v in r.items():
            if k.startswith("_"):
                continue
            parts.append(f"{k}={v}")
        print(" ".join(parts))


# ---- MX ----

register("configure shared_record mx", words="add delete")
register("configure shared_record mx add", words="<name>")
register("configure shared_record mx add <name>", words="<canonical>")
register("configure shared_record mx add <name> <canonical>", words="<priority>")
register("configure shared_record mx delete", words="<name>")
register("show shared_record mx", words="<cr> group")
register("show shared_record mx group", words="<name>")


@command(
    "configure shared_record mx add <name> <canonical> <priority>",
    words="<cr> group=<name> view=<name> comment=<text>",
    help="Add a shared MX record.",
)
async def cli_add_shared_mx(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bshared_record mx add (\S+) (\S+) (\d+)", line)
    if not m:
        print("  Error: name, mail_exchanger, preference required")
        return
    name, mail_exchanger, preference = m.group(1), m.group(2), int(m.group(3))
    group = _parse_kv(line, "group")
    if not group:
        print("  Error: group required")
        return
    body: dict = {
        "name": name,
        "mail_exchanger": mail_exchanger,
        "preference": preference,
        "shared_record_group": group,
    }
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    await ctx.client.dns.sharedrecord_mx.create(body)


@command(
    "configure shared_record mx delete <name>",
    words="<cr> group=<name>",
    help="Delete a shared MX record.",
)
async def cli_delete_shared_mx(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bshared_record mx delete (\S+)", line)
    if not m:
        return
    name = m.group(1)
    group = _parse_kv(line, "group")
    params: dict[str, str] = {"name": name}
    if group:
        params["shared_record_group"] = group
    records = [as_dict(r) async for r in ctx.client.dns.sharedrecord_mx.list(**params)]
    if not records:
        print(f"  No shared MX record found: {name}")
        return
    await ctx.client.dns.sharedrecord_mx.delete(records[0]["_ref"])


@command("show shared_record mx", words="<cr> group=<name>", help="Show shared MX records.")
@command("show shared_record mx group <name>", words="<cr>", help="Show shared MX by group.")
async def cli_show_shared_mx(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    group = _parse_kv(line, "group")
    m_g = re.search(r"\bgroup\s+(\S+)", line)
    if not group and m_g:
        group = m_g.group(1)
    params: dict[str, str] = {}
    if group:
        params["shared_record_group"] = group
    records = [as_dict(r) async for r in ctx.client.dns.sharedrecord_mx.list(**params)]
    for r in records:
        parts = ["type=sharedrecord:mx"]
        for k, v in r.items():
            if k.startswith("_"):
                continue
            parts.append(f"{k}={v}")
        print(" ".join(parts))


# ---- TXT ----

register("configure shared_record txt", words="add delete")
register("configure shared_record txt add", words="<name>")
register("configure shared_record txt add <name>", words="<value>")
register("configure shared_record txt delete", words="<name>")
register("show shared_record txt", words="<cr> group")
register("show shared_record txt group", words="<name>")


@command(
    "configure shared_record txt add <name> <value>",
    words="<cr> group=<name> view=<name> comment=<text>",
    help="Add a shared TXT record.",
)
async def cli_add_shared_txt(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r'\bshared_record txt add (\S+) (".+?"|\S+)', line)
    if not m:
        print("  Error: name and text required")
        return
    name = m.group(1)
    text = m.group(2).strip('"')
    group = _parse_kv(line, "group")
    if not group:
        print("  Error: group required")
        return
    body: dict = {"name": name, "text": text, "shared_record_group": group}
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    await ctx.client.dns.sharedrecord_txt.create(body)


@command(
    "configure shared_record txt delete <name>",
    words="<cr> group=<name>",
    help="Delete a shared TXT record.",
)
async def cli_delete_shared_txt(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bshared_record txt delete (\S+)", line)
    if not m:
        return
    name = m.group(1)
    group = _parse_kv(line, "group")
    params: dict[str, str] = {"name": name}
    if group:
        params["shared_record_group"] = group
    records = [as_dict(r) async for r in ctx.client.dns.sharedrecord_txt.list(**params)]
    if not records:
        print(f"  No shared TXT record found: {name}")
        return
    await ctx.client.dns.sharedrecord_txt.delete(records[0]["_ref"])


@command("show shared_record txt", words="<cr> group=<name>", help="Show shared TXT records.")
@command("show shared_record txt group <name>", words="<cr>", help="Show shared TXT by group.")
async def cli_show_shared_txt(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    group = _parse_kv(line, "group")
    m_g = re.search(r"\bgroup\s+(\S+)", line)
    if not group and m_g:
        group = m_g.group(1)
    params: dict[str, str] = {}
    if group:
        params["shared_record_group"] = group
    records = [as_dict(r) async for r in ctx.client.dns.sharedrecord_txt.list(**params)]
    for r in records:
        parts = ["type=sharedrecord:txt"]
        for k, v in r.items():
            if k.startswith("_"):
                continue
            parts.append(f"{k}={v}")
        print(" ".join(parts))


# ---- SRV ----

register("configure shared_record srv", words="add delete")
register("configure shared_record srv add", words="<name>")
register("configure shared_record srv add <name>", words="<priority>")
register("configure shared_record srv add <name> <priority>", words="<weight>")
register("configure shared_record srv add <name> <priority> <weight>", words="<port>")
register("configure shared_record srv add <name> <priority> <weight> <port>", words="<target>")
register("configure shared_record srv delete", words="<name>")
register("show shared_record srv", words="<cr> group")
register("show shared_record srv group", words="<name>")


@command(
    "configure shared_record srv add <name> <priority> <weight> <port> <target>",
    words="<cr> group=<name> view=<name> comment=<text>",
    help="Add a shared SRV record.",
)
async def cli_add_shared_srv(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bshared_record srv add (\S+) (\d+) (\d+) (\d+) (\S+)", line)
    if not m:
        print("  Error: name, priority, weight, port, target required")
        return
    name = m.group(1)
    priority = int(m.group(2))
    weight = int(m.group(3))
    port = int(m.group(4))
    target = m.group(5)
    group = _parse_kv(line, "group")
    if not group:
        print("  Error: group required")
        return
    body: dict = {
        "name": name,
        "priority": priority,
        "weight": weight,
        "port": port,
        "target": target,
        "shared_record_group": group,
    }
    view = _parse_kv(line, "view")
    if view:
        body["view"] = view
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    eas = _parse_extattrs(line)
    if eas:
        body["extattrs"] = eas
    await ctx.client.dns.sharedrecord_srv.create(body)


@command(
    "configure shared_record srv delete <name>",
    words="<cr> group=<name>",
    help="Delete a shared SRV record.",
)
async def cli_delete_shared_srv(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bshared_record srv delete (\S+)", line)
    if not m:
        return
    name = m.group(1)
    group = _parse_kv(line, "group")
    params: dict[str, str] = {"name": name}
    if group:
        params["shared_record_group"] = group
    records = [as_dict(r) async for r in ctx.client.dns.sharedrecord_srv.list(**params)]
    if not records:
        print(f"  No shared SRV record found: {name}")
        return
    await ctx.client.dns.sharedrecord_srv.delete(records[0]["_ref"])


@command("show shared_record srv", words="<cr> group=<name>", help="Show shared SRV records.")
@command("show shared_record srv group <name>", words="<cr>", help="Show shared SRV by group.")
async def cli_show_shared_srv(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    group = _parse_kv(line, "group")
    m_g = re.search(r"\bgroup\s+(\S+)", line)
    if not group and m_g:
        group = m_g.group(1)
    params: dict[str, str] = {}
    if group:
        params["shared_record_group"] = group
    records = [as_dict(r) async for r in ctx.client.dns.sharedrecord_srv.list(**params)]
    for r in records:
        parts = ["type=sharedrecord:srv"]
        for k, v in r.items():
            if k.startswith("_"):
                continue
            parts.append(f"{k}={v}")
        print(" ".join(parts))
