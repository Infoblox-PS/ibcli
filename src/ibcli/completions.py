# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Dynamic completion helpers - sync callables that return [(value, meta), ...].

These are attached to `CommandEntry.dynamic` via `register(..., dynamic=fn)`.
The prompt_toolkit completer calls them synchronously, so they only read from
caches on `ctx.caches`. The caches themselves are populated lazily: on first
tab press we kick off a background task to fill the cache, and the second
tab press picks up the values.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from ibcli.context import Context
from ibcli.utils import as_dict

CompletionFetcher = Callable[[Context], Awaitable[list[tuple[str, str]]]]


def _cached(key: str, fetch: CompletionFetcher) -> Callable[[Context], list[tuple[str, str]]]:
    """Wrap an async fetcher as a sync completion callable backed by ctx.caches[key].

    First call returns []; the fetcher runs in the background and fills the
    cache. Second call returns the cached list.
    """

    def _reader(ctx: Context) -> list[tuple[str, str]]:
        cache = ctx.caches.get(key)
        if cache is not None:
            return cache
        if ctx.client is None:
            return []
        ctx.caches[key] = []  # sentinel to avoid repeat spawns
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return []

        async def _runner() -> None:
            try:
                ctx.caches[key] = await fetch(ctx)
            except Exception:
                ctx.caches.pop(key, None)

        loop.create_task(_runner())
        return []

    return _reader


# ---------------------------------------------------------------------------
# Fetchers - each returns [(value, meta), ...] for one WAPI collection.
# ---------------------------------------------------------------------------


async def _fetch_members(ctx: Context) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    async for raw in ctx.client.grid.member.list(return_fields_plus=["vip_setting", "host_name"]):
        m = as_dict(raw)
        name = m.get("host_name", "")
        vip = (m.get("vip_setting") or {}).get("address") or ""
        if name:
            items.append((name, vip))
    return items


async def _fetch_by_name(
    resource,
    *,
    plus: list[str] | None = None,
    meta_key: str = "comment",
) -> list[tuple[str, str]]:
    """Generic helper: list an obj type and return (name, meta[meta_key]) pairs."""
    items: list[tuple[str, str]] = []
    kwargs = {"return_fields_plus": plus} if plus else {}
    async for raw in resource.list(**kwargs):
        d = as_dict(raw)
        name = d.get("name") or d.get("fqdn") or ""
        if not name:
            continue
        items.append((name, str(d.get(meta_key, "") or "")))
    return items


async def _fetch_views(ctx: Context) -> list[tuple[str, str]]:
    return await _fetch_by_name(ctx.client.dns.view, plus=["comment"])


async def _fetch_zones(ctx: Context) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    async for raw in ctx.client.dns.zone_auth.list(return_fields_plus=["fqdn", "view"]):
        d = as_dict(raw)
        fqdn = d.get("fqdn") or ""
        if fqdn:
            items.append((fqdn, str(d.get("view", "") or "")))
    return items


async def _fetch_networks(ctx: Context) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    async for raw in ctx.client.ipam.network.list(return_fields_plus=["network", "comment"]):
        d = as_dict(raw)
        cidr = d.get("network") or ""
        if cidr:
            items.append((cidr, str(d.get("comment", "") or "")))
    return items


async def _fetch_nsgroups(ctx: Context) -> list[tuple[str, str]]:
    return await _fetch_by_name(ctx.client.dns.nsgroup, plus=["comment"])


async def _fetch_acls(ctx: Context) -> list[tuple[str, str]]:
    return await _fetch_by_name(ctx.client.acl.namedacl, plus=["comment"])


async def _fetch_failover(ctx: Context) -> list[tuple[str, str]]:
    return await _fetch_by_name(ctx.client.dhcp.dhcpfailover, plus=["comment"])


async def _fetch_dtc_servers(ctx: Context) -> list[tuple[str, str]]:
    return await _fetch_by_name(ctx.client.dtc.server, plus=["comment", "host"])


async def _fetch_dtc_pools(ctx: Context) -> list[tuple[str, str]]:
    return await _fetch_by_name(ctx.client.dtc.pool, plus=["comment"])


async def _fetch_dtc_lbdns(ctx: Context) -> list[tuple[str, str]]:
    return await _fetch_by_name(ctx.client.dtc.lbdn, plus=["comment"])


