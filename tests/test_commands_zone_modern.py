# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.zone_modern - Phase 3 DNS record commands."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import (
    zone,  # noqa: F401
    zone_modern,  # noqa: F401
)
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


def _rec_list(records: list[dict]) -> dict:
    return {"result": records}


def _api_posts(requests_seen: list, fragment: str = "") -> list:
    return [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/logout" not in r.url.path
        and (fragment == "" or fragment in r.url.path)
    ]


# ===========================================================================
# CHUNK A - CAA, DNAME, ALIAS, NS
# ===========================================================================


# ---------------------------------------------------------------------------
# CAA
# ---------------------------------------------------------------------------


async def test_add_caa_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"_ref": "record:caa/abc:test.example.com/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure record caa add test.example.com 0 issue letsencrypt.org", ctx)

    posts = _api_posts(requests_seen, "record%3Acaa")
    if not posts:
        posts = _api_posts(requests_seen, "record:caa")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "test.example.com"
    assert body["ca_flag"] == 0
    assert body["ca_tag"] == "issue"
    assert body["ca_value"] == "letsencrypt.org"


async def test_delete_caa_record():
    ref = "record:caa/abc:test.example.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=_rec_list([{"_ref": ref, "name": "test.example.com"}]))
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure record caa delete test.example.com", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_show_caa_record(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {
                            "_ref": "record:caa/abc:test.example.com/default",
                            "name": "test.example.com",
                            "ca_flag": 0,
                            "ca_tag": "issue",
                            "ca_value": "letsencrypt.org",
                        }
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record caa test.example.com", ctx)

    out = capsys.readouterr().out
    assert "test.example.com" in out
    assert "issue" in out


# ---------------------------------------------------------------------------
# DNAME
# ---------------------------------------------------------------------------


async def test_add_dname_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"_ref": "record:dname/abc:old.example.com/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure record dname add old.example.com new.example.com", ctx)

    posts = _api_posts(requests_seen)
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "old.example.com"
    assert body["target"] == "new.example.com"


async def test_delete_dname_record():
    ref = "record:dname/abc:old.example.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=_rec_list([{"_ref": ref, "name": "old.example.com"}]))
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure record dname delete old.example.com", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_show_dname_record(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {
                            "_ref": "record:dname/abc:old.example.com/default",
                            "name": "old.example.com",
                            "target": "new.example.com",
                        }
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record dname old.example.com", ctx)

    out = capsys.readouterr().out
    assert "old.example.com" in out
    assert "new.example.com" in out


# ---------------------------------------------------------------------------
# ALIAS
# ---------------------------------------------------------------------------


async def test_add_alias_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"_ref": "record:alias/abc:alias.example.com/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure record alias add alias.example.com real.example.com", ctx)

    posts = _api_posts(requests_seen)
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "alias.example.com"
    assert body["target_name"] == "real.example.com"


async def test_delete_alias_record():
    ref = "record:alias/abc:alias.example.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=_rec_list([{"_ref": ref, "name": "alias.example.com"}]))
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure record alias delete alias.example.com", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_show_alias_record(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {
                            "_ref": "record:alias/abc:alias.example.com/default",
                            "name": "alias.example.com",
                            "target_name": "real.example.com",
                        }
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record alias alias.example.com", ctx)

    out = capsys.readouterr().out
    assert "alias.example.com" in out


# ---------------------------------------------------------------------------
# NS
# ---------------------------------------------------------------------------


async def test_add_ns_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"_ref": "record:ns/abc:example.com/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure record ns add example.com ns1.example.com", ctx)

    posts = _api_posts(requests_seen)
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "example.com"
    assert body["nameserver"] == "ns1.example.com"


async def test_delete_ns_record():
    ref = "record:ns/abc:example.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=_rec_list([{"_ref": ref, "name": "example.com"}]))
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure record ns delete example.com", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_show_ns_record(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {
                            "_ref": "record:ns/abc:example.com/default",
                            "name": "example.com",
                            "nameserver": "ns1.example.com",
                        }
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record ns example.com", ctx)

    out = capsys.readouterr().out
    assert "example.com" in out
    assert "ns1.example.com" in out


# ===========================================================================
# CHUNK B - NAPTR, TLSA, HTTPS, SVCB
# ===========================================================================


# ---------------------------------------------------------------------------
# NAPTR
# ---------------------------------------------------------------------------


async def test_add_naptr_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"_ref": "record:naptr/abc:sip.example.com/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure record naptr add sip.example.com 10 20 U SIP+D2U !^.*$!sip:info@example.com! .",
            ctx,
        )

    posts = _api_posts(requests_seen)
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "sip.example.com"
    assert body["order"] == 10
    assert body["preference"] == 20
    assert body["flags"] == "U"
    assert body["services"] == "SIP+D2U"
    assert body["replacement"] == "."


async def test_delete_naptr_record():
    ref = "record:naptr/abc:sip.example.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=_rec_list([{"_ref": ref, "name": "sip.example.com"}]))
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure record naptr delete sip.example.com", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_show_naptr_record(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {
                            "_ref": "record:naptr/abc:sip.example.com/default",
                            "name": "sip.example.com",
                            "order": 10,
                            "preference": 20,
                        }
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record naptr sip.example.com", ctx)

    out = capsys.readouterr().out
    assert "sip.example.com" in out


