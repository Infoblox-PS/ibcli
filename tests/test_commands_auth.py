# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for auth-service configuration commands - Phase 5.

Chunks:
  A - LDAP + AD
  B - RADIUS auth service + TACACS+
  C - SAML + Certificate + LocalUser
  D - Auth policy (singleton)
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import auth  # noqa: F401 - registers handlers
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Seed the NULL root entry so the parser resolves top-level words."""
    COMMANDS.setdefault("NULL", CommandEntry(words="configure show"))


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test")


def _list(items: list[dict]) -> dict:
    """Return a paged list-response body."""
    return {"result": items}


def _path_has(request: httpx.Request, wapi_type: str) -> bool:
    """True if wapi_type appears in the request URL path.

    The SDK percent-encodes ':' as '%3A', so we check both the literal and
    encoded form.  wapi_type is the raw WAPI object type, e.g. 'radius:authservice'.
    """
    path = request.url.path
    encoded = wapi_type.replace(":", "%3A")
    return wapi_type in path or encoded in path


# WAPI type constants - match _wapi_type in the SDK resource classes.
_WAPI_LDAP = "ldap_auth_service"
_WAPI_AD = "ad_auth_service"
_WAPI_RADIUS = "radius:authservice"
_WAPI_TACACS = "tacacsplus:authservice"
_WAPI_SAML = "saml:authservice"
_WAPI_CERT = "certificate:authservice"
_WAPI_LOCALUSER = "localuser:authservice"
_WAPI_AUTHPOLICY = "authpolicy"


def _api_posts(requests_seen: list, wapi_type: str = "") -> list:
    """Filter POST requests, excluding logout."""
    return [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/logout" not in r.url.path
        and (wapi_type == "" or _path_has(r, wapi_type))
    ]


def _api_puts(requests_seen: list, wapi_type: str = "") -> list:
    """Filter PUT requests."""
    return [
        r
        for r in requests_seen
        if r.method == "PUT" and (wapi_type == "" or _path_has(r, wapi_type))
    ]


def _api_deletes(requests_seen: list, wapi_type: str = "") -> list:
    """Filter DELETE requests."""
    return [
        r
        for r in requests_seen
        if r.method == "DELETE" and (wapi_type == "" or _path_has(r, wapi_type))
    ]


# =============================================================================
# Chunk A - LDAP
# =============================================================================


class TestAuthLdapAdd:
    async def test_add_ldap_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_LDAP):
                return httpx.Response(
                    201, json={"_ref": "ldap_auth_service/ZG5z:corp", "name": "corp-ldap"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ldap add corp-ldap", ctx)

        posts = _api_posts(requests_seen, _WAPI_LDAP)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "corp-ldap"

    async def test_add_ldap_with_server_and_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_LDAP):
                return httpx.Response(
                    201, json={"_ref": "ldap_auth_service/ZG5z:corp", "name": "corp-ldap"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure auth ldap add corp-ldap server=ldap.corp.com:389 comment="corp LDAP"',
                ctx,
            )

        posts = _api_posts(requests_seen, _WAPI_LDAP)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "corp-ldap"
        assert body["servers"] == [
            {"address": "ldap.corp.com", "port": 389, "encryption": "NONE", "base_dn": ""},
        ]
        assert body["comment"] == "corp LDAP"

    async def test_add_ldap_with_timeout(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_LDAP):
                return httpx.Response(
                    201, json={"_ref": "ldap_auth_service/ZG5z:corp", "name": "corp-ldap"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ldap add corp-ldap timeout=5", ctx)

        posts = _api_posts(requests_seen, _WAPI_LDAP)
        body = json.loads(posts[0].content)
        assert body["timeout"] == 5

    async def test_add_ldap_server_default_port(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_LDAP):
                return httpx.Response(
                    201, json={"_ref": "ldap_auth_service/ZG5z:corp", "name": "corp-ldap"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ldap add corp-ldap server=ldap.corp.com", ctx)

        posts = _api_posts(requests_seen, _WAPI_LDAP)
        body = json.loads(posts[0].content)
        assert body["servers"] == [
            {"address": "ldap.corp.com", "port": 389, "encryption": "NONE", "base_dn": ""},
        ]

    async def test_add_ldap_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth ldap add corp-ldap", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_add_ldap_wapi_error(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "POST" and _path_has(request, _WAPI_LDAP):
                return httpx.Response(
                    400,
                    json={"Error": "AdmConDataError", "text": "Already exists"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ldap add corp-ldap", ctx)

        assert "Error" in capsys.readouterr().out


class TestAuthLdapDelete:
    async def test_delete_ldap_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_LDAP):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "ldap_auth_service/ZG5z:corp", "name": "corp-ldap"}]),
                )
            if request.method == "DELETE" and _path_has(request, _WAPI_LDAP):
                return httpx.Response(200, json="ldap_auth_service/ZG5z:corp")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ldap corp-ldap delete", ctx)

        deletes = _api_deletes(requests_seen, _WAPI_LDAP)
        assert len(deletes) == 1

    async def test_delete_ldap_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_LDAP):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ldap nosuchldap delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "nosuchldap" in out

    async def test_delete_ldap_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth ldap corp-ldap delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestAuthLdapSet:
    async def test_set_ldap_field(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_LDAP):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "ldap_auth_service/ZG5z:corp", "name": "corp-ldap"}]),
                )
            if request.method == "PUT" and _path_has(request, _WAPI_LDAP):
                return httpx.Response(200, json={"_ref": "ldap_auth_service/ZG5z:corp"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ldap corp-ldap set mode=ORDERED_LIST", ctx)

        puts = _api_puts(requests_seen, _WAPI_LDAP)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["mode"] == "ORDERED_LIST"

    async def test_set_ldap_no_kvs(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ldap corp-ldap set", ctx)

        out = capsys.readouterr().out
        assert "Error" in out or "required" in out.lower()


class TestAuthLdapShow:
    async def test_show_all_ldap(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_LDAP):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "ldap_auth_service/ZG5z:a", "name": "corp-ldap"},
                            {"_ref": "ldap_auth_service/ZG5z:b", "name": "dev-ldap"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth ldap", ctx)

        out = capsys.readouterr().out
        assert "corp-ldap" in out
        assert "dev-ldap" in out

    async def test_show_specific_ldap(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_LDAP):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "ldap_auth_service/ZG5z:a", "name": "corp-ldap"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth ldap corp-ldap", ctx)

        out = capsys.readouterr().out
        assert "corp-ldap" in out
        gets = [r for r in requests_seen if r.method == "GET" and _path_has(r, _WAPI_LDAP)]
        assert "name=corp-ldap" in str(gets[0].url)

    async def test_show_ldap_not_connected(self, capsys):
        ctx = Context()
        await process_line("show auth ldap", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk A - AD
# =============================================================================


class TestAuthAdAdd:
    async def test_add_ad_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_AD):
                return httpx.Response(
                    201, json={"_ref": "ad_auth_service/ZG5z:corp", "name": "corp-ad"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ad add corp-ad", ctx)

        posts = _api_posts(requests_seen, _WAPI_AD)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "corp-ad"

    async def test_add_ad_with_domain_and_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_AD):
                return httpx.Response(
                    201, json={"_ref": "ad_auth_service/ZG5z:corp", "name": "corp-ad"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure auth ad add corp-ad domain=corp.example.com comment="AD svc"',
                ctx,
            )

        posts = _api_posts(requests_seen, _WAPI_AD)
        body = json.loads(posts[0].content)
        assert body["ad_domain"] == "corp.example.com"
        assert body["comment"] == "AD svc"

    async def test_add_ad_with_domain_controllers(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_AD):
                return httpx.Response(
                    201, json={"_ref": "ad_auth_service/ZG5z:corp", "name": "corp-ad"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure auth ad add corp-ad domain=corp.example.com "
                "dc=dc1.corp.example.com dc=dc2.corp.example.com",
                ctx,
            )

        posts = _api_posts(requests_seen, _WAPI_AD)
        body = json.loads(posts[0].content)
        assert body["ad_domain"] == "corp.example.com"
        assert body["domain_controllers"] == [
            {
                "fqdn_or_ip": "dc1.corp.example.com",
                "auth_port": 389,
                "encryption": "NONE",
                "mgmt_port": False,
            },
            {
                "fqdn_or_ip": "dc2.corp.example.com",
                "auth_port": 389,
                "encryption": "NONE",
                "mgmt_port": False,
            },
        ]

    async def test_add_ad_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth ad add corp-ad", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_add_ad_wapi_error(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "POST" and _path_has(request, _WAPI_AD):
                return httpx.Response(
                    400,
                    json={"Error": "AdmConDataError", "text": "Already exists"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ad add corp-ad", ctx)

        assert "Error" in capsys.readouterr().out


class TestAuthAdDelete:
    async def test_delete_ad_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_AD):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "ad_auth_service/ZG5z:corp", "name": "corp-ad"}]),
                )
            if request.method == "DELETE" and _path_has(request, _WAPI_AD):
                return httpx.Response(200, json="ad_auth_service/ZG5z:corp")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ad corp-ad delete", ctx)

        deletes = _api_deletes(requests_seen, _WAPI_AD)
        assert len(deletes) == 1

    async def test_delete_ad_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_AD):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ad noad delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "noad" in out

    async def test_delete_ad_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth ad corp-ad delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestAuthAdSet:
    async def test_set_ad_field(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_AD):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "ad_auth_service/ZG5z:corp", "name": "corp-ad"}]),
                )
            if request.method == "PUT" and _path_has(request, _WAPI_AD):
                return httpx.Response(200, json={"_ref": "ad_auth_service/ZG5z:corp"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ad corp-ad set disabled=true", ctx)

        puts = _api_puts(requests_seen, _WAPI_AD)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["disabled"] is True


class TestAuthAdShow:
    async def test_show_all_ad(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_AD):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "ad_auth_service/ZG5z:a",
                                "name": "corp-ad",
                                "ad_domain": "corp.example.com",
                            },
                            {"_ref": "ad_auth_service/ZG5z:b", "name": "dev-ad"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth ad", ctx)

        out = capsys.readouterr().out
        assert "corp-ad" in out
        assert "dev-ad" in out
        assert "corp.example.com" in out

    async def test_show_specific_ad(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_AD):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "ad_auth_service/ZG5z:a", "name": "corp-ad"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth ad corp-ad", ctx)

        out = capsys.readouterr().out
        assert "corp-ad" in out
        gets = [r for r in requests_seen if r.method == "GET" and _path_has(r, _WAPI_AD)]
        assert "name=corp-ad" in str(gets[0].url)

    async def test_show_ad_not_connected(self, capsys):
        ctx = Context()
        await process_line("show auth ad", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk B - RADIUS auth service
# =============================================================================


class TestAuthRadiusAdd:
    async def test_add_radius_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_RADIUS):
                return httpx.Response(
                    201, json={"_ref": "radius:authservice/ZG5z:corp", "name": "corp-radius"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth radius add corp-radius", ctx)

        posts = _api_posts(requests_seen, _WAPI_RADIUS)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "corp-radius"

    async def test_add_radius_with_server(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_RADIUS):
                return httpx.Response(
                    201, json={"_ref": "radius:authservice/ZG5z:corp", "name": "corp-radius"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure auth radius add corp-radius server=radius.corp.com:1812 "
                "shared_secret=s3cret",
                ctx,
            )

        posts = _api_posts(requests_seen, _WAPI_RADIUS)
        body = json.loads(posts[0].content)
        assert body["servers"] == [
            {"address": "radius.corp.com", "shared_secret": "s3cret", "auth_port": 1812},
        ]

    async def test_add_radius_with_shared_secret(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_RADIUS):
                return httpx.Response(
                    201, json={"_ref": "radius:authservice/ZG5z:corp", "name": "corp-radius"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure auth radius add corp-radius server=radius.corp.com:1812 "
                "server=radius2.corp.com shared_secret=s3cret",
                ctx,
            )

        posts = _api_posts(requests_seen, _WAPI_RADIUS)
        body = json.loads(posts[0].content)
        assert body["servers"] == [
            {"address": "radius.corp.com", "shared_secret": "s3cret", "auth_port": 1812},
            {"address": "radius2.corp.com", "shared_secret": "s3cret", "auth_port": 1812},
        ]

    async def test_add_radius_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth radius add corp-radius", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_add_radius_wapi_error(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "POST" and _path_has(request, _WAPI_RADIUS):
                return httpx.Response(
                    400, json={"Error": "AdmConDataError", "text": "Already exists"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth radius add corp-radius", ctx)

        assert "Error" in capsys.readouterr().out


class TestAuthRadiusDelete:
    async def test_delete_radius_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_RADIUS):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "radius:authservice/ZG5z:corp", "name": "corp-radius"}]),
                )
            if request.method == "DELETE" and _path_has(request, _WAPI_RADIUS):
                return httpx.Response(200, json="radius:authservice/ZG5z:corp")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth radius corp-radius delete", ctx)

        deletes = _api_deletes(requests_seen, _WAPI_RADIUS)
        assert len(deletes) == 1

    async def test_delete_radius_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_RADIUS):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth radius noradius delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "noradius" in out

    async def test_delete_radius_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth radius corp-radius delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestAuthRadiusSet:
    async def test_set_radius_field(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_RADIUS):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "radius:authservice/ZG5z:corp", "name": "corp-radius"}]),
                )
            if request.method == "PUT" and _path_has(request, _WAPI_RADIUS):
                return httpx.Response(200, json={"_ref": "radius:authservice/ZG5z:corp"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth radius corp-radius set auth_retries=3", ctx)

        puts = _api_puts(requests_seen, _WAPI_RADIUS)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["auth_retries"] == 3


class TestAuthRadiusShow:
    async def test_show_all_radius(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_RADIUS):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "radius:authservice/ZG5z:a", "name": "corp-radius"},
                            {"_ref": "radius:authservice/ZG5z:b", "name": "dev-radius"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth radius", ctx)

        out = capsys.readouterr().out
        assert "corp-radius" in out
        assert "dev-radius" in out

    async def test_show_specific_radius(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_RADIUS):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "radius:authservice/ZG5z:a", "name": "corp-radius"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth radius corp-radius", ctx)

        out = capsys.readouterr().out
        assert "corp-radius" in out
        gets = [r for r in requests_seen if r.method == "GET" and _path_has(r, _WAPI_RADIUS)]
        assert "name=corp-radius" in str(gets[0].url)

    async def test_show_radius_not_connected(self, capsys):
        ctx = Context()
        await process_line("show auth radius", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk B - TACACS+
# =============================================================================


class TestAuthTacacsAdd:
    async def test_add_tacacs_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_TACACS):
                return httpx.Response(
                    201, json={"_ref": "tacacsplus:authservice/ZG5z:corp", "name": "corp-tacacs"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth tacacs add corp-tacacs", ctx)

        posts = _api_posts(requests_seen, _WAPI_TACACS)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "corp-tacacs"

    async def test_add_tacacs_with_server(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_TACACS):
                return httpx.Response(
                    201, json={"_ref": "tacacsplus:authservice/ZG5z:corp", "name": "corp-tacacs"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure auth tacacs add corp-tacacs server=tacacs.corp.com:49", ctx
            )

        posts = _api_posts(requests_seen, _WAPI_TACACS)
        body = json.loads(posts[0].content)
        assert body["servers"] == [{"address": "tacacs.corp.com", "port": 49}]

    async def test_add_tacacs_server_default_port(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_TACACS):
                return httpx.Response(
                    201, json={"_ref": "tacacsplus:authservice/ZG5z:corp", "name": "corp-tacacs"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth tacacs add corp-tacacs server=tacacs.corp.com", ctx)

        posts = _api_posts(requests_seen, _WAPI_TACACS)
        body = json.loads(posts[0].content)
        assert body["servers"] == [{"address": "tacacs.corp.com", "port": 49}]

    async def test_add_tacacs_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth tacacs add corp-tacacs", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_add_tacacs_wapi_error(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "POST" and _path_has(request, _WAPI_TACACS):
                return httpx.Response(
                    400, json={"Error": "AdmConDataError", "text": "Already exists"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth tacacs add corp-tacacs", ctx)

        assert "Error" in capsys.readouterr().out


class TestAuthTacacsDelete:
    async def test_delete_tacacs_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_TACACS):
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": "tacacsplus:authservice/ZG5z:corp", "name": "corp-tacacs"}]
                    ),
                )
            if request.method == "DELETE" and _path_has(request, _WAPI_TACACS):
                return httpx.Response(200, json="tacacsplus:authservice/ZG5z:corp")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth tacacs corp-tacacs delete", ctx)

        deletes = _api_deletes(requests_seen, _WAPI_TACACS)
        assert len(deletes) == 1

    async def test_delete_tacacs_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_TACACS):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth tacacs notacacs delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "notacacs" in out

    async def test_delete_tacacs_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth tacacs corp-tacacs delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestAuthTacacsSet:
    async def test_set_tacacs_field(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_TACACS):
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": "tacacsplus:authservice/ZG5z:corp", "name": "corp-tacacs"}]
                    ),
                )
            if request.method == "PUT" and _path_has(request, _WAPI_TACACS):
                return httpx.Response(200, json={"_ref": "tacacsplus:authservice/ZG5z:corp"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth tacacs corp-tacacs set auth_retries=3", ctx)

        puts = _api_puts(requests_seen, _WAPI_TACACS)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["auth_retries"] == 3


class TestAuthTacacsShow:
    async def test_show_all_tacacs(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_TACACS):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "tacacsplus:authservice/ZG5z:a", "name": "corp-tacacs"},
                            {"_ref": "tacacsplus:authservice/ZG5z:b", "name": "dev-tacacs"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth tacacs", ctx)

        out = capsys.readouterr().out
        assert "corp-tacacs" in out
        assert "dev-tacacs" in out

    async def test_show_specific_tacacs(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_TACACS):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "tacacsplus:authservice/ZG5z:a", "name": "corp-tacacs"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth tacacs corp-tacacs", ctx)

        out = capsys.readouterr().out
        assert "corp-tacacs" in out
        gets = [r for r in requests_seen if r.method == "GET" and _path_has(r, _WAPI_TACACS)]
        assert "name=corp-tacacs" in str(gets[0].url)

    async def test_show_tacacs_not_connected(self, capsys):
        ctx = Context()
        await process_line("show auth tacacs", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk C - SAML
# =============================================================================


class TestAuthSamlAdd:
    async def test_add_saml_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_SAML):
                return httpx.Response(
                    201, json={"_ref": "saml:authservice/ZG5z:corp", "name": "corp-saml"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth saml add corp-saml", ctx)

        posts = _api_posts(requests_seen, _WAPI_SAML)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "corp-saml"

    async def test_add_saml_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_SAML):
                return httpx.Response(
                    201, json={"_ref": "saml:authservice/ZG5z:corp", "name": "corp-saml"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure auth saml add corp-saml comment="corp SSO"', ctx)

        posts = _api_posts(requests_seen, _WAPI_SAML)
        body = json.loads(posts[0].content)
        assert body["comment"] == "corp SSO"

    async def test_add_saml_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth saml add corp-saml", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_add_saml_wapi_error(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "POST" and _path_has(request, _WAPI_SAML):
                return httpx.Response(
                    400, json={"Error": "AdmConDataError", "text": "Already exists"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth saml add corp-saml", ctx)

        assert "Error" in capsys.readouterr().out


class TestAuthSamlDelete:
    async def test_delete_saml_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_SAML):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "saml:authservice/ZG5z:corp", "name": "corp-saml"}]),
                )
            if request.method == "DELETE" and _path_has(request, _WAPI_SAML):
                return httpx.Response(200, json="saml:authservice/ZG5z:corp")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth saml corp-saml delete", ctx)

        deletes = _api_deletes(requests_seen, _WAPI_SAML)
        assert len(deletes) == 1

    async def test_delete_saml_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_SAML):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth saml nosaml delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "nosaml" in out

    async def test_delete_saml_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth saml corp-saml delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestAuthSamlSet:
    async def test_set_saml_field(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_SAML):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "saml:authservice/ZG5z:corp", "name": "corp-saml"}]),
                )
            if request.method == "PUT" and _path_has(request, _WAPI_SAML):
                return httpx.Response(200, json={"_ref": "saml:authservice/ZG5z:corp"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth saml corp-saml set session_timeout=3600", ctx)

        puts = _api_puts(requests_seen, _WAPI_SAML)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["session_timeout"] == 3600


class TestAuthSamlShow:
    async def test_show_all_saml(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_SAML):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "saml:authservice/ZG5z:a", "name": "corp-saml"},
                            {"_ref": "saml:authservice/ZG5z:b", "name": "dev-saml"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth saml", ctx)

        out = capsys.readouterr().out
        assert "corp-saml" in out
        assert "dev-saml" in out

    async def test_show_specific_saml(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_SAML):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "saml:authservice/ZG5z:a", "name": "corp-saml"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth saml corp-saml", ctx)

        out = capsys.readouterr().out
        assert "corp-saml" in out
        gets = [r for r in requests_seen if r.method == "GET" and _path_has(r, _WAPI_SAML)]
        assert "name=corp-saml" in str(gets[0].url)

    async def test_show_saml_not_connected(self, capsys):
        ctx = Context()
        await process_line("show auth saml", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk C - Certificate
# =============================================================================


class TestAuthCertificateAdd:
    async def test_add_certificate_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_CERT):
                return httpx.Response(
                    201,
                    json={"_ref": "certificate:authservice/ZG5z:corp", "name": "corp-cert"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth certificate add corp-cert", ctx)

        posts = _api_posts(requests_seen, _WAPI_CERT)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "corp-cert"

    async def test_add_certificate_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_CERT):
                return httpx.Response(
                    201,
                    json={"_ref": "certificate:authservice/ZG5z:corp", "name": "corp-cert"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure auth certificate add corp-cert comment="cert auth"', ctx)

        posts = _api_posts(requests_seen, _WAPI_CERT)
        body = json.loads(posts[0].content)
        assert body["comment"] == "cert auth"

    async def test_add_certificate_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth certificate add corp-cert", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_add_certificate_wapi_error(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "POST" and _path_has(request, _WAPI_CERT):
                return httpx.Response(
                    400, json={"Error": "AdmConDataError", "text": "Already exists"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth certificate add corp-cert", ctx)

        assert "Error" in capsys.readouterr().out


class TestAuthCertificateDelete:
    async def test_delete_certificate_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_CERT):
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": "certificate:authservice/ZG5z:corp", "name": "corp-cert"}]
                    ),
                )
            if request.method == "DELETE" and _path_has(request, _WAPI_CERT):
                return httpx.Response(200, json="certificate:authservice/ZG5z:corp")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth certificate corp-cert delete", ctx)

        deletes = _api_deletes(requests_seen, _WAPI_CERT)
        assert len(deletes) == 1

    async def test_delete_certificate_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_CERT):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth certificate nocert delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "nocert" in out

    async def test_delete_certificate_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth certificate corp-cert delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestAuthCertificateSet:
    async def test_set_certificate_field(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_CERT):
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": "certificate:authservice/ZG5z:corp", "name": "corp-cert"}]
                    ),
                )
            if request.method == "PUT" and _path_has(request, _WAPI_CERT):
                return httpx.Response(200, json={"_ref": "certificate:authservice/ZG5z:corp"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure auth certificate corp-cert set auto_populate_login=S_DN_CN", ctx
            )

        puts = _api_puts(requests_seen, _WAPI_CERT)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["auto_populate_login"] == "S_DN_CN"


class TestAuthCertificateShow:
    async def test_show_all_certificate(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_CERT):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "certificate:authservice/ZG5z:a", "name": "corp-cert"},
                            {"_ref": "certificate:authservice/ZG5z:b", "name": "dev-cert"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth certificate", ctx)

        out = capsys.readouterr().out
        assert "corp-cert" in out
        assert "dev-cert" in out

    async def test_show_specific_certificate(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_CERT):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "certificate:authservice/ZG5z:a", "name": "corp-cert"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth certificate corp-cert", ctx)

        out = capsys.readouterr().out
        assert "corp-cert" in out
        gets = [r for r in requests_seen if r.method == "GET" and _path_has(r, _WAPI_CERT)]
        assert "name=corp-cert" in str(gets[0].url)

    async def test_show_certificate_not_connected(self, capsys):
        ctx = Context()
        await process_line("show auth certificate", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk C - LocalUser (read-only singleton)
# =============================================================================


class TestAuthLocaluser:
    async def test_show_localuser(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_LOCALUSER):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "localuser:authservice/ZG5z:local",
                                "name": "Local User AuthService",
                                "disabled": False,
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth localuser", ctx)

        out = capsys.readouterr().out
        # Should print name, disabled=False
        assert "Local User AuthService" in out or "disabled" in out

    async def test_show_localuser_not_connected(self, capsys):
        ctx = Context()
        await process_line("show auth localuser", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_configure_localuser_prints_hint(self, capsys):
        """configure auth localuser should print an informational message (no WAPI call)."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth localuser", ctx)

        out = capsys.readouterr().out
        assert "read-only" in out.lower() or "singleton" in out.lower() or "show" in out.lower()
        # No WAPI mutation calls should have been issued
        assert not any(r.method in ("POST", "PUT", "DELETE") for r in requests_seen)