async def _fetch_grid_name(ctx: Context) -> list[tuple[str, str]]:
    """Connected grid's name - used to auto-complete the `configure grid <name>`
    slot, since a session only ever targets one grid."""
    items: list[tuple[str, str]] = []
    async for raw in ctx.client.grid.grid.list():
        d = as_dict(raw)
        name = d.get("name") or ""
        if name:
            items.append((name, "connected grid"))
    return items


async def _fetch_ca_certificates(ctx: Context) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    async for raw in ctx.client.security.cacertificate.list(return_fields_plus=["issuer"]):
        d = as_dict(raw)
        dn = d.get("distinguished_name") or ""
        if dn:
            items.append((dn, str(d.get("issuer", "") or "")))
    return items


async def _fetch_auth_ldap(ctx: Context) -> list[tuple[str, str]]:
    return await _fetch_by_name(ctx.client.security.ldap_auth_service, plus=["comment"])


async def _fetch_auth_ad(ctx: Context) -> list[tuple[str, str]]:
    return await _fetch_by_name(ctx.client.security.ad_auth_service, plus=["comment"])


async def _fetch_auth_radius(ctx: Context) -> list[tuple[str, str]]:
    return await _fetch_by_name(ctx.client.security.radius_authservice, plus=["comment"])


async def _fetch_auth_tacacs(ctx: Context) -> list[tuple[str, str]]:
    return await _fetch_by_name(ctx.client.security.tacacsplus_authservice, plus=["comment"])


async def _fetch_auth_saml(ctx: Context) -> list[tuple[str, str]]:
    return await _fetch_by_name(ctx.client.security.saml_authservice, plus=["comment"])


async def _fetch_auth_certificate(ctx: Context) -> list[tuple[str, str]]:
    return await _fetch_by_name(ctx.client.security.certificate_authservice, plus=["comment"])


def _dtc_monitor_fetcher(proto: str) -> CompletionFetcher:
    async def _fetch(ctx: Context) -> list[tuple[str, str]]:
        resource = getattr(ctx.client.dtc, f"monitor_{proto}")
        return await _fetch_by_name(resource, plus=["comment"])

    return _fetch


# ---------------------------------------------------------------------------
# Public sync completers - attach these to `register(..., dynamic=...)`.
# ---------------------------------------------------------------------------

members = _cached("members", _fetch_members)
views = _cached("views", _fetch_views)
zones = _cached("zones", _fetch_zones)
networks = _cached("networks", _fetch_networks)
nsgroups = _cached("nsgroups", _fetch_nsgroups)
acls = _cached("acls", _fetch_acls)
failover = _cached("failover", _fetch_failover)
dtc_servers = _cached("dtc_servers", _fetch_dtc_servers)
dtc_pools = _cached("dtc_pools", _fetch_dtc_pools)
dtc_lbdns = _cached("dtc_lbdns", _fetch_dtc_lbdns)
dtc_monitor_http = _cached("dtc_monitor_http", _dtc_monitor_fetcher("http"))
dtc_monitor_icmp = _cached("dtc_monitor_icmp", _dtc_monitor_fetcher("icmp"))
dtc_monitor_tcp = _cached("dtc_monitor_tcp", _dtc_monitor_fetcher("tcp"))
dtc_monitor_snmp = _cached("dtc_monitor_snmp", _dtc_monitor_fetcher("snmp"))
dtc_monitor_sip = _cached("dtc_monitor_sip", _dtc_monitor_fetcher("sip"))
dtc_monitor_pdp = _cached("dtc_monitor_pdp", _dtc_monitor_fetcher("pdp"))

grid_name = _cached("grid_name", _fetch_grid_name)
ca_certificates = _cached("ca_certificates", _fetch_ca_certificates)
auth_ldap = _cached("auth_ldap", _fetch_auth_ldap)
auth_ad = _cached("auth_ad", _fetch_auth_ad)
auth_radius = _cached("auth_radius", _fetch_auth_radius)
auth_tacacs = _cached("auth_tacacs", _fetch_auth_tacacs)
auth_saml = _cached("auth_saml", _fetch_auth_saml)
auth_certificate = _cached("auth_certificate", _fetch_auth_certificate)


# Backwards-compatible private name retained for the connect-time primer.
_refresh_members = _fetch_members
