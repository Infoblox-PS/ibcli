# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for admin + RADIUS slices 4a, 4b, 4c.

Slices:
  4a - admin users, groups, roles (full CRUD + show)
  4b - admin permissions (add + delete + modify)
  4c - RADIUS users and NAS devices
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import admin  # noqa: F401 - registers handlers
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Seed the NULL root entry so the parser resolves top-level words.

    system.py (not yet converted) normally provides this. Register the minimal
    subset needed for admin and radius commands.
    """
    COMMANDS.setdefault("NULL", CommandEntry(words="configure show"))


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
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


# ===========================================================================
# Slice 4a - Admin Users
# ===========================================================================


class TestAdminUserAdd:
    async def test_add_user_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/adminuser" in request.url.path:
                return httpx.Response(201, json={"_ref": "adminuser/ZG5z:bob", "name": "bob"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin user add bob password=secret", ctx)

        posts = _api_posts(requests_seen, "/adminuser")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "bob"
        assert body["password"] == "secret"

    async def test_add_user_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/adminuser" in request.url.path:
                return httpx.Response(201, json={"_ref": "adminuser/ZG5z:bob", "name": "bob"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure admin user add bob password=secret comment="my user"',
                ctx,
            )

        posts = _api_posts(requests_seen, "/adminuser")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["comment"] == "my user"

    async def test_add_user_no_password(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin user add bob", ctx)

        out = capsys.readouterr().out
        assert "password" in out.lower() or "required" in out.lower()

    async def test_add_user_wapi_error(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "POST" and "/adminuser" in request.url.path:
                return httpx.Response(
                    400,
                    json={
                        "Error": "AdmConDataError",
                        "code": "Client.Ibap.Data",
                        "text": "User exists",
                    },
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin user add bob password=secret", ctx)

        assert "Error" in capsys.readouterr().out

    async def test_add_user_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure admin user add bob password=secret", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestAdminUserDelete:
    async def test_delete_user_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/adminuser" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "adminuser/ZG5z:bob", "name": "bob"},
                        ]
                    ),
                )
            if request.method == "DELETE" and "adminuser" in request.url.path:
                return httpx.Response(200, json="adminuser/ZG5z:bob")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin user bob delete", ctx)

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1
        assert "adminuser" in str(deletes[0].url)

    async def test_delete_user_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/adminuser" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin user nobody delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "not found" in out.lower() or "nobody" in out

    async def test_delete_user_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure admin user bob delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestAdminUserShow:
    async def test_show_all_users(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/adminuser" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "adminuser/ZG5z:alice", "name": "alice"},
                            {"_ref": "adminuser/ZG5z:bob", "name": "bob"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show admin user", ctx)

        out = capsys.readouterr().out
        assert "alice" in out
        assert "bob" in out

    async def test_show_specific_user(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/adminuser" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "adminuser/ZG5z:alice", "name": "alice"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show admin user alice", ctx)

        out = capsys.readouterr().out
        assert "alice" in out
        gets = [r for r in requests_seen if r.method == "GET" and "/adminuser" in r.url.path]
        assert len(gets) >= 1
        assert "name=alice" in str(gets[0].url)

    async def test_show_users_not_connected(self, capsys):
        ctx = Context()
        await process_line("show admin user", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 4a - Admin Groups
# ===========================================================================


class TestAdminGroupAdd:
    async def test_add_group_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/admingroup" in request.url.path:
                return httpx.Response(201, json={"_ref": "admingroup/ZG5z:ops", "name": "ops"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin group add ops", ctx)

        posts = _api_posts(requests_seen, "/admingroup")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "ops"

    async def test_add_group_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/admingroup" in request.url.path:
                return httpx.Response(201, json={"_ref": "admingroup/ZG5z:ops", "name": "ops"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure admin group add ops comment="ops team"', ctx)

        posts = _api_posts(requests_seen, "/admingroup")
        body = json.loads(posts[0].content)
        assert body["comment"] == "ops team"

    async def test_add_group_wapi_error(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "POST" and "/admingroup" in request.url.path:
                return httpx.Response(
                    400,
                    json={
                        "Error": "AdmConDataError",
                        "code": "Client.Ibap.Data",
                        "text": "Group exists",
                    },
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin group add ops", ctx)

        assert "Error" in capsys.readouterr().out

    async def test_add_group_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure admin group add ops", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestAdminGroupDelete:
    async def test_delete_group_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/admingroup" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "admingroup/ZG5z:ops", "name": "ops"},
                        ]
                    ),
                )
            if request.method == "DELETE" and "admingroup" in request.url.path:
                return httpx.Response(200, json="admingroup/ZG5z:ops")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin group ops delete", ctx)

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1

    async def test_delete_group_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/admingroup" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin group nogroup delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "nogroup" in out

    async def test_delete_group_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure admin group ops delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestAdminGroupShow:
    async def test_show_all_groups(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/admingroup" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "admingroup/ZG5z:ops", "name": "ops"},
                            {"_ref": "admingroup/ZG5z:dns", "name": "dns"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show admin admin_group", ctx)

        out = capsys.readouterr().out
        assert "ops" in out
        assert "dns" in out

    async def test_show_specific_group(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/admingroup" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "admingroup/ZG5z:ops", "name": "ops"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show admin admin_group ops", ctx)

        out = capsys.readouterr().out
        assert "ops" in out
        gets = [r for r in requests_seen if r.method == "GET" and "/admingroup" in r.url.path]
        assert len(gets) >= 1
        assert "name=ops" in str(gets[0].url)

    async def test_show_groups_not_connected(self, capsys):
        ctx = Context()
        await process_line("show admin admin_group", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 4a - Admin Roles
# ===========================================================================


class TestAdminRoleAdd:
    async def test_add_role_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/adminrole" in request.url.path:
                return httpx.Response(201, json={"_ref": "adminrole/ZG5z:dns", "name": "dns-admin"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin role add dns-admin", ctx)

        posts = _api_posts(requests_seen, "/adminrole")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "dns-admin"

    async def test_add_role_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/adminrole" in request.url.path:
                return httpx.Response(201, json={"_ref": "adminrole/ZG5z:dns", "name": "dns-admin"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure admin role add dns-admin comment="dns role"', ctx)

        posts = _api_posts(requests_seen, "/adminrole")
        body = json.loads(posts[0].content)
        assert body["comment"] == "dns role"

    async def test_add_role_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure admin role add dns-admin", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestAdminRoleDelete:
    async def test_delete_role_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/adminrole" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "adminrole/ZG5z:dns", "name": "dns-admin"},
                        ]
                    ),
                )
            if request.method == "DELETE" and "adminrole" in request.url.path:
                return httpx.Response(200, json="adminrole/ZG5z:dns")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin role dns-admin delete", ctx)

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1

    async def test_delete_role_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/adminrole" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin role norole delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "norole" in out

    async def test_delete_role_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure admin role myrole delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestAdminRoleShow:
    async def test_show_all_roles(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/adminrole" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "adminrole/ZG5z:r1", "name": "role1"},
                            {"_ref": "adminrole/ZG5z:r2", "name": "role2"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show admin role", ctx)

        out = capsys.readouterr().out
        assert "role1" in out
        assert "role2" in out

    async def test_show_specific_role(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/adminrole" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "adminrole/ZG5z:r1", "name": "role1"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show admin role role1", ctx)

        out = capsys.readouterr().out
        assert "role1" in out
        gets = [r for r in requests_seen if r.method == "GET" and "/adminrole" in r.url.path]
        assert len(gets) >= 1
        assert "name=role1" in str(gets[0].url)

    async def test_show_roles_not_connected(self, capsys):
        ctx = Context()
        await process_line("show admin role", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 4b - Admin Permissions
# ===========================================================================


class TestPermissionAdd:
    async def test_add_permission_with_group(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/permission" in request.url.path:
                return httpx.Response(201, json={"_ref": "permission/ZG5z:p1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin permission add group=ops object=myobj read", ctx)

        posts = _api_posts(requests_seen, "/permission")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["group"] == "ops"
        assert body["object"] == "myobj"
        assert body["permission"] == "READ"

    async def test_add_permission_with_role(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/permission" in request.url.path:
                return httpx.Response(201, json={"_ref": "permission/ZG5z:p2"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure admin permission add role=dns-admin object=myobj write", ctx
            )

        posts = _api_posts(requests_seen, "/permission")
        body = json.loads(posts[0].content)
        assert body["role"] == "dns-admin"
        assert body["permission"] == "WRITE"
        assert "group" not in body

    async def test_add_permission_both_group_and_role_is_error(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure admin permission add group=ops role=dns-admin object=myobj read", ctx
            )

        out = capsys.readouterr().out
        assert "Error" in out or "error" in out.lower()
        assert not _api_posts(requests_seen)

    async def test_add_permission_neither_group_nor_role_is_error(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin permission add object=myobj read", ctx)

        out = capsys.readouterr().out
        assert "Error" in out or "error" in out.lower()
        assert not _api_posts(requests_seen)

    async def test_add_permission_deny(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/permission" in request.url.path:
                return httpx.Response(201, json={"_ref": "permission/ZG5z:p3"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin permission add group=ops object=myobj deny", ctx)

        posts = _api_posts(requests_seen, "/permission")
        body = json.loads(posts[0].content)
        assert body["permission"] == "DENY"

    async def test_add_permission_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure admin permission add group=ops object=myobj read", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestPermissionDelete:
    async def test_delete_permission_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/permission" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": "permission/ZG5z:p1"}]))
            if request.method == "DELETE" and "permission" in request.url.path:
                return httpx.Response(200, json="permission/ZG5z:p1")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin permission delete group=ops object=myobj", ctx)

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1

    async def test_delete_permission_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/permission" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure admin permission delete group=ops object=myobj", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "not found" in out.lower() or "permission" in out.lower()

    async def test_delete_permission_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure admin permission delete group=ops object=myobj", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestPermissionModify:
    async def test_modify_permission_success(self):
        ref = "permission/ZG5z:p1"
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/permission" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref}]))
            if request.method == "PUT" and "permission" in request.url.path:
                return httpx.Response(200, json={"_ref": ref})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure admin permission modify group=ops object=myobj permission=write",
                ctx,
            )

        puts = [r for r in requests_seen if r.method == "PUT"]
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["permission"] == "WRITE"

    async def test_modify_permission_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/permission" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure admin permission modify group=ops object=myobj permission=read",
                ctx,
            )

        out = capsys.readouterr().out
        assert "No" in out or "not found" in out.lower()

    async def test_modify_permission_multiple_matches_error(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/permission" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "permission/ZG5z:p1"},
                            {"_ref": "permission/ZG5z:p2"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure admin permission modify group=ops permission=read",
                ctx,
            )

        out = capsys.readouterr().out
        assert "Error" in out or "error" in out.lower()

    async def test_modify_permission_missing_permission_field(self, capsys):
        """The missing-permission validation fires before any WAPI call."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure admin permission modify group=ops object=myobj",
                ctx,
            )

        out = capsys.readouterr().out
        assert "permission" in out.lower() or "Error" in out
        # No GET or PUT should have been issued
        assert not any(
            r.method in ("GET", "PUT") for r in requests_seen if "?_schema" not in str(r.url)
        )

    async def test_modify_permission_not_connected(self, capsys):
        ctx = Context()
        await process_line(
            "configure admin permission modify group=ops object=myobj permission=read",
            ctx,
        )
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Slice 4c - RADIUS (removed)
#
# `radius:user` and `radius:nas` were dropped from ibx-nios-sdk in 0.1.6 and
# do not exist on NIOS 9.1 ("Unknown object type"), so the CLI no longer
# registers commands for them. The grammar assertion below is what keeps
# them from creeping back in.
# ===========================================================================


def test_no_commands_reference_the_removed_radius_objects():
    """`auth radius` (radius:authservice) stays; radius user/device do not."""
    from ibcli.registry import COMMANDS

    dead = [k for k in COMMANDS if k.startswith(("configure radius ", "show radius "))]
    assert dead == [], f"removed RADIUS commands are back: {dead}"
    # The auth service is a different object and must survive.
    assert "show auth radius" in COMMANDS
    assert "configure auth radius add <name>" in COMMANDS
