# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for grid management slices 5a, 5b, 5c.

Slices:
  5a - members (add/delete/modify/dns/dhcp) + show grid dns/dhcp
  5b - nsgroups, views, shared record groups
  5c - service restart, scheduled tasks
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import grid  # noqa: F401 - registers handlers
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Seed the NULL root entry and show grid chain so the parser resolves top-level words.

    system.py and server.py (not yet converted) normally provide these.
    Register the minimal subset needed for grid commands so the parser resolves
    configure, show, and restart correctly.
    """
    from ibcli.registry import _merge_words  # type: ignore[attr-defined]

    COMMANDS.setdefault("NULL", CommandEntry(words="configure show restart"))
    # server.py normally registers "show grid" with words including "<name>".
    # Merge "<name>" in case the key already exists (set by another module).
    show_grid = COMMANDS.setdefault("show grid", CommandEntry(words="<cr> <name>"))
    show_grid.words = _merge_words(show_grid.words or "", "<name>")


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


def _list(items: list[dict]) -> dict:
    """Return a paged list-response body."""
    return {"result": items}


def _api_posts(requests_seen: list, path_fragment: str = "") -> list:
    """Filter POST requests, excluding the SDK's logout call."""
    return [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/logout" not in r.url.path
        and (path_fragment == "" or path_fragment in r.url.path)
    ]


def _api_puts(requests_seen: list, path_fragment: str = "") -> list:
    """Filter PUT requests."""
    return [
        r
        for r in requests_seen
        if r.method == "PUT" and (path_fragment == "" or path_fragment in r.url.path)
    ]


def _api_deletes(requests_seen: list, path_fragment: str = "") -> list:
    """Filter DELETE requests."""
    return [
        r
        for r in requests_seen
        if r.method == "DELETE" and (path_fragment == "" or path_fragment in r.url.path)
    ]


def _api_gets(requests_seen: list, path_fragment: str = "") -> list:
    """Filter GET requests, excluding schema probes."""
    return [
        r
        for r in requests_seen
        if r.method == "GET"
        and "_schema" not in str(r.url.query)
        and (path_fragment == "" or path_fragment in r.url.path)
    ]


# ===========================================================================
# Slice 5a - Member Add
# ===========================================================================


class TestMemberAdd:
    async def test_add_member_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/member" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    201, json={"_ref": "member/ZG5z:ns1", "host_name": "ns1.lab.com"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member add ns1.lab.com"
                " ipaddress 192.168.1.10/24 gateway 192.168.1.1",
                ctx,
            )

        posts = _api_posts(requests_seen, "/member")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["host_name"] == "ns1.lab.com"
        vip = body["vip_setting"]
        assert vip["address"] == "192.168.1.10"
        assert vip["subnet_mask"] == "255.255.255.0"
        assert vip["gateway"] == "192.168.1.1"

    async def test_add_member_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/member" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    201, json={"_ref": "member/ZG5z:ns1", "host_name": "ns1.lab.com"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member add ns1.lab.com"
                ' ipaddress 192.168.1.10/24 gateway 192.168.1.1 comment "my member"',
                ctx,
            )

        posts = _api_posts(requests_seen, "/member")
        body = json.loads(posts[0].content)
        assert body["comment"] == "my member"

    async def test_add_member_no_name(self, capsys):
        async with connected_ctx() as ctx:
            await process_line("configure grid Infoblox member add", ctx)
        out = capsys.readouterr().out
        assert "error" in out.lower() or "required" in out.lower() or "name" in out.lower()

    async def test_add_member_wapi_error(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if (
                request.method == "POST"
                and "/member" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    400,
                    json={"Error": "X", "code": "Y", "text": "Member exists"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member add ns1.lab.com"
                " ipaddress 192.168.1.10/24 gateway 192.168.1.1",
                ctx,
            )
        assert "Error" in capsys.readouterr().out

    async def test_add_member_not_connected(self, capsys):
        ctx = Context()
        await process_line(
            "configure grid Infoblox member add ns1.lab.com"
            " ipaddress 192.168.1.10/24 gateway 192.168.1.1",
            ctx,
        )
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5a - Member Add: Pre-Provisioning
# ===========================================================================


class TestMemberAddPreProvisioning:
    async def test_add_member_with_preprovisioning(self):
        """POST then PUT; POST body has only basic fields; PUT body has both top-level
        platform and pre_provisioning.hardware_info[0].hwtype as separate values."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/member" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    201, json={"_ref": "member/ZG5z:dns1", "host_name": "dns1.example.com"}
                )
            if request.method == "PUT" and "/member/ZG5z:dns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member/ZG5z:dns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member add dns1.example.com"
                " ipaddress 10.0.0.5/24 gateway 10.0.0.1"
                " platform VNIOS hwtype IB-V4126 model IB-V1425 serial abc123"
                " license vnios license enterprise",
                ctx,
            )

        member_posts = _api_posts(requests_seen, "/member")
        put_reqs = _api_puts(requests_seen, "/member")

        assert len(member_posts) == 1, "expected exactly one POST to /member"
        assert len(put_reqs) == 1, "expected exactly one PUT"

        # POST body has only basic fields - no pre_provisioning, platform, or enable_ha
        create_data = json.loads(member_posts[0].content)
        assert create_data["host_name"] == "dns1.example.com"
        assert "pre_provisioning" not in create_data
        assert "platform" not in create_data
        assert "enable_ha" not in create_data
        vip = create_data["vip_setting"]
        assert vip["address"] == "10.0.0.5"
        assert vip["subnet_mask"] == "255.255.255.0"
        assert vip["gateway"] == "10.0.0.1"

        # PUT body has top-level platform (broad category enum)
        put_data = json.loads(put_reqs[0].content)
        assert put_data.get("platform") == "VNIOS", "top-level platform must be VNIOS"

        # PUT body has pre_provisioning with hwtype (hardware SKU enum) separate from platform
        pp = put_data.get("pre_provisioning")
        assert pp is not None, "pre_provisioning key missing from PUT body"
        hw = pp.get("hardware_info", [])
        assert len(hw) == 1
        assert hw[0]["hwtype"] == "IB-V4126", (
            "hwtype must be the hardware SKU, not the platform category"
        )
        assert hw[0]["hwmodel"] == "IB-V1425"
        assert hw[0]["serial_number"] == "abc123"
        assert set(pp.get("licenses", [])) == {"vnios", "enterprise"}

    async def test_add_member_ha_pair(self):
        """POST then PUT; PUT includes enable_ha=True and 2-entry hardware_info."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/member" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    201, json={"_ref": "member/ZG5z:dns1", "host_name": "dns1.example.com"}
                )
            if request.method == "PUT" and "/member/ZG5z:dns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member/ZG5z:dns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member add dns1.example.com"
                " ipaddress 10.0.0.5/24"
                " platform VNIOS hwtype IB-V4126 model X serial primary"
                " node IB-V4126,X,secondary"
                " license dns",
                ctx,
            )

        member_posts = _api_posts(requests_seen, "/member")
        put_reqs = _api_puts(requests_seen, "/member")

        assert len(member_posts) == 1, "expected one POST to /member"
        assert len(put_reqs) == 1, "expected one PUT"

        # POST body must not have enable_ha or pre_provisioning
        create_data = json.loads(member_posts[0].content)
        assert "enable_ha" not in create_data
        assert "pre_provisioning" not in create_data

        put_data = json.loads(put_reqs[0].content)
        assert put_data.get("platform") == "VNIOS"
        pp = put_data.get("pre_provisioning")
        assert pp is not None
        hw = pp.get("hardware_info", [])
        assert len(hw) == 2
        serials = {e["serial_number"] for e in hw}
        assert serials == {"primary", "secondary"}
        assert all(e["hwtype"] == "IB-V4126" for e in hw)
        assert pp.get("licenses") == ["dns"]
        assert put_data.get("enable_ha") is True

    async def test_add_member_no_preprovisioning_still_works(self):
        """No preprovision keywords → single POST to /member only, no PUT."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/member" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    201, json={"_ref": "member/ZG5z:ns1", "host_name": "ns1.lab.com"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member add ns1.lab.com"
                " ipaddress 192.168.1.10/24 gateway 192.168.1.1",
                ctx,
            )

        post_body = json.loads(_api_posts(requests_seen, "/member")[0].content)
        assert post_body["host_name"] == "ns1.lab.com"
        assert "pre_provisioning" not in post_body
        assert len(_api_puts(requests_seen, "/member")) == 0, (
            "no PUT should be issued without preprovision keywords"
        )

    async def test_add_member_platform_only_uses_put(self):
        """platform keyword alone triggers POST + PUT path."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/member" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    201, json={"_ref": "member/ZG5z:dns1", "host_name": "dns1.example.com"}
                )
            if request.method == "PUT" and "/member/ZG5z:dns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member/ZG5z:dns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member add dns1.example.com"
                " ipaddress 10.0.0.5/24 platform VNIOS",
                ctx,
            )

        member_posts = _api_posts(requests_seen, "/member")
        put_reqs = _api_puts(requests_seen, "/member")

        assert len(member_posts) == 1, "platform alone must trigger POST to /member"
        assert len(put_reqs) == 1, "platform alone must trigger PUT"

        # POST body has basic fields only
        assert "platform" not in json.loads(member_posts[0].content)

        # PUT body has verbatim platform value; no pre_provisioning since no hwtype given
        put_data = json.loads(put_reqs[0].content)
        assert put_data.get("platform") == "VNIOS"
        assert "pre_provisioning" not in put_data

    async def test_add_member_platform_only_no_hwtype(self):
        """platform VNIOS but no hwtype → PUT body has platform, NO pre_provisioning."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/member" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    201, json={"_ref": "member/ZG5z:dns1", "host_name": "dns1.example.com"}
                )
            if request.method == "PUT" and "/member/ZG5z:dns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member/ZG5z:dns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member add dns1.example.com"
                " ipaddress 10.0.0.5/24 platform VNIOS",
                ctx,
            )

        put_reqs = _api_puts(requests_seen, "/member")
        assert len(put_reqs) == 1
        put_data = json.loads(put_reqs[0].content)
        assert put_data.get("platform") == "VNIOS"
        assert "pre_provisioning" not in put_data, (
            "pre_provisioning must not be set when no hwtype/model/serial/license/node given"
        )

    async def test_add_member_hwtype_only_no_platform(self):
        """hwtype but no platform → PUT body has pre_provisioning, NO top-level platform."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/member" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    201, json={"_ref": "member/ZG5z:dns1", "host_name": "dns1.example.com"}
                )
            if request.method == "PUT" and "/member/ZG5z:dns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member/ZG5z:dns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member add dns1.example.com"
                " ipaddress 10.0.0.5/24 hwtype IB-V4126",
                ctx,
            )

        put_reqs = _api_puts(requests_seen, "/member")
        assert len(put_reqs) == 1
        put_data = json.loads(put_reqs[0].content)
        assert "platform" not in put_data, "top-level platform must not be set when not specified"
        pp = put_data.get("pre_provisioning")
        assert pp is not None, "pre_provisioning must be set when hwtype is given"
        hw = pp.get("hardware_info", [])
        assert len(hw) == 1
        assert hw[0]["hwtype"] == "IB-V4126"

    async def test_add_member_preprovisioning_failure_rolls_back(self, capsys):
        """POST succeeds, PUT fails → DELETE called; shows Pre-provisioning failed + Rolled back."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/member" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    201, json={"_ref": "member/ZG5z:dns1", "host_name": "dns1.example.com"}
                )
            if request.method == "PUT" and "/member/ZG5z:dns1" in request.url.path:
                return httpx.Response(
                    400,
                    json={"Error": "X", "code": "Y", "text": "Invalid value for licenses"},
                )
            if request.method == "DELETE" and "/member/ZG5z:dns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member/ZG5z:dns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member add dns1.example.com"
                " ipaddress 10.0.0.5/24 gateway 10.0.0.1"
                " platform VNIOS hwtype IB-V4126 model IB-V1425 serial abc123"
                " license enterprise",
                ctx,
            )

        out = capsys.readouterr().out
        assert "Added member dns1.example.com" in out
        assert "Pre-provisioning failed:" in out
        assert "Rolled back: deleted dns1.example.com" in out
        # Confirm DELETE was actually called
        delete_reqs = _api_deletes(requests_seen, "/member")
        assert len(delete_reqs) == 1

    async def test_add_member_preprovisioning_failure_rollback_fails(self, capsys):
        """POST succeeds, PUT fails, DELETE also fails → WARNING + manual-delete hint shown."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/member" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    201, json={"_ref": "member/ZG5z:dns1", "host_name": "dns1.example.com"}
                )
            if request.method == "PUT" and "/member/ZG5z:dns1" in request.url.path:
                return httpx.Response(
                    400,
                    json={"Error": "X", "code": "Y", "text": "Invalid value for licenses"},
                )
            if request.method == "DELETE" and "/member/ZG5z:dns1" in request.url.path:
                return httpx.Response(
                    500,
                    json={"Error": "X", "code": "Y", "text": "Internal error"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member add dns1.example.com"
                " ipaddress 10.0.0.5/24"
                " platform VNIOS hwtype IB-V4126 model IB-V1425 serial abc123"
                " license enterprise",
                ctx,
            )

        out = capsys.readouterr().out
        assert "Pre-provisioning failed:" in out
        assert "WARNING: rollback also failed" in out
        assert "dns1.example.com" in out

    async def test_add_member_handles_dict_ref_response(self):
        """POST returns a dict {"_ref": "..."} - PUT goes to correct URL."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/member" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    201,
                    json={"_ref": "member/abc:test/default", "host_name": "test.example.com"},
                )
            if request.method == "PUT" and "/member/abc:test/default" in request.url.path:
                return httpx.Response(200, json={"_ref": "member/abc:test/default"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member add test.example.com"
                " ipaddress 10.0.0.5/24 platform VNIOS",
                ctx,
            )

        put_reqs = _api_puts(requests_seen)
        assert len(put_reqs) == 1
        assert "/member/abc:test/default" in put_reqs[0].url.path

    async def test_add_member_empty_ref_skips_preprovision(self, capsys):
        """POST returns no _ref → skip PUT, print the unprovisioned warning."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/member" in request.url.path
                and "/logout" not in request.url.path
            ):
                # Return a response with no _ref
                return httpx.Response(201, json={})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member add test.example.com"
                " ipaddress 10.0.0.5/24 platform VNIOS",
                ctx,
            )

        out = capsys.readouterr().out
        assert "Added member test.example.com" in out
        assert (
            "no ref" in out.lower()
            or "unprovisioned" in out.lower()
            or "cannot pre-provision" in out.lower()
        )
        assert len(_api_puts(requests_seen)) == 0, "PUT should not be issued when ref is empty"


