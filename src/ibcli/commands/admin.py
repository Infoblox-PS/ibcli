# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Admin + RADIUS slice - slices 4a, 4b, 4c.

Command shapes:

  Slice 4a - users, groups, roles:
    configure admin user add <name> password=<value> [comment=<comment>]
    configure admin user <name> delete
    configure admin group add <name> [comment=<comment>]
    configure admin group <name> delete
    configure admin role add <name> [comment=<comment>]
    configure admin role <name> delete
    show admin user [<name>]
    show admin admin_group [<name>]
    show admin role [<name>]

  Slice 4b - permissions:
    configure admin permission add group=<name>|role=<name> object=<name> <read,write,deny>
    configure admin permission delete group=<name>|role=<name> object=<name>

  Slice 4c - RADIUS:
    configure radius user add <name> [password=<pw>] [comment=<text>]
    configure radius user <name> delete
    show radius user [<name>]
    configure radius device add <name> [address=<ip>] [shared_secret=<str>] [comment=<text>]
    configure radius device <name> delete
    show radius device [<name>]
"""

from __future__ import annotations

import re

from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict, format_extra_field, parse_extra_fields

# ---------------------------------------------------------------------------
# Helpers (duplicated from network.py / dhcp.py to keep modules independent)
# ---------------------------------------------------------------------------


def _parse_kv_all(line: str, key: str) -> list[str]:
    return [m.group(1) for m in re.finditer(rf"\b{re.escape(key)}[= ]+(\S+)", line)]


def _parse_kv(line: str, key: str) -> str | None:
    """Extract value for key from key=value or 'key value' form (dispatcher expands = to space)."""
    m = re.search(rf"\b{re.escape(key)}[= ](\S+)", line)
    return m.group(1) if m else None


def _parse_comment(line: str) -> str | None:
    """Extract comment value, supporting comment="quoted string" or comment=word or 'comment word'."""
    m = re.search(r'\bcomment[= ]"([^"]+)"', line)
    if m:
        return m.group(1)
    m = re.search(r"\bcomment[= ](\S+)", line)
    return m.group(1) if m else None


# ===========================================================================
# Slice 4a - Users, Groups, Roles
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - configure admin user / group / role
# ---------------------------------------------------------------------------

register("configure", words="admin", help="Create, modify or delete grid objects.")
register(
    "configure admin",
    words="user group role permission",
    help="Manage admin users, groups, roles, and permissions.",
)

# user
register(
    "configure admin user",
    words="add <name>",
    help="Local admin-user accounts (for non-SSO logins).",
)
register("configure admin user add", words="<name>")
register(
    "configure admin user add <name>",
    words="<cr> password=<value>|comment=<comment>|group=<name>",
)
register("configure admin user <name>", words="delete")
register("configure admin user <name> delete", words="<cr>")

# group
register(
    "configure admin group",
    words="add <name>",
    help="Groups that bundle admin users under shared roles.",
)
register("configure admin group add", words="<name>")
register(
    "configure admin group add <name>",
    words="<cr> comment=<comment>|role=<name>",
)
register("configure admin group <name>", words="delete")
register("configure admin group <name> delete", words="<cr>")

# role
register("configure admin role", words="add <name>", help="Admin roles - templates of permissions.")
register("configure admin role add", words="<name>")
register(
    "configure admin role add <name>",
    words="<cr> comment=<comment>",
)
register("configure admin role <name>", words="delete")
register("configure admin role <name> delete", words="<cr>")

# ---------------------------------------------------------------------------
# Waypoints - show admin user / admin_group / role
# ---------------------------------------------------------------------------

register("show", words="admin", help="Read grid state without modifying anything.")
register("show admin", words="user admin_group role", help="Show admin users, groups, and roles.")
register("show admin user", words="<cr> <name>")
register("show admin user <name>", words="<cr> fields=<field1,field2,...>")
register("show admin admin_group", words="<cr> <name>")
register("show admin admin_group <name>", words="<cr> fields=<field1,field2,...>")
register("show admin role", words="<cr> <name>")
register("show admin role <name>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Handler: configure admin user add <name> password=<value>
# ---------------------------------------------------------------------------


@command(
    "configure admin user add <name>",
    words="<cr> password=<value>|comment=<comment>|group=<name>",
    help="Add an admin user. group=<name> is repeatable and assigns the "
    "user to one or more admin groups (at least one is required).",
)
async def cli_add_admin_user(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\badmin user add\s+(\S+)", line)
    if not m:
        print("  Error: user name required")
        return
    name = m.group(1)

    password = _parse_kv(line, "password")
    if not password:
        print("  Error: password is required (password=<value>)")
        return

    body: dict = {"name": name, "password": password}

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    groups = _parse_kv_all(line, "group")
    if groups:
        body["admin_groups"] = groups

    await ctx.client.security.adminuser.create(body)


# ---------------------------------------------------------------------------
# Handler: configure admin user <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure admin user <name> delete",
    words="<cr>",
    help="Delete an admin user.",
)
async def cli_delete_admin_user(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\badmin user\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: user name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.security.adminuser.list(name=name)]
    if not results:
        print(f"  No admin user found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.adminuser.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show admin user [<name>]
# ---------------------------------------------------------------------------


@command("show admin user", words="<cr> <name>", help="List admin users.")
@command(
    "show admin user <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific admin user.",
)
async def cli_show_admin_user(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    # "show admin user [<name>]" → tokens[3] if present
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["name", "comment", "admin_groups"] + extra}
    if name_filter:
        kwargs["name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.adminuser.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("admin_groups"):
            groups = r["admin_groups"]
            if isinstance(groups, list):
                parts.append(f"groups={','.join(groups)}")
            else:
                parts.append(f"groups={groups}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: configure admin group add <name>
# ---------------------------------------------------------------------------


@command(
    "configure admin group add <name>",
    words="<cr> comment=<comment>|role=<name>",
    help="Add an admin group. role=<name> is repeatable.",
)
async def cli_add_admin_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\badmin group add\s+(\S+)", line)
    if not m:
        print("  Error: group name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    roles = _parse_kv_all(line, "role")
    if roles:
        body["roles"] = roles

    await ctx.client.security.admingroup.create(body)


# ---------------------------------------------------------------------------
# Handler: configure admin group <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure admin group <name> delete",
    words="<cr>",
    help="Delete an admin group.",
)
async def cli_delete_admin_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\badmin group\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: group name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.security.admingroup.list(name=name)]
    if not results:
        print(f"  No admin group found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.admingroup.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show admin admin_group [<name>]
# ---------------------------------------------------------------------------


@command("show admin admin_group", words="<cr> <name>", help="List admin groups.")
@command(
    "show admin admin_group <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific admin group.",
)
async def cli_show_admin_group(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    # "show admin admin_group [<name>]" → tokens[3] if present
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["name", "comment", "roles"] + extra}
    if name_filter:
        kwargs["name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.admingroup.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("roles"):
            roles = r["roles"]
            if isinstance(roles, list):
                parts.append(f"roles={','.join(roles)}")
            else:
                parts.append(f"roles={roles}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: configure admin role add <name>
# ---------------------------------------------------------------------------


@command(
    "configure admin role add <name>",
    words="<cr> comment=<comment>",
    help="Add an admin role.",
)
async def cli_add_admin_role(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\badmin role add\s+(\S+)", line)
    if not m:
        print("  Error: role name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.adminrole.create(body)


# ---------------------------------------------------------------------------
# Handler: configure admin role <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure admin role <name> delete",
    words="<cr>",
    help="Delete an admin role.",
)
async def cli_delete_admin_role(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\badmin role\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: role name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.security.adminrole.list(name=name)]
    if not results:
        print(f"  No admin role found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.adminrole.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show admin role [<name>]
# ---------------------------------------------------------------------------


@command("show admin role", words="<cr> <name>", help="List admin roles.")
@command(
    "show admin role <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific admin role.",
)
async def cli_show_admin_role(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    # "show admin role [<name>]" → tokens[3] if present
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["name", "comment"] + extra}
    if name_filter:
        kwargs["name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.adminrole.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Slice 4b - Permissions
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - configure admin permission
# ---------------------------------------------------------------------------

register(
    "configure admin permission",
    words="add delete modify",
    help="Grid permissions attached to roles.",
)
register(
    "configure admin permission add",
    words="<cr> group=<name>|role=<name>|object=<name>|read|write|deny",
)
register("configure admin permission delete", words="<cr> group=<name>|role=<name>|object=<name>")
register(
    "configure admin permission modify",
    words="<cr> group=<name>|role=<name>|object=<name>|permission=<name>",
)


# ---------------------------------------------------------------------------
# Handler: configure admin permission add group=<name>|role=<name> object=<name> <perm>
# ---------------------------------------------------------------------------


@command(
    "configure admin permission add",
    words="<cr> group=<name>|role=<name>|object=<name>|read|write|deny",
    help="Add a permission (specify group= XOR role=, object=, and read|write|deny).",
)
async def cli_add_admin_permission(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    group = _parse_kv(line, "group")
    role = _parse_kv(line, "role")
    obj = _parse_kv(line, "object")

    # Validate group XOR role
    if group and role:
        print("  Error: specify either group= or role=, not both")
        return
    if not group and not role:
        print("  Error: group= or role= is required")
        return

    # Extract permission keyword (read|write|deny) - last non-kv token after "add"
    perm_match = re.search(r"\b(read|write|deny)\b", line, re.IGNORECASE)
    if not perm_match:
        print("  Error: permission must be read, write, or deny")
        return
    perm = perm_match.group(1).upper()

    body: dict = {"permission": perm}
    if group:
        body["group"] = group
    else:
        body["role"] = role
    if obj:
        body["object"] = obj

    await ctx.client.security.permission.create(body)


# ---------------------------------------------------------------------------
# Handler: configure admin permission delete group=<name>|role=<name> object=<name>
# ---------------------------------------------------------------------------


@command(
    "configure admin permission delete",
    words="<cr> group=<name>|role=<name>|object=<name>",
    help="Delete a permission by group/role and object.",
)
async def cli_delete_admin_permission(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    group = _parse_kv(line, "group")
    role = _parse_kv(line, "role")
    obj = _parse_kv(line, "object")

    filters: dict = {}
    if group:
        filters["group"] = group
    if role:
        filters["role"] = role
    if obj:
        filters["object"] = obj

    results = [as_dict(r) async for r in ctx.client.security.permission.list(**filters)]
    if not results:
        print("  No permission found matching the criteria")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.permission.delete(ref)


# ---------------------------------------------------------------------------
# Handler: configure admin permission modify group=<g> role=<r> object=<o> permission=<p>
# ---------------------------------------------------------------------------


@command(
    "configure admin permission modify",
    words="<cr> group=<name>|role=<name>|object=<name>|permission=<name>",
    help="Modify an existing permission (GET-then-PUT).",
)
async def cli_modify_admin_permission(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    group = _parse_kv(line, "group")
    role = _parse_kv(line, "role")
    obj = _parse_kv(line, "object")
    # Extract 'permission' value only when it appears as kv, not the command word.
    # The command line contains 'permission modify ...' so we must match only
    # the kv-form 'permission <read|write|deny>' - use a whitelist regex.
    perm_m = re.search(r"\bpermission[= ](read|write|deny)\b", line, re.IGNORECASE)
    perm = perm_m.group(1) if perm_m else None

    if not perm:
        print("  Error: permission= is required (read|write|deny)")
        return

    filters: dict = {}
    if group:
        filters["group"] = group
    if role:
        filters["role"] = role
    if obj:
        filters["resource_type"] = obj

    results = [as_dict(r) async for r in ctx.client.security.permission.list(**filters)]
    if not results:
        print("  No permission found matching the criteria")
        return
    if len(results) > 1:
        print(f"  Error: {len(results)} permissions matched; refine the filter")
        return

    ref = results[0]["_ref"]
    await ctx.client.security.permission.update(ref, {"permission": perm.upper()})


# ===========================================================================
# Slice 4c - RADIUS (removed)
#
# `radius:user` and `radius:nas` no longer exist. NIOS 9.1 answers
# "Unknown object type (radius:user)" / "(radius:nas)", and ibx-nios-sdk
# dropped both resources in 0.1.6 after confirming that against a live grid.
# The commands could not work, so they are gone rather than left to fail at
# runtime: `configure radius user|device` and `show radius user|device`.
#
# Unaffected and still here: `configure auth radius` / `show auth radius`,
# which are `radius:authservice` - a different object that NIOS still has.
# ===========================================================================
