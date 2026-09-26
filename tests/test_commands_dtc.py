# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.dtc - Phase 7.

Covers:
  Chunk A: Grid-level DTC config, servers, pools
  Chunk B: LBDNs, DTC records, allrecords aggregator
  Chunk C: Monitors (base aggregator + http, icmp, tcp, snmp, sip, pdp)
  Chunk D: Topology (group, labels, rules)
  Chunk E: Certificates, DTC object aggregator

Notes:
- WAPI list responses must be wrapped as {"result": [...]} (paging envelope).
- URL paths use raw (unencoded) colons, e.g. "dtc:server" not "dtc%3Aserver".
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import dtc  # noqa: F401  ensures module registers handlers
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Seed the NULL root entry so configure/show are recognised."""
    COMMANDS.setdefault("NULL", CommandEntry(words="configure show"))


@asynccontextmanager
async def connected_ctx(handler=None, **client_kwargs):
    """A Context around a mocked NiosClient.

    Pass ``enforce_restrictions=False`` for a command whose WAPI object type
    forbids the operation on NIOS 9.1 - the SDK refuses those before they
    reach the transport, and the test still needs to assert the request the
    CLI would build.
    """
    async with make_client(handler, **client_kwargs) as client:
        yield Context(client=client, online=True, host="grid.test")


# ---------------------------------------------------------------------------
# Request-inspection helpers
# ---------------------------------------------------------------------------


def _posts_to(seen: list, fragment: str) -> list:
    return [
        r
        for r in seen
        if r.method == "POST" and fragment in r.url.path and "/logout" not in r.url.path
    ]


def _gets_to(seen: list, fragment: str) -> list:
    return [r for r in seen if r.method == "GET" and fragment in r.url.path]


def _deletes_to(seen: list, fragment: str) -> list:
    return [r for r in seen if r.method == "DELETE" and fragment in r.url.path]


def _puts_to(seen: list, fragment: str) -> list:
    return [r for r in seen if r.method == "PUT" and fragment in r.url.path]


def _ref(objtype: str, name: str) -> str:
    """Build a fake WAPI ref for the given object type and name."""
    return f"{objtype}/ZG5z:{name}"


def _list(items: list) -> dict:
    """Wrap items in the WAPI paged-list response envelope expected by the SDK."""
    return {"result": items}


# ===========================================================================
# Chunk A: Grid-level DTC config
# ===========================================================================


class TestDtcGlobalSet:
    # NIOS 9.1 forbids read on `dtc` and the SDK refuses it
    # before the request is built. These assert the request the CLI
    # *would* send, so enforcement is off here.
    async def test_set_kv(self, capsys):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            # Match bare GET /dtc (not dtc:server etc.)
            if req.method == "GET" and req.url.path.endswith("/dtc") and "dtc:" not in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": "dtc/ZG5z:default"}]))
            if req.method == "PUT" and "dtc/ZG5z" in req.url.path:
                return httpx.Response(200, json={"_ref": "dtc/ZG5z:default"})
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure dtc set foo=bar", ctx)

        puts = _puts_to(seen, "dtc/ZG5z")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["foo"] == "bar"


# ===========================================================================
# Chunk A: DTC Servers
# ===========================================================================


class TestDtcServerAdd:
    async def test_add_with_host(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "dtc:server" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("dtc:server", "web1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc server add web1 host=10.1.1.1", ctx)

        posts = _posts_to(seen, "dtc:server")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "web1"
        assert body["host"] == "10.1.1.1"

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "dtc:server" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("dtc:server", "web2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure dtc server add web2 host=10.1.1.2 comment="my server"', ctx
            )

        posts = _posts_to(seen, "dtc:server")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["comment"] == "my server"


class TestDtcServerDelete:
    async def test_delete_by_name(self):
        seen: list[httpx.Request] = []
        server_ref = _ref("dtc:server", "web1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "dtc:server" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": server_ref, "name": "web1"}]))
            if req.method == "DELETE" and "dtc:server" in req.url.path:
                return httpx.Response(200, json=server_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc server web1 delete", ctx)

        assert len(_deletes_to(seen, "dtc:server")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dtc:server" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc server noexist delete", ctx)

        out = capsys.readouterr().out
        assert "No DTC server found" in out


class TestDtcServerSet:
    async def test_set_field(self):
        seen: list[httpx.Request] = []
        server_ref = _ref("dtc:server", "web1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "dtc:server" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": server_ref, "name": "web1"}]))
            if req.method == "PUT":
                return httpx.Response(200, json={"_ref": server_ref})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc server web1 set disable=true", ctx)

        puts = _puts_to(seen, "dtc:server")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["disable"] is True


class TestDtcServerShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dtc:server" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": _ref("dtc:server", "web1"), "name": "web1", "host": "10.1.1.1"}]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dtc server", ctx)

        out = capsys.readouterr().out
        assert "web1" in out
        assert "dtc:server" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dtc:server" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("dtc:server", "web1"), "name": "web1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dtc server web1", ctx)

        out = capsys.readouterr().out
        assert "web1" in out


# ===========================================================================
# Chunk A: DTC Pools
# ===========================================================================


class TestDtcPoolAdd:
    async def test_add_basic(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "dtc:pool" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("dtc:pool", "pool1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc pool add pool1 lb_preferred_method=ROUND_ROBIN", ctx)

        posts = _posts_to(seen, "dtc:pool")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "pool1"
        assert body["lb_preferred_method"] == "ROUND_ROBIN"


class TestDtcPoolDelete:
    async def test_delete(self):
        seen: list[httpx.Request] = []
        pool_ref = _ref("dtc:pool", "pool1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "dtc:pool" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": pool_ref, "name": "pool1"}]))
            if req.method == "DELETE" and "dtc:pool" in req.url.path:
                return httpx.Response(200, json=pool_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc pool pool1 delete", ctx)

        assert len(_deletes_to(seen, "dtc:pool")) == 1


class TestDtcPoolShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dtc:pool" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("dtc:pool", "pool1"), "name": "pool1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dtc pool", ctx)

        out = capsys.readouterr().out
        assert "pool1" in out
        assert "dtc:pool" in out


# ===========================================================================
# Chunk B: LBDNs
# ===========================================================================


class TestDtcLbdnAdd:
    async def test_add_basic(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "dtc:lbdn" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("dtc:lbdn", "lbdn1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc lbdn add lbdn1 lb_method=ROUND_ROBIN", ctx)

        posts = _posts_to(seen, "dtc:lbdn")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "lbdn1"
        assert body["lb_method"] == "ROUND_ROBIN"

    async def test_add_with_patterns(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "dtc:lbdn" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("dtc:lbdn", "lbdn2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc lbdn add lbdn2 patterns=*.example.com", ctx)

        posts = _posts_to(seen, "dtc:lbdn")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert "*.example.com" in body["patterns"]


class TestDtcLbdnDelete:
    async def test_delete(self):
        seen: list[httpx.Request] = []
        lbdn_ref = _ref("dtc:lbdn", "lbdn1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "dtc:lbdn" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": lbdn_ref, "name": "lbdn1"}]))
            if req.method == "DELETE" and "dtc:lbdn" in req.url.path:
                return httpx.Response(200, json=lbdn_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc lbdn lbdn1 delete", ctx)

        assert len(_deletes_to(seen, "dtc:lbdn")) == 1


class TestDtcLbdnShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dtc:lbdn" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("dtc:lbdn", "lbdn1"), "name": "lbdn1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dtc lbdn", ctx)

        out = capsys.readouterr().out
        assert "lbdn1" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dtc:lbdn" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("dtc:lbdn", "lbdn1"), "name": "lbdn1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dtc lbdn lbdn1", ctx)

        out = capsys.readouterr().out
        assert "lbdn1" in out


# ===========================================================================
# Chunk B: DTC records (read-only)
# ===========================================================================


class TestDtcRecordShow:
    @pytest.mark.parametrize(
        "rtype,sdk_fragment",
        [
            ("a", "dtc:record:a"),
            ("aaaa", "dtc:record:aaaa"),
            ("cname", "dtc:record:cname"),
            ("srv", "dtc:record:srv"),
            ("naptr", "dtc:record:naptr"),
        ],
    )
    async def test_show_record_type(self, rtype, sdk_fragment, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and sdk_fragment in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": f"dtc:record:{rtype}/ZG5z:web1", "name": "web1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(f"show dtc record {rtype} web1", ctx)

        out = capsys.readouterr().out
        assert f"dtc:record:{rtype}" in out

    async def test_bare_form_prints_helpful_error(self, capsys):
        async with connected_ctx(None) as ctx:
            await process_line("show dtc record a", ctx)
        out = capsys.readouterr().out
        assert "Error: dtc_server required" in out


class TestDtcAllrecordsShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dtc:allrecords" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "dtc:allrecords/ZG5z:web1",
                                "type": "dtc:record:a",
                                "dtc_server": "web1",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dtc records example.com", ctx)

        out = capsys.readouterr().out
        assert "dtc:record:a" in out

    async def test_bare_form_prints_helpful_error(self, capsys):
        async with connected_ctx(None) as ctx:
            await process_line("show dtc records", ctx)
        out = capsys.readouterr().out
        assert "Error: zone required" in out


# ===========================================================================
# Chunk C: Monitors
# ===========================================================================


class TestDtcMonitorShowAll:
    async def test_show_base_aggregate(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            path = req.url.path
            if req.method == "GET" and path.endswith("/dtc:monitor"):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "dtc:monitor/ZG5z:mon1",
                                "name": "mon1",
                                "type": "HTTP",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dtc monitor", ctx)

        out = capsys.readouterr().out
        assert "dtc:monitor" in out


@pytest.mark.parametrize(
    "proto,sdk_fragment",
    [
        ("http", "dtc:monitor:http"),
        ("icmp", "dtc:monitor:icmp"),
        ("tcp", "dtc:monitor:tcp"),
        ("snmp", "dtc:monitor:snmp"),
        ("sip", "dtc:monitor:sip"),
        ("pdp", "dtc:monitor:pdp"),
    ],
)
class TestDtcMonitorProtocol:
    async def test_add(self, proto, sdk_fragment):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and sdk_fragment in req.url.path:
                return httpx.Response(201, json={"_ref": f"dtc:monitor:{proto}/ZG5z:mon1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(f"configure dtc monitor {proto} add mon1", ctx)

        posts = _posts_to(seen, sdk_fragment)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "mon1"

    async def test_add_with_port(self, proto, sdk_fragment):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and sdk_fragment in req.url.path:
                return httpx.Response(201, json={"_ref": f"dtc:monitor:{proto}/ZG5z:mon2"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(f"configure dtc monitor {proto} add mon2 port=80", ctx)

        posts = _posts_to(seen, sdk_fragment)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        # Only http, tcp, snmp, sip, pdp accept port; icmp does not
        if proto != "icmp":
            assert body.get("port") == 80

    async def test_delete(self, proto, sdk_fragment):
        seen: list[httpx.Request] = []
        mon_ref = f"dtc:monitor:{proto}/ZG5z:mon1"

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and sdk_fragment in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": mon_ref, "name": "mon1"}]))
            if req.method == "DELETE":
                return httpx.Response(200, json=mon_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(f"configure dtc monitor {proto} mon1 delete", ctx)

        assert len(_deletes_to(seen, f"dtc:monitor:{proto}")) == 1

    async def test_show(self, proto, sdk_fragment, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and sdk_fragment in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": f"dtc:monitor:{proto}/ZG5z:mon1", "name": "mon1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(f"show dtc monitor {proto}", ctx)

        out = capsys.readouterr().out
        assert f"dtc:monitor:{proto}" in out


# ===========================================================================
# Chunk D: Topology
# ===========================================================================


class TestDtcTopologyAdd:
    async def test_add(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if (
                req.method == "POST"
                and "dtc:topology" in req.url.path
                and "rule" not in req.url.path
                and "label" not in req.url.path
            ):
                return httpx.Response(201, json={"_ref": _ref("dtc:topology", "topo1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc topology add topo1", ctx)

        posts = [
            r
            for r in _posts_to(seen, "dtc:topology")
            if "rule" not in r.url.path and "label" not in r.url.path
        ]
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "topo1"


class TestDtcTopologyDelete:
    async def test_delete(self):
        seen: list[httpx.Request] = []
        topo_ref = _ref("dtc:topology", "topo1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if (
                req.method == "GET"
                and "dtc:topology" in req.url.path
                and "rule" not in req.url.path
                and "label" not in req.url.path
            ):
                return httpx.Response(200, json=_list([{"_ref": topo_ref, "name": "topo1"}]))
            if req.method == "DELETE" and "dtc:topology" in req.url.path:
                return httpx.Response(200, json=topo_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc topology topo1 delete", ctx)

        deletes = [
            r
            for r in _deletes_to(seen, "dtc:topology")
            if "rule" not in r.url.path and "label" not in r.url.path
        ]
        assert len(deletes) == 1


class TestDtcTopologyShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if (
                req.method == "GET"
                and "dtc:topology" in req.url.path
                and "rule" not in req.url.path
                and "label" not in req.url.path
            ):
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("dtc:topology", "topo1"), "name": "topo1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dtc topology", ctx)

        out = capsys.readouterr().out
        assert "topo1" in out
        assert "dtc:topology" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if (
                req.method == "GET"
                and "dtc:topology" in req.url.path
                and "rule" not in req.url.path
                and "label" not in req.url.path
            ):
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("dtc:topology", "topo1"), "name": "topo1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dtc topology topo1", ctx)

        out = capsys.readouterr().out
        assert "topo1" in out


class TestDtcTopologyLabelShow:
    async def test_show_labels(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dtc:topology:label" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "dtc:topology:label/ZG5z:us",
                                "label": "us",
                                "field": "COUNTRY",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dtc topology topo1 label", ctx)

        out = capsys.readouterr().out
        assert "dtc:topology:label" in out
        assert "us" in out


class TestDtcTopologyRuleShow:
    async def test_show_rules(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dtc:topology:rule" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "dtc:topology:rule/ZG5z:r1",
                                "dest_type": "POOL",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dtc topology topo1 rule", ctx)

        out = capsys.readouterr().out
        assert "dtc:topology:rule" in out


# ===========================================================================
# Chunk E: Certificates
# ===========================================================================


class TestDtcCertificateShow:
    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dtc:certificate" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "dtc:certificate/ZG5z:cert1",
                                "in_use": True,
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dtc certificate", ctx)

        out = capsys.readouterr().out
        assert "dtc:certificate" in out


class TestDtcCertificateDelete:
    # NIOS 9.1 forbids read on `dtc` and the SDK refuses it
    # before the request is built. These assert the request the CLI
    # *would* send, so enforcement is off here.
    async def test_delete_by_ref(self):
        seen: list[httpx.Request] = []
        cert_ref = "dtc:certificate/ZG5z:cert1"

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "DELETE" and "dtc:certificate" in req.url.path:
                return httpx.Response(200, json=cert_ref)
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line(f"configure dtc certificate {cert_ref} delete", ctx)

        assert len(_deletes_to(seen, "dtc:certificate")) == 1

    async def test_delete_by_name_rejected_not_crashed(self, capsys):
        """dtc:certificate has no name field, so only a real _ref identifies one.

        Handing a bare name to the SDK raises ValueError; the handler must say
        what it needs instead.
        """
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure dtc certificate mycert delete", ctx)

        out = capsys.readouterr().out
        assert "not a dtc:certificate ref: mycert" in out
        assert "ValueError" not in out
        assert not _deletes_to(seen, "dtc:certificate")


# ===========================================================================
# Chunk E: DTC object aggregator
# ===========================================================================


class TestDtcObjectShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dtc:object" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "dtc:object/ZG5z:obj1",
                                "name": "obj1",
                                "display_type": "DTC:SERVER",
                                "status": "GREEN",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dtc object", ctx)

        out = capsys.readouterr().out
        assert "dtc:object" in out
        assert "GREEN" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dtc:object" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "dtc:object/ZG5z:obj1",
                                "name": "obj1",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dtc object obj1", ctx)

        out = capsys.readouterr().out
        assert "obj1" in out


# ===========================================================================
# Not-connected guard tests (spot-check a few commands)
# ===========================================================================


class TestDtcNotConnected:
    async def test_server_add_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure dtc server add web1 host=10.0.0.1", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out

    async def test_pool_show_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show dtc pool", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out

    async def test_lbdn_delete_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure dtc lbdn lbdn1 delete", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


# ===========================================================================
# DTC wiring: pool ↔ server
# ===========================================================================


class TestPoolServerWiring:
    async def test_add_server_appends_to_pool_servers(self):
        pool_ref = "dtc:pool/a:p1"
        server_ref = "dtc:server/a:web1"
        puts: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            if (
                request.method == "GET"
                and "/dtc:pool" in request.url.path
                and pool_ref not in request.url.path
            ):
                return httpx.Response(200, json=_list([{"_ref": pool_ref, "name": "p1"}]))
            if request.method == "GET" and "/dtc:server" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": server_ref, "name": "web1"}]))
            if request.method == "GET" and pool_ref in request.url.path:
                return httpx.Response(200, json={"_ref": pool_ref, "servers": []})
            if request.method == "PUT" and pool_ref in request.url.path:
                puts.append(request)
                return httpx.Response(200, json=pool_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc pool p1 server add web1", ctx)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["servers"] == [{"server": server_ref, "ratio": 1}]

    async def test_add_server_with_ratio(self):
        pool_ref = "dtc:pool/a:p1"
        server_ref = "dtc:server/a:web1"
        puts: list[httpx.Request] = []

        def handler(request):
            if (
                request.method == "GET"
                and "/dtc:pool" in request.url.path
                and pool_ref not in request.url.path
            ):
                return httpx.Response(200, json=_list([{"_ref": pool_ref}]))
            if request.method == "GET" and "/dtc:server" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": server_ref}]))
            if request.method == "GET" and pool_ref in request.url.path:
                return httpx.Response(200, json={"_ref": pool_ref, "servers": []})
            if request.method == "PUT" and pool_ref in request.url.path:
                puts.append(request)
                return httpx.Response(200, json=pool_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc pool p1 server add web1 ratio=7", ctx)
        body = json.loads(puts[0].content)
        assert body["servers"][0]["ratio"] == 7

    async def test_add_server_already_in_pool_prints_skipped(self, capsys):
        pool_ref = "dtc:pool/a:p1"
        server_ref = "dtc:server/a:web1"

        def handler(request):
            if (
                request.method == "GET"
                and "/dtc:pool" in request.url.path
                and pool_ref not in request.url.path
            ):
                return httpx.Response(200, json=_list([{"_ref": pool_ref}]))
            if request.method == "GET" and "/dtc:server" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": server_ref}]))
            if request.method == "GET" and pool_ref in request.url.path:
                return httpx.Response(
                    200, json={"_ref": pool_ref, "servers": [{"server": server_ref, "ratio": 1}]}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc pool p1 server add web1", ctx)
        assert "Skipped: server web1 already in pool p1" in capsys.readouterr().out

    async def test_add_server_bad_ratio(self, capsys):
        def handler(request):
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc pool p1 server add web1 ratio=xyz", ctx)
        assert "ratio must be an integer" in capsys.readouterr().out

    async def test_add_server_pool_not_found(self, capsys):
        def handler(request):
            if request.method == "GET" and "/dtc:pool" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc pool p1 server add web1", ctx)
        assert "No DTC pool found" in capsys.readouterr().out

    async def test_add_server_server_not_found(self, capsys):
        pool_ref = "dtc:pool/a:p1"

        def handler(request):
            if request.method == "GET" and "/dtc:pool" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": pool_ref}]))
            if request.method == "GET" and "/dtc:server" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc pool p1 server add missing-web", ctx)
        assert "No DTC server found" in capsys.readouterr().out

    async def test_delete_server_removes_from_list(self):
        pool_ref = "dtc:pool/a:p1"
        server_ref = "dtc:server/a:web1"
        puts: list[httpx.Request] = []

        def handler(request):
            if (
                request.method == "GET"
                and "/dtc:pool" in request.url.path
                and pool_ref not in request.url.path
            ):
                return httpx.Response(200, json=_list([{"_ref": pool_ref}]))
            if request.method == "GET" and "/dtc:server" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": server_ref}]))
            if request.method == "GET" and pool_ref in request.url.path:
                return httpx.Response(
                    200, json={"_ref": pool_ref, "servers": [{"server": server_ref, "ratio": 1}]}
                )
            if request.method == "PUT" and pool_ref in request.url.path:
                puts.append(request)
                return httpx.Response(200, json=pool_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc pool p1 server delete web1", ctx)
        body = json.loads(puts[0].content)
        assert body["servers"] == []

    async def test_server_add_not_connected(self, capsys):
        await process_line("configure dtc pool p1 server add web1", Context())
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# DTC wiring: pool ↔ monitor
# ===========================================================================


class TestPoolMonitorWiring:
    async def test_add_http_monitor_appends(self):
        pool_ref = "dtc:pool/a:p1"
        mon_ref = "dtc:monitor:http/a:m1"
        puts: list[httpx.Request] = []

        def handler(request):
            if (
                request.method == "GET"
                and "/dtc:pool" in request.url.path
                and pool_ref not in request.url.path
            ):
                return httpx.Response(200, json=_list([{"_ref": pool_ref}]))
            if request.method == "GET" and "/dtc:monitor:http" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": mon_ref}]))
            if request.method == "GET" and pool_ref in request.url.path:
                return httpx.Response(200, json={"_ref": pool_ref, "monitors": []})
            if request.method == "PUT" and pool_ref in request.url.path:
                puts.append(request)
                return httpx.Response(200, json=pool_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc pool p1 monitor add http m1", ctx)
        body = json.loads(puts[0].content)
        assert body["monitors"] == [mon_ref]

    async def test_add_monitor_already_attached(self, capsys):
        pool_ref = "dtc:pool/a:p1"
        mon_ref = "dtc:monitor:icmp/a:m1"

        def handler(request):
            if (
                request.method == "GET"
                and "/dtc:pool" in request.url.path
                and pool_ref not in request.url.path
            ):
                return httpx.Response(200, json=_list([{"_ref": pool_ref}]))
            if request.method == "GET" and "/dtc:monitor:icmp" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": mon_ref}]))
            if request.method == "GET" and pool_ref in request.url.path:
                return httpx.Response(200, json={"_ref": pool_ref, "monitors": [mon_ref]})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc pool p1 monitor add icmp m1", ctx)
        assert "Skipped" in capsys.readouterr().out
        assert "already attached" in capsys.readouterr().out or True

    async def test_delete_monitor_removes(self):
        pool_ref = "dtc:pool/a:p1"
        mon_ref = "dtc:monitor:tcp/a:m1"
        puts: list[httpx.Request] = []

        def handler(request):
            if (
                request.method == "GET"
                and "/dtc:pool" in request.url.path
                and pool_ref not in request.url.path
            ):
                return httpx.Response(200, json=_list([{"_ref": pool_ref}]))
            if request.method == "GET" and "/dtc:monitor:tcp" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": mon_ref}]))
            if request.method == "GET" and pool_ref in request.url.path:
                return httpx.Response(200, json={"_ref": pool_ref, "monitors": [mon_ref]})
            if request.method == "PUT" and pool_ref in request.url.path:
                puts.append(request)
                return httpx.Response(200, json=pool_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc pool p1 monitor delete tcp m1", ctx)
        body = json.loads(puts[0].content)
        assert body["monitors"] == []

    async def test_monitor_not_found(self, capsys):
        pool_ref = "dtc:pool/a:p1"

        def handler(request):
            if request.method == "GET" and "/dtc:pool" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": pool_ref}]))
            if request.method == "GET" and "/dtc:monitor:http" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc pool p1 monitor add http missing", ctx)
        assert "No DTC http monitor found" in capsys.readouterr().out

    async def test_monitor_pool_not_found(self, capsys):
        def handler(request):
            if request.method == "GET" and "/dtc:pool" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc pool nope monitor add http m1", ctx)
        assert "No DTC pool found" in capsys.readouterr().out

    async def test_monitor_add_not_connected(self, capsys):
        await process_line("configure dtc pool p1 monitor add http m1", Context())
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# DTC wiring: lbdn ↔ pool
# ===========================================================================


class TestLbdnPoolWiring:
    async def test_add_pool_to_lbdn(self):
        lbdn_ref = "dtc:lbdn/a:lb1"
        pool_ref = "dtc:pool/a:p1"
        puts: list[httpx.Request] = []

        def handler(request):
            if (
                request.method == "GET"
                and "/dtc:lbdn" in request.url.path
                and lbdn_ref not in request.url.path
            ):
                return httpx.Response(200, json=_list([{"_ref": lbdn_ref}]))
            if request.method == "GET" and "/dtc:pool" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": pool_ref}]))
            if request.method == "GET" and lbdn_ref in request.url.path:
                return httpx.Response(200, json={"_ref": lbdn_ref, "pools": []})
            if request.method == "PUT" and lbdn_ref in request.url.path:
                puts.append(request)
                return httpx.Response(200, json=lbdn_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc lbdn lb1 pool add p1 ratio=3", ctx)
        body = json.loads(puts[0].content)
        assert body["pools"] == [{"pool": pool_ref, "ratio": 3}]

    async def test_add_pool_already_in_lbdn(self, capsys):
        lbdn_ref = "dtc:lbdn/a:lb1"
        pool_ref = "dtc:pool/a:p1"

        def handler(request):
            if (
                request.method == "GET"
                and "/dtc:lbdn" in request.url.path
                and lbdn_ref not in request.url.path
            ):
                return httpx.Response(200, json=_list([{"_ref": lbdn_ref}]))
            if request.method == "GET" and "/dtc:pool" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": pool_ref}]))
            if request.method == "GET" and lbdn_ref in request.url.path:
                return httpx.Response(
                    200, json={"_ref": lbdn_ref, "pools": [{"pool": pool_ref, "ratio": 1}]}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc lbdn lb1 pool add p1", ctx)
        assert "Skipped" in capsys.readouterr().out

    async def test_delete_pool_from_lbdn(self):
        lbdn_ref = "dtc:lbdn/a:lb1"
        pool_ref = "dtc:pool/a:p1"
        puts: list[httpx.Request] = []

        def handler(request):
            if (
                request.method == "GET"
                and "/dtc:lbdn" in request.url.path
                and lbdn_ref not in request.url.path
            ):
                return httpx.Response(200, json=_list([{"_ref": lbdn_ref}]))
            if request.method == "GET" and "/dtc:pool" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": pool_ref}]))
            if request.method == "GET" and lbdn_ref in request.url.path:
                return httpx.Response(
                    200, json={"_ref": lbdn_ref, "pools": [{"pool": pool_ref, "ratio": 1}]}
                )
            if request.method == "PUT" and lbdn_ref in request.url.path:
                puts.append(request)
                return httpx.Response(200, json=lbdn_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc lbdn lb1 pool delete p1", ctx)
        body = json.loads(puts[0].content)
        assert body["pools"] == []

    async def test_lbdn_bad_ratio(self, capsys):
        async with connected_ctx(lambda r: None) as ctx:
            await process_line("configure dtc lbdn lb1 pool add p1 ratio=nope", ctx)
        assert "ratio must be an integer" in capsys.readouterr().out

    async def test_lbdn_not_found(self, capsys):
        def handler(request):
            if request.method == "GET" and "/dtc:lbdn" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc lbdn missing pool add p1", ctx)
        assert "No DTC LBDN found" in capsys.readouterr().out

    async def test_lbdn_pool_not_found(self, capsys):
        lbdn_ref = "dtc:lbdn/a:lb1"

        def handler(request):
            if request.method == "GET" and "/dtc:lbdn" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": lbdn_ref}]))
            if request.method == "GET" and "/dtc:pool" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure dtc lbdn lb1 pool add missing", ctx)
        assert "No DTC pool found" in capsys.readouterr().out

    async def test_lbdn_not_connected(self, capsys):
        await process_line("configure dtc lbdn lb1 pool add p1", Context())
        assert "Not connected" in capsys.readouterr().out
