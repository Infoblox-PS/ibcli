# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.notify - Phase 12.

Covers:
  Chunk A: ACL - namedacl (add, delete, set, show)
  Chunk B: Notification - REST endpoint (add, delete, set, show)
  Chunk C: Notification - REST template (delete, set, show - no POST)
           Notification - Rule (add, delete, set, show)

Notes:
- WAPI list responses must be wrapped as {"result": [...]} (paging envelope).
- URL paths use raw colons, e.g. "notification:rest:endpoint".
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import notify  # noqa: F401  ensures module registers handlers
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Seed the NULL root entry so configure/show are recognised."""
    COMMANDS.setdefault("NULL", CommandEntry(words="configure show"))


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
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
# Chunk A: ACL - namedacl
# ===========================================================================


class TestAclAdd:
    async def test_add_basic(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "namedacl" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("namedacl", "myacl")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure acl add myacl", ctx)

        posts = _posts_to(seen, "namedacl")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "myacl"

    async def test_add_with_access_list(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "namedacl" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("namedacl", "myacl")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure acl add myacl access_list=10.0.0.0/8,192.168.1.0/24", ctx)

        posts = _posts_to(seen, "namedacl")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert "access_list" in body
        assert len(body["access_list"]) == 2
        addresses = [e["address"] for e in body["access_list"]]
        assert "10.0.0.0/8" in addresses
        assert "192.168.1.0/24" in addresses
        # All entries default to ALLOW
        assert all(e["permission"] == "ALLOW" for e in body["access_list"])

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "namedacl" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("namedacl", "myacl")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure acl add myacl comment="my acl"', ctx)

        posts = _posts_to(seen, "namedacl")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["comment"] == "my acl"


class TestAclDelete:
    async def test_delete_by_name(self):
        seen: list[httpx.Request] = []
        acl_ref = _ref("namedacl", "myacl")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "namedacl" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": acl_ref, "name": "myacl"}]))
            if req.method == "DELETE" and "namedacl" in req.url.path:
                return httpx.Response(200, json=acl_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure acl myacl delete", ctx)

        assert len(_deletes_to(seen, "namedacl")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "namedacl" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure acl noexist delete", ctx)

        out = capsys.readouterr().out
        assert "No named ACL found" in out


class TestAclSet:
    async def test_set_field(self):
        seen: list[httpx.Request] = []
        acl_ref = _ref("namedacl", "myacl")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "namedacl" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": acl_ref, "name": "myacl"}]))
            if req.method == "PUT":
                return httpx.Response(200, json={"_ref": acl_ref})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure acl myacl set comment=updated", ctx)

        puts = _puts_to(seen, "namedacl")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["comment"] == "updated"

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "namedacl" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure acl noexist set comment=x", ctx)

        out = capsys.readouterr().out
        assert "No named ACL found" in out


class TestAclShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "namedacl" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("namedacl", "a1"), "name": "a1", "comment": "first"},
                            {"_ref": _ref("namedacl", "a2"), "name": "a2"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show acl", ctx)

        out = capsys.readouterr().out
        assert "name=a1" in out
        assert "name=a2" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "namedacl" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("namedacl", "a1"), "name": "a1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show acl a1", ctx)

        out = capsys.readouterr().out
        assert "name=a1" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "namedacl" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show acl missing", ctx)

        out = capsys.readouterr().out
        assert "No named ACL found" in out


# ===========================================================================
# Chunk B: Notification - REST endpoint
# ===========================================================================


class TestNotificationEndpointAdd:
    async def test_add_with_uri(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "notification:rest:endpoint" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("notification:rest:endpoint", "ep1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure notification endpoint add ep1 uri=https://example.com/hook",
                ctx,
            )

        posts = _posts_to(seen, "notification:rest:endpoint")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "ep1"
        assert body["uri"] == "https://example.com/hook"

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "notification:rest:endpoint" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("notification:rest:endpoint", "ep2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure notification endpoint add ep2 uri=https://svc.local comment="webhook"',
                ctx,
            )

        posts = _posts_to(seen, "notification:rest:endpoint")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["comment"] == "webhook"


class TestNotificationEndpointDelete:
    async def test_delete_by_name(self):
        seen: list[httpx.Request] = []
        ep_ref = _ref("notification:rest:endpoint", "ep1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "notification:rest:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": ep_ref, "name": "ep1"}]))
            if req.method == "DELETE" and "notification:rest:endpoint" in req.url.path:
                return httpx.Response(200, json=ep_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure notification endpoint ep1 delete", ctx)

        assert len(_deletes_to(seen, "notification:rest:endpoint")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "notification:rest:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure notification endpoint noexist delete", ctx)

        out = capsys.readouterr().out
        assert "No notification endpoint found" in out


class TestNotificationEndpointSet:
    async def test_set_field(self):
        seen: list[httpx.Request] = []
        ep_ref = _ref("notification:rest:endpoint", "ep1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "notification:rest:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": ep_ref, "name": "ep1"}]))
            if req.method == "PUT":
                return httpx.Response(200, json={"_ref": ep_ref})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure notification endpoint ep1 set log_level=DEBUG", ctx)

        puts = _puts_to(seen, "notification:rest:endpoint")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["log_level"] == "DEBUG"


class TestNotificationEndpointShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "notification:rest:endpoint" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("notification:rest:endpoint", "ep1"),
                                "name": "ep1",
                                "uri": "https://a.com",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show notification endpoint", ctx)

        out = capsys.readouterr().out
        assert "name=ep1" in out
        assert "type=notification:rest:endpoint" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "notification:rest:endpoint" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": _ref("notification:rest:endpoint", "ep1"), "name": "ep1"}]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show notification endpoint ep1", ctx)

        out = capsys.readouterr().out
        assert "name=ep1" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "notification:rest:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show notification endpoint missing", ctx)

        out = capsys.readouterr().out
        assert "No notification endpoint found" in out


# ===========================================================================
# Chunk C: Notification - REST template (no POST) + Rule (full CRUD)
# ===========================================================================


class TestNotificationTemplateDelete:
    async def test_delete_by_name(self):
        seen: list[httpx.Request] = []
        tmpl_ref = _ref("notification:rest:template", "tmpl1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "notification:rest:template" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": tmpl_ref, "name": "tmpl1"}]))
            if req.method == "DELETE" and "notification:rest:template" in req.url.path:
                return httpx.Response(200, json=tmpl_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure notification template tmpl1 delete", ctx)

        assert len(_deletes_to(seen, "notification:rest:template")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "notification:rest:template" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure notification template noexist delete", ctx)

        out = capsys.readouterr().out
        assert "No notification template found" in out


class TestNotificationTemplateSet:
    async def test_set_comment(self):
        seen: list[httpx.Request] = []
        tmpl_ref = _ref("notification:rest:template", "tmpl1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "notification:rest:template" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": tmpl_ref, "name": "tmpl1"}]))
            if req.method == "PUT":
                return httpx.Response(200, json={"_ref": tmpl_ref})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure notification template tmpl1 set comment=updated", ctx)

        puts = _puts_to(seen, "notification:rest:template")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["comment"] == "updated"


class TestNotificationTemplateShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "notification:rest:template" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("notification:rest:template", "t1"),
                                "name": "t1",
                                "outbound_type": "REST",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show notification template", ctx)

        out = capsys.readouterr().out
        assert "name=t1" in out
        assert "type=notification:rest:template" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "notification:rest:template" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": _ref("notification:rest:template", "t1"), "name": "t1"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show notification template t1", ctx)

        out = capsys.readouterr().out
        assert "name=t1" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "notification:rest:template" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show notification template missing", ctx)

        out = capsys.readouterr().out
        assert "No notification template found" in out


class TestNotificationRuleAdd:
    async def test_add_basic(self):
        """Rule add must (1) resolve endpoint=<name> via a GET, (2) POST a
        rule with name, event_type, notification_action, notification_target."""
        seen: list[httpx.Request] = []
        ep_ref = _ref("notification:rest:endpoint", "ep1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "notification:rest:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": ep_ref, "name": "ep1"}]))
            if req.method == "POST" and "notification:rule" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("notification:rule", "rule1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure notification rule add rule1 endpoint=ep1 event_type=DHCP_LEASES",
                ctx,
            )

        posts = _posts_to(seen, "notification:rule")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "rule1"
        assert body["event_type"] == "DHCP_LEASES"
        assert body["notification_target"] == ep_ref
        assert body["notification_action"]  # has a default

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []
        ep_ref = _ref("notification:rest:endpoint", "ep2")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "notification:rest:endpoint" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": ep_ref, "name": "ep2"}]))
            if req.method == "POST" and "notification:rule" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("notification:rule", "rule2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure notification rule add rule2 endpoint=ep2 "
                'event_type=DNS_RPZ comment="my rule"',
                ctx,
            )

        posts = _posts_to(seen, "notification:rule")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["comment"] == "my rule"


class TestNotificationRuleDelete:
    async def test_delete_by_name(self):
        seen: list[httpx.Request] = []
        rule_ref = _ref("notification:rule", "rule1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "notification:rule" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": rule_ref, "name": "rule1"}]))
            if req.method == "DELETE" and "notification:rule" in req.url.path:
                return httpx.Response(200, json=rule_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure notification rule rule1 delete", ctx)

        assert len(_deletes_to(seen, "notification:rule")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "notification:rule" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure notification rule noexist delete", ctx)

        out = capsys.readouterr().out
        assert "No notification rule found" in out


class TestNotificationRuleSet:
    async def test_set_field(self):
        seen: list[httpx.Request] = []
        rule_ref = _ref("notification:rule", "rule1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "notification:rule" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": rule_ref, "name": "rule1"}]))
            if req.method == "PUT":
                return httpx.Response(200, json={"_ref": rule_ref})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure notification rule rule1 set disable=true", ctx)

        puts = _puts_to(seen, "notification:rule")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["disable"] is True


class TestNotificationRuleShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "notification:rule" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("notification:rule", "r1"),
                                "name": "r1",
                                "event_type": "DNS_RPZ",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show notification rule", ctx)

        out = capsys.readouterr().out
        assert "name=r1" in out
        assert "type=notification:rule" in out

    async def test_show_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "notification:rule" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("notification:rule", "r1"), "name": "r1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show notification rule r1", ctx)

        out = capsys.readouterr().out
        assert "name=r1" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "notification:rule" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show notification rule missing", ctx)

        out = capsys.readouterr().out
        assert "No notification rule found" in out