# =============================================================================
# Chunk D - Auth policy (singleton)
# =============================================================================


class TestAuthPolicy:
    async def test_show_auth_policy(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_AUTHPOLICY):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "authpolicy/ZG5z:singleton",
                                "auth_services": ["localuser:authservice/ZG5z:local"],
                                "default_group": "admin",
                                "usage_type": "FULL",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth policy", ctx)

        out = capsys.readouterr().out
        assert "auth_services" in out or "admin" in out or "FULL" in out

    async def test_show_auth_policy_not_connected(self, capsys):
        ctx = Context()
        await process_line("show auth policy", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_set_auth_policy_default_group(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_AUTHPOLICY):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "authpolicy/ZG5z:singleton"}]),
                )
            if request.method == "PUT" and _path_has(request, _WAPI_AUTHPOLICY):
                return httpx.Response(200, json={"_ref": "authpolicy/ZG5z:singleton"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth policy set default_group=admin", ctx)

        puts = _api_puts(requests_seen, _WAPI_AUTHPOLICY)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["default_group"] == "admin"

    async def test_set_auth_policy_usage_type(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_AUTHPOLICY):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "authpolicy/ZG5z:singleton"}]),
                )
            if request.method == "PUT" and _path_has(request, _WAPI_AUTHPOLICY):
                return httpx.Response(200, json={"_ref": "authpolicy/ZG5z:singleton"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth policy set usage_type=AUTH_ONLY", ctx)

        puts = _api_puts(requests_seen, _WAPI_AUTHPOLICY)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["usage_type"] == "AUTH_ONLY"

    async def test_set_auth_policy_no_kvs(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth policy set", ctx)

        out = capsys.readouterr().out
        assert "Error" in out or "required" in out.lower()

    async def test_set_auth_policy_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth policy set default_group=admin", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_set_auth_policy_no_object_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_AUTHPOLICY):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth policy set default_group=admin", ctx)

        out = capsys.readouterr().out
        assert "Error" in out or "no" in out.lower()
