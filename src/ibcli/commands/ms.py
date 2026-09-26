# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Microsoft Server integration commands - Phase 17.

Exposes NIOS Microsoft Server resources via ctx.client.microsoftserver.*

SDK / WAPI surface notes
------------------------
- msserver              full CRUD - MS server registration (identified by address/IPv4)
- msserver:dhcp         show + set (DHCP service config on MS server; address read-only)
- msserver:dns          show + set (DNS service config on MS server; address read-only)
- msserver:adsites:domain  GET only - read-only aggregate (all fields readonly in model)
- msserver:adsites:site    full CRUD - AD sites
- mssuperscope          full CRUD - MS DHCP superscopes (identified by name)

Command vocabulary
------------------
# MS Server registration (address = IPv4)
configure ms_server add <svr> [comment=<comment>]
configure ms_server <svr> delete
configure ms_server <svr> set <key>=<value>
show ms_server [<svr>]

# MS DHCP service config (per MS server)
show ms_server <svr> dhcp
configure ms_server <svr> dhcp set <key>=<value>

# MS DNS service config (per MS server)
show ms_server <svr> dns
configure ms_server <svr> dns set <key>=<value>

# AD sites domain (read-only)
show ms_server <svr> ad_domain [<name>]

# AD sites site (full CRUD)
configure ms_server <svr> ad_site add <name> [comment=<comment>]
configure ms_server <svr> ad_site <name> delete
show ms_server <svr> ad_site [<name>]

