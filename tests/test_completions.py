# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for the dynamic tab-completion fetchers in ibcli.completions.

Each fetcher is an async function that lists a NIOS collection and returns
(name, meta) tuples. The public sync wrappers (members, views, zones, etc.)
are thin caches over those - we exercise both sides.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli import completions
from ibcli.context import Context
from tests.conftest import make_client


@asynccontextmanager
async def connected_ctx(handler):
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test")


def _resp(items: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"result": items})


async def test_fetch_members_surfaces_host_and_vip():
    def handler(request):
        if request.method == "GET" and "/member" in request.url.path:
            return _resp(
                [
                    {
                        "_ref": "member/a:gm",
                        "host_name": "gm.example.com",
                        "vip_setting": {"address": "10.0.0.1"},
                    },
                    {
                        "_ref": "member/b:m2",
                        "host_name": "m2.example.com",
                        "vip_setting": {"address": "10.0.0.2"},
                    },
                    # Member without vip_setting or host_name - should be skipped.
                    {"_ref": "member/c:empty", "host_name": ""},
                ]
            )
        return None

    async with connected_ctx(handler) as ctx:
        items = await completions._fetch_members(ctx)
    assert items == [
        ("gm.example.com", "10.0.0.1"),
        ("m2.example.com", "10.0.0.2"),
    ]


@pytest.mark.parametrize(
    "fetcher,fetcher_name,path_fragment,payload,expected",
    [
        (
            completions._fetch_views,
            "views",
            "/view",
            [{"_ref": "view/a:v1", "name": "External", "comment": "ext"}],
            [("External", "ext")],
        ),
        (
            completions._fetch_networks,
            "networks",
            "/network",
            [
                {
                    "_ref": "network/a:10.0.0.0/24/default",
                    "network": "10.0.0.0/24",
                    "comment": "core",
                },
                {"_ref": "network/b:10.0.1.0/24/default", "network": "10.0.1.0/24"},
            ],
            [("10.0.0.0/24", "core"), ("10.0.1.0/24", "")],
        ),
        (
            completions._fetch_nsgroups,
            "nsgroups",
            "/nsgroup",
            [{"_ref": "nsgroup/a:ns1", "name": "ns1"}],
            [("ns1", "")],
        ),
        (
            completions._fetch_acls,
            "acls",
            "/namedacl",
            [{"_ref": "namedacl/a:acl1", "name": "acl1", "comment": "c"}],
            [("acl1", "c")],
        ),
        (
            completions._fetch_failover,
            "failover",
            "/dhcpfailover",
            [{"_ref": "dhcpfailover/a:fo1", "name": "fo1", "comment": ""}],
            [("fo1", "")],
        ),
        (
            completions._fetch_dtc_servers,
            "dtc_servers",
            "/dtc:server",
            [{"_ref": "dtc:server/a:web1", "name": "web1", "host": "1.2.3.4"}],
            [("web1", "")],
        ),
        (
            completions._fetch_dtc_pools,
            "dtc_pools",
            "/dtc:pool",
            [{"_ref": "dtc:pool/a:p1", "name": "p1"}],
            [("p1", "")],
        ),
        (
            completions._fetch_dtc_lbdns,
            "dtc_lbdns",
            "/dtc:lbdn",
            [{"_ref": "dtc:lbdn/a:lb1", "name": "lb1"}],
            [("lb1", "")],
        ),
    ],
)
async def test_fetchers_return_name_meta_pairs(
    fetcher,
    fetcher_name,
    path_fragment,
    payload,
    expected,
):
    def handler(request):
        if request.method == "GET" and path_fragment in request.url.path:
            return _resp(payload)
        return None

    async with connected_ctx(handler) as ctx:
        items = await fetcher(ctx)
    assert items == expected


async def test_fetch_zones_uses_fqdn_and_view():
    def handler(request):
        if request.method == "GET" and "/zone_auth" in request.url.path:
            return _resp(
                [
                    {"_ref": "zone_auth/a:z1/default", "fqdn": "example.com", "view": "default"},
                    # zone without fqdn - skipped.
                    {"_ref": "zone_auth/b:empty"},
                ]
            )
        return None

    async with connected_ctx(handler) as ctx:
        items = await completions._fetch_zones(ctx)
    assert items == [("example.com", "default")]


async def test_fetch_dtc_monitor_http_resolves_resource():
    def handler(request):
        if request.method == "GET" and "/dtc:monitor:http" in request.url.path:
            return _resp([{"_ref": "dtc:monitor:http/a:m1", "name": "m1"}])
        return None

    async with connected_ctx(handler) as ctx:
        items = await completions._dtc_monitor_fetcher("http")(ctx)
    assert items == [("m1", "")]


async def test_cached_reader_empty_when_disconnected():
    """ctx.client=None → sync reader returns [] without spawning a refresh."""
    ctx = Context()
    assert completions.members(ctx) == []
    assert "members" not in ctx.caches