# ===========================================================================
# Slice 5a - Member Preprovision (existing member)
# ===========================================================================


class TestMemberPreprovision:
    async def test_preprovision_existing_member(self):
        """configure grid g member m preprovision → GET then PUT with pre_provisioning."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "GET"
                and "/member" in request.url.path
                and "member:" not in request.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "member/ZG5z:ns1", "host_name": "ns1.lab.com"}]),
                )
            if request.method == "PUT" and "/member/ZG5z:ns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member/ZG5z:ns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member ns1.lab.com preprovision"
                " platform VNIOS hwtype IB-V4126 model IB-V1425 serial xyz789 license dns",
                ctx,
            )

        put_reqs = _api_puts(requests_seen, "/member")
        assert len(put_reqs) == 1
        body = json.loads(put_reqs[0].content)
        assert body.get("platform") == "VNIOS"
        pp = body.get("pre_provisioning")
        assert pp is not None
        hw = pp.get("hardware_info", [])
        assert len(hw) == 1
        assert hw[0]["hwtype"] == "IB-V4126"
        assert hw[0]["serial_number"] == "xyz789"
        assert "dns" in pp.get("licenses", [])

    async def test_preprovision_ha_pair_sets_enable_ha(self):
        """Preprovisioning with 2 hardware entries sets enable_ha in PUT body."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "GET"
                and "/member" in request.url.path
                and "member:" not in request.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "member/ZG5z:ns1", "host_name": "ns1.lab.com"}]),
                )
            if request.method == "PUT" and "/member/ZG5z:ns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member/ZG5z:ns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member ns1.lab.com preprovision"
                " platform VNIOS hwtype IB-V4126 model IB-V1425 serial primary-sn"
                " node IB-V4126,IB-V1425,secondary-sn"
                " license vnios license dns",
                ctx,
            )

        put_reqs = _api_puts(requests_seen, "/member")
        assert len(put_reqs) == 1
        body = json.loads(put_reqs[0].content)
        assert body.get("platform") == "VNIOS"
        assert body.get("enable_ha") is True
        pp = body.get("pre_provisioning")
        assert pp is not None
        hw = pp.get("hardware_info", [])
        assert len(hw) == 2
        serials = {e["serial_number"] for e in hw}
        assert serials == {"primary-sn", "secondary-sn"}
        assert all(e["hwtype"] == "IB-V4126" for e in hw)
        assert set(pp.get("licenses", [])) == {"vnios", "dns"}

    async def test_preprovision_member_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if (
                request.method == "GET"
                and "/member" in request.url.path
                and "member:" not in request.url.path
            ):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member nobody.lab.com preprovision"
                " hwtype IB-V4126 model IB-V1425 serial x",
                ctx,
            )

        out = capsys.readouterr().out
        assert "No" in out or "not found" in out.lower()

    async def test_preprovision_no_keywords(self, capsys):
        """preprovision without any keywords → error, no PUT."""
        async with connected_ctx() as ctx:
            await process_line(
                "configure grid Infoblox member ns1.lab.com preprovision",
                ctx,
            )

        out = capsys.readouterr().out
        assert "Error" in out or "error" in out.lower()

    async def test_preprovision_not_connected(self, capsys):
        ctx = Context()
        await process_line(
            "configure grid Infoblox member ns1.lab.com preprovision"
            " hwtype IB-V4126 model IB-V1425 serial x",
            ctx,
        )
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5a - Member Delete
# ===========================================================================


class TestMemberDelete:
    async def test_delete_member_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "GET"
                and "/member" in request.url.path
                and "member:" not in request.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "member/ZG5z:ns1", "host_name": "ns1.lab.com"}]),
                )
            if request.method == "DELETE" and "/member/ZG5z:ns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member/ZG5z:ns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid Infoblox member ns1.lab.com delete", ctx)

        deletes = _api_deletes(requests_seen, "/member")
        assert len(deletes) == 1

    async def test_delete_member_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if (
                request.method == "GET"
                and "/member" in request.url.path
                and "member:" not in request.url.path
            ):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid Infoblox member nobody.lab.com delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "not found" in out.lower() or "nobody" in out

    async def test_delete_member_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid Infoblox member ns1.lab.com delete", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5a - Member Modify
# ===========================================================================


class TestMemberModify:
    async def test_modify_member_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "GET"
                and "/member" in request.url.path
                and "member:" not in request.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "member/ZG5z:ns1", "host_name": "ns1.lab.com"}]),
                )
            if request.method == "PUT" and "/member/ZG5z:ns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member/ZG5z:ns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure grid Infoblox member ns1.lab.com modify comment "updated"',
                ctx,
            )

        put_reqs = _api_puts(requests_seen, "/member")
        assert len(put_reqs) == 1
        body = json.loads(put_reqs[0].content)
        assert body["comment"] == "updated"

    async def test_modify_member_gateway(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "GET"
                and "/member" in request.url.path
                and "member:" not in request.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "member/ZG5z:ns1", "host_name": "ns1.lab.com"}]),
                )
            if request.method == "PUT" and "/member/ZG5z:ns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member/ZG5z:ns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member ns1.lab.com modify gateway 10.0.0.1",
                ctx,
            )

        body = json.loads(_api_puts(requests_seen, "/member")[0].content)
        assert body.get("vip_setting", {}).get("gateway") == "10.0.0.1"

    async def test_modify_member_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if (
                request.method == "GET"
                and "/member" in request.url.path
                and "member:" not in request.url.path
            ):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member nobody.lab.com modify comment x", ctx
            )

        out = capsys.readouterr().out
        assert "No" in out or "not found" in out.lower() or "nobody" in out

    async def test_modify_member_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid Infoblox member ns1.lab.com modify comment x", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5a - Member DNS
# ===========================================================================


class TestMemberDns:
    async def test_member_dns_enable(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "member:dns" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "member:dns/ZG5z:ns1", "host_name": "ns1.lab.com"}]),
                )
            if request.method == "PUT" and "member:dns/ZG5z:ns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member:dns/ZG5z:ns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid Infoblox member ns1.lab.com dns enable", ctx)

        put_reqs = _api_puts(requests_seen)
        assert len(put_reqs) == 1
        assert json.loads(put_reqs[0].content).get("enable_dns") is True

    async def test_member_dns_disable(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "member:dns" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "member:dns/ZG5z:ns1", "host_name": "ns1.lab.com"}]),
                )
            if request.method == "PUT" and "member:dns/ZG5z:ns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member:dns/ZG5z:ns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid Infoblox member ns1.lab.com dns disable", ctx)

        body = json.loads(_api_puts(requests_seen)[0].content)
        assert body.get("enable_dns") is False

    async def test_member_dns_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "member:dns" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid Infoblox member nobody.lab.com dns enable", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "not found" in out.lower() or "nobody" in out

    async def test_member_dns_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid Infoblox member ns1.lab.com dns enable", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5a - Member DHCP