# MS superscope (identified by name)
configure ms_superscope add <name> [comment=<comment>]
configure ms_superscope <name> delete
configure ms_superscope <name> set <key>=<value>
show ms_superscope [<name>]
"""

from __future__ import annotations

import re

from ibcli.coerce import coerce as _coerce  # noqa: F401
from ibcli.completions_keys import keys_completer_for_path
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict

_MS_KEYS = keys_completer_for_path("microsoftserver", "msserver")
_MS_DHCP_KEYS = keys_completer_for_path("microsoftserver", "dhcp")
_MS_DNS_KEYS = keys_completer_for_path("microsoftserver", "dns")
_MS_SUPERSCOPE_KEYS = keys_completer_for_path("microsoftserver", "mssuperscope")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _kv(line: str, key: str) -> str | None:
    """Extract value for *key* from 'key=value' or 'key value' forms."""
    m = re.search(rf"\b{re.escape(key)}[= ](\S+)", line)
    return m.group(1) if m else None


def _comment(line: str) -> str | None:
    """Extract a quoted or bare comment value."""
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
# Chunk A: MS Server registration (msserver)
# MS servers are identified by address (IPv4), not a name field.
# ===========================================================================

register(
    "configure", words="ms_server ms_superscope", help="Create, modify or delete grid objects."
)
register(
    "show", words="ms_server ms_superscope", help="Read grid state without modifying anything."
)

register(
    "configure ms_server",
    words="add <svr>",
    help="Microsoft DNS/DHCP servers integrated with NIOS.",
)
register("configure ms_server add", words="<svr>")
register("configure ms_server add <svr>", words="<cr> comment=<comment>")


@command(
    "configure ms_server add <svr>",
    words="<cr> comment=<comment>",
    help="Register a new Microsoft server.",
)
async def cli_ms_server_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bms_server add (\S+)", line)
    if not m:
        print("  Error: server address required")
        return
    address = m.group(1)
    body: dict = {"address": address}
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.microsoftserver.msserver.create(body)


register("configure ms_server <svr>", words="delete set dhcp dns ad_site")
register("configure ms_server <svr> delete", words="<cr>")


@command(
    "configure ms_server <svr> delete",
    words="<cr>",
    help="Delete a registered Microsoft server.",
)
async def cli_ms_server_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bms_server (\S+) delete", line)
    if not m:
        print("  Error: server address required")
        return
    address = m.group(1)
    results = [
        as_dict(r)
        async for r in ctx.client.microsoftserver.msserver.list(address=address, max_results=1)
    ]
    if not results:
        print(f"  No MS server found: {address}")
        return
    await ctx.client.microsoftserver.msserver.delete(results[0]["_ref"])


register("configure ms_server <svr> set", words="<key>=<value>", dynamic=_MS_KEYS)


@command(
    "configure ms_server <svr> set",
    words="<key>=<value>",
    help="Set fields on a registered Microsoft server.",
)
async def cli_ms_server_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bms_server (\S+) set\b", line)
    if not m:
        print("  Error: server address required")
        return
    address = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [
        as_dict(r)
        async for r in ctx.client.microsoftserver.msserver.list(address=address, max_results=1)
    ]
    if not results:
        print(f"  No MS server found: {address}")
        return
    await ctx.client.microsoftserver.msserver.update(results[0]["_ref"], body)


register("show ms_server", words="<cr> <svr>", help="Microsoft DNS/DHCP integration servers.")
register("show ms_server <svr>", words="<cr> dhcp dns ad_domain ad_site")


@command("show ms_server", words="<cr> <svr>", help="Show registered Microsoft servers.")
@command(
    "show ms_server <svr>",
    words="<cr> dhcp dns ad_domain ad_site",
    help="Show a specific Microsoft server.",
)
async def cli_ms_server_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show ms_server [<svr>]
    address = None
    if len(tokens) >= 3:
        candidate = tokens[2]
        if not candidate.startswith("<"):
            address = candidate
    params: dict = {}
    if address:
        params["address"] = address
    records = [as_dict(r) async for r in ctx.client.microsoftserver.msserver.list(**params)]
    if not records:
        if address:
            print(f"  No MS server found: {address}")
        return
    _print_records(records, "msserver")


# ===========================================================================
# Chunk B: MS DHCP service config (msserver:dhcp)
# Identified via address (read-only on the object itself).
# Show and set only - no add/delete (lifecycle tied to msserver).
# ===========================================================================

register("show ms_server <svr> dhcp", words="<cr>")
register("configure ms_server <svr> dhcp", words="set")
register("configure ms_server <svr> dhcp set", words="<key>=<value>", dynamic=_MS_DHCP_KEYS)


@command(
    "show ms_server <svr> dhcp",
    words="<cr>",
    help="Show MS server DHCP service configuration.",
)
async def cli_ms_server_dhcp_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bms_server (\S+) dhcp", line)
    if not m:
        print("  Error: server address required")
        return
    address = m.group(1)
    records = [as_dict(r) async for r in ctx.client.microsoftserver.dhcp.list(address=address)]
    if not records:
        print(f"  No MS DHCP config found: {address}")
        return
    _print_records(records, "msserver:dhcp")


@command(
    "configure ms_server <svr> dhcp set",
    words="<key>=<value>",
    help="Set fields on MS server DHCP service configuration.",
)
async def cli_ms_server_dhcp_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bms_server (\S+) dhcp set\b", line)
    if not m:
        print("  Error: server address required")
        return
    address = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [
        as_dict(r)
        async for r in ctx.client.microsoftserver.dhcp.list(address=address, max_results=1)
    ]
    if not results:
        print(f"  No MS DHCP config found: {address}")
        return
    await ctx.client.microsoftserver.dhcp.update(results[0]["_ref"], body)


# ===========================================================================
# Chunk C: MS DNS service config (msserver:dns)
# Show and set only - no add/delete.
# ===========================================================================

register("show ms_server <svr> dns", words="<cr>")
register("configure ms_server <svr> dns", words="set")
register("configure ms_server <svr> dns set", words="<key>=<value>", dynamic=_MS_DNS_KEYS)


@command(
    "show ms_server <svr> dns",
    words="<cr>",
    help="Show MS server DNS service configuration.",
)
async def cli_ms_server_dns_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bms_server (\S+) dns", line)
    if not m:
        print("  Error: server address required")
        return
    address = m.group(1)
    records = [as_dict(r) async for r in ctx.client.microsoftserver.dns.list(address=address)]
    if not records:
        print(f"  No MS DNS config found: {address}")
        return
    _print_records(records, "msserver:dns")


@command(
    "configure ms_server <svr> dns set",
    words="<key>=<value>",
    help="Set fields on MS server DNS service configuration.",
)
async def cli_ms_server_dns_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bms_server (\S+) dns set\b", line)
    if not m:
        print("  Error: server address required")
        return
    address = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [
        as_dict(r)
        async for r in ctx.client.microsoftserver.dns.list(address=address, max_results=1)
    ]
    if not results:
        print(f"  No MS DNS config found: {address}")
        return
    await ctx.client.microsoftserver.dns.update(results[0]["_ref"], body)


# ===========================================================================
# Chunk D: AD sites domain (msserver:adsites:domain)
# Read-only in the WAPI - show only.
# ===========================================================================

register("show ms_server <svr> ad_domain", words="<cr> <name>")
register("show ms_server <svr> ad_domain <name>", words="<cr>")


@command(
    "show ms_server <svr> ad_domain",
    words="<cr> <name>",
    help="Show AD domain properties for a Microsoft server.",
)
@command(
    "show ms_server <svr> ad_domain <name>",
    words="<cr>",
    help="Show a specific AD domain property object.",
)
async def cli_ms_server_ad_domain_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bms_server (\S+) ad_domain", line)
    if not m:
        print("  Error: server address required")
        return
    address = m.group(1)
    # Optional name token after 'ad_domain'
    m2 = re.search(r"\bad_domain (\S+)", line)
    domain_name = m2.group(1) if m2 else None

    params: dict = {"ms_sync_master_name": address}
    if domain_name:
        params["name"] = domain_name
    records = [as_dict(r) async for r in ctx.client.microsoftserver.adsites_domain.list(**params)]
    if not records:
        if domain_name:
            print(f"  No AD domain found: {domain_name}")
        else:
            print(f"  No AD domains found for server: {address}")
        return
    _print_records(records, "msserver:adsites:domain")


# ===========================================================================
# Chunk E: AD sites site (msserver:adsites:site)
# Full CRUD - add/delete/show.
# ===========================================================================

register("configure ms_server <svr> ad_site", words="add <name>")
register("configure ms_server <svr> ad_site add", words="<name>")
register("configure ms_server <svr> ad_site add <name>", words="<cr> comment=<comment>")


@command(
    "configure ms_server <svr> ad_site add <name>",
    words="<cr> comment=<comment>",
    help="Add an AD site for a Microsoft server.",
)
async def cli_ms_server_ad_site_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bms_server (\S+) ad_site add (\S+)", line)
    if not m:
        print("  Error: server address and site name required")
        return
    address, site_name = m.group(1), m.group(2)
    body: dict = {"name": site_name, "domain": address}
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.microsoftserver.adsites_site.create(body)


register("configure ms_server <svr> ad_site <name>", words="delete")
register("configure ms_server <svr> ad_site <name> delete", words="<cr>")


@command(
    "configure ms_server <svr> ad_site <name> delete",
    words="<cr>",
    help="Delete an AD site.",
)
async def cli_ms_server_ad_site_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bms_server (\S+) ad_site (\S+) delete", line)
    if not m:
        print("  Error: server address and site name required")
        return
    address, site_name = m.group(1), m.group(2)
    results = [
        as_dict(r)
        async for r in ctx.client.microsoftserver.adsites_site.list(
            name=site_name, domain=address, max_results=1
        )
    ]
    if not results:
        print(f"  No AD site found: {site_name}")
        return
    await ctx.client.microsoftserver.adsites_site.delete(results[0]["_ref"])


register("show ms_server <svr> ad_site", words="<cr> <name>")
register("show ms_server <svr> ad_site <name>", words="<cr>")


@command(
    "show ms_server <svr> ad_site",
    words="<cr> <name>",
    help="Show AD sites for a Microsoft server.",
)
@command(
    "show ms_server <svr> ad_site <name>",
    words="<cr>",
    help="Show a specific AD site.",
)
async def cli_ms_server_ad_site_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bms_server (\S+) ad_site", line)
    if not m:
        print("  Error: server address required")
        return
    address = m.group(1)
    m2 = re.search(r"\bad_site (\S+)", line)
    site_name = m2.group(1) if m2 else None

    params: dict = {"domain": address}
    if site_name:
        params["name"] = site_name
    records = [as_dict(r) async for r in ctx.client.microsoftserver.adsites_site.list(**params)]
    if not records:
        if site_name:
            print(f"  No AD site found: {site_name}")
        else:
            print(f"  No AD sites found for server: {address}")
        return
    _print_records(records, "msserver:adsites:site")


# ===========================================================================
# Chunk F: MS superscope (mssuperscope)
# Full CRUD - identified by name.
# ===========================================================================

register("configure ms_superscope", words="add <name>", help="Microsoft DHCP superscopes.")
register("configure ms_superscope add", words="<name>")
register("configure ms_superscope add <name>", words="<cr> comment=<comment>")


@command(
    "configure ms_superscope add <name>",
    words="<cr> comment=<comment>",
    help="Add a Microsoft DHCP superscope.",
)
async def cli_ms_superscope_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bms_superscope add (\S+)", line)
    if not m:
        print("  Error: superscope name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.microsoftserver.mssuperscope.create(body)


register("configure ms_superscope <name>", words="delete set")
register("configure ms_superscope <name> delete", words="<cr>")


@command(
    "configure ms_superscope <name> delete",
    words="<cr>",
    help="Delete a Microsoft DHCP superscope.",
)
async def cli_ms_superscope_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bms_superscope (\S+) delete", line)
    if not m:
        print("  Error: superscope name required")
        return
    name = m.group(1)
    results = [
        as_dict(r)
        async for r in ctx.client.microsoftserver.mssuperscope.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No MS superscope found: {name}")
        return
    await ctx.client.microsoftserver.mssuperscope.delete(results[0]["_ref"])


register("configure ms_superscope <name> set", words="<key>=<value>", dynamic=_MS_SUPERSCOPE_KEYS)


@command(
    "configure ms_superscope <name> set",
    words="<key>=<value>",
    help="Set fields on a Microsoft DHCP superscope.",
)
async def cli_ms_superscope_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bms_superscope (\S+) set\b", line)
    if not m:
        print("  Error: superscope name required")
        return
    name = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [
        as_dict(r)
        async for r in ctx.client.microsoftserver.mssuperscope.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No MS superscope found: {name}")
        return
    await ctx.client.microsoftserver.mssuperscope.update(results[0]["_ref"], body)


register("show ms_superscope", words="<cr> <name>", help="Microsoft DHCP superscopes.")
register("show ms_superscope <name>", words="<cr>")


@command("show ms_superscope", words="<cr> <name>", help="Show Microsoft DHCP superscopes.")
@command("show ms_superscope <name>", words="<cr>", help="Show a specific MS DHCP superscope.")
async def cli_ms_superscope_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show ms_superscope [<name>]
    name = None
    if len(tokens) >= 3:
        candidate = tokens[2]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.microsoftserver.mssuperscope.list(**params)]
    if not records:
        if name:
            print(f"  No MS superscope found: {name}")
        return
    _print_records(records, "mssuperscope")
