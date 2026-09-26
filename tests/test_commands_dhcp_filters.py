# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for Phase 10 Chunk A - DHCP filters.

Covers: filterfingerprint, filternac, filteroption, filterrelayagent,
        ipv6filteroption (add / delete / show per type).
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import dhcp  # noqa: F401  - registers handlers
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    COMMANDS.setdefault("NULL", CommandEntry(words="configure show"))


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test")


def _list(items: list[dict]) -> dict:
    return {"result": items}


def _api_posts(requests_seen: list, fragment: str = "") -> list:
    return [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/logout" not in r.url.path
        and (fragment == "" or fragment in r.url.path)
    ]


def _api_deletes(requests_seen: list, fragment: str = "") -> list:
    return [
        r
        for r in requests_seen
        if r.method == "DELETE" and (fragment == "" or fragment in r.url.path)
    ]


# ===========================================================================
# FilterFingerprint
# ===========================================================================


class TestFilterFingerprintAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filterfingerprint" in request.url.path:
                return httpx.Response(201, json={"_ref": "filterfingerprint/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter fingerprint add myfp", ctx)

        posts = _api_posts(requests_seen, "/filterfingerprint")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "myfp"

    async def test_add_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filterfingerprint" in request.url.path:
                return httpx.Response(201, json={"_ref": "filterfingerprint/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure filter fingerprint add myfp comment "my fingerprint filter"', ctx
            )

        posts = _api_posts(requests_seen, "/filterfingerprint")
        body = json.loads(posts[0].content)
        assert body["comment"] == "my fingerprint filter"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure filter fingerprint add myfp", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFilterFingerprintDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/filterfingerprint" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "filterfingerprint/abc", "name": "myfp"}])
                )
            if request.method == "DELETE" and "/filterfingerprint" in request.url.path:
                return httpx.Response(200, json="filterfingerprint/abc")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter fingerprint myfp delete", ctx)

        deletes = _api_deletes(requests_seen, "/filterfingerprint")
        assert len(deletes) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/filterfingerprint" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter fingerprint nope delete", ctx)

        assert "No fingerprint filter found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure filter fingerprint myfp delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFilterFingerprintShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/filterfingerprint" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "filterfingerprint/abc", "name": "myfp", "comment": "c1"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show filter fingerprint", ctx)

        out = capsys.readouterr().out
        assert "myfp" in out
        assert "c1" in out

    async def test_show_named(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/filterfingerprint" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "filterfingerprint/abc", "name": "myfp"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show filter fingerprint myfp", ctx)

        gets = [
            r for r in requests_seen if r.method == "GET" and "/filterfingerprint" in r.url.path
        ]
        assert gets
        assert "myfp" in str(gets[-1].url)

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show filter fingerprint", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# FilterNac
# ===========================================================================


class TestFilterNacAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filternac" in request.url.path:
                return httpx.Response(201, json={"_ref": "filternac/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter nac add mynac", ctx)

        posts = _api_posts(requests_seen, "/filternac")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "mynac"

    async def test_add_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filternac" in request.url.path:
                return httpx.Response(201, json={"_ref": "filternac/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure filter nac add mynac comment "nac filter"', ctx)

        body = json.loads(_api_posts(requests_seen, "/filternac")[0].content)
        assert body["comment"] == "nac filter"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure filter nac add mynac", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFilterNacDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/filternac" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": "filternac/abc", "name": "mynac"}]))
            if request.method == "DELETE" and "/filternac" in request.url.path:
                return httpx.Response(200, json="filternac/abc")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter nac mynac delete", ctx)

        assert len(_api_deletes(requests_seen, "/filternac")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/filternac" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter nac nope delete", ctx)

        assert "No NAC filter found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure filter nac mynac delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFilterNacShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/filternac" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "filternac/abc", "name": "mynac", "comment": "nc"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show filter nac", ctx)

        out = capsys.readouterr().out
        assert "mynac" in out

    async def test_show_named(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/filternac" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": "filternac/abc", "name": "mynac"}]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show filter nac mynac", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/filternac" in r.url.path]
        assert "mynac" in str(gets[-1].url)

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show filter nac", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# FilterOption
# ===========================================================================


class TestFilterOptionAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filteroption" in request.url.path:
                return httpx.Response(201, json={"_ref": "filteroption/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter option add myopt", ctx)

        posts = _api_posts(requests_seen, "/filteroption")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "myopt"

    async def test_add_with_expression(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filteroption" in request.url.path:
                return httpx.Response(201, json={"_ref": "filteroption/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter option add myopt expression option-60-exists", ctx)

        body = json.loads(_api_posts(requests_seen, "/filteroption")[0].content)
        assert body["expression"] == "option-60-exists"

    async def test_add_with_rule(self):
        """rule=<name>:<value>[:<num>] populates option_list.

        Regression guard for the smoke test ``option_filter row N: Rule list
        must contain at least one rule value or a list`` failure - NIOS
        rejects an option filter with no expression and no option_list.
        """
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filteroption" in request.url.path:
                return httpx.Response(201, json={"_ref": "filteroption/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure filter option add myopt rule=vendor-class-identifier:"MSFT 5.0":60',
                ctx,
            )

        body = json.loads(_api_posts(requests_seen, "/filteroption")[0].content)
        assert body["option_list"] == [
            {"name": "vendor-class-identifier", "value": "MSFT 5.0", "num": 60}
        ]

    async def test_add_with_match(self):
        """match=<opt>:<value> builds a NIOS match expression.

        Regression guard for the UDDI / CSP global-csv import failure
        ``option_filter row N: (400) Rule list must contain at least one
        rule value or a list.`` - downstream importers require an explicit
        expression, they won't synthesise one from apply_as_class +
        option_list.
        """
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filteroption" in request.url.path:
                return httpx.Response(201, json={"_ref": "filteroption/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure filter option add myopt match=vendor-class-identifier:ArubaAP",
                ctx,
            )

        body = json.loads(_api_posts(requests_seen, "/filteroption")[0].content)
        assert body["expression"] == 'option vendor-class-identifier = "ArubaAP"'

    async def test_add_with_match_and_rule(self):
        """match= and rule= are independent: expression + option_list both set."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filteroption" in request.url.path:
                return httpx.Response(201, json={"_ref": "filteroption/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure filter option add myopt "
                'match=vendor-class-identifier:"MSFT 5.0" '
                'rule=vendor-class-identifier:"MSFT 5.0":60',
                ctx,
            )

        body = json.loads(_api_posts(requests_seen, "/filteroption")[0].content)
        assert body["expression"] == 'option vendor-class-identifier = "MSFT 5.0"'
        assert body["option_list"] == [
            {"name": "vendor-class-identifier", "value": "MSFT 5.0", "num": 60}
        ]

    async def test_add_explicit_expression_overrides_match(self):
        """expression= wins when both are present - the shortcut defers."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filteroption" in request.url.path:
                return httpx.Response(201, json={"_ref": "filteroption/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure filter option add myopt "
                "expression=exists-vendor-class "
                "match=vendor-class-identifier:ArubaAP",
                ctx,
            )

        body = json.loads(_api_posts(requests_seen, "/filteroption")[0].content)
        assert body["expression"] == "exists-vendor-class"

    async def test_add_with_multiple_matches_joined(self):
        """Multiple match= clauses AND-join."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filteroption" in request.url.path:
                return httpx.Response(201, json={"_ref": "filteroption/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure filter option add myopt "
                "match=vendor-class-identifier:ArubaAP "
                "match=host-name:myhost",
                ctx,
            )

        body = json.loads(_api_posts(requests_seen, "/filteroption")[0].content)
        assert body["expression"] == (
            'option vendor-class-identifier = "ArubaAP" and option host-name = "myhost"'
        )

    async def test_add_with_multiple_rules(self):
        """Multiple rule= keywords stack into option_list, num optional."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filteroption" in request.url.path:
                return httpx.Response(201, json={"_ref": "filteroption/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure filter option add myopt "
                "rule=host-name:myhost "
                "rule=vendor-class-identifier:MSFT:60",
                ctx,
            )

        body = json.loads(_api_posts(requests_seen, "/filteroption")[0].content)
        assert body["option_list"] == [
            {"name": "host-name", "value": "myhost"},
            {"name": "vendor-class-identifier", "value": "MSFT", "num": 60},
        ]

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure filter option add myopt", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFilterOptionDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/filteroption" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "filteroption/abc", "name": "myopt"}])
                )
            if request.method == "DELETE" and "/filteroption" in request.url.path:
                return httpx.Response(200, json="filteroption/abc")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter option myopt delete", ctx)

        assert len(_api_deletes(requests_seen, "/filteroption")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/filteroption" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter option nope delete", ctx)

        assert "No option filter found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure filter option myopt delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFilterOptionShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/filteroption" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "filteroption/abc",
                                "name": "myopt",
                                "expression": "expr1",
                                "comment": "co",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show filter option", ctx)

        out = capsys.readouterr().out
        assert "myopt" in out
        assert "expr1" in out

    async def test_show_named(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/filteroption" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "filteroption/abc", "name": "myopt"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show filter option myopt", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/filteroption" in r.url.path]
        assert "myopt" in str(gets[-1].url)

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show filter option", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# FilterRelayAgent
# ===========================================================================


class TestFilterRelayAgentAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filterrelayagent" in request.url.path:
                return httpx.Response(201, json={"_ref": "filterrelayagent/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter relayagent add myrelay", ctx)

        posts = _api_posts(requests_seen, "/filterrelayagent")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "myrelay"

    async def test_add_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filterrelayagent" in request.url.path:
                return httpx.Response(201, json={"_ref": "filterrelayagent/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure filter relayagent add myrelay comment "relay filter"', ctx
            )

        body = json.loads(_api_posts(requests_seen, "/filterrelayagent")[0].content)
        assert body["comment"] == "relay filter"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure filter relayagent add myrelay", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFilterRelayAgentDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/filterrelayagent" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "filterrelayagent/abc", "name": "myrelay"}])
                )
            if request.method == "DELETE" and "/filterrelayagent" in request.url.path:
                return httpx.Response(200, json="filterrelayagent/abc")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter relayagent myrelay delete", ctx)

        assert len(_api_deletes(requests_seen, "/filterrelayagent")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/filterrelayagent" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter relayagent nope delete", ctx)

        assert "No relay-agent filter found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure filter relayagent myrelay delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFilterRelayAgentShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/filterrelayagent" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "filterrelayagent/abc", "name": "myrelay", "comment": "rc"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show filter relayagent", ctx)

        assert "myrelay" in capsys.readouterr().out

    async def test_show_named(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/filterrelayagent" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "filterrelayagent/abc", "name": "myrelay"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show filter relayagent myrelay", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/filterrelayagent" in r.url.path]
        assert "myrelay" in str(gets[-1].url)

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show filter relayagent", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# FilterIpv6Option
# ===========================================================================


class TestFilterIpv6OptionAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6filteroption" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6filteroption/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter ipv6option add myv6opt", ctx)

        posts = _api_posts(requests_seen, "/ipv6filteroption")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "myv6opt"

    async def test_add_with_expression(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6filteroption" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6filteroption/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure filter ipv6option add myv6opt expression option-vendor-class-exists",
                ctx,
            )

        body = json.loads(_api_posts(requests_seen, "/ipv6filteroption")[0].content)
        assert body["expression"] == "option-vendor-class-exists"

    async def test_add_with_rule(self):
        """rule= populates option_list on ipv6filteroption as well."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6filteroption" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6filteroption/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure filter ipv6option add myv6opt "
                'rule=dhcp6.vendor-class:"smoke-v6class":16',
                ctx,
            )

        body = json.loads(_api_posts(requests_seen, "/ipv6filteroption")[0].content)
        assert body["option_list"] == [
            {"name": "dhcp6.vendor-class", "value": "smoke-v6class", "num": 16}
        ]

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure filter ipv6option add myv6opt", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFilterIpv6OptionDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/ipv6filteroption" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "ipv6filteroption/abc", "name": "myv6opt"}])
                )
            if request.method == "DELETE" and "/ipv6filteroption" in request.url.path:
                return httpx.Response(200, json="ipv6filteroption/abc")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter ipv6option myv6opt delete", ctx)

        assert len(_api_deletes(requests_seen, "/ipv6filteroption")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/ipv6filteroption" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure filter ipv6option nope delete", ctx)

        assert "No IPv6 option filter found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure filter ipv6option myv6opt delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFilterIpv6OptionShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/ipv6filteroption" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "ipv6filteroption/abc",
                                "name": "myv6opt",
                                "expression": "v6expr",
                                "comment": "v6c",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show filter ipv6option", ctx)

        out = capsys.readouterr().out
        assert "myv6opt" in out
        assert "v6expr" in out

    async def test_show_named(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/ipv6filteroption" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "ipv6filteroption/abc", "name": "myv6opt"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show filter ipv6option myv6opt", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/ipv6filteroption" in r.url.path]
        assert "myv6opt" in str(gets[-1].url)

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show filter ipv6option", ctx)
        assert "Not connected" in capsys.readouterr().out
