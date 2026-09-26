# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.ops - Phase 15.

Covers:
  Chunk A: DB snapshot (show), data collection cluster (add/delete/show),
           CSV task (show), scavenging (show), capacity report (show)
  Chunk B: Integration endpoints - TAXII (show/set), syslog (add/delete/show),
           pxgrid (add/delete/show), dxl (add/delete/show),
           outbound (show/set), allendpoints (show)
  Chunk C: BFD template (add/delete/show), Kerberos key (delete/show),
           TFTP dir (add/delete/show), Ruleset (add/delete/show)
  Chunk D: Deleted objects (show), DB objects (show)

Notes:
- WAPI list responses must be wrapped as {"result": [...]} (paging envelope).
- URL paths use raw colons for colon-typed objects (e.g. "syslog:endpoint").
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import ops  # noqa: F401  ensures module registers handlers
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
    return f"{objtype}/ZG5z:{name}"


def _list(items: list) -> dict:
    return {"result": items}


# ===========================================================================
# Chunk A: DB snapshot + data collection + CSV task + scavenging + capacity
# ===========================================================================


class TestDbSnapshotShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dbsnapshot" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("dbsnapshot", "snap1"),
                                "comment": "daily",
                                "timestamp": 1000,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show db snapshot", ctx)

        out = capsys.readouterr().out
        assert "type=dbsnapshot" in out
        assert "comment=daily" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dbsnapshot" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show db snapshot", ctx)

        out = capsys.readouterr().out
        assert out == ""


@pytest.mark.skip(reason="data_collection commands hidden from CLI surface")
class TestDataCollectionAdd:
    async def test_add_no_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "datacollectioncluster" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("datacollectioncluster", "c1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure data_collection add", ctx)

        posts = _posts_to(seen, "datacollectioncluster")
        assert len(posts) == 1

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "datacollectioncluster" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("datacollectioncluster", "c1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure data_collection add comment="my cluster"', ctx)

        posts = _posts_to(seen, "datacollectioncluster")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body.get("comment") == "my cluster"


@pytest.mark.skip(reason="data_collection commands hidden from CLI surface")
class TestDataCollectionDelete:
    async def test_delete_by_name(self):
        seen: list[httpx.Request] = []
        cluster_ref = _ref("datacollectioncluster", "c1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "datacollectioncluster" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": cluster_ref, "name": "c1"}]))
            if req.method == "DELETE" and "datacollectioncluster" in req.url.path:
                return httpx.Response(200, json=cluster_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure data_collection c1 delete", ctx)

        assert len(_deletes_to(seen, "datacollectioncluster")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "datacollectioncluster" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure data_collection noexist delete", ctx)

        out = capsys.readouterr().out
        assert "No data collection cluster found" in out


@pytest.mark.skip(reason="data_collection commands hidden from CLI surface")
class TestDataCollectionShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "datacollectioncluster" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("datacollectioncluster", "c1"), "name": "c1"},
                            {"_ref": _ref("datacollectioncluster", "c2"), "name": "c2"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show data_collection", ctx)

        out = capsys.readouterr().out
        assert "name=c1" in out
        assert "name=c2" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "datacollectioncluster" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("datacollectioncluster", "c1"), "name": "c1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show data_collection c1", ctx)

        out = capsys.readouterr().out
        assert "name=c1" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "datacollectioncluster" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show data_collection noexist", ctx)

        out = capsys.readouterr().out
        assert "No data collection cluster found" in out


class TestCsvTaskShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "csvimporttask" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("csvimporttask", "t1"),
                                "file_name": "data.csv",
                                "status": "COMPLETED",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show csv_task", ctx)

        out = capsys.readouterr().out
        assert "type=csvimporttask" in out
        assert "file_name=data.csv" in out

    async def test_show_by_id(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "csvimporttask" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("csvimporttask", "t1"),
                                "file_name": "data.csv",
                                "status": "RUNNING",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show csv_task 42", ctx)

        out = capsys.readouterr().out
        assert "status=RUNNING" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "csvimporttask" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show csv_task 999", ctx)

        out = capsys.readouterr().out
        assert "No CSV import task found" in out


class TestScavengingShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "scavengingtask" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("scavengingtask", "s1"),
                                "status": "RUNNING",
                                "action": "RECLAIM",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show scavenging", ctx)

        out = capsys.readouterr().out
        assert "type=scavengingtask" in out
        assert "status=RUNNING" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "scavengingtask" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show scavenging", ctx)

        out = capsys.readouterr().out
        assert out == ""


class TestCapacityReportShow:
    async def test_show_all_requires_name(self, capsys):
        """WAPI requires a name filter; the bare form prints an error and lists members."""

        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and req.url.path.endswith("/member"):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("member", "gm1"),
                                "host_name": "gm1",
                                "address": "10.0.0.1",
                            },
                            {
                                "_ref": _ref("member", "gm2"),
                                "host_name": "gm2",
                                "address": "10.0.0.2",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show capacity_report", ctx)
        out = capsys.readouterr().out
        assert "Error: member name required" in out
        assert "Available members" in out
        assert "gm1" in out
        assert "gm2" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "capacityreport" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("capacityreport", "gm1"), "name": "gm1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show capacity_report gm1", ctx)

        out = capsys.readouterr().out
        assert "name=gm1" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "capacityreport" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show capacity_report noexist", ctx)

        out = capsys.readouterr().out
        assert "No capacity report found" in out


# ===========================================================================
# Chunk B: Integrations
# ===========================================================================


class TestIntegrationTaxiiShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "/taxii" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("taxii", "t1"),
                                "name": "member1",
                                "enable_service": True,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration taxii", ctx)

        out = capsys.readouterr().out
        assert "type=taxii" in out
        assert "name=member1" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "/taxii" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("taxii", "t1"), "name": "member1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration taxii member1", ctx)

        out = capsys.readouterr().out
        assert "name=member1" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "/taxii" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration taxii noexist", ctx)

        out = capsys.readouterr().out
        assert "No TAXII endpoint found" in out