# ---------------------------------------------------------------------------
# TLSA
# ---------------------------------------------------------------------------


async def test_add_tlsa_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(
                201, json={"_ref": "record:tlsa/abc:_443._tcp.www.example.com/default"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure record tlsa add _443._tcp.www.example.com 3 1 1 abc123deadbeef",
            ctx,
        )

    posts = _api_posts(requests_seen)
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "_443._tcp.www.example.com"
    assert body["certificate_usage"] == 3
    assert body["selector"] == 1
    assert body["matching_type"] == 1
    assert body["certificate_data"] == "abc123deadbeef"


async def test_delete_tlsa_record():
    ref = "record:tlsa/abc:_443._tcp.www.example.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list([{"_ref": ref, "name": "_443._tcp.www.example.com"}]),
            )
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure record tlsa delete _443._tcp.www.example.com", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_show_tlsa_record(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {
                            "_ref": "record:tlsa/abc:_443._tcp.www.example.com/default",
                            "name": "_443._tcp.www.example.com",
                            "certificate_usage": 3,
                            "selector": 1,
                            "matched_type": 1,
                        }
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record tlsa _443._tcp.www.example.com", ctx)

    out = capsys.readouterr().out
    assert "_443._tcp.www.example.com" in out


# ---------------------------------------------------------------------------
# HTTPS
# ---------------------------------------------------------------------------


async def test_add_https_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"_ref": "record:https/abc:www.example.com/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure record https add www.example.com 1 backend.example.com", ctx)

    posts = _api_posts(requests_seen)
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "www.example.com"
    assert body["priority"] == 1
    assert body["target_name"] == "backend.example.com"


async def test_delete_https_record():
    ref = "record:https/abc:www.example.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=_rec_list([{"_ref": ref, "name": "www.example.com"}]))
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure record https delete www.example.com", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_show_https_record(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {
                            "_ref": "record:https/abc:www.example.com/default",
                            "name": "www.example.com",
                            "priority": 1,
                            "target_name": "backend.example.com",
                        }
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record https www.example.com", ctx)

    out = capsys.readouterr().out
    assert "www.example.com" in out
    assert "backend.example.com" in out


# ---------------------------------------------------------------------------
# SVCB
# ---------------------------------------------------------------------------


async def test_add_svcb_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(
                201, json={"_ref": "record:svcb/abc:_8080._tcp.api.example.com/default"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure record svcb add _8080._tcp.api.example.com 2 svc.example.com",
            ctx,
        )

    posts = _api_posts(requests_seen)
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "_8080._tcp.api.example.com"
    assert body["priority"] == 2
    assert body["target_name"] == "svc.example.com"


async def test_delete_svcb_record():
    ref = "record:svcb/abc:_8080._tcp.api.example.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list([{"_ref": ref, "name": "_8080._tcp.api.example.com"}]),
            )
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure record svcb delete _8080._tcp.api.example.com", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_show_svcb_record(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {
                            "_ref": "record:svcb/abc:_8080._tcp.api.example.com/default",
                            "name": "_8080._tcp.api.example.com",
                            "priority": 2,
                            "target_name": "svc.example.com",
                        }
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record svcb _8080._tcp.api.example.com", ctx)

    out = capsys.readouterr().out
    assert "_8080._tcp.api.example.com" in out


# ===========================================================================
# CHUNK C - DNSSEC show-only
# ===========================================================================


@pytest.mark.parametrize(
    "cli_word,wapi_type,field,value",
    [
        ("dnskey", "record:dnskey", "name", "example.com"),
        ("ds", "record:ds", "name", "sub.example.com"),
        ("rrsig", "record:rrsig", "name", "example.com"),
        ("nsec", "record:nsec", "name", "a.example.com"),
        ("nsec3", "record:nsec3", "name", "0abc.example.com"),
        ("nsec3param", "record:nsec3param", "name", "example.com"),
        ("dhcid", "record:dhcid", "name", "host.example.com"),
    ],
)
async def test_show_dnssec_record(capsys, cli_word, wapi_type, field, value):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list([{"_ref": f"{wapi_type}/abc:{value}/default", field: value}]),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(f"show record {cli_word} {value}", ctx)

    out = capsys.readouterr().out
    assert value in out


# ===========================================================================
# CHUNK D - Shared records
# ===========================================================================


# ---------------------------------------------------------------------------
# shared A
# ---------------------------------------------------------------------------


async def test_add_shared_a_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"_ref": "sharedrecord:a/abc:web/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure shared_record a add web 1.2.3.4 group my_group", ctx)

    posts = _api_posts(requests_seen)
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "web"
    assert body["ipv4addr"] == "1.2.3.4"
    assert body["shared_record_group"] == "my_group"


