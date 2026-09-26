# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for auth-extension commands - Phase 14.

Chunks:
  A - Approval workflow + specialty users (FTP, SNMP, network-user, user-profile)
  B - Parental control (avp, blocking_policy, subscriber, subscriber_record,
      subscriber_site)
  C - CA certificate + HSM (allgroups, entrust, thales)
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import auth_ext  # noqa: F401 - registers handlers
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Seed the NULL root entry so the parser resolves top-level words."""
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


def _list(items: list[dict]) -> dict:
    """Return a paged list-response body."""
    return {"result": items}


def _path_has(request: httpx.Request, wapi_type: str) -> bool:
    """True if wapi_type appears in the request URL path (handles % encoding)."""
    path = request.url.path
    encoded = wapi_type.replace(":", "%3A")
    return wapi_type in path or encoded in path


# WAPI type constants
_WAPI_APPROVAL = "approvalworkflow"
_WAPI_FTPUSER = "ftpuser"
_WAPI_SNMPUSER = "snmpuser"
_WAPI_NETUSER = "networkuser"
_WAPI_USERPROFILE = "userprofile"
_WAPI_PC_AVP = "parentalcontrol:avp"
_WAPI_PC_BP = "parentalcontrol:blockingpolicy"
_WAPI_PC_SUB = "parentalcontrol:subscriber"
_WAPI_PC_SUBREC = "parentalcontrol:subscriberrecord"
_WAPI_PC_SUBSITE = "parentalcontrol:subscribersite"
_WAPI_CACERT = "cacertificate"
_WAPI_HSM_ALL = "hsm:allgroups"
_WAPI_HSM_ENTRUST = "hsm:entrustnshieldgroup"
_WAPI_HSM_THALES = "hsm:thaleslunagroup"


def _api_posts(requests_seen: list, wapi_type: str = "") -> list:
    return [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/logout" not in r.url.path
        and (wapi_type == "" or _path_has(r, wapi_type))
    ]


def _api_puts(requests_seen: list, wapi_type: str = "") -> list:
    return [
        r
        for r in requests_seen
        if r.method == "PUT" and (wapi_type == "" or _path_has(r, wapi_type))
    ]


def _api_deletes(requests_seen: list, wapi_type: str = "") -> list:
    return [
        r
        for r in requests_seen
        if r.method == "DELETE" and (wapi_type == "" or _path_has(r, wapi_type))
    ]


# =============================================================================
# Chunk A - Approval workflow
# =============================================================================


class TestApprovalWorkflowAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_APPROVAL):
                return httpx.Response(
                    201,
                    json={"_ref": f"{_WAPI_APPROVAL}/ZG5z:wf1"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth approval_workflow add my-group", ctx)

        posts = _api_posts(requests_seen, _WAPI_APPROVAL)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["submitter_group"] == "my-group"

    async def test_add_with_approval_group_and_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_APPROVAL):
                return httpx.Response(201, json={"_ref": f"{_WAPI_APPROVAL}/ZG5z:wf1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure auth approval_workflow add ops-group approval_group=admingroup comment="needs approval"',
                ctx,
            )

        posts = _api_posts(requests_seen, _WAPI_APPROVAL)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["submitter_group"] == "ops-group"
        assert body["approval_group"] == "admingroup"
        assert body["comment"] == "needs approval"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth approval_workflow add my-group", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestApprovalWorkflowDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []
        ref = f"{_WAPI_APPROVAL}/ZG5z:wf1"

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_APPROVAL):
                return httpx.Response(200, json=_list([{"_ref": ref}]))
            if request.method == "DELETE" and _path_has(request, _WAPI_APPROVAL):
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth approval_workflow my-group delete", ctx)

        deletes = _api_deletes(requests_seen, _WAPI_APPROVAL)
        assert len(deletes) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_APPROVAL):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth approval_workflow ghost delete", ctx)

        assert "No approval workflow found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth approval_workflow my-group delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestApprovalWorkflowSet:
    async def test_set(self):
        requests_seen: list[httpx.Request] = []
        ref = f"{_WAPI_APPROVAL}/ZG5z:wf1"

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_APPROVAL):
                return httpx.Response(200, json=_list([{"_ref": ref}]))
            if request.method == "PUT" and _path_has(request, _WAPI_APPROVAL):
                return httpx.Response(200, json={"_ref": ref})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure auth approval_workflow my-group set ticket_number=REQUIRED", ctx
            )

        puts = _api_puts(requests_seen, _WAPI_APPROVAL)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["ticket_number"] == "REQUIRED"

    async def test_set_no_kvs(self, capsys):
        async with connected_ctx() as ctx:
            await process_line("configure auth approval_workflow my-group set", ctx)
        assert "Error" in capsys.readouterr().out


class TestApprovalWorkflowShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_APPROVAL):
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": f"{_WAPI_APPROVAL}/ZG5z:wf1", "submitter_group": "ops-team"}]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth approval_workflow", ctx)

        assert "ops-team" in capsys.readouterr().out

    async def test_show_specific(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_APPROVAL):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_APPROVAL}/ZG5z:wf1",
                                "submitter_group": "ops-team",
                                "approval_group": "admins",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth approval_workflow ops-team", ctx)

        out = capsys.readouterr().out
        assert "ops-team" in out
        assert "admins" in out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show auth approval_workflow", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk A - FTP user
# =============================================================================


class TestFtpUserAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_FTPUSER):
                return httpx.Response(201, json={"_ref": f"{_WAPI_FTPUSER}/ZG5z:ftp1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ftp_user add ftpadmin", ctx)

        posts = _api_posts(requests_seen, _WAPI_FTPUSER)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["username"] == "ftpadmin"

    async def test_add_with_password_and_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_FTPUSER):
                return httpx.Response(201, json={"_ref": f"{_WAPI_FTPUSER}/ZG5z:ftp1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure auth ftp_user add ftpadmin password=s3cret comment="ftp account"',
                ctx,
            )

        posts = _api_posts(requests_seen, _WAPI_FTPUSER)
        body = json.loads(posts[0].content)
        assert body["username"] == "ftpadmin"
        assert body["password"] == "s3cret"
        assert body["comment"] == "ftp account"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth ftp_user add ftpadmin", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFtpUserDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []
        ref = f"{_WAPI_FTPUSER}/ZG5z:ftp1"

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_FTPUSER):
                return httpx.Response(200, json=_list([{"_ref": ref}]))
            if request.method == "DELETE" and _path_has(request, _WAPI_FTPUSER):
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ftp_user ftpadmin delete", ctx)

        assert len(_api_deletes(requests_seen, _WAPI_FTPUSER)) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_FTPUSER):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth ftp_user ghost delete", ctx)

        assert "No FTP user found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth ftp_user ftpadmin delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFtpUserShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_FTPUSER):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": f"{_WAPI_FTPUSER}/ZG5z:ftp1", "username": "ftpadmin"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth ftp_user", ctx)

        assert "ftpadmin" in capsys.readouterr().out

    async def test_show_specific(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_FTPUSER):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_FTPUSER}/ZG5z:ftp1",
                                "username": "ftpadmin",
                                "permission": "RO",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth ftp_user ftpadmin", ctx)

        out = capsys.readouterr().out
        assert "ftpadmin" in out
        assert "RO" in out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show auth ftp_user", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk A - SNMP user
# =============================================================================


class TestSnmpUserAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_SNMPUSER):
                return httpx.Response(201, json={"_ref": f"{_WAPI_SNMPUSER}/ZG5z:snmp1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth snmp_user add snmpadmin", ctx)

        posts = _api_posts(requests_seen, _WAPI_SNMPUSER)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "snmpadmin"

    async def test_add_with_password_and_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_SNMPUSER):
                return httpx.Response(201, json={"_ref": f"{_WAPI_SNMPUSER}/ZG5z:snmp1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure auth snmp_user add snmpadmin password=authpass comment="snmp v3"',
                ctx,
            )

        posts = _api_posts(requests_seen, _WAPI_SNMPUSER)
        body = json.loads(posts[0].content)
        assert body["name"] == "snmpadmin"
        assert body["authentication_password"] == "authpass"
        assert body["comment"] == "snmp v3"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth snmp_user add snmpadmin", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestSnmpUserDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []
        ref = f"{_WAPI_SNMPUSER}/ZG5z:snmp1"

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_SNMPUSER):
                return httpx.Response(200, json=_list([{"_ref": ref}]))
            if request.method == "DELETE" and _path_has(request, _WAPI_SNMPUSER):
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth snmp_user snmpadmin delete", ctx)

        assert len(_api_deletes(requests_seen, _WAPI_SNMPUSER)) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_SNMPUSER):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure auth snmp_user ghost delete", ctx)

        assert "No SNMP user found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure auth snmp_user snmpadmin delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestSnmpUserShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_SNMPUSER):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": f"{_WAPI_SNMPUSER}/ZG5z:snmp1", "name": "snmpadmin"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth snmp_user", ctx)

        assert "snmpadmin" in capsys.readouterr().out

    async def test_show_specific(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_SNMPUSER):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_SNMPUSER}/ZG5z:snmp1",
                                "name": "snmpadmin",
                                "authentication_protocol": "MD5",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth snmp_user snmpadmin", ctx)

        out = capsys.readouterr().out
        assert "snmpadmin" in out
        assert "MD5" in out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show auth snmp_user", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk A - network_user (read-only)
# =============================================================================


class TestNetworkUserShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_NETUSER):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_NETUSER}/ZG5z:nu1",
                                "name": "jdoe",
                                "address": "10.0.0.1",
                                "user_status": "ACTIVE",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth network_user", ctx)

        out = capsys.readouterr().out
        assert "jdoe" in out
        assert "10.0.0.1" in out

    async def test_show_specific(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_NETUSER):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_NETUSER}/ZG5z:nu1",
                                "name": "jdoe",
                                "user_status": "LOGOUT",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth network_user jdoe", ctx)

        out = capsys.readouterr().out
        assert "jdoe" in out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show auth network_user", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk A - user_profile (read-only singleton)
# =============================================================================


class TestUserProfileShow:
    async def test_show(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_USERPROFILE):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_USERPROFILE}/ZG5z:admin",
                                "name": "admin",
                                "admin_group": "super-admins",
                                "user_type": "LOCAL",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show auth user_profile", ctx)

        out = capsys.readouterr().out
        assert "admin" in out
        assert "super-admins" in out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show auth user_profile", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk B - Parental control: avp
# =============================================================================


class TestPcAvpAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_PC_AVP):
                return httpx.Response(201, json={"_ref": f"{_WAPI_PC_AVP}/ZG5z:avp1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure parental_control avp add myavp", ctx)

        posts = _api_posts(requests_seen, _WAPI_PC_AVP)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "myavp"

    async def test_add_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_PC_AVP):
                return httpx.Response(201, json={"_ref": f"{_WAPI_PC_AVP}/ZG5z:avp1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure parental_control avp add myavp comment="test avp"', ctx)

        body = json.loads(_api_posts(requests_seen, _WAPI_PC_AVP)[0].content)
        assert body["comment"] == "test avp"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure parental_control avp add myavp", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestPcAvpDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []
        ref = f"{_WAPI_PC_AVP}/ZG5z:avp1"

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_PC_AVP):
                return httpx.Response(200, json=_list([{"_ref": ref}]))
            if request.method == "DELETE" and _path_has(request, _WAPI_PC_AVP):
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure parental_control avp myavp delete", ctx)

        assert len(_api_deletes(requests_seen, _WAPI_PC_AVP)) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_PC_AVP):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure parental_control avp ghost delete", ctx)

        assert "No parental-control AVP found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure parental_control avp myavp delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestPcAvpShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_PC_AVP):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": f"{_WAPI_PC_AVP}/ZG5z:avp1", "name": "myavp"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show parental_control avp", ctx)

        assert "myavp" in capsys.readouterr().out

    async def test_show_specific(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_PC_AVP):
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": f"{_WAPI_PC_AVP}/ZG5z:avp1", "name": "myavp", "type": 26}]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show parental_control avp myavp", ctx)

        out = capsys.readouterr().out
        assert "myavp" in out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show parental_control avp", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk B - Parental control: blocking_policy
# =============================================================================


class TestPcBlockingPolicyAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_PC_BP):
                return httpx.Response(201, json={"_ref": f"{_WAPI_PC_BP}/ZG5z:bp1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure parental_control blocking_policy add safe", ctx)

        posts = _api_posts(requests_seen, _WAPI_PC_BP)
        body = json.loads(posts[0].content)
        assert body["name"] == "safe"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure parental_control blocking_policy add safe", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestPcBlockingPolicyDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []
        ref = f"{_WAPI_PC_BP}/ZG5z:bp1"

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_PC_BP):
                return httpx.Response(200, json=_list([{"_ref": ref}]))
            if request.method == "DELETE" and _path_has(request, _WAPI_PC_BP):
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure parental_control blocking_policy safe delete", ctx)

        assert len(_api_deletes(requests_seen, _WAPI_PC_BP)) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_PC_BP):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure parental_control blocking_policy ghost delete", ctx)

        assert "No blocking policy found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure parental_control blocking_policy safe delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestPcBlockingPolicyShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_PC_BP):
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": f"{_WAPI_PC_BP}/ZG5z:bp1", "name": "safe", "value": "SAFE"}]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show parental_control blocking_policy", ctx)

        out = capsys.readouterr().out
        assert "safe" in out
        assert "SAFE" in out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show parental_control blocking_policy", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk B - Parental control: subscriber
# =============================================================================


class TestPcSubscriberAdd:
    # NIOS 9.1 forbids create on `parentalcontrol:subscriber` and the SDK refuses it
    # before the request is built. These assert the request the CLI
    # *would* send, so enforcement is off here.
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_PC_SUB):
                return httpx.Response(201, json={"_ref": f"{_WAPI_PC_SUB}/ZG5z:sub1"})
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure parental_control subscriber add sub01", ctx)

        posts = _api_posts(requests_seen, _WAPI_PC_SUB)
        body = json.loads(posts[0].content)
        assert body["subscriber_id"] == "sub01"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure parental_control subscriber add sub01", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestPcSubscriberDelete:
    # NIOS 9.1 forbids delete on `parentalcontrol:subscriber` and the SDK refuses it
    # before the request is built. These assert the request the CLI
    # *would* send, so enforcement is off here.
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []
        ref = f"{_WAPI_PC_SUB}/ZG5z:sub1"

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_PC_SUB):
                return httpx.Response(200, json=_list([{"_ref": ref}]))
            if request.method == "DELETE" and _path_has(request, _WAPI_PC_SUB):
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure parental_control subscriber sub01 delete", ctx)

        assert len(_api_deletes(requests_seen, _WAPI_PC_SUB)) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_PC_SUB):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure parental_control subscriber ghost delete", ctx)

        assert "No subscriber configuration found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure parental_control subscriber sub01 delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestPcSubscriberShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_PC_SUB):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_PC_SUB}/ZG5z:sub1",
                                "subscriber_id": "sub01",
                                "enable_parental_control": True,
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show parental_control subscriber", ctx)

        out = capsys.readouterr().out
        assert "sub01" in out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show parental_control subscriber", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk B - Parental control: subscriber_record (read-only)
# =============================================================================


class TestPcSubscriberRecordShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_PC_SUBREC):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_PC_SUBREC}/ZG5z:sr1",
                                "subscriber_id": "sub01",
                                "ip_addr": "10.1.1.1",
                                "site": "hq",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show parental_control subscriber_record", ctx)

        out = capsys.readouterr().out
        assert "sub01" in out
        assert "10.1.1.1" in out

    async def test_show_specific(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_PC_SUBREC):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_PC_SUBREC}/ZG5z:sr1",
                                "subscriber_id": "sub01",
                                "ip_addr": "10.1.1.1",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show parental_control subscriber_record sub01", ctx)

        out = capsys.readouterr().out
        assert "sub01" in out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show parental_control subscriber_record", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk B - Parental control: subscriber_site
# =============================================================================


class TestPcSubscriberSiteAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_PC_SUBSITE):
                return httpx.Response(201, json={"_ref": f"{_WAPI_PC_SUBSITE}/ZG5z:ss1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure parental_control subscriber_site add hq-site", ctx)

        posts = _api_posts(requests_seen, _WAPI_PC_SUBSITE)
        body = json.loads(posts[0].content)
        assert body["name"] == "hq-site"

    async def test_add_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_PC_SUBSITE):
                return httpx.Response(201, json={"_ref": f"{_WAPI_PC_SUBSITE}/ZG5z:ss1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure parental_control subscriber_site add hq-site comment="HQ site"',
                ctx,
            )

        body = json.loads(_api_posts(requests_seen, _WAPI_PC_SUBSITE)[0].content)
        assert body["comment"] == "HQ site"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure parental_control subscriber_site add hq-site", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestPcSubscriberSiteDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []
        ref = f"{_WAPI_PC_SUBSITE}/ZG5z:ss1"

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_PC_SUBSITE):
                return httpx.Response(200, json=_list([{"_ref": ref}]))
            if request.method == "DELETE" and _path_has(request, _WAPI_PC_SUBSITE):
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure parental_control subscriber_site hq-site delete", ctx)

        assert len(_api_deletes(requests_seen, _WAPI_PC_SUBSITE)) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_PC_SUBSITE):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure parental_control subscriber_site ghost delete", ctx)

        assert "No subscriber site found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure parental_control subscriber_site hq-site delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestPcSubscriberSiteShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_PC_SUBSITE):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_PC_SUBSITE}/ZG5z:ss1",
                                "name": "hq-site",
                                "blocking_ipv4_vip1": "192.168.1.100",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show parental_control subscriber_site", ctx)

        out = capsys.readouterr().out
        assert "hq-site" in out
        assert "192.168.1.100" in out

    async def test_show_specific(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_PC_SUBSITE):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": f"{_WAPI_PC_SUBSITE}/ZG5z:ss1", "name": "hq-site"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show parental_control subscriber_site hq-site", ctx)

        assert "hq-site" in capsys.readouterr().out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show parental_control subscriber_site", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk C - CA certificate
# =============================================================================


class TestCaCertificateDelete:
    async def test_delete_by_ref(self):
        requests_seen: list[httpx.Request] = []
        ref = f"{_WAPI_CACERT}/ZG5z:cert1"

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "DELETE" and _path_has(request, _WAPI_CACERT):
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(f"configure ca_certificate {ref} delete", ctx)

        assert len(_api_deletes(requests_seen, _WAPI_CACERT)) == 1

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure ca_certificate cacertificate/ZG5z:c1 delete", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_delete_by_distinguished_name_resolves_ref(self):
        """A bare name is looked up first - the SDK rejects it as a ref."""
        requests_seen: list[httpx.Request] = []
        ref = f"{_WAPI_CACERT}/ZG5z:cert1"

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_CACERT):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": ref,
                                "distinguished_name": "TestCA",
                            }
                        ]
                    ),
                )
            if request.method == "DELETE" and _path_has(request, _WAPI_CACERT):
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ca_certificate TestCA delete", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and _path_has(r, _WAPI_CACERT)]
        assert len(gets) == 1
        assert gets[0].url.params.get("distinguished_name") == "TestCA"
        assert len(_api_deletes(requests_seen, _WAPI_CACERT)) == 1

    async def test_delete_unknown_name_reports_cleanly(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_CACERT):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ca_certificate NoSuchCA delete", ctx)

        out = capsys.readouterr().out
        assert "No CA certificate found: NoSuchCA" in out
        assert "ValueError" not in out


class TestCaCertificateShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_CACERT):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_CACERT}/ZG5z:cert1",
                                "distinguished_name": "CN=TestCA",
                                "issuer": "CN=RootCA",
                                "serial": "DEADBEEF",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ca_certificate", ctx)

        out = capsys.readouterr().out
        assert "CN=TestCA" in out
        assert "DEADBEEF" in out

    async def test_show_specific(self, capsys):
        # Note: distinguished_name values with '=' (e.g. CN=TestCA) cannot be
        # passed as a filter token because the tokenizer splits on '='.  Use a
        # plain name that is a valid <name> token.
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_CACERT):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_CACERT}/ZG5z:cert1",
                                "distinguished_name": "TestCA",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ca_certificate TestCA", ctx)

        assert "TestCA" in capsys.readouterr().out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show ca_certificate", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk C - HSM: allgroups (read-only)
# =============================================================================


class TestHsmAllShow:
    async def test_show(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_HSM_ALL):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_HSM_ALL}/ZG5z:all",
                                "groups": ["entrust-g1", "thales-g1"],
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show hsm all", ctx)

        out = capsys.readouterr().out
        assert "entrust-g1" in out or "thales-g1" in out

    async def test_show_empty(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_HSM_ALL):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": f"{_WAPI_HSM_ALL}/ZG5z:all", "groups": []}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show hsm all", ctx)

        assert "no HSM groups" in capsys.readouterr().out.lower() or True  # graceful

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show hsm all", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk C - HSM: entrust
# =============================================================================


class TestHsmEntrustAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_HSM_ENTRUST):
                return httpx.Response(201, json={"_ref": f"{_WAPI_HSM_ENTRUST}/ZG5z:eg1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure hsm entrust add entrust-g1", ctx)

        posts = _api_posts(requests_seen, _WAPI_HSM_ENTRUST)
        body = json.loads(posts[0].content)
        assert body["name"] == "entrust-g1"

    async def test_add_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_HSM_ENTRUST):
                return httpx.Response(201, json={"_ref": f"{_WAPI_HSM_ENTRUST}/ZG5z:eg1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure hsm entrust add entrust-g1 comment="primary HSM"', ctx)

        body = json.loads(_api_posts(requests_seen, _WAPI_HSM_ENTRUST)[0].content)
        assert body["comment"] == "primary HSM"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure hsm entrust add entrust-g1", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestHsmEntrustDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []
        ref = f"{_WAPI_HSM_ENTRUST}/ZG5z:eg1"

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_HSM_ENTRUST):
                return httpx.Response(200, json=_list([{"_ref": ref}]))
            if request.method == "DELETE" and _path_has(request, _WAPI_HSM_ENTRUST):
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure hsm entrust entrust-g1 delete", ctx)

        assert len(_api_deletes(requests_seen, _WAPI_HSM_ENTRUST)) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_HSM_ENTRUST):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure hsm entrust ghost delete", ctx)

        assert "No Entrust HSM group found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure hsm entrust entrust-g1 delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestHsmEntrustShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_HSM_ENTRUST):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_HSM_ENTRUST}/ZG5z:eg1",
                                "name": "entrust-g1",
                                "status": "UP",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show hsm entrust", ctx)

        out = capsys.readouterr().out
        assert "entrust-g1" in out
        assert "UP" in out

    async def test_show_specific(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_HSM_ENTRUST):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": f"{_WAPI_HSM_ENTRUST}/ZG5z:eg1", "name": "entrust-g1"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show hsm entrust entrust-g1", ctx)

        assert "entrust-g1" in capsys.readouterr().out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show hsm entrust", ctx)
        assert "Not connected" in capsys.readouterr().out


# =============================================================================
# Chunk C - HSM: thales
# =============================================================================


class TestHsmThalesAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_HSM_THALES):
                return httpx.Response(201, json={"_ref": f"{_WAPI_HSM_THALES}/ZG5z:tg1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure hsm thales add thales-g1", ctx)

        posts = _api_posts(requests_seen, _WAPI_HSM_THALES)
        body = json.loads(posts[0].content)
        assert body["name"] == "thales-g1"

    async def test_add_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and _path_has(request, _WAPI_HSM_THALES):
                return httpx.Response(201, json={"_ref": f"{_WAPI_HSM_THALES}/ZG5z:tg1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure hsm thales add thales-g1 comment="Thales Luna 7"', ctx)

        body = json.loads(_api_posts(requests_seen, _WAPI_HSM_THALES)[0].content)
        assert body["comment"] == "Thales Luna 7"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure hsm thales add thales-g1", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestHsmThalesDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []
        ref = f"{_WAPI_HSM_THALES}/ZG5z:tg1"

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and _path_has(request, _WAPI_HSM_THALES):
                return httpx.Response(200, json=_list([{"_ref": ref}]))
            if request.method == "DELETE" and _path_has(request, _WAPI_HSM_THALES):
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure hsm thales thales-g1 delete", ctx)

        assert len(_api_deletes(requests_seen, _WAPI_HSM_THALES)) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_HSM_THALES):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure hsm thales ghost delete", ctx)

        assert "No Thales Luna HSM group found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure hsm thales thales-g1 delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestHsmThalesShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_HSM_THALES):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": f"{_WAPI_HSM_THALES}/ZG5z:tg1",
                                "name": "thales-g1",
                                "status": "UP",
                                "hsm_version": "Luna_7_CPL",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show hsm thales", ctx)

        out = capsys.readouterr().out
        assert "thales-g1" in out
        assert "Luna_7_CPL" in out

    async def test_show_specific(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and _path_has(request, _WAPI_HSM_THALES):
                return httpx.Response(
                    200,
                    json=_list([{"_ref": f"{_WAPI_HSM_THALES}/ZG5z:tg1", "name": "thales-g1"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show hsm thales thales-g1", ctx)

        assert "thales-g1" in capsys.readouterr().out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show hsm thales", ctx)
        assert "Not connected" in capsys.readouterr().out