# ===========================================================================


class TestMemberDhcp:
    async def test_member_dhcp_enable(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "member:dhcpproperties" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": "member:dhcpproperties/ZG5z:ns1", "host_name": "ns1.lab.com"}]
                    ),
                )
            if request.method == "PUT" and "member:dhcpproperties/ZG5z:ns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member:dhcpproperties/ZG5z:ns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid Infoblox member ns1.lab.com dhcp enable", ctx)

        put_reqs = _api_puts(requests_seen)
        assert len(put_reqs) == 1
        assert json.loads(put_reqs[0].content).get("enable_dhcp") is True

    async def test_member_dhcp_disable(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "member:dhcpproperties" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": "member:dhcpproperties/ZG5z:ns1", "host_name": "ns1.lab.com"}]
                    ),
                )
            if request.method == "PUT" and "member:dhcpproperties/ZG5z:ns1" in request.url.path:
                return httpx.Response(200, json={"_ref": "member:dhcpproperties/ZG5z:ns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid Infoblox member ns1.lab.com dhcp disable", ctx)

        body = json.loads(_api_puts(requests_seen)[0].content)
        assert body.get("enable_dhcp") is False

    async def test_member_dhcp_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid Infoblox member ns1.lab.com dhcp enable", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5a - Show Member
# ===========================================================================


class TestShowMember:
    async def test_show_all_members(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if (
                request.method == "GET"
                and "/member" in request.url.path
                and "member:" not in request.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "member/ZG5z:ns1",
                                "host_name": "ns1.lab.com",
                                "vip_setting": {"address": "1.2.3.4"},
                            },
                            {
                                "_ref": "member/ZG5z:ns2",
                                "host_name": "ns2.lab.com",
                                "vip_setting": {"address": "1.2.3.5"},
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox member", ctx)

        out = capsys.readouterr().out
        assert "ns1.lab.com" in out
        assert "ns2.lab.com" in out

    async def test_show_specific_member(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "GET"
                and "/member" in request.url.path
                and "member:" not in request.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "member/ZG5z:ns1",
                                "host_name": "ns1.lab.com",
                                "vip_setting": {"address": "1.2.3.4"},
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox member ns1.lab.com", ctx)

        out = capsys.readouterr().out
        assert "ns1.lab.com" in out
        get_reqs = _api_gets(requests_seen, "/member")
        assert any("ns1.lab.com" in str(r.url) for r in get_reqs)

    async def test_show_member_not_connected(self, capsys):
        ctx = Context()
        await process_line("show grid Infoblox member", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_show_member_shortcut_lists_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if (
                request.method == "GET"
                and "/member" in request.url.path
                and "member:" not in request.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "member/ZG5z:ns1",
                                "host_name": "ns1.lab.com",
                                "vip_setting": {"address": "1.2.3.4"},
                            },
                            {
                                "_ref": "member/ZG5z:ns2",
                                "host_name": "ns2.lab.com",
                                "vip_setting": {"address": "1.2.3.5"},
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show member", ctx)

        out = capsys.readouterr().out
        assert "ns1.lab.com" in out
        assert "ns2.lab.com" in out

    async def test_show_member_shortcut_by_name(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "GET"
                and "/member" in request.url.path
                and "member:" not in request.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "member/ZG5z:ns1",
                                "host_name": "ns1.lab.com",
                                "vip_setting": {"address": "1.2.3.4"},
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show member ns1.lab.com", ctx)

        out = capsys.readouterr().out
        assert "ns1.lab.com" in out
        get_reqs = _api_gets(requests_seen, "/member")
        assert any("ns1.lab.com" in str(r.url) for r in get_reqs)

    async def test_show_member_prints_preprovisioning(self, capsys):
        """GET returns member with pre_provisioning → output includes hardware and licenses."""

        def handler(request: httpx.Request) -> httpx.Response | None:
            if (
                request.method == "GET"
                and "/member" in request.url.path
                and "member:" not in request.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "member/ZG5z:ns1",
                                "host_name": "ns1.lab.com",
                                "vip_setting": {"address": "10.0.0.5"},
                                "pre_provisioning": {
                                    "hardware_info": [
                                        {
                                            "hwtype": "IB-VNIOS",
                                            "hwmodel": "IB-V1425",
                                            "serial_number": "abc123",
                                        },
                                        {
                                            "hwtype": "IB-VNIOS",
                                            "hwmodel": "IB-V1425",
                                            "serial_number": "secondary-sn",
                                        },
                                    ],
                                    "licenses": ["vnios", "enterprise", "dns", "dhcp"],
                                },
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox member ns1.lab.com", ctx)

        out = capsys.readouterr().out
        assert "pre_provisioning" in out
        assert "IB-VNIOS" in out
        assert "abc123" in out
        assert "secondary-sn" in out
        assert "vnios" in out
        assert "enterprise" in out


# ===========================================================================
# Slice 5a - Show Member DNS
# ===========================================================================


class TestShowMemberDns:
    async def test_show_member_dns(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "member:dns" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "member:dns/ZG5z:ns1",
                                "host_name": "ns1.lab.com",
                                "enable_dns": True,
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox member ns1.lab.com dns", ctx)

        out = capsys.readouterr().out
        assert "ns1.lab.com" in out or "enable_dns" in out

    async def test_show_member_dns_not_connected(self, capsys):
        ctx = Context()
        await process_line("show grid Infoblox member ns1.lab.com dns", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5a - Show Grid DNS
# ===========================================================================


class TestShowGridDns:
    async def test_show_grid_dns(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "grid:dns" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "grid:dns/ZG5z:Infoblox",
                                "allow_recursive_query": True,
                                "default_ttl": 900,
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox dns", ctx)

        out = capsys.readouterr().out
        assert out.strip()  # some output produced

    async def test_show_grid_dns_not_connected(self, capsys):
        ctx = Context()
        await process_line("show grid Infoblox dns", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5a - Show Grid DHCP
# ===========================================================================


class TestShowGridDhcp:
    async def test_show_grid_dhcp(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "grid:dhcp" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "grid:dhcp/ZG5z:Infoblox",
                                "lease_time": 3600,
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox dhcp", ctx)

        out = capsys.readouterr().out
        assert out.strip()

    async def test_show_grid_dhcp_not_connected(self, capsys):
        ctx = Context()
        await process_line("show grid Infoblox dhcp", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5b - NSGroup Add
# ===========================================================================


class TestNsgroupAdd:
    async def test_add_nsgroup_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/nsgroup" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(201, json={"_ref": "nsgroup/ZG5z:ns1", "name": "mygroup"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure nsgroup add mygroup primary ns1.lab.com", ctx)

        posts = _api_posts(requests_seen, "/nsgroup")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "mygroup"
        assert body["grid_primary"][0]["name"] == "ns1.lab.com"

    async def test_add_nsgroup_with_secondaries(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/nsgroup" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(201, json={"_ref": "nsgroup/ZG5z:ns1", "name": "mygroup"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure nsgroup add mygroup primary ns1.lab.com"
                " secondary ns2.lab.com secondary ns3.lab.com",
                ctx,
            )

        body = json.loads(_api_posts(requests_seen, "/nsgroup")[0].content)
        names = [s["name"] for s in body.get("grid_secondaries", [])]
        assert "ns2.lab.com" in names
        assert "ns3.lab.com" in names

    async def test_add_nsgroup_no_name(self, capsys):
        async with connected_ctx() as ctx:
            await process_line("configure nsgroup add", ctx)
        out = capsys.readouterr().out
        assert "error" in out.lower() or "name" in out.lower() or "required" in out.lower()

    async def test_add_nsgroup_wapi_error(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if (
                request.method == "POST"
                and "/nsgroup" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    400,
                    json={"Error": "X", "code": "Y", "text": "Group exists"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure nsgroup add mygroup primary ns1.lab.com", ctx)

        assert "Error" in capsys.readouterr().out

    async def test_add_nsgroup_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure nsgroup add mygroup primary ns1.lab.com", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5b - NSGroup Delete
# ===========================================================================


class TestNsgroupDelete:
    async def test_delete_nsgroup_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/nsgroup" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "nsgroup/ZG5z:mygroup", "name": "mygroup"}]),
                )
            if request.method == "DELETE" and "/nsgroup/ZG5z:mygroup" in request.url.path:
                return httpx.Response(200, json={"_ref": "nsgroup/ZG5z:mygroup"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure nsgroup mygroup delete", ctx)

        assert len(_api_deletes(requests_seen, "/nsgroup")) == 1

    async def test_delete_nsgroup_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/nsgroup" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure nsgroup nogroup delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "not found" in out.lower() or "nogroup" in out

    async def test_delete_nsgroup_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure nsgroup mygroup delete", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5b - NSGroup Modify
# ===========================================================================


class TestNsgroupModify:
    async def test_modify_nsgroup_primary(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/nsgroup" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "nsgroup/ZG5z:mygroup", "name": "mygroup"}]),
                )
            if request.method == "PUT" and "/nsgroup/ZG5z:mygroup" in request.url.path:
                return httpx.Response(200, json={"_ref": "nsgroup/ZG5z:mygroup"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure nsgroup mygroup modify primary ns1.lab.com", ctx)

        put_reqs = _api_puts(requests_seen, "/nsgroup")
        assert len(put_reqs) == 1
        body = json.loads(put_reqs[0].content)
        assert body["grid_primary"] == [{"name": "ns1.lab.com"}]

    async def test_modify_nsgroup_secondaries(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/nsgroup" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "nsgroup/ZG5z:mygroup", "name": "mygroup"}]),
                )
            if request.method == "PUT" and "/nsgroup/ZG5z:mygroup" in request.url.path:
                return httpx.Response(200, json={"_ref": "nsgroup/ZG5z:mygroup"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure nsgroup mygroup modify secondary ns2.lab.com secondary ns3.lab.com",
                ctx,
            )

        put_reqs = _api_puts(requests_seen, "/nsgroup")
        assert len(put_reqs) == 1
        body = json.loads(put_reqs[0].content)
        assert body["grid_secondaries"] == [
            {"name": "ns2.lab.com"},
            {"name": "ns3.lab.com"},
        ]

    async def test_modify_nsgroup_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/nsgroup" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure nsgroup nogroup modify primary ns1.lab.com", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "not found" in out.lower()

    async def test_modify_nsgroup_no_fields(self, capsys):
        async with connected_ctx() as ctx:
            await process_line("configure nsgroup mygroup modify", ctx)

        out = capsys.readouterr().out
        assert "Error" in out or "error" in out.lower()

    async def test_modify_nsgroup_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure nsgroup mygroup modify primary ns1.lab.com", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5b - Show NSGroup
# ===========================================================================


class TestShowNsgroup:
    async def test_show_all_nsgroups(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/nsgroup" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "nsgroup/ZG5z:g1", "name": "group1"},
                            {"_ref": "nsgroup/ZG5z:g2", "name": "group2"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show zone ns_group", ctx)

        out = capsys.readouterr().out
        assert "group1" in out
        assert "group2" in out

    async def test_show_specific_nsgroup(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/nsgroup" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "nsgroup/ZG5z:g1", "name": "group1"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show zone ns_group group1", ctx)

        out = capsys.readouterr().out
        assert "group1" in out
        get_reqs = _api_gets(requests_seen, "/nsgroup")
        assert any("group1" in str(r.url) for r in get_reqs)

    async def test_show_nsgroup_not_connected(self, capsys):
        ctx = Context()
        await process_line("show zone ns_group", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5b - View Add
# ===========================================================================


class TestViewAdd:
    async def test_add_view_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/view" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(201, json={"_ref": "view/ZG5z:internal", "name": "internal"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure view add internal", ctx)

        posts = _api_posts(requests_seen, "/view")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "internal"

    async def test_add_view_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/view" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(201, json={"_ref": "view/ZG5z:internal", "name": "internal"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure view add internal comment "my view"', ctx)

        body = json.loads(_api_posts(requests_seen, "/view")[0].content)
        assert body["comment"] == "my view"

    async def test_add_view_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure view add internal", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5b - View Delete
# ===========================================================================


class TestViewDelete:
    async def test_delete_view_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/view" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "view/ZG5z:internal", "name": "internal"}]),
                )
            if request.method == "DELETE" and "/view/ZG5z:internal" in request.url.path:
                return httpx.Response(200, json={"_ref": "view/ZG5z:internal"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure view internal delete", ctx)

        assert len(_api_deletes(requests_seen, "/view")) == 1

    async def test_delete_view_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/view" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure view noview delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "not found" in out.lower() or "noview" in out

    async def test_delete_view_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure view internal delete", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5b - Shared Record Group Add
# ===========================================================================


class TestSharedRecordGroupAdd:
    async def test_add_srg_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/sharedrecordgroup" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    201, json={"_ref": "sharedrecordgroup/ZG5z:sg1", "name": "mygroup"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure shared_record_group add mygroup", ctx)

        posts = _api_posts(requests_seen, "/sharedrecordgroup")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "mygroup"

    async def test_add_srg_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/sharedrecordgroup" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    201, json={"_ref": "sharedrecordgroup/ZG5z:sg1", "name": "mygroup"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure shared_record_group add mygroup comment "my group"', ctx)

        body = json.loads(_api_posts(requests_seen, "/sharedrecordgroup")[0].content)
        assert body["comment"] == "my group"

    async def test_add_srg_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure shared_record_group add mygroup", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5b - Shared Record Group Delete
# ===========================================================================


class TestSharedRecordGroupDelete:
    async def test_delete_srg_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/sharedrecordgroup" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "sharedrecordgroup/ZG5z:sg1", "name": "mygroup"}]),
                )
            if request.method == "DELETE" and "/sharedrecordgroup/ZG5z:sg1" in request.url.path:
                return httpx.Response(200, json={"_ref": "sharedrecordgroup/ZG5z:sg1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure shared_record_group mygroup delete", ctx)

        assert len(_api_deletes(requests_seen, "/sharedrecordgroup")) == 1

    async def test_delete_srg_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/sharedrecordgroup" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure shared_record_group nogroup delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "not found" in out.lower() or "nogroup" in out

    async def test_delete_srg_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure shared_record_group mygroup delete", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5b - Show Shared Record Group
# ===========================================================================


class TestShowSharedRecordGroup:
    async def test_show_all_srgs(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/sharedrecordgroup" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "sharedrecordgroup/ZG5z:sg1", "name": "group1"},
                            {"_ref": "sharedrecordgroup/ZG5z:sg2", "name": "group2"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show zone shared_record_group", ctx)

        out = capsys.readouterr().out
        assert "group1" in out
        assert "group2" in out

    async def test_show_specific_srg(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/sharedrecordgroup" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "sharedrecordgroup/ZG5z:sg1", "name": "group1"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show zone shared_record_group group1", ctx)

        out = capsys.readouterr().out
        assert "group1" in out
        get_reqs = _api_gets(requests_seen, "/sharedrecordgroup")
        assert any("group1" in str(r.url) for r in get_reqs)

    async def test_show_srg_not_connected(self, capsys):
        ctx = Context()
        await process_line("show zone shared_record_group", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5c - Restart DNS / DHCP
# ===========================================================================


class TestRestart:
    async def test_restart_dns(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and request.url.path.endswith("/grid"):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "grid/ZG5z:Infoblox", "name": "Infoblox"}]),
                )
            if (
                request.method == "POST"
                and "grid/ZG5z:Infoblox" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(200, json={"result": "started"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("restart dns", ctx)

        posts = _api_posts(requests_seen)
        assert any("restartservices" in str(r.url) for r in posts)
        body = json.loads(posts[0].content)
        assert "DNS" in body.get("services", [])

    async def test_restart_dhcp(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and request.url.path.endswith("/grid"):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "grid/ZG5z:Infoblox", "name": "Infoblox"}]),
                )
            if (
                request.method == "POST"
                and "grid/ZG5z:Infoblox" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(200, json={"result": "started"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("restart dhcp", ctx)

        posts = _api_posts(requests_seen)
        body = json.loads(posts[0].content)
        assert "DHCP" in body.get("services", [])

    async def test_restart_dns_with_delay(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and request.url.path.endswith("/grid"):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "grid/ZG5z:Infoblox", "name": "Infoblox"}]),
                )
            if (
                request.method == "POST"
                and "grid/ZG5z:Infoblox" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(200, json={"result": "started"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("restart dns delay 30", ctx)

        posts = _api_posts(requests_seen)
        body = json.loads(posts[0].content)
        assert body.get("delay") == 30

    async def test_restart_grid_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and request.url.path.endswith("/grid"):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("restart dns", ctx)

        out = capsys.readouterr().out
        assert "Error" in out or "error" in out.lower() or "not found" in out.lower()

    async def test_restart_not_connected(self, capsys):
        ctx = Context()
        await process_line("restart dns", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_restart_dns_with_mode(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and request.url.path.endswith("/grid"):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "grid/ZG5z:Infoblox", "name": "Infoblox"}]),
                )
            if (
                request.method == "POST"
                and "grid/ZG5z:Infoblox" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(200, json={"result": "ok"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("restart dns mode SEQUENTIAL", ctx)

        posts = _api_posts(requests_seen)
        body = json.loads(posts[0].content)
        assert body.get("mode") == "SEQUENTIAL"
        assert "DNS" in body.get("services", [])

    async def test_restart_dhcp_with_option_and_members(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and request.url.path.endswith("/grid"):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "grid/ZG5z:Infoblox", "name": "Infoblox"}]),
                )
            if (
                request.method == "POST"
                and "grid/ZG5z:Infoblox" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(200, json={"result": "ok"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "restart dhcp option FORCE_RESTART member ns1.lab.com member ns2.lab.com",
                ctx,
            )

        posts = _api_posts(requests_seen)
        body = json.loads(posts[0].content)
        assert body.get("restart_option") == "FORCE_RESTART"
        assert "ns1.lab.com" in body.get("members", [])
        assert "ns2.lab.com" in body.get("members", [])
        assert "DHCP" in body.get("services", [])

    async def test_restart_dhcpv4(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and request.url.path.endswith("/grid"):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "grid/ZG5z:Infoblox", "name": "Infoblox"}]),
                )
            if (
                request.method == "POST"
                and "grid/ZG5z:Infoblox" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(200, json={"result": "ok"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("restart dhcpv4", ctx)

        body = json.loads(_api_posts(requests_seen)[0].content)
        assert "DHCPV4" in body.get("services", [])

    async def test_restart_dhcpv6(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and request.url.path.endswith("/grid"):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "grid/ZG5z:Infoblox", "name": "Infoblox"}]),
                )
            if (
                request.method == "POST"
                and "grid/ZG5z:Infoblox" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(200, json={"result": "ok"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("restart dhcpv6", ctx)

        body = json.loads(_api_posts(requests_seen)[0].content)
        assert "DHCPV6" in body.get("services", [])

    async def test_restart_all(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and request.url.path.endswith("/grid"):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "grid/ZG5z:Infoblox", "name": "Infoblox"}]),
                )
            if (
                request.method == "POST"
                and "grid/ZG5z:Infoblox" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(200, json={"result": "ok"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("restart all mode GROUPED option RESTART_IF_NEEDED", ctx)

        body = json.loads(_api_posts(requests_seen)[0].content)
        assert "ALL" in body.get("services", [])
        assert body.get("mode") == "GROUPED"
        assert body.get("restart_option") == "RESTART_IF_NEEDED"

    async def test_restart_invalid_mode(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and request.url.path.endswith("/grid"):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "grid/ZG5z:Infoblox", "name": "Infoblox"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("restart dns mode BADMODE", ctx)

        out = capsys.readouterr().out
        assert "Error" in out


# ===========================================================================
# Slice 5c - Restart Discovery (stub)
# ===========================================================================


class TestRestartDiscovery:
    # NIOS 9.1 forbids create on `discoverytask` and the SDK refuses it
    # before the request is built. These assert the request the CLI
    # *would* send, so enforcement is off here.
    async def test_restart_discovery_posts_discoverytask(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "/discoverytask" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    201,
                    json={"_ref": "discoverytask/ZG5z:dt1"},
                )
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("restart discovery", ctx)

        posts = _api_posts(requests_seen, "/discoverytask")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body.get("action") == "START"

    async def test_restart_discovery_not_connected(self, capsys):
        ctx = Context()
        await process_line("restart discovery", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_restart_discovery_wapi_error(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if (
                request.method == "POST"
                and "/discoverytask" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(
                    400,
                    json={"Error": "X", "code": "Y", "text": "Discovery unavailable"},
                )
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("restart discovery", ctx)

        assert "Error" in capsys.readouterr().out


# ===========================================================================
# Slice 5c - Show Schedule
# ===========================================================================


class TestShowSchedule:
    async def test_show_schedule(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/scheduledtask" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "scheduledtask/ZG5z:1",
                                "task_id": 1,
                                "submitter": "admin",
                                "task_type": "OBJECT_CHANGE",
                                "execution_status": "PENDING",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show schedule", ctx)

        out = capsys.readouterr().out
        assert "admin" in out or "1" in out

    async def test_show_schedule_not_connected(self, capsys):
        ctx = Context()
        await process_line("show schedule", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 5c - Delete Schedule
# ===========================================================================


class TestDeleteSchedule:
    async def test_delete_schedule_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/scheduledtask" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "scheduledtask/ZG5z:1", "task_id": 42}]),
                )
            if request.method == "DELETE" and "/scheduledtask/ZG5z:1" in request.url.path:
                return httpx.Response(200, json={"_ref": "scheduledtask/ZG5z:1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure schedule 42 delete", ctx)

        assert len(_api_deletes(requests_seen, "/scheduledtask")) == 1

    async def test_delete_schedule_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/scheduledtask" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure schedule 999 delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "not found" in out.lower() or "999" in out

    async def test_delete_schedule_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure schedule 42 delete", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Gap 5 - restart status / show restart
# ===========================================================================


class TestRestartStatus:
    """Tests for restart status [refresh] and show restart."""

    _status_data = [
        {
            "member": "ns1.lab.com",
            "dns_status": "RESTARTED",
            "dhcp_status": "NEEDS_RESTART",
            "reporting_status": "NO_REQUEST",
        },
    ]

    async def test_restart_status_without_refresh(self, capsys):
        """restart status (no refresh) - only GETs restartservicestatus."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "restartservicestatus" in request.url.path:
                return httpx.Response(200, json=_list(self._status_data))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("restart status", ctx)

        out = capsys.readouterr().out
        assert "dns_status=RESTARTED" in out
        # No POST should have been issued
        posts = _api_posts(requests_seen)
        assert not posts, "Unexpected POST when refresh not requested"

    async def test_restart_status_with_refresh(self, capsys):
        """restart status refresh - POSTs requestrestartservicestatus then GETs."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and request.url.path.endswith("/grid"):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "grid/ZG5z:Infoblox", "name": "Infoblox"}]),
                )
            if (
                request.method == "POST"
                and "grid/ZG5z:Infoblox" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(200, json={})
            if request.method == "GET" and "restartservicestatus" in request.url.path:
                return httpx.Response(200, json=_list(self._status_data))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("restart status refresh", ctx)

        out = capsys.readouterr().out
        assert "dns_status=RESTARTED" in out
        # Verify refresh POST was sent
        posts = _api_posts(requests_seen)
        assert posts, "Expected POST for refresh"
        assert "requestrestartservicestatus" in str(posts[0].url)
        body = json.loads(posts[0].content)
        assert body.get("service_option") == "ALL"

    async def test_restart_status_not_connected(self, capsys):
        ctx = Context()
        await process_line("restart status", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_show_restart(self, capsys):
        """show restart - alias for restart status (no refresh)."""

        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "restartservicestatus" in request.url.path:
                return httpx.Response(200, json=_list(self._status_data))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show restart", ctx)

        out = capsys.readouterr().out
        assert "dns_status=RESTARTED" in out
        assert "member=ns1.lab.com" in out

    async def test_show_restart_not_connected(self, capsys):
        ctx = Context()
        await process_line("show restart", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Phase 4 - Chunk A: member dhcp/dns set, member license
# ===========================================================================


class TestMemberDhcpSet:
    """Tests for configure grid <name> member <name> dhcp set <kv>."""

    async def test_dhcp_set_sends_put(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "member:dhcpproperties" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": "member:dhcpproperties/ZG5z:dhcp1", "host_name": "ns1.lab.com"}]
                    ),
                )
            if request.method == "PUT" and "member:dhcpproperties" in request.url.path:
                return httpx.Response(200, json={"_ref": "member:dhcpproperties/ZG5z:dhcp1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member ns1.lab.com dhcp set domain_name=lab.com lease_time=86400",
                ctx,
            )

        puts = _api_puts(requests_seen, "member:dhcpproperties")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["domain_name"] == "lab.com"
        assert body["lease_time"] == 86400

    async def test_dhcp_set_bool_coercion(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "member:dhcpproperties" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "member:dhcpproperties/ZG5z:dhcp1"}])
                )
            if request.method == "PUT":
                return httpx.Response(200, json={})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member ns1.lab.com dhcp set authority=true",
                ctx,
            )

        puts = _api_puts(requests_seen, "member:dhcpproperties")
        body = json.loads(puts[0].content)
        assert body["authority"] is True

    async def test_dhcp_set_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid Infoblox member ns1.lab.com dhcp set foo=bar", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_dhcp_set_no_kvs(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "member:dhcpproperties" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "member:dhcpproperties/ZG5z:dhcp1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid Infoblox member ns1.lab.com dhcp set", ctx)
        out = capsys.readouterr().out
        assert "error" in out.lower()


class TestMemberDnsSet:
    """Tests for configure grid <name> member <name> dns set <kv>."""

    async def test_dns_set_sends_put(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "member:dns" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "member:dns/ZG5z:dns1", "host_name": "ns1.lab.com"}])
                )
            if request.method == "PUT" and "member:dns" in request.url.path:
                return httpx.Response(200, json={"_ref": "member:dns/ZG5z:dns1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member ns1.lab.com dns set default_ttl=3600 dnssec_enabled=false",
                ctx,
            )

        puts = _api_puts(requests_seen, "member:dns")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["default_ttl"] == 3600
        assert body["dnssec_enabled"] is False

    async def test_dns_set_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid Infoblox member ns1.lab.com dns set foo=bar", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_dns_set_member_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "member:dns" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member missing.lab.com dns set foo=bar", ctx
            )
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "no member" in out.lower()


class TestMemberLicense:
    # NIOS 9.1 forbids create on `member:license` and the SDK refuses it
    # before the request is built. These assert the request the CLI
    # *would* send, so enforcement is off here.
    """Tests for show/add/remove member license."""

    async def test_show_member_license(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "member:license" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "member:license/ZG5z:lic1",
                                "type": "DNS",
                                "kind": "Static",
                                "hwid": "abc",
                            },
                            {
                                "_ref": "member:license/ZG5z:lic2",
                                "type": "DHCP",
                                "kind": "Static",
                                "hwid": "abc",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("show grid Infoblox member ns1.lab.com license", ctx)

        out = capsys.readouterr().out
        assert "DNS" in out
        assert "DHCP" in out

    async def test_add_member_license(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if (
                request.method == "POST"
                and "member:license" in request.url.path
                and "/logout" not in request.url.path
            ):
                return httpx.Response(201, json={"_ref": "member:license/ZG5z:new"})
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line(
                "configure grid Infoblox member ns1.lab.com license add DNS",
                ctx,
            )

        posts = _api_posts(requests_seen, "member:license")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["type"] == "DNS"
        assert body["host_name"] == "ns1.lab.com"

    async def test_remove_member_license(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "member:license" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "member:license/ZG5z:lic1", "type": "DNS"},
                        ]
                    ),
                )
            if request.method == "DELETE" and "member:license" in request.url.path:
                return httpx.Response(200, json="member:license/ZG5z:lic1")
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line(
                "configure grid Infoblox member ns1.lab.com license remove DNS",
                ctx,
            )

        deletes = _api_deletes(requests_seen, "member:license")
        assert len(deletes) == 1

    async def test_remove_member_license_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "member:license" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line(
                "configure grid Infoblox member ns1.lab.com license remove DNS",
                ctx,
            )
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "no license" in out.lower()

    async def test_add_member_license_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid Infoblox member ns1.lab.com license add DNS", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Phase 4 - Chunk B: member threat-insight / threat-protection / file-distribution
# ===========================================================================


class TestMemberThreatInsight:
    """Tests for show and set member threat_insight."""

    async def test_show_member_threat_insight(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "member:threatinsight" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "member:threatinsight/ZG5z:ti1",
                                "host_name": "ns1.lab.com",
                                "enable_service": True,
                                "status": "ACTIVE",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox member ns1.lab.com threat_insight", ctx)

        out = capsys.readouterr().out
        assert "ns1.lab.com" in out
        assert "enable_service=True" in out

    async def test_set_member_threat_insight(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "member:threatinsight" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": "member:threatinsight/ZG5z:ti1"}]))
            if request.method == "PUT":
                return httpx.Response(200, json={})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member ns1.lab.com threat_insight set enable_service=true",
                ctx,
            )

        puts = _api_puts(requests_seen, "member:threatinsight")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["enable_service"] is True

    async def test_set_member_threat_insight_not_connected(self, capsys):
        ctx = Context()
        await process_line(
            "configure grid Infoblox member ns1.lab.com threat_insight set enable_service=true", ctx
        )
        assert "Not connected" in capsys.readouterr().out


class TestMemberThreatProtection:
    """Tests for show and set member threat_protection."""

    async def test_show_member_threat_protection(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "member:threatprotection" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "member:threatprotection/ZG5z:tp1",
                                "host_name": "ns1.lab.com",
                                "enable_service": False,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox member ns1.lab.com threat_protection", ctx)

        out = capsys.readouterr().out
        assert "ns1.lab.com" in out

    async def test_set_member_threat_protection(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "member:threatprotection" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "member:threatprotection/ZG5z:tp1"}])
                )
            if request.method == "PUT":
                return httpx.Response(200, json={})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member ns1.lab.com threat_protection set enable_service=false",
                ctx,
            )

        puts = _api_puts(requests_seen, "member:threatprotection")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["enable_service"] is False

    async def test_set_member_threat_protection_not_connected(self, capsys):
        ctx = Context()
        await process_line(
            "configure grid Infoblox member ns1.lab.com threat_protection set enable_service=true",
            ctx,
        )
        assert "Not connected" in capsys.readouterr().out


class TestMemberFileDistribution:
    """Tests for show and set member file_distribution."""

    async def test_show_member_file_distribution(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "member:filedistribution" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "member:filedistribution/ZG5z:fd1",
                                "host_name": "ns1.lab.com",
                                "status": "RUNNING",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox member ns1.lab.com file_distribution", ctx)

        out = capsys.readouterr().out
        assert "ns1.lab.com" in out
        assert "RUNNING" in out

    async def test_set_member_file_distribution(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "member:filedistribution" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "member:filedistribution/ZG5z:fd1"}])
                )
            if request.method == "PUT":
                return httpx.Response(200, json={})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member ns1.lab.com file_distribution set comment=myfd",
                ctx,
            )

        puts = _api_puts(requests_seen, "member:filedistribution")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["comment"] == "myfd"

    async def test_set_member_file_distribution_not_connected(self, capsys):
        ctx = Context()
        await process_line(
            "configure grid Infoblox member ns1.lab.com file_distribution set comment=x", ctx
        )
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Phase 4 - Chunk C: grid-level dns/dhcp/threat-insight/threat-protection/
#            file-distribution set
# ===========================================================================


class TestGridDnsSet:
    """Tests for configure grid <name> dns set <kv>."""

    async def test_grid_dns_set_sends_put(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "grid:dns" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": "grid:dns/ZG5z:dns"}]))
            if request.method == "PUT" and "grid:dns" in request.url.path:
                return httpx.Response(200, json={})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid Infoblox dns set default_ttl=300", ctx)

        puts = _api_puts(requests_seen, "grid:dns")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["default_ttl"] == 300

    async def test_grid_dns_set_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid Infoblox dns set default_ttl=300", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_grid_dns_set_no_kvs(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "grid:dns" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": "grid:dns/ZG5z:dns"}]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid Infoblox dns set", ctx)
        out = capsys.readouterr().out
        assert "error" in out.lower()


class TestGridDhcpSet:
    """Tests for configure grid <name> dhcp set <kv>."""

    async def test_grid_dhcp_set_sends_put(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "grid:dhcpproperties" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": "grid:dhcpproperties/ZG5z:dhcp"}]))
            if request.method == "PUT" and "grid:dhcpproperties" in request.url.path:
                return httpx.Response(200, json={})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox dhcp set lease_time=3600 authority=true", ctx
            )

        puts = _api_puts(requests_seen, "grid:dhcpproperties")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["lease_time"] == 3600
        assert body["authority"] is True

    async def test_grid_dhcp_set_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid Infoblox dhcp set lease_time=3600", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestGridThreatInsight:
    """Tests for show and set grid threat_insight."""

    async def test_show_grid_threat_insight(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "grid:threatinsight" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "grid:threatinsight/ZG5z:ti", "name": "Infoblox"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox threat_insight", ctx)

        out = capsys.readouterr().out
        assert "Infoblox" in out

    async def test_set_grid_threat_insight(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "grid:threatinsight" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": "grid:threatinsight/ZG5z:ti"}]))
            if request.method == "PUT":
                return httpx.Response(200, json={})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox threat_insight set enable_auto_download=true", ctx
            )

        puts = _api_puts(requests_seen, "grid:threatinsight")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["enable_auto_download"] is True

    async def test_set_grid_threat_insight_not_connected(self, capsys):
        ctx = Context()
        await process_line(
            "configure grid Infoblox threat_insight set enable_auto_download=true", ctx
        )
        assert "Not connected" in capsys.readouterr().out


class TestGridThreatProtection:
    """Tests for show and set grid threat_protection."""

    async def test_show_grid_threat_protection(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "grid:threatprotection" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "grid:threatprotection/ZG5z:tp",
                                "current_ruleset": "ruleset-1",
                                "disable_multiple_dns_tcp_request": False,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox threat_protection", ctx)

        out = capsys.readouterr().out
        assert "ruleset-1" in out

    async def test_set_grid_threat_protection(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "grid:threatprotection" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": "grid:threatprotection/ZG5z:tp"}]))
            if request.method == "PUT":
                return httpx.Response(200, json={})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox threat_protection set disable_multiple_dns_tcp_request=true",
                ctx,
            )

        puts = _api_puts(requests_seen, "grid:threatprotection")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["disable_multiple_dns_tcp_request"] is True

    async def test_set_grid_threat_protection_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid Infoblox threat_protection set foo=bar", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestGridFileDistribution:
    """Tests for show and set grid file_distribution."""

    async def test_show_grid_file_distribution(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "grid:filedistribution" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "grid:filedistribution/ZG5z:fd", "name": "Infoblox"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox file_distribution", ctx)

        out = capsys.readouterr().out
        assert "Infoblox" in out

    async def test_set_grid_file_distribution(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "grid:filedistribution" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": "grid:filedistribution/ZG5z:fd"}]))
            if request.method == "PUT":
                return httpx.Response(200, json={})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox file_distribution set allow_uploads=true",
                ctx,
            )

        puts = _api_puts(requests_seen, "grid:filedistribution")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["allow_uploads"] is True

    async def test_set_grid_file_distribution_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid Infoblox file_distribution set allow_uploads=true", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Phase 4 - Chunk D: grid license pool + x509 cert + service-restart show
# ===========================================================================


class TestGridLicensePool:
    """Tests for show grid <name> license_pool."""

    async def test_show_grid_license_pool(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "grid:license_pool_container" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "grid:license_pool_container/ZG5z:lpc",
                                "lpc_uid": "uid-1234",
                                "last_entitlement_update": 1700000000,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox license_pool", ctx)

        out = capsys.readouterr().out
        assert "uid-1234" in out
        assert "1700000000" in out

    async def test_show_grid_license_pool_not_connected(self, capsys):
        ctx = Context()
        await process_line("show grid Infoblox license_pool", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestGridCertificate:
    # NIOS 9.1 forbids delete on `grid:x509certificate` and the SDK refuses it
    # before the request is built. These assert the request the CLI
    # *would* send, so enforcement is off here.
    """Tests for show and delete grid certificate."""

    async def test_show_grid_certificate(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "grid:x509certificate" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "grid:x509certificate/ZG5z:cert1",
                                "serial": "AABBCC",
                                "subject": "CN=grid.lab.com",
                                "issuer": "CN=lab-ca",
                                "valid_not_after": 9999999999,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("show grid Infoblox certificate", ctx)

        out = capsys.readouterr().out
        assert "AABBCC" in out
        assert "CN=grid.lab.com" in out

    async def test_delete_grid_certificate(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "grid:x509certificate" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "grid:x509certificate/ZG5z:cert1", "serial": "AABBCC"},
                        ]
                    ),
                )
            if request.method == "DELETE" and "grid:x509certificate" in request.url.path:
                return httpx.Response(200, json="grid:x509certificate/ZG5z:cert1")
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure grid Infoblox certificate delete AABBCC", ctx)

        deletes = _api_deletes(requests_seen, "grid:x509certificate")
        assert len(deletes) == 1

    async def test_delete_grid_certificate_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "grid:x509certificate" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure grid Infoblox certificate delete DEADBEEF", ctx)
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "no certificate" in out.lower()

    async def test_show_grid_certificate_not_connected(self, capsys):
        ctx = Context()
        await process_line("show grid Infoblox certificate", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestGridServiceRestartObservability:
    """Tests for show grid <name> restart status/group/request."""

    async def test_show_grid_restart_status(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "grid:servicerestart:status" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "grid:servicerestart:status/ZG5z:s1",
                                "parent": "grid/ZG5z:Infoblox",
                                "pending": 2,
                                "success": 5,
                                "failures": 0,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox restart status", ctx)

        out = capsys.readouterr().out
        assert "pending=2" in out
        assert "success=5" in out

    async def test_show_grid_restart_group(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "grid:servicerestart:group" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "grid:servicerestart:group/ZG5z:g1",
                                "name": "default",
                                "service": "DNS",
                                "mode": "SEQUENTIAL",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox restart group", ctx)

        out = capsys.readouterr().out
        assert "default" in out
        assert "DNS" in out
        assert "SEQUENTIAL" in out

    async def test_show_grid_restart_request(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "grid:servicerestart:request" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "grid:servicerestart:request/ZG5z:r1",
                                "member": "ns1.lab.com",
                                "service": "DNS",
                                "state": "QUEUED",
                                "result": None,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox restart request", ctx)

        out = capsys.readouterr().out
        assert "ns1.lab.com" in out
        assert "DNS" in out
        assert "QUEUED" in out

    async def test_show_grid_restart_status_not_connected(self, capsys):
        ctx = Context()
        await process_line("show grid Infoblox restart status", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_show_grid_restart_group_not_connected(self, capsys):
        ctx = Context()
        await process_line("show grid Infoblox restart group", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_show_grid_restart_request_not_connected(self, capsys):
        ctx = Context()
        await process_line("show grid Infoblox restart request", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Phase 4 - Coercion helper tests
# ===========================================================================


class TestCoerceValue:
    """Unit tests for the _coerce_value helper."""

    def test_true_coercion(self):
        from ibcli.commands.grid import _coerce_value

        assert _coerce_value("true") is True
        assert _coerce_value("True") is True
        assert _coerce_value("TRUE") is True

    def test_false_coercion(self):
        from ibcli.commands.grid import _coerce_value

        assert _coerce_value("false") is False
        assert _coerce_value("False") is False

    def test_int_coercion(self):
        from ibcli.commands.grid import _coerce_value

        assert _coerce_value("300") == 300
        assert isinstance(_coerce_value("300"), int)

    def test_string_passthrough(self):
        from ibcli.commands.grid import _coerce_value

        assert _coerce_value("lab.com") == "lab.com"
        assert _coerce_value("SEQUENTIAL") == "SEQUENTIAL"


# ===========================================================================
# Dual-stack member add - IPv6 VIP, MGMT v4+v6, anycast
# ===========================================================================


class TestDualStackMemberAdd:
    async def test_ipv6_only_member_sets_config_addr_type_ipv6(self):
        posts: list[httpx.Request] = []

        def handler(request):
            if request.method == "POST" and "/member" in request.url.path:
                posts.append(request)
                return httpx.Response(201, json="member/a:m1.example.com")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Migration member add m1.example.com "
                "ipv6addr=2001:db8::10/64 ipv6gateway=2001:db8::1 "
                "platform=VNIOS",
                ctx,
            )
        body = json.loads(posts[0].content)
        assert body["config_addr_type"] == "IPV6"
        assert body["ipv6_setting"]["virtual_ip"] == "2001:db8::10"
        assert body["ipv6_setting"]["gateway"] == "2001:db8::1"

    async def test_dual_stack_sets_config_addr_type_both(self):
        posts: list[httpx.Request] = []

        def handler(request):
            if request.method == "POST" and "/member" in request.url.path:
                posts.append(request)
                return httpx.Response(201, json="member/a:m1.example.com")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Migration member add m1.example.com "
                "ipaddress=10.0.0.10/24 gateway=10.0.0.1 "
                "ipv6addr=2001:db8::10/64 ipv6gateway=2001:db8::1",
                ctx,
            )
        body = json.loads(posts[0].content)
        assert body["config_addr_type"] == "BOTH"

    async def test_mgmt_v4_and_v6_land_on_node_info(self):
        posts: list[httpx.Request] = []

        def handler(request):
            if request.method == "POST" and "/member" in request.url.path:
                posts.append(request)
                return httpx.Response(201, json="member/a:m1.example.com")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Migration member add m1.example.com "
                "ipaddress=10.0.0.10/24 gateway=10.0.0.1 "
                "mgmt_ipaddress=10.65.0.10/24 mgmt_gateway=10.65.0.1 "
                "mgmt_ipv6addr=2001:db8:65::10/64 mgmt_ipv6gateway=2001:db8:65::1",
                ctx,
            )
        body = json.loads(posts[0].content)
        assert body["mgmt_port_setting"]["enabled"] is True
        node = body["node_info"][0]
        assert node["mgmt_network_setting"]["address"] == "10.65.0.10"
        assert node["mgmt_network_setting"]["gateway"] == "10.65.0.1"
        assert node["v6_mgmt_network_setting"]["virtual_ip"] == "2001:db8:65::10"

    async def test_member_add_warns_no_gateway(self, capsys):
        def handler(request):
            if request.method == "POST" and "/member" in request.url.path:
                return httpx.Response(201, json="member/a:m1")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Migration member add m1.example.com "
                "ipaddress=10.0.0.10/24 platform=VNIOS",
                ctx,
            )
        assert "Warning: no gateway" in capsys.readouterr().out


# ===========================================================================
# Anycast add/delete
# ===========================================================================


class TestMemberAnycast:
    async def test_anycast_add_ipv4(self):
        ref = "member/a:m1.example.com"
        puts: list[httpx.Request] = []

        def handler(request):
            if request.method == "GET" and "/member" in request.url.path:
                return httpx.Response(
                    200,
                    json={
                        "result": [
                            {"_ref": ref, "host_name": "m1.example.com", "additional_ip_list": []}
                        ]
                    },
                )
            if request.method == "PUT" and ref in request.url.path:
                puts.append(request)
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Migration member m1.example.com anycast add 192.0.2.53",
                ctx,
            )
        body = json.loads(puts[0].content)
        entry = body["additional_ip_list"][0]
        assert entry["interface"] == "LOOPBACK"
        assert entry["anycast"] is True
        assert entry["ipv4_network_setting"]["address"] == "192.0.2.53"
        assert entry["ipv4_network_setting"]["subnet_mask"] == "255.255.255.255"

    async def test_anycast_add_ipv6(self):
        ref = "member/a:m1.example.com"
        puts: list[httpx.Request] = []

        def handler(request):
            if request.method == "GET" and "/member" in request.url.path:
                return httpx.Response(
                    200, json={"result": [{"_ref": ref, "additional_ip_list": []}]}
                )
            if request.method == "PUT" and ref in request.url.path:
                puts.append(request)
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Migration member m1.example.com anycast add 2001:db8::53",
                ctx,
            )
        body = json.loads(puts[0].content)
        entry = body["additional_ip_list"][0]
        assert entry["ipv6_network_setting"]["virtual_ip"] == "2001:db8::53"
        assert entry["ipv6_network_setting"]["cidr_prefix"] == 128

    async def test_anycast_add_explicit_prefix(self):
        ref = "member/a:m1.example.com"
        puts: list[httpx.Request] = []

        def handler(request):
            if request.method == "GET" and "/member" in request.url.path:
                return httpx.Response(
                    200, json={"result": [{"_ref": ref, "additional_ip_list": []}]}
                )
            if request.method == "PUT" and ref in request.url.path:
                puts.append(request)
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Migration member m1.example.com anycast add 192.0.2.0/30",
                ctx,
            )
        body = json.loads(puts[0].content)
        assert (
            body["additional_ip_list"][0]["ipv4_network_setting"]["subnet_mask"]
            == "255.255.255.252"
        )

    async def test_anycast_duplicate_skipped(self, capsys):
        ref = "member/a:m1.example.com"

        def handler(request):
            if request.method == "GET" and "/member" in request.url.path:
                return httpx.Response(
                    200,
                    json={
                        "result": [
                            {
                                "_ref": ref,
                                "additional_ip_list": [
                                    {
                                        "interface": "LOOPBACK",
                                        "anycast": True,
                                        "ipv4_network_setting": {
                                            "address": "192.0.2.53",
                                            "subnet_mask": "255.255.255.255",
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Migration member m1.example.com anycast add 192.0.2.53",
                ctx,
            )
        assert "Skipped: anycast 192.0.2.53 already" in capsys.readouterr().out

    async def test_anycast_delete(self):
        ref = "member/a:m1.example.com"
        puts: list[httpx.Request] = []

        def handler(request):
            if request.method == "GET" and "/member" in request.url.path:
                return httpx.Response(
                    200,
                    json={
                        "result": [
                            {
                                "_ref": ref,
                                "additional_ip_list": [
                                    {
                                        "interface": "LOOPBACK",
                                        "anycast": True,
                                        "ipv4_network_setting": {
                                            "address": "192.0.2.53",
                                            "subnet_mask": "255.255.255.255",
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                )
            if request.method == "PUT" and ref in request.url.path:
                puts.append(request)
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Migration member m1.example.com anycast delete 192.0.2.53",
                ctx,
            )
        body = json.loads(puts[0].content)
        assert body["additional_ip_list"] == []

    async def test_anycast_delete_not_present(self, capsys):
        ref = "member/a:m1.example.com"

        def handler(request):
            if request.method == "GET" and "/member" in request.url.path:
                return httpx.Response(
                    200, json={"result": [{"_ref": ref, "additional_ip_list": []}]}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Migration member m1.example.com anycast delete 192.0.2.53",
                ctx,
            )
        assert "not present" in capsys.readouterr().out

    async def test_anycast_member_not_found(self, capsys):
        def handler(request):
            if request.method == "GET" and "/member" in request.url.path:
                return httpx.Response(200, json={"result": []})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Migration member missing.example.com anycast add 192.0.2.53",
                ctx,
            )
        assert "No member found" in capsys.readouterr().out

    async def test_anycast_deferred_on_v6_without_lan_v6(self, capsys):
        """NIOS blocks v6 loopback until LAN has IPv6. Handler reports it as
        Deferred rather than Error so batch scripts stay green."""
        ref = "member/a:m1.example.com"

        class _PutBlocker:
            def __init__(self, handler):
                self.handler = handler
                self.call = 0

            def __call__(self, request):
                if request.method == "PUT" and ref in request.url.path:
                    return httpx.Response(
                        400,
                        json={
                            "Error": "IB.Data.Conflict:Configuration of an IPv6 loopback address requires configuration of an IPv6 address on the LAN interface.",
                            "code": "Client.Ibap.Data.Conflict",
                            "text": "Configuration of an IPv6 loopback address requires configuration of an IPv6 address on the LAN interface.",
                        },
                    )
                return self.handler(request)

        def base_handler(request):
            if request.method == "GET" and "/member" in request.url.path:
                return httpx.Response(
                    200, json={"result": [{"_ref": ref, "additional_ip_list": []}]}
                )
            return None

        async with connected_ctx(_PutBlocker(base_handler)) as ctx:
            await process_line(
                "configure grid Migration member m1.example.com anycast add 2001:db8::53",
                ctx,
            )
        out = capsys.readouterr().out
        assert "Deferred" in out


# ===========================================================================
# Member add - HA, MGMT, VLAN tagging, LAN2 and NIC redundancy
#
# All verified against a live NIOS 9.x grid. The shapes here are the ones
# NIOS actually accepts; several plausible-looking alternatives do not work
# and are called out in the individual tests.
# ===========================================================================


def _member_handler(requests_seen: list, hw_fields: list[str] | None = None):
    """Handler that answers member POST/PUT and, optionally, the schema probe.

    `hw_fields` mimics a grid whose `pre_provisioning.hardware_info` accepts
    only those field names - NIOS 9.x accepts `hwtype` alone and rejects the
    whole request if sent `hwmodel` or `serial_number`.
    """

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        # Only the member-type schema read - `GET /?_schema=1` is the SDK's
        # login probe and must fall through to the default handler.
        if (
            request.method == "GET"
            and "_schema" in str(request.url)
            and request.url.path.rstrip("/").endswith("/member")
        ):
            if hw_fields is None:
                return httpx.Response(500, json={"Error": "no schema"})
            return httpx.Response(
                200,
                json={
                    "fields": [
                        {
                            "name": "pre_provisioning",
                            "schema": {
                                "fields": [
                                    {
                                        "name": "hardware_info",
                                        "schema": {"fields": [{"name": f} for f in hw_fields]},
                                    }
                                ]
                            },
                        }
                    ]
                },
            )
        if (
            request.method == "POST"
            and "/member" in request.url.path
            and "/logout" not in request.url.path
        ):
            return httpx.Response(201, json={"_ref": "member/ZG5z:m1"})
        if request.method == "PUT" and "/member/" in request.url.path:
            return httpx.Response(200, json={"_ref": "member/ZG5z:m1"})
        return None

    return handler


async def _add(cmd: str, hw_fields: list[str] | None = None):
    """Run a member-add command; return (post_body, seen_requests)."""
    seen: list[httpx.Request] = []
    async with connected_ctx(_member_handler(seen, hw_fields)) as ctx:
        await process_line(cmd, ctx)
    posts = _api_posts(seen, "/member")
    body = json.loads(posts[0].content) if posts else None
    return body, seen


class TestMemberVlanTagging:
    async def test_vlan_id_lands_on_lan1_vip(self):
        body, _ = await _add(
            "configure grid Infoblox member add m1.example.com"
            " ipaddress 10.0.0.5/24 gateway 10.0.0.1 vlan_id 110"
        )
        assert body["vip_setting"]["vlan_id"] == 110

    async def test_no_vlan_id_means_no_key(self):
        """An untagged interface must not send vlan_id at all."""
        body, _ = await _add(
            "configure grid Infoblox member add m1.example.com"
            " ipaddress 10.0.0.5/24 gateway 10.0.0.1"
        )
        assert "vlan_id" not in body["vip_setting"]

    async def test_non_numeric_vlan_is_rejected(self, capsys):
        """The grammar declares vlan_id=<num>, so a non-numeric value is
        caught during parsing - before any handler or WAPI call runs."""
        body, _ = await _add(
            "configure grid Infoblox member add m1.example.com ipaddress 10.0.0.5/24 vlan_id abc"
        )
        assert body is None
        out = capsys.readouterr().out
        assert "^---" in out and "Unknown argument" in out


class TestMemberMgmt:
    async def test_mgmt_address_and_vlan(self):
        body, _ = await _add(
            "configure grid Infoblox member add m1.example.com"
            " ipaddress 10.0.0.5/24 mgmt_ipaddress 10.1.0.5/24"
            " mgmt_gateway 10.1.0.1 mgmt_vlan_id 210"
        )
        assert body["mgmt_port_setting"]["enabled"] is True
        mgmt = body["node_info"][0]["mgmt_network_setting"]
        assert mgmt["address"] == "10.1.0.5"
        assert mgmt["gateway"] == "10.1.0.1"
        # Sent because the schema allows it; NIOS 9.x ignores it in practice.
        assert mgmt["vlan_id"] == 210


class TestMemberHa:
    _HA = (
        "configure grid Infoblox member add ha1.example.com"
        " ipaddress 10.0.0.5/24 gateway 10.0.0.1 router_id 55"
        " ha_node 10.0.0.6,10.0.0.8 ha_node 10.0.0.7,10.0.0.9"
    )

    async def test_ha_pair_shape(self):
        body, _ = await _add(self._HA)
        assert body["enable_ha"] is True
        assert body["router_id"] == 55
        nodes = body["node_info"]
        assert len(nodes) == 2
        # NIOS needs BOTH per node: "Send HA and Grid communication requires
        # valid LAN1 IPv4 addresses" if mgmt_lan is missing.
        assert nodes[0]["lan_ha_port_setting"] == {
            "mgmt_lan": "10.0.0.6",
            "ha_ip_address": "10.0.0.8",
        }
        assert nodes[1]["lan_ha_port_setting"] == {
            "mgmt_lan": "10.0.0.7",
            "ha_ip_address": "10.0.0.9",
        }

    async def test_ha_requires_router_id(self, capsys):
        body, _ = await _add(
            "configure grid Infoblox member add ha1.example.com"
            " ipaddress 10.0.0.5/24 ha_node 10.0.0.6,10.0.0.8"
            " ha_node 10.0.0.7,10.0.0.9"
        )
        assert body is None
        assert "router_id" in capsys.readouterr().out

    async def test_ha_requires_exactly_two_nodes(self, capsys):
        body, _ = await _add(
            "configure grid Infoblox member add ha1.example.com"
            " ipaddress 10.0.0.5/24 router_id 55 ha_node 10.0.0.6,10.0.0.8"
        )
        assert body is None
        assert "exactly two" in capsys.readouterr().out

    async def test_router_id_range_is_checked(self, capsys):
        body, _ = await _add(self._HA.replace("router_id 55", "router_id 300"))
        assert body is None
        assert "1-255" in capsys.readouterr().out

    async def test_per_node_mgmt_addresses_differ(self):
        """Sharing one MGMT address across nodes fails on a real grid with
        'The node 2 address <ip> is already in use by node 1'."""
        body, _ = await _add(
            "configure grid Infoblox member add ha1.example.com"
            " ipaddress 10.0.0.5/24 router_id 55"
            " ha_node 10.0.0.6,10.0.0.8,10.1.0.6"
            " ha_node 10.0.0.7,10.0.0.9,10.1.0.7"
            " mgmt_ipaddress 10.1.0.5/24 mgmt_gateway 10.1.0.1"
        )
        n1, n2 = body["node_info"]
        assert n1["mgmt_network_setting"]["address"] == "10.1.0.6"
        assert n2["mgmt_network_setting"]["address"] == "10.1.0.7"
        assert n1["mgmt_network_setting"]["subnet_mask"] == "255.255.255.0"
        assert n1["mgmt_network_setting"]["gateway"] == "10.1.0.1"

    async def test_malformed_ha_node_is_rejected(self, capsys):
        body, _ = await _add(self._HA.replace("ha_node 10.0.0.6,10.0.0.8", "ha_node 10.0.0.6"))
        assert body is None
        assert "ha_node must be" in capsys.readouterr().out


class TestMemberLan2AndNicRedundancy:
    async def test_lan2_address_and_vlan(self):
        body, _ = await _add(
            "configure grid Infoblox member add m1.example.com"
            " ipaddress 10.0.0.5/24 lan2_ipaddress 10.2.0.5/24"
            " lan2_gateway 10.2.0.1 lan2_vlan_id 250 lan2_router_id 78"
        )
        l2 = body["lan2_port_setting"]
        assert l2["enabled"] is True
        assert l2["virtual_router_id"] == 78
        assert l2["network_setting"]["address"] == "10.2.0.5"
        assert l2["network_setting"]["vlan_id"] == 250

    async def test_nic_failover_enables_lan2_without_an_address(self):
        """A redundant NIC is a standby interface - it carries no IP."""
        body, _ = await _add(
            "configure grid Infoblox member add m1.example.com"
            " ipaddress 10.0.0.5/24 nic_failover true nic_failover_primary true"
        )
        l2 = body["lan2_port_setting"]
        assert l2["enabled"] is True
        assert l2["nic_failover_enabled"] is True
        assert l2["nic_failover_enable_primary"] is True
        assert "network_setting" not in l2

    async def test_nic_failover_with_lan2_address_warns(self, capsys):
        """NIOS silently drops the LAN2 address in this combination."""
        await _add(
            "configure grid Infoblox member add m1.example.com"
            " ipaddress 10.0.0.5/24 nic_failover true"
            " lan2_ipaddress 10.2.0.5/24"
        )
        assert "standby interface" in capsys.readouterr().out

    async def test_nic_failover_and_default_route_failover_conflict(self, capsys):
        """NIOS: 'Cannot enable default route redundancy and NIC failover
        together.' Caught before the round trip."""
        body, _ = await _add(
            "configure grid Infoblox member add m1.example.com"
            " ipaddress 10.0.0.5/24 nic_failover true"
            " default_route_failover true"
        )
        assert body is None
        assert "mutually exclusive" in capsys.readouterr().out


class TestPreProvisioningSchemaAdaptation:
    async def test_unsupported_hw_fields_are_dropped(self, capsys):
        """NIOS 9.x rejects the whole PUT on an unknown hardware_info field,
        so they must be stripped rather than sent and rolled back."""
        _, seen = await _add(
            "configure grid Infoblox member add m1.example.com"
            " ipaddress 10.0.0.5/24 hwtype IB-V1425 model IB-V1425"
            " serial abc123 license dns",
            hw_fields=["hwtype"],
        )
        puts = _api_puts(seen, "/member")
        hw = json.loads(puts[0].content)["pre_provisioning"]["hardware_info"]
        assert hw == [{"hwtype": "IB-V1425"}]
        out = capsys.readouterr().out
        assert "hwmodel" in out and "serial_number" in out

    async def test_supported_hw_fields_are_kept(self):
        _, seen = await _add(
            "configure grid Infoblox member add m1.example.com"
            " ipaddress 10.0.0.5/24 hwtype IB-V1425 model IB-V1425"
            " serial abc123 license dns",
            hw_fields=["hwtype", "hwmodel", "serial_number"],
        )
        puts = _api_puts(seen, "/member")
        hw = json.loads(puts[0].content)["pre_provisioning"]["hardware_info"]
        assert hw == [{"hwtype": "IB-V1425", "hwmodel": "IB-V1425", "serial_number": "abc123"}]

    async def test_partial_drop_names_what_still_goes(self):
        """A grid that takes hwtype+hwmodel but not serial_number still sends
        hwmodel, so the warning must not claim "hwtype only"."""
        _, seen = await _add(
            "configure grid Infoblox member add m1.example.com"
            " ipaddress 10.0.0.5/24 hwtype IB-V1425 model IB-V1425"
            " serial abc123 license dns",
            hw_fields=["hwtype", "hwmodel"],
        )
        puts = _api_puts(seen, "/member")
        hw = json.loads(puts[0].content)["pre_provisioning"]["hardware_info"]
        assert hw == [{"hwtype": "IB-V1425", "hwmodel": "IB-V1425"}]

    async def test_partial_drop_warning_wording(self, capsys):
        await _add(
            "configure grid Infoblox member add m1.example.com"
            " ipaddress 10.0.0.5/24 hwtype IB-V1425 model IB-V1425"
            " serial abc123 license dns",
            hw_fields=["hwtype", "hwmodel"],
        )
        out = capsys.readouterr().out
        assert "does not accept serial_number" in out
        assert "sending hwmodel, hwtype" in out
        assert "hwtype only" not in out

    async def test_failed_schema_read_is_not_cached(self):
        """A transient schema failure must not disable the filter for the
        rest of the session - caching the failure would send fields the grid
        rejects on every later add."""
        from ibcli.commands.grid import _supported_hw_fields

        seen: list[httpx.Request] = []
        async with connected_ctx(_member_handler(seen, None)) as ctx:
            assert await _supported_hw_fields(ctx) is None
            assert "hw_fields" not in ctx.caches

    async def test_successful_schema_read_is_cached(self):
        """The probe costs a round trip, so a good answer is asked for once."""
        from ibcli.commands.grid import _supported_hw_fields

        seen: list[httpx.Request] = []
        async with connected_ctx(_member_handler(seen, ["hwtype"])) as ctx:
            assert await _supported_hw_fields(ctx) == {"hwtype"}
            probes = [
                r
                for r in seen
                if "_schema" in str(r.url) and r.url.path.rstrip("/").endswith("/member")
            ]
            assert await _supported_hw_fields(ctx) == {"hwtype"}
            after = [
                r
                for r in seen
                if "_schema" in str(r.url) and r.url.path.rstrip("/").endswith("/member")
            ]
            assert len(after) == len(probes) == 1

    async def test_node_accepts_hwtype_only(self):
        """`node=IB-V1425` must work on a grid that only takes hwtype."""
        _, seen = await _add(
            "configure grid Infoblox member add m1.example.com"
            " ipaddress 10.0.0.5/24 node IB-V1425 node IB-V1425 license dns",
            hw_fields=["hwtype"],
        )
        puts = _api_puts(seen, "/member")
        body = json.loads(puts[0].content)
        assert body["pre_provisioning"]["hardware_info"] == [
            {"hwtype": "IB-V1425"},
            {"hwtype": "IB-V1425"},
        ]
        # Two hardware_info entries still imply an HA pair.
        assert body["enable_ha"] is True


class TestMemberHaMgmtWarning:
    async def test_ha_with_mgmt_but_no_per_node_addresses_warns(self, capsys):
        """Without a third ha_node field both nodes would share one MGMT
        address, which NIOS rejects - warn rather than let it fail on the
        grid."""
        body, _ = await _add(
            "configure grid Infoblox member add ha1.example.com"
            " ipaddress 10.0.0.5/24 router_id 55"
            " ha_node 10.0.0.6,10.0.0.8 ha_node 10.0.0.7,10.0.0.9"
            " mgmt_ipaddress 10.1.0.5/24 mgmt_gateway 10.1.0.1"
        )
        out = capsys.readouterr().out
        assert "per-node MGMT address" in out
        # The member is still created - MGMT is simply left off the nodes.
        assert body["enable_ha"] is True
        assert "mgmt_network_setting" not in body["node_info"][0]