async def test_delete_shared_a_record():
    ref = "sharedrecord:a/abc:web/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=_rec_list([{"_ref": ref, "name": "web"}]))
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure shared_record a delete web group my_group", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_show_shared_a_by_group(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {
                            "_ref": "sharedrecord:a/abc:web/default",
                            "name": "web",
                            "ipv4addr": "1.2.3.4",
                            "shared_record_group": "my_group",
                        }
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show shared_record a group my_group", ctx)

    out = capsys.readouterr().out
    assert "web" in out
    assert "1.2.3.4" in out


# ---------------------------------------------------------------------------
# shared AAAA
# ---------------------------------------------------------------------------


async def test_add_shared_aaaa_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"_ref": "sharedrecord:aaaa/abc:v6host/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure shared_record aaaa add v6host fe80::1 group my_group", ctx)

    posts = _api_posts(requests_seen)
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "v6host"
    assert body["ipv6addr"] == "fe80::1"
    assert body["shared_record_group"] == "my_group"


async def test_delete_shared_aaaa_record():
    ref = "sharedrecord:aaaa/abc:v6host/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=_rec_list([{"_ref": ref, "name": "v6host"}]))
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure shared_record aaaa delete v6host", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_show_shared_aaaa(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [{"_ref": "sharedrecord:aaaa/abc:v6host/default", "name": "v6host"}]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show shared_record aaaa", ctx)

    out = capsys.readouterr().out
    assert "v6host" in out


# ---------------------------------------------------------------------------
# shared CNAME
# ---------------------------------------------------------------------------


async def test_add_shared_cname_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"_ref": "sharedrecord:cname/abc:alias/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure shared_record cname add alias canonical.example.com group my_group",
            ctx,
        )

    posts = _api_posts(requests_seen)
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "alias"
    assert body["canonical"] == "canonical.example.com"
    assert body["shared_record_group"] == "my_group"


async def test_delete_shared_cname_record():
    ref = "sharedrecord:cname/abc:alias/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=_rec_list([{"_ref": ref, "name": "alias"}]))
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure shared_record cname delete alias", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_show_shared_cname(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {
                            "_ref": "sharedrecord:cname/abc:alias/default",
                            "name": "alias",
                            "canonical": "canonical.example.com",
                        }
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show shared_record cname group my_group", ctx)

    out = capsys.readouterr().out
    assert "alias" in out


# ---------------------------------------------------------------------------
# shared MX
# ---------------------------------------------------------------------------


async def test_add_shared_mx_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"_ref": "sharedrecord:mx/abc:example.com/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure shared_record mx add example.com mail.example.com 10 group my_group",
            ctx,
        )

    posts = _api_posts(requests_seen)
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "example.com"
    assert body["mail_exchanger"] == "mail.example.com"
    assert body["preference"] == 10
    assert body["shared_record_group"] == "my_group"


async def test_delete_shared_mx_record():
    ref = "sharedrecord:mx/abc:example.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=_rec_list([{"_ref": ref, "name": "example.com"}]))
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure shared_record mx delete example.com", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_show_shared_mx(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {
                            "_ref": "sharedrecord:mx/abc:example.com/default",
                            "name": "example.com",
                            "mail_exchanger": "mail.example.com",
                            "preference": 10,
                        }
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show shared_record mx", ctx)

    out = capsys.readouterr().out
    assert "mail.example.com" in out


# ---------------------------------------------------------------------------
# shared TXT
# ---------------------------------------------------------------------------


async def test_add_shared_txt_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"_ref": "sharedrecord:txt/abc:spf/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line('configure shared_record txt add spf "v=spf1" group my_group', ctx)

    posts = _api_posts(requests_seen)
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "spf"
    assert body["text"] == "v=spf1"
    assert body["shared_record_group"] == "my_group"


async def test_delete_shared_txt_record():
    ref = "sharedrecord:txt/abc:spf/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=_rec_list([{"_ref": ref, "name": "spf"}]))
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure shared_record txt delete spf", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_show_shared_txt(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [{"_ref": "sharedrecord:txt/abc:spf/default", "name": "spf", "text": "v=spf1"}]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show shared_record txt group my_group", ctx)

    out = capsys.readouterr().out
    assert "v=spf1" in out


# ---------------------------------------------------------------------------
# shared SRV
# ---------------------------------------------------------------------------


async def test_add_shared_srv_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"_ref": "sharedrecord:srv/abc:_sip._tcp/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure shared_record srv add _sip._tcp 10 20 5060 sip.example.com group my_group",
            ctx,
        )

    posts = _api_posts(requests_seen)
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "_sip._tcp"
    assert body["priority"] == 10
    assert body["weight"] == 20
    assert body["port"] == 5060
    assert body["target"] == "sip.example.com"
    assert body["shared_record_group"] == "my_group"


async def test_delete_shared_srv_record():
    ref = "sharedrecord:srv/abc:_sip._tcp/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=_rec_list([{"_ref": ref, "name": "_sip._tcp"}]))
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure shared_record srv delete _sip._tcp", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_show_shared_srv(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {
                            "_ref": "sharedrecord:srv/abc:_sip._tcp/default",
                            "name": "_sip._tcp",
                            "priority": 10,
                            "target": "sip.example.com",
                        }
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show shared_record srv", ctx)

    out = capsys.readouterr().out
    assert "_sip._tcp" in out