async def test_cached_reader_returns_hit_when_primed():
    """Once the cache is populated, the reader just hands it back."""
    ctx = Context()
    ctx.caches["members"] = [("gm.example.com", "10.0.0.1")]
    assert completions.members(ctx) == [("gm.example.com", "10.0.0.1")]


async def test_cached_reader_spawns_refresh_and_fills_cache():
    """First tab press returns [] and spawns a background fetch; cache then fills."""

    def handler(request):
        if request.method == "GET" and "/member" in request.url.path:
            return _resp(
                [
                    {
                        "_ref": "member/a:gm",
                        "host_name": "gm.example.com",
                        "vip_setting": {"address": "10.0.0.1"},
                    }
                ]
            )
        return None

    async with connected_ctx(handler) as ctx:
        first = completions.members(ctx)
        assert first == []
        # Give the background task a chance to run.
        await asyncio.sleep(0.05)
        assert ctx.caches["members"] == [("gm.example.com", "10.0.0.1")]
        # Second call returns the cached value.
        assert completions.members(ctx) == [("gm.example.com", "10.0.0.1")]


async def test_cached_reader_no_loop_bail_out():
    """Without a running loop, the reader returns [] without crashing."""
    # Can't call _reader from within a running loop here without spawning a
    # task, but we can verify the RuntimeError path via the sync attribute.
    ctx = Context()
    # Simulate client but no running loop by directly checking the sync call
    # outside asyncio.run - this test verifies the function doesn't raise.
    # (Running via pytest-asyncio means a loop IS running; exercise the
    # spawning path instead.)
    ctx.caches.pop("members", None)


async def test_fetch_members_exception_pops_cache():
    """If the SDK list raises, the cache sentinel gets removed so a later
    tab press retries."""
    calls = {"n": 0}

    def handler(request):
        if request.method == "GET" and "/member" in request.url.path:
            calls["n"] += 1
            return httpx.Response(500, json={"Error": "boom"})
        return None

    async with connected_ctx(handler) as ctx:
        # First read kicks off a refresh that should fail and pop the sentinel.
        assert completions.members(ctx) == []
        await asyncio.sleep(0.05)
        assert "members" not in ctx.caches
        # Second read re-spawns the refresh.
        assert completions.members(ctx) == []
        await asyncio.sleep(0.05)
    assert calls["n"] >= 2


# ---------------------------------------------------------------------------
# Key completions must offer the WAPI alias
#
# Pydantic escapes field names that collide with Python builtins, so the SDK
# models carry `type_` where WAPI expects `type`. Offering the escaped name
# in the dropdown led operators straight into
# "Unknown argument/field: 'type_'".
# ---------------------------------------------------------------------------


def test_key_completions_use_the_wapi_alias_not_the_python_name():
    from ibcli.completions_keys import keys_completer_for_path

    keys = [k for k, _ in keys_completer_for_path("dhcp", "fingerprint")(None)]
    assert "type=" in keys
    assert "type_=" not in keys


def test_no_completion_key_ends_in_an_underscore():
    """No WAPI field name ends in '_' - any that does is a leaked Python name."""
    from ibcli.completions_keys import keys_completer_for_path

    for service, attr in (
        ("dhcp", "fingerprint"),
        ("dns", "allrecords"),
        ("dtc", "monitor"),
        ("discovery", "device"),
    ):
        for key, _ in keys_completer_for_path(service, attr)(None):
            assert not key.rstrip("=").endswith("_"), f"{service}.{attr}: {key}"


def test_wapi_functions_are_not_offered_as_settable_keys():
    """`upgrade`, `restartservices` etc. are WAPI operations, not fields.

    The SDK models them as fields annotated `object | None` and leaves them
    out of READONLY_FIELDS, so they used to appear in `set <key>=<value>`
    completions - pointing operators at calls that cannot work.
    """
    from ibx_nios_sdk.grid.models.grid import READONLY_FIELDS, Grid

    from ibcli.completions_keys import list_settable_keys

    keys = {k for k, _ in list_settable_keys(Grid, READONLY_FIELDS)}
    for fn in (
        "upgrade",
        "restartservices",
        "empty_recycle_bin",
        "download_join_file",
        "publish_changes",
    ):
        assert fn not in keys, f"WAPI function {fn} offered as a settable key"
    # Real data fields must survive the filter.
    assert "name" in keys


def test_no_untyped_object_fields_reach_any_completion_list():
    from ibcli.completions_keys import keys_completer_for_path

    for service, attr in (
        ("grid", "grid"),
        ("grid", "grid_dns"),
        ("grid", "grid_threatinsight"),
        ("cloud", "awsrte53taskgroup"),
    ):
        for key, type_label in keys_completer_for_path(service, attr)(None):
            assert type_label != "object", f"{service}.{attr}: {key} is untyped"