class TestIntegrationTaxiiSet:
    async def test_set_field(self):
        seen: list[httpx.Request] = []
        taxii_ref = _ref("taxii", "t1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "/taxii" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": taxii_ref, "name": "member1"}]))
            if req.method == "PUT":
                return httpx.Response(200, json={"_ref": taxii_ref})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure integration taxii member1 set enable_service=true", ctx)

        puts = _puts_to(seen, "taxii")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["enable_service"] is True

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "/taxii" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure integration taxii noexist set enable_service=true", ctx)

        out = capsys.readouterr().out
        assert "No TAXII endpoint found" in out


class TestIntegrationSyslogAdd:
    async def test_add_basic(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "syslog:endpoint" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("syslog:endpoint", "sl1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure integration syslog add sl1", ctx)

        posts = _posts_to(seen, "syslog:endpoint")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "sl1"

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "syslog:endpoint" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("syslog:endpoint", "sl2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure integration syslog add sl2 comment="syslog ep"', ctx)

        posts = _posts_to(seen, "syslog:endpoint")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["comment"] == "syslog ep"


class TestIntegrationSyslogDelete:
    async def test_delete_by_name(self):
        seen: list[httpx.Request] = []
        sl_ref = _ref("syslog:endpoint", "sl1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "syslog:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": sl_ref, "name": "sl1"}]))
            if req.method == "DELETE" and "syslog:endpoint" in req.url.path:
                return httpx.Response(200, json=sl_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure integration syslog sl1 delete", ctx)

        assert len(_deletes_to(seen, "syslog:endpoint")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "syslog:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure integration syslog noexist delete", ctx)

        out = capsys.readouterr().out
        assert "No syslog endpoint found" in out


class TestIntegrationSyslogShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "syslog:endpoint" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("syslog:endpoint", "sl1"),
                                "name": "sl1",
                                "log_level": "INFO",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration syslog", ctx)

        out = capsys.readouterr().out
        assert "type=syslog:endpoint" in out
        assert "name=sl1" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "syslog:endpoint" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("syslog:endpoint", "sl1"), "name": "sl1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration syslog sl1", ctx)

        out = capsys.readouterr().out
        assert "name=sl1" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "syslog:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration syslog missing", ctx)

        out = capsys.readouterr().out
        assert "No syslog endpoint found" in out


class TestIntegrationPxgridAdd:
    async def test_add_basic(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "pxgrid:endpoint" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("pxgrid:endpoint", "pg1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure integration pxgrid add pg1", ctx)

        posts = _posts_to(seen, "pxgrid:endpoint")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "pg1"

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "pxgrid:endpoint" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("pxgrid:endpoint", "pg2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure integration pxgrid add pg2 comment="pxgrid ep"', ctx)

        posts = _posts_to(seen, "pxgrid:endpoint")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["comment"] == "pxgrid ep"


class TestIntegrationPxgridDelete:
    async def test_delete_by_name(self):
        seen: list[httpx.Request] = []
        pg_ref = _ref("pxgrid:endpoint", "pg1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "pxgrid:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": pg_ref, "name": "pg1"}]))
            if req.method == "DELETE" and "pxgrid:endpoint" in req.url.path:
                return httpx.Response(200, json=pg_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure integration pxgrid pg1 delete", ctx)

        assert len(_deletes_to(seen, "pxgrid:endpoint")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "pxgrid:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure integration pxgrid noexist delete", ctx)

        out = capsys.readouterr().out
        assert "No pxGrid endpoint found" in out


class TestIntegrationPxgridShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "pxgrid:endpoint" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("pxgrid:endpoint", "pg1"),
                                "name": "pg1",
                                "address": "10.0.0.1",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration pxgrid", ctx)

        out = capsys.readouterr().out
        assert "type=pxgrid:endpoint" in out
        assert "name=pg1" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "pxgrid:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration pxgrid missing", ctx)

        out = capsys.readouterr().out
        assert "No pxGrid endpoint found" in out


class TestIntegrationDxlAdd:
    async def test_add_basic(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "dxl:endpoint" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("dxl:endpoint", "dx1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure integration dxl add dx1", ctx)

        posts = _posts_to(seen, "dxl:endpoint")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "dx1"

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "dxl:endpoint" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("dxl:endpoint", "dx2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure integration dxl add dx2 comment="dxl ep"', ctx)

        posts = _posts_to(seen, "dxl:endpoint")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["comment"] == "dxl ep"


class TestIntegrationDxlDelete:
    async def test_delete_by_name(self):
        seen: list[httpx.Request] = []
        dx_ref = _ref("dxl:endpoint", "dx1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "dxl:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": dx_ref, "name": "dx1"}]))
            if req.method == "DELETE" and "dxl:endpoint" in req.url.path:
                return httpx.Response(200, json=dx_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure integration dxl dx1 delete", ctx)

        assert len(_deletes_to(seen, "dxl:endpoint")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dxl:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure integration dxl noexist delete", ctx)

        out = capsys.readouterr().out
        assert "No DXL endpoint found" in out


class TestIntegrationDxlShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dxl:endpoint" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("dxl:endpoint", "dx1"),
                                "name": "dx1",
                                "log_level": "INFO",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration dxl", ctx)

        out = capsys.readouterr().out
        assert "type=dxl:endpoint" in out
        assert "name=dx1" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "dxl:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration dxl missing", ctx)

        out = capsys.readouterr().out
        assert "No DXL endpoint found" in out


class TestIntegrationOutboundShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "outbound:cloudclient" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("outbound:cloudclient", "oc1"),
                                "grid_member": "member1",
                                "enable": True,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration outbound", ctx)

        out = capsys.readouterr().out
        assert "type=outbound:cloudclient" in out
        assert "grid_member=member1" in out

    async def test_show_by_member(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "outbound:cloudclient" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": _ref("outbound:cloudclient", "oc1"), "grid_member": "member1"}]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration outbound member1", ctx)

        out = capsys.readouterr().out
        assert "grid_member=member1" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "outbound:cloudclient" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration outbound noexist", ctx)

        out = capsys.readouterr().out
        assert "No outbound cloud client found" in out


class TestIntegrationOutboundSet:
    async def test_set_field(self):
        seen: list[httpx.Request] = []
        oc_ref = _ref("outbound:cloudclient", "oc1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "outbound:cloudclient" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": oc_ref, "grid_member": "m1"}]))
            if req.method == "PUT":
                return httpx.Response(200, json={"_ref": oc_ref})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure integration outbound m1 set enable=true", ctx)

        puts = _puts_to(seen, "outbound:cloudclient")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["enable"] is True

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "outbound:cloudclient" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure integration outbound noexist set enable=true", ctx)

        out = capsys.readouterr().out
        assert "No outbound cloud client found" in out


class TestIntegrationAllShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "allendpoints" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("allendpoints", "ep1"),
                                "type": "TYPE_DXL",
                                "address": "10.0.0.1",
                            },
                            {
                                "_ref": _ref("allendpoints", "ep2"),
                                "type": "TYPE_CISCO",
                                "address": "10.0.0.2",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration all", ctx)

        out = capsys.readouterr().out
        assert "type=allendpoints" in out
        assert "address=10.0.0.1" in out
        assert "address=10.0.0.2" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "allendpoints" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show integration all", ctx)

        out = capsys.readouterr().out
        assert out == ""


# ===========================================================================
# Chunk C: BFD template + Kerberos key + TFTP dir + Ruleset
# ===========================================================================


class TestBfdTemplateAdd:
    async def test_add_basic(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "bfdtemplate" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("bfdtemplate", "b1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure bfd_template add bfd1", ctx)

        posts = _posts_to(seen, "bfdtemplate")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "bfd1"

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "bfdtemplate" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("bfdtemplate", "b2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure bfd_template add bfd2 comment="my bfd"', ctx)

        posts = _posts_to(seen, "bfdtemplate")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["comment"] == "my bfd"


class TestBfdTemplateDelete:
    async def test_delete_by_name(self):
        seen: list[httpx.Request] = []
        bfd_ref = _ref("bfdtemplate", "b1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "bfdtemplate" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": bfd_ref, "name": "bfd1"}]))
            if req.method == "DELETE" and "bfdtemplate" in req.url.path:
                return httpx.Response(200, json=bfd_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure bfd_template bfd1 delete", ctx)

        assert len(_deletes_to(seen, "bfdtemplate")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "bfdtemplate" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure bfd_template noexist delete", ctx)

        out = capsys.readouterr().out
        assert "No BFD template found" in out


class TestBfdTemplateShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "bfdtemplate" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("bfdtemplate", "b1"),
                                "name": "bfd1",
                                "detection_multiplier": 3,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show bfd_template", ctx)

        out = capsys.readouterr().out
        assert "type=bfdtemplate" in out
        assert "name=bfd1" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "bfdtemplate" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("bfdtemplate", "b1"), "name": "bfd1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show bfd_template bfd1", ctx)

        out = capsys.readouterr().out
        assert "name=bfd1" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "bfdtemplate" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show bfd_template noexist", ctx)

        out = capsys.readouterr().out
        assert "No BFD template found" in out


class TestKerberosKeyDelete:
    async def test_delete_by_ref(self):
        seen: list[httpx.Request] = []
        kk_ref = _ref("kerberoskey", "kk1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "DELETE" and "kerberoskey" in req.url.path:
                return httpx.Response(200, json=kk_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(f"configure kerberos_key {kk_ref} delete", ctx)

        assert len(_deletes_to(seen, "kerberoskey")) == 1

    async def test_delete_by_principal_resolves_ref(self):
        """A bare principal is looked up first - the SDK rejects it as a ref."""
        seen: list[httpx.Request] = []
        kk_ref = _ref("kerberoskey", "kk1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "kerberoskey" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": kk_ref, "principal": "hostgm.local"},
                        ]
                    ),
                )
            if req.method == "DELETE" and "kerberoskey" in req.url.path:
                return httpx.Response(200, json=kk_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure kerberos_key hostgm.local delete", ctx)

        gets = [r for r in seen if r.method == "GET" and "kerberoskey" in r.url.path]
        assert len(gets) == 1
        assert gets[0].url.params.get("principal") == "hostgm.local"
        assert len(_deletes_to(seen, "kerberoskey")) == 1

    async def test_delete_unknown_principal_reports_cleanly(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "kerberoskey" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure kerberos_key nobody delete", ctx)

        out = capsys.readouterr().out
        assert "No Kerberos key found: nobody" in out
        assert "ValueError" not in out


class TestKerberosKeyShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "kerberoskey" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("kerberoskey", "kk1"),
                                "principal": "host/gm.local",
                                "domain": "LOCAL",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show kerberos_key", ctx)

        out = capsys.readouterr().out
        assert "type=kerberoskey" in out
        assert "principal=host/gm.local" in out

    async def test_show_by_principal(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "kerberoskey" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": _ref("kerberoskey", "kk1"), "principal": "host/gm.local"}]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show kerberos_key host/gm.local", ctx)

        out = capsys.readouterr().out
        assert "principal=host/gm.local" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "kerberoskey" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show kerberos_key nobody", ctx)

        out = capsys.readouterr().out
        assert "No Kerberos key found" in out


class TestTftpDirAdd:
    async def test_add_basic(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "tftpfiledir" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("tftpfiledir", "td1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure tftp_dir add configs", ctx)

        posts = _posts_to(seen, "tftpfiledir")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "configs"

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "tftpfiledir" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("tftpfiledir", "td2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure tftp_dir add configs2 comment="config files"', ctx)

        posts = _posts_to(seen, "tftpfiledir")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["comment"] == "config files"


class TestTftpDirDelete:
    async def test_delete_by_name(self):
        seen: list[httpx.Request] = []
        td_ref = _ref("tftpfiledir", "td1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "tftpfiledir" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": td_ref, "name": "configs"}]))
            if req.method == "DELETE" and "tftpfiledir" in req.url.path:
                return httpx.Response(200, json=td_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure tftp_dir configs delete", ctx)

        assert len(_deletes_to(seen, "tftpfiledir")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "tftpfiledir" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure tftp_dir noexist delete", ctx)

        out = capsys.readouterr().out
        assert "No TFTP file directory found" in out


class TestTftpDirShow:
    async def test_show_all_requires_directory(self, capsys):
        """WAPI requires a directory filter; bare form prints helpful error."""
        async with connected_ctx(None) as ctx:
            await process_line("show tftp_dir", ctx)
        out = capsys.readouterr().out
        assert "Error: directory required" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "tftpfiledir" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("tftpfiledir", "td1"), "name": "configs"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show tftp_dir configs", ctx)

        out = capsys.readouterr().out
        assert "name=configs" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "tftpfiledir" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show tftp_dir noexist", ctx)

        out = capsys.readouterr().out
        assert "No TFTP file directory found" in out


class TestRulesetAdd:
    async def test_add_basic(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "ruleset" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("ruleset", "rs1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ruleset add myruleset", ctx)

        posts = _posts_to(seen, "ruleset")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "myruleset"

    async def test_add_with_type(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "ruleset" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("ruleset", "rs2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ruleset add myruleset type=NXDOMAIN", ctx)

        posts = _posts_to(seen, "ruleset")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["type"] == "NXDOMAIN"

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "ruleset" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("ruleset", "rs3")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure ruleset add myruleset type=BLACKLIST comment="block list"', ctx
            )

        posts = _posts_to(seen, "ruleset")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["type"] == "BLACKLIST"
        assert body["comment"] == "block list"


class TestRulesetDelete:
    async def test_delete_by_name(self):
        seen: list[httpx.Request] = []
        rs_ref = _ref("ruleset", "rs1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "ruleset" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": rs_ref, "name": "myruleset"}]))
            if req.method == "DELETE" and "ruleset" in req.url.path:
                return httpx.Response(200, json=rs_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ruleset myruleset delete", ctx)

        assert len(_deletes_to(seen, "ruleset")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "ruleset" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ruleset noexist delete", ctx)

        out = capsys.readouterr().out
        assert "No ruleset found" in out


class TestRulesetShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "ruleset" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("ruleset", "rs1"),
                                "name": "myruleset",
                                "type": "NXDOMAIN",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ruleset", ctx)

        out = capsys.readouterr().out
        assert "type=ruleset" in out
        assert "name=myruleset" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "ruleset" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("ruleset", "rs1"), "name": "myruleset"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ruleset myruleset", ctx)

        out = capsys.readouterr().out
        assert "name=myruleset" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "ruleset" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ruleset noexist", ctx)

        out = capsys.readouterr().out
        assert "No ruleset found" in out


# ===========================================================================
# Chunk D: Read-only aggregates
# ===========================================================================


class TestDeletedObjectsShow:
    # NIOS 9.1 forbids read on `deleted_objects` and the SDK refuses it
    # before the request is built. These assert the request the CLI
    # *would* send, so enforcement is off here.
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "deleted_objects" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("deleted_objects", "d1"), "object_type": "record:a"},
                            {"_ref": _ref("deleted_objects", "d2"), "object_type": "record:cname"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("show deleted_objects", ctx)

        out = capsys.readouterr().out
        assert "type=deleted_objects" in out
        assert "object_type=record:a" in out
        assert "object_type=record:cname" in out

    async def test_show_by_type(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "deleted_objects" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("deleted_objects", "d1"), "object_type": "record:a"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("show deleted_objects record:a", ctx)

        out = capsys.readouterr().out
        assert "object_type=record:a" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "deleted_objects" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("show deleted_objects notype", ctx)

        out = capsys.readouterr().out
        assert "No deleted objects found" in out


class TestDbObjectsShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "db_objects" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("db_objects", "o1"),
                                "object_type": "record:a",
                                "unique_id": "abc123",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show db_objects", ctx)

        out = capsys.readouterr().out
        assert "type=db_objects" in out
        assert "object_type=record:a" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "db_objects" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show db_objects", ctx)

        out = capsys.readouterr().out
        assert out == ""

    async def test_show_default_sends_all_types_param(self, capsys):
        """With no object_type= arg, the WAPI 'all_object_types_supported_in_version'
        flag must be sent - otherwise NIOS returns a validation error."""
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "db_objects" in req.url.path:
                seen.append(req)
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show db_objects", ctx)

        assert any("all_object_types_supported_in_version" in r.url.query.decode() for r in seen)

    async def test_show_with_object_type_filter(self, capsys):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "db_objects" in req.url.path:
                seen.append(req)
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show db_objects object_types=record:a", ctx)

        assert any(
            "object_types=record%3Aa" in r.url.query.decode()
            or "object_types=record:a" in r.url.query.decode()
            for r in seen
        )
