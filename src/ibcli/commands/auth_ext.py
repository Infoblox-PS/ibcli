# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Auth-extension commands - Phase 14.

Covers remaining security-domain gaps:

  Chunk A - Approval workflow + specialty users (FTP, SNMP, network, user profile)
  Chunk B - Parental control (avp, blocking_policy, subscriber, subscriber_record,
             subscriber_site)
  Chunk C - CA certificate (show/delete) + HSM (allgroups, entrust, thales)

Command vocabulary:

  # Approval workflow
  configure auth approval_workflow add <name> [approval_group=<ref>] [comment=<text>]
  configure auth approval_workflow <name> delete
  configure auth approval_workflow <name> set <key>=<value>
  show auth approval_workflow [<name>]

  # FTP user  (primary WAPI field: username, not name)
  configure auth ftp_user add <name> [password=<pw>] [comment=<text>]
  configure auth ftp_user <name> delete
  show auth ftp_user [<name>]

  # SNMP user
  configure auth snmp_user add <name> [password=<pw>] [comment=<text>]
  configure auth snmp_user <name> delete
  show auth snmp_user [<name>]

  # Read-only specialty
  show auth network_user [<name>]
  show auth user_profile

  # Parental control
  configure parental_control avp add <name> [comment=<text>]
  configure parental_control avp <name> delete
  show parental_control avp [<name>]

  configure parental_control blocking_policy add <name> [comment=<text>]
  configure parental_control blocking_policy <name> delete
  show parental_control blocking_policy [<name>]

  configure parental_control subscriber add <name> [comment=<text>]
  configure parental_control subscriber <name> delete
  show parental_control subscriber [<name>]

  show parental_control subscriber_record [<name>]

  configure parental_control subscriber_site add <name> [comment=<text>]
  configure parental_control subscriber_site <name> delete
  show parental_control subscriber_site [<name>]

  # CA certificate  (read-only fields; delete supported by ref)
  configure ca_certificate <ref> delete
  show ca_certificate [<name>]

  # HSM
  show hsm all
  configure hsm entrust add <name> [comment=<text>]
  configure hsm entrust <name> delete
  show hsm entrust [<name>]

  configure hsm thales add <name> [comment=<text>]
  configure hsm thales <name> delete
  show hsm thales [<name>]

SDK resources (all under ctx.client.security.*):
  approvalworkflow, ftpuser, snmpuser, networkuser, userprofile,
  parentalcontrol_avp, parentalcontrol_blockingpolicy,
  parentalcontrol_subscriber, parentalcontrol_subscriberrecord,
  parentalcontrol_subscribersite,
  cacertificate,
  hsm_allgroups, hsm_entrustnshieldgroup, hsm_thaleslunagroup

Notes:
  - approvalworkflow: no 'name' field; <name> arg maps to submitter_group
    (WAPI create-only field that identifies the workflow).
  - ftpuser: primary WAPI key is 'username', not 'name'.
  - networkuser: all identifying fields are read-only; list-only.
  - userprofile: read-only singleton (current user).
  - cacertificate: all business fields are read-only; show + delete only.
  - hsm_allgroups: read-only aggregate.
"""

from __future__ import annotations

import re

from ibcli import completions as _completions

# Re-use helpers already defined in auth.py - import selectively to avoid
# circular issues; these are pure-function utilities.
from ibcli.commands.auth import (
    _parse_comment,
    _parse_kv,
    _parse_set_kvs,
)
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict, format_extra_field, parse_extra_fields

# ===========================================================================
# Chunk A - Approval workflow + specialty users
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - top-level extensions to configure/show auth
# ---------------------------------------------------------------------------

# network_user and user_profile are read-only: only `show auth …` exists for
# them, so they must not appear under `configure auth`.
register(
    "configure auth",
    words="approval_workflow ftp_user snmp_user",
    help="Authentication services - LDAP, AD, RADIUS, TACACS+, SAML, cert.",
)
register(
    "show auth",
    words="approval_workflow ftp_user snmp_user network_user user_profile",
    help="Show authentication services.",
)

# ---------------------------------------------------------------------------
# Waypoints - approval_workflow
# ---------------------------------------------------------------------------

register(
    "configure auth approval_workflow",
    words="add <name>",
    help="Approval workflows - admin changes held pending approval.",
)
register("configure auth approval_workflow add", words="<name>")
register(
    "configure auth approval_workflow add <name>",
    words="<cr> approval_group=<value> comment=<comment>",
)
register("configure auth approval_workflow <name>", words="delete set")
register("configure auth approval_workflow <name> delete", words="<cr>")
register("configure auth approval_workflow <name> set", words="<cr> <key>=<value>")
register("show auth approval_workflow", words="<cr> <name>")
register("show auth approval_workflow <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure auth approval_workflow add <name>
# ---------------------------------------------------------------------------


@command(
    "configure auth approval_workflow add <name>",
    words="<cr> approval_group=<value> comment=<comment>",
    help="Add an approval workflow (submitter_group = <name>).",
)
async def cli_add_auth_approval_workflow(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth approval_workflow add\s+(\S+)", line)
    if not m:
        print("  Error: workflow name (submitter_group) required")
        return
    name = m.group(1)

    body: dict = {"submitter_group": name}
    approval_group = _parse_kv(line, "approval_group")
    if approval_group:
        body["approval_group"] = approval_group
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.approvalworkflow.create(body)


# ---------------------------------------------------------------------------
# Handler: configure auth approval_workflow <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure auth approval_workflow <name> delete",
    words="<cr>",
    help="Delete an approval workflow by submitter_group name.",
)
async def cli_delete_auth_approval_workflow(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth approval_workflow\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: workflow name required")
        return
    name = m.group(1)

    results = [
        as_dict(r) async for r in ctx.client.security.approvalworkflow.list(submitter_group=name)
    ]
    if not results:
        print(f"  No approval workflow found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.approvalworkflow.delete(ref)


# ---------------------------------------------------------------------------
# Handler: configure auth approval_workflow <name> set key=value
# ---------------------------------------------------------------------------


@command(
    "configure auth approval_workflow <name> set",
    words="<cr> <key>=<value>",
    help="Update fields on an approval workflow (GET-then-PUT).",
)
async def cli_set_auth_approval_workflow(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth approval_workflow\s+(\S+)\s+set\b", line)
    if not m:
        print("  Error: workflow name required")
        return
    name = m.group(1)

    updates = _parse_set_kvs(line)
    if not updates:
        print("  Error: at least one key=value pair is required")
        return

    results = [
        as_dict(r) async for r in ctx.client.security.approvalworkflow.list(submitter_group=name)
    ]
    if not results:
        print(f"  No approval workflow found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.approvalworkflow.update(ref, updates)


# ---------------------------------------------------------------------------
# Handler: show auth approval_workflow [<name>]
# ---------------------------------------------------------------------------


@command("show auth approval_workflow", words="<cr> <name>", help="List approval workflows.")
@command(
    "show auth approval_workflow <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific approval workflow.",
)
async def cli_show_auth_approval_workflow(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": ["submitter_group", "approval_group", "ticket_number"] + extra
    }
    if name_filter:
        kwargs["submitter_group"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.approvalworkflow.list(**kwargs)]

    for r in results:
        parts = [f"submitter_group={r.get('submitter_group', '')}"]
        if r.get("approval_group"):
            parts.append(f"approval_group={r['approval_group']}")
        if r.get("ticket_number"):
            parts.append(f"ticket_number={r['ticket_number']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Waypoints - FTP user
# ---------------------------------------------------------------------------

register(
    "configure auth ftp_user",
    words="add <name>",
    help="FTP users allowed to push/pull CSV and backups over FTP.",
)
register("configure auth ftp_user add", words="<name>")
register(
    "configure auth ftp_user add <name>",
    words="<cr> password=<value> comment=<comment>",
)
register("configure auth ftp_user <name>", words="delete")
register("configure auth ftp_user <name> delete", words="<cr>")
register("show auth ftp_user", words="<cr> <name>")
register("show auth ftp_user <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure auth ftp_user add <name>
# ---------------------------------------------------------------------------


@command(
    "configure auth ftp_user add <name>",
    words="<cr> password=<value> comment=<comment>",
    help="Add an FTP user (username = <name>).",
)
async def cli_add_auth_ftp_user(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth ftp_user add\s+(\S+)", line)
    if not m:
        print("  Error: FTP username required")
        return
    username = m.group(1)

    body: dict = {"username": username}
    pw = _parse_kv(line, "password")
    if pw:
        body["password"] = pw
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.ftpuser.create(body)


# ---------------------------------------------------------------------------
# Handler: configure auth ftp_user <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure auth ftp_user <name> delete",
    words="<cr>",
    help="Delete an FTP user.",
)
async def cli_delete_auth_ftp_user(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth ftp_user\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: FTP username required")
        return
    username = m.group(1)

    results = [as_dict(r) async for r in ctx.client.security.ftpuser.list(username=username)]
    if not results:
        print(f"  No FTP user found: {username}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.ftpuser.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show auth ftp_user [<name>]
# ---------------------------------------------------------------------------


@command("show auth ftp_user", words="<cr> <name>", help="List FTP users.")
@command(
    "show auth ftp_user <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific FTP user.",
)
async def cli_show_auth_ftp_user(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["username", "home_dir", "permission"] + extra}
    if name_filter:
        kwargs["username"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.ftpuser.list(**kwargs)]

    for r in results:
        parts = [f"username={r.get('username', '')}"]
        if r.get("home_dir"):
            parts.append(f"home_dir={r['home_dir']}")
        if r.get("permission"):
            parts.append(f"permission={r['permission']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Waypoints - SNMP user
# ---------------------------------------------------------------------------

register("configure auth snmp_user", words="add <name>", help="SNMPv3 users for grid SNMP access.")
register("configure auth snmp_user add", words="<name>")
register(
    "configure auth snmp_user add <name>",
    words="<cr> password=<value> comment=<comment>",
)
register("configure auth snmp_user <name>", words="delete")
register("configure auth snmp_user <name> delete", words="<cr>")
register("show auth snmp_user", words="<cr> <name>")
register("show auth snmp_user <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure auth snmp_user add <name>
# ---------------------------------------------------------------------------


@command(
    "configure auth snmp_user add <name>",
    words="<cr> password=<value> comment=<comment>",
    help="Add an SNMP user.",
)
async def cli_add_auth_snmp_user(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth snmp_user add\s+(\S+)", line)
    if not m:
        print("  Error: SNMP username required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    pw = _parse_kv(line, "password")
    if pw:
        body["authentication_password"] = pw
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.snmpuser.create(body)


# ---------------------------------------------------------------------------
# Handler: configure auth snmp_user <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure auth snmp_user <name> delete",
    words="<cr>",
    help="Delete an SNMP user.",
)
async def cli_delete_auth_snmp_user(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth snmp_user\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: SNMP username required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.security.snmpuser.list(name=name)]
    if not results:
        print(f"  No SNMP user found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.snmpuser.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show auth snmp_user [<name>]
# ---------------------------------------------------------------------------


@command("show auth snmp_user", words="<cr> <name>", help="List SNMP users.")
@command(
    "show auth snmp_user <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific SNMP user.",
)
async def cli_show_auth_snmp_user(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": [
            "name",
            "comment",
            "disable",
            "authentication_protocol",
            "privacy_protocol",
        ]
        + extra
    }
    if name_filter:
        kwargs["name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.snmpuser.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("authentication_protocol"):
            parts.append(f"auth_protocol={r['authentication_protocol']}")
        if r.get("privacy_protocol"):
            parts.append(f"privacy_protocol={r['privacy_protocol']}")
        if r.get("disable") is not None:
            parts.append(f"disable={r['disable']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Waypoints - network_user (read-only list)
# ---------------------------------------------------------------------------

register("show auth network_user", words="<cr> <name>")
register("show auth network_user <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: show auth network_user [<name>]
# ---------------------------------------------------------------------------


@command("show auth network_user", words="<cr> <name>", help="List network users (read-only).")
@command(
    "show auth network_user <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific network user (read-only).",
)
async def cli_show_auth_network_user(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": ["name", "address", "user_status", "domainname", "network"] + extra
    }
    if name_filter:
        kwargs["name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.networkuser.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("address"):
            parts.append(f"address={r['address']}")
        if r.get("user_status"):
            parts.append(f"status={r['user_status']}")
        if r.get("domainname"):
            parts.append(f"domain={r['domainname']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Waypoints - user_profile (read-only singleton)
# ---------------------------------------------------------------------------

register("show auth user_profile", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: show auth user_profile
# ---------------------------------------------------------------------------


@command(
    "show auth user_profile",
    words="<cr> fields=<field1,field2,...>",
    help="Show the current user's profile (read-only singleton).",
)
async def cli_show_auth_user_profile(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": [
            "name",
            "admin_group",
            "user_type",
            "email",
            "last_login",
        ]
        + extra
    }
    results = [as_dict(r) async for r in ctx.client.security.userprofile.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("admin_group"):
            parts.append(f"admin_group={r['admin_group']}")
        if r.get("user_type"):
            parts.append(f"user_type={r['user_type']}")
        if r.get("email"):
            parts.append(f"email={r['email']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Chunk B - Parental control
# ===========================================================================

# ---------------------------------------------------------------------------
# Top-level waypoints
# ---------------------------------------------------------------------------

register("configure", words="parental_control hsm", help="Create, modify or delete grid objects.")
register("show", words="parental_control hsm", help="Read grid state without modifying anything.")
register(
    "configure parental_control",
    words="avp blocking_policy subscriber subscriber_site",
    help="Parental-control policies, sites, subscribers.",
)
register(
    "show parental_control",
    words="avp blocking_policy subscriber subscriber_record subscriber_site",
    help="Parental-control AVPs, policies, subscribers.",
)

# ---------------------------------------------------------------------------
# Waypoints - parental_control avp
# ---------------------------------------------------------------------------

register("configure parental_control avp", words="add <name>")
register("configure parental_control avp add", words="<name>")
register(
    "configure parental_control avp add <name>",
    words="<cr> comment=<comment>",
)
register("configure parental_control avp <name>", words="delete")
register("configure parental_control avp <name> delete", words="<cr>")
register("show parental_control avp", words="<cr> <name>")
register("show parental_control avp <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure parental_control avp add <name>
# ---------------------------------------------------------------------------


@command(
    "configure parental_control avp add <name>",
    words="<cr> comment=<comment>",
    help="Add a parental-control AVP definition.",
)
async def cli_add_pc_avp(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bparental_control avp add\s+(\S+)", line)
    if not m:
        print("  Error: AVP name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.parentalcontrol_avp.create(body)


# ---------------------------------------------------------------------------
# Handler: configure parental_control avp <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure parental_control avp <name> delete",
    words="<cr>",
    help="Delete a parental-control AVP definition.",
)
async def cli_delete_pc_avp(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bparental_control avp\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: AVP name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.security.parentalcontrol_avp.list(name=name)]
    if not results:
        print(f"  No parental-control AVP found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.parentalcontrol_avp.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show parental_control avp [<name>]
# ---------------------------------------------------------------------------


@command("show parental_control avp", words="<cr> <name>", help="List parental-control AVPs.")
@command(
    "show parental_control avp <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific parental-control AVP.",
)
async def cli_show_pc_avp(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": ["name", "type", "value_type", "vendor_id", "comment"] + extra
    }
    if name_filter:
        kwargs["name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.parentalcontrol_avp.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("type") is not None:
            parts.append(f"type={r['type']}")
        if r.get("value_type"):
            parts.append(f"value_type={r['value_type']}")
        if r.get("vendor_id") is not None:
            parts.append(f"vendor_id={r['vendor_id']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Waypoints - parental_control blocking_policy
# ---------------------------------------------------------------------------

register("configure parental_control blocking_policy", words="add <name>")
register("configure parental_control blocking_policy add", words="<name>")
register(
    "configure parental_control blocking_policy add <name>",
    words="<cr> comment=<comment>",
)
register("configure parental_control blocking_policy <name>", words="delete")
register("configure parental_control blocking_policy <name> delete", words="<cr>")
register("show parental_control blocking_policy", words="<cr> <name>")
register("show parental_control blocking_policy <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure parental_control blocking_policy add <name>
# ---------------------------------------------------------------------------


@command(
    "configure parental_control blocking_policy add <name>",
    words="<cr> comment=<comment>",
    help="Add a parental-control blocking policy.",
)
async def cli_add_pc_blocking_policy(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bparental_control blocking_policy add\s+(\S+)", line)
    if not m:
        print("  Error: blocking policy name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.parentalcontrol_blockingpolicy.create(body)


# ---------------------------------------------------------------------------
# Handler: configure parental_control blocking_policy <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure parental_control blocking_policy <name> delete",
    words="<cr>",
    help="Delete a parental-control blocking policy.",
)
async def cli_delete_pc_blocking_policy(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bparental_control blocking_policy\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: blocking policy name required")
        return
    name = m.group(1)

    results = [
        as_dict(r) async for r in ctx.client.security.parentalcontrol_blockingpolicy.list(name=name)
    ]
    if not results:
        print(f"  No blocking policy found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.parentalcontrol_blockingpolicy.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show parental_control blocking_policy [<name>]
# ---------------------------------------------------------------------------


@command(
    "show parental_control blocking_policy",
    words="<cr> <name>",
    help="List parental-control blocking policies.",
)
@command(
    "show parental_control blocking_policy <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific parental-control blocking policy.",
)
async def cli_show_pc_blocking_policy(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["name", "value"] + extra}
    if name_filter:
        kwargs["name"] = name_filter

    results = [
        as_dict(r) async for r in ctx.client.security.parentalcontrol_blockingpolicy.list(**kwargs)
    ]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("value"):
            parts.append(f"value={r['value']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Waypoints - parental_control subscriber
# ---------------------------------------------------------------------------

register("configure parental_control subscriber", words="add <name>")
register("configure parental_control subscriber add", words="<name>")
register(
    "configure parental_control subscriber add <name>",
    words="<cr> comment=<comment>",
)
register("configure parental_control subscriber <name>", words="delete")
register("configure parental_control subscriber <name> delete", words="<cr>")
register("show parental_control subscriber", words="<cr> <name>")
register("show parental_control subscriber <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure parental_control subscriber add <name>
# ---------------------------------------------------------------------------


@command(
    "configure parental_control subscriber add <name>",
    words="<cr> comment=<comment>",
    help="Add a parental-control subscriber configuration.",
)
async def cli_add_pc_subscriber(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bparental_control subscriber add\s+(\S+)", line)
    if not m:
        print("  Error: subscriber_id required")
        return
    subscriber_id = m.group(1)

    body: dict = {"subscriber_id": subscriber_id}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.parentalcontrol_subscriber.create(body)


# ---------------------------------------------------------------------------
# Handler: configure parental_control subscriber <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure parental_control subscriber <name> delete",
    words="<cr>",
    help="Delete a parental-control subscriber configuration.",
)
async def cli_delete_pc_subscriber(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bparental_control subscriber\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: subscriber_id required")
        return
    subscriber_id = m.group(1)

    results = [
        as_dict(r)
        async for r in ctx.client.security.parentalcontrol_subscriber.list(
            subscriber_id=subscriber_id
        )
    ]
    if not results:
        print(f"  No subscriber configuration found: {subscriber_id}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.parentalcontrol_subscriber.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show parental_control subscriber [<name>]
# ---------------------------------------------------------------------------


@command(
    "show parental_control subscriber",
    words="<cr> <name>",
    help="List parental-control subscriber configurations.",
)
@command(
    "show parental_control subscriber <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific parental-control subscriber configuration.",
)
async def cli_show_pc_subscriber(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": [
            "subscriber_id",
            "enable_parental_control",
            "pc_zone_name",
            "category_url",
        ]
        + extra
    }
    if name_filter:
        kwargs["subscriber_id"] = name_filter

    results = [
        as_dict(r) async for r in ctx.client.security.parentalcontrol_subscriber.list(**kwargs)
    ]

    for r in results:
        parts = [f"subscriber_id={r.get('subscriber_id', '')}"]
        if r.get("enable_parental_control") is not None:
            parts.append(f"enabled={r['enable_parental_control']}")
        if r.get("pc_zone_name"):
            parts.append(f"zone={r['pc_zone_name']}")
        if r.get("category_url"):
            parts.append(f"category_url={r['category_url']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Waypoints - parental_control subscriber_record (read-only)
# ---------------------------------------------------------------------------

register("show parental_control subscriber_record", words="<cr> <name>")
register("show parental_control subscriber_record <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: show parental_control subscriber_record [<name>]
# ---------------------------------------------------------------------------


@command(
    "show parental_control subscriber_record",
    words="<cr> <name>",
    help="List parental-control subscriber records (read-only).",
)
@command(
    "show parental_control subscriber_record <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific parental-control subscriber record (read-only).",
)
async def cli_show_pc_subscriber_record(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": [
            "subscriber_id",
            "ip_addr",
            "site",
            "parental_control_policy",
        ]
        + extra
    }
    if name_filter:
        kwargs["subscriber_id"] = name_filter

    results = [
        as_dict(r)
        async for r in ctx.client.security.parentalcontrol_subscriberrecord.list(**kwargs)
    ]

    for r in results:
        parts = [f"subscriber_id={r.get('subscriber_id', '')}"]
        if r.get("ip_addr"):
            parts.append(f"ip_addr={r['ip_addr']}")
        if r.get("site"):
            parts.append(f"site={r['site']}")
        if r.get("parental_control_policy"):
            parts.append(f"policy={r['parental_control_policy']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Waypoints - parental_control subscriber_site
# ---------------------------------------------------------------------------

register("configure parental_control subscriber_site", words="add <name>")
register("configure parental_control subscriber_site add", words="<name>")
register(
    "configure parental_control subscriber_site add <name>",
    words="<cr> comment=<comment>",
)
register("configure parental_control subscriber_site <name>", words="delete")
register("configure parental_control subscriber_site <name> delete", words="<cr>")
register("show parental_control subscriber_site", words="<cr> <name>")
register("show parental_control subscriber_site <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure parental_control subscriber_site add <name>
# ---------------------------------------------------------------------------


@command(
    "configure parental_control subscriber_site add <name>",
    words="<cr> comment=<comment>",
    help="Add a parental-control subscriber site.",
)
async def cli_add_pc_subscriber_site(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bparental_control subscriber_site add\s+(\S+)", line)
    if not m:
        print("  Error: site name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.parentalcontrol_subscribersite.create(body)


# ---------------------------------------------------------------------------
# Handler: configure parental_control subscriber_site <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure parental_control subscriber_site <name> delete",
    words="<cr>",
    help="Delete a parental-control subscriber site.",
)
async def cli_delete_pc_subscriber_site(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bparental_control subscriber_site\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: site name required")
        return
    name = m.group(1)

    results = [
        as_dict(r) async for r in ctx.client.security.parentalcontrol_subscribersite.list(name=name)
    ]
    if not results:
        print(f"  No subscriber site found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.parentalcontrol_subscribersite.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show parental_control subscriber_site [<name>]
# ---------------------------------------------------------------------------


@command(
    "show parental_control subscriber_site",
    words="<cr> <name>",
    help="List parental-control subscriber sites.",
)
@command(
    "show parental_control subscriber_site <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific parental-control subscriber site.",
)
async def cli_show_pc_subscriber_site(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": [
            "name",
            "blocking_ipv4_vip1",
            "blocking_ipv4_vip2",
            "maximum_subscribers",
            "comment",
        ]
        + extra
    }
    if name_filter:
        kwargs["name"] = name_filter

    results = [
        as_dict(r) async for r in ctx.client.security.parentalcontrol_subscribersite.list(**kwargs)
    ]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("blocking_ipv4_vip1"):
            parts.append(f"vip1={r['blocking_ipv4_vip1']}")
        if r.get("blocking_ipv4_vip2"):
            parts.append(f"vip2={r['blocking_ipv4_vip2']}")
        if r.get("maximum_subscribers") is not None:
            parts.append(f"max_subscribers={r['maximum_subscribers']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Chunk C - CA certificate + HSM
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - ca_certificate  (show + delete; all fields are read-only)
# ---------------------------------------------------------------------------

register("configure", words="ca_certificate", help="Create, modify or delete grid objects.")
register("show", words="ca_certificate hsm", help="Read grid state without modifying anything.")
register(
    "configure ca_certificate", words="<name>", help="CA certificates trusted by grid TLS stacks."
)
register("configure ca_certificate <name>", words="delete")
register("configure ca_certificate <name> delete", words="<cr>")
register(
    "show ca_certificate",
    words="<cr> <name>",
    dynamic=_completions.ca_certificates,
    help="List trusted CA certificates.",
)
register("show ca_certificate <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure ca_certificate <ref> delete
# ---------------------------------------------------------------------------


@command(
    "configure ca_certificate <name> delete",
    words="<cr>",
    help="Delete a CA certificate by ref (all data fields are read-only).",
)
async def cli_delete_ca_certificate(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bca_certificate\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: certificate ref or distinguished name required")
        return
    # A distinguished name contains '=', so it has to be quoted to survive
    # the tokenizer; strip the quotes back off before using it.
    token = m.group(1).strip('"')

    # Accept either a WAPI _ref or the distinguished name shown by
    # `show ca_certificate`. Passing a bare name straight to the SDK raises
    # ValueError, so resolve it to a ref first.
    if token.startswith("cacertificate/"):
        ref = token
    else:
        results = [
            as_dict(r)
            async for r in ctx.client.security.cacertificate.list(distinguished_name=token)
        ]
        if not results:
            print(f"  No CA certificate found: {token}")
            return
        ref = results[0]["_ref"]
    await ctx.client.security.cacertificate.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show ca_certificate [<name>]
# ---------------------------------------------------------------------------


@command("show ca_certificate", words="<cr> <name>", help="List CA certificates.")
@command(
    "show ca_certificate <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific CA certificate.",
)
async def cli_show_ca_certificate(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    if len(tokens) >= 3 and not tokens[2].startswith("<") and "=" not in tokens[2]:
        name_filter = tokens[2]

    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": ["distinguished_name", "issuer", "serial", "valid_not_after"] + extra
    }
    if name_filter:
        kwargs["distinguished_name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.cacertificate.list(**kwargs)]

    for r in results:
        parts = [f"dn={r.get('distinguished_name', '')}"]
        if r.get("issuer"):
            parts.append(f"issuer={r['issuer']}")
        if r.get("serial"):
            parts.append(f"serial={r['serial']}")
        if r.get("valid_not_after") is not None:
            parts.append(f"expires={r['valid_not_after']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Waypoints - HSM
# ---------------------------------------------------------------------------

register(
    "configure hsm",
    words="entrust thales",
    help="Hardware Security Module (HSM) group configuration.",
)
register("show hsm", words="all entrust thales", help="HSM groups currently configured.")

register("configure hsm entrust", words="add <name>", help="Entrust nShield HSM groups.")
register("configure hsm entrust add", words="<name>")
register(
    "configure hsm entrust add <name>",
    words="<cr> comment=<comment>",
)
register("configure hsm entrust <name>", words="delete")
register("configure hsm entrust <name> delete", words="<cr>")
register("show hsm all", words="<cr> fields=<field1,field2,...>")
register("show hsm entrust", words="<cr> <name>")
register("show hsm entrust <name>", words="<cr> fields=<field1,field2,...>")

register("configure hsm thales", words="add <name>", help="Thales Luna HSM groups.")
register("configure hsm thales add", words="<name>")
register(
    "configure hsm thales add <name>",
    words="<cr> comment=<comment>",
)
register("configure hsm thales <name>", words="delete")
register("configure hsm thales <name> delete", words="<cr>")
register("show hsm thales", words="<cr> <name>")
register("show hsm thales <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: show hsm all  (aggregate, read-only)
# ---------------------------------------------------------------------------


@command(
    "show hsm all",
    words="<cr> fields=<field1,field2,...>",
    help="Show aggregate HSM group list (read-only).",
)
async def cli_show_hsm_all(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["groups"] + extra}
    results = [as_dict(r) async for r in ctx.client.security.hsm_allgroups.list(**kwargs)]

    for r in results:
        groups = r.get("groups") or []
        if groups:
            print(f"groups={','.join(groups) if isinstance(groups, list) else groups}")
        else:
            print("  (no HSM groups configured)")
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: configure hsm entrust add <name>
# ---------------------------------------------------------------------------


@command(
    "configure hsm entrust add <name>",
    words="<cr> comment=<comment>",
    help="Add an Entrust nShield HSM group.",
)
async def cli_add_hsm_entrust(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bhsm entrust add\s+(\S+)", line)
    if not m:
        print("  Error: Entrust group name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.hsm_entrustnshieldgroup.create(body)


# ---------------------------------------------------------------------------
# Handler: configure hsm entrust <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure hsm entrust <name> delete",
    words="<cr>",
    help="Delete an Entrust nShield HSM group.",
)
async def cli_delete_hsm_entrust(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bhsm entrust\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: Entrust group name required")
        return
    name = m.group(1)

    results = [
        as_dict(r) async for r in ctx.client.security.hsm_entrustnshieldgroup.list(name=name)
    ]
    if not results:
        print(f"  No Entrust HSM group found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.hsm_entrustnshieldgroup.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show hsm entrust [<name>]
# ---------------------------------------------------------------------------


@command("show hsm entrust", words="<cr> <name>", help="List Entrust nShield HSM groups.")
@command(
    "show hsm entrust <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific Entrust nShield HSM group.",
)
async def cli_show_hsm_entrust(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["name", "comment", "status", "key_server_ip"] + extra}
    if name_filter:
        kwargs["name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.hsm_entrustnshieldgroup.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("status"):
            parts.append(f"status={r['status']}")
        if r.get("key_server_ip"):
            parts.append(f"key_server={r['key_server_ip']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: configure hsm thales add <name>
# ---------------------------------------------------------------------------


@command(
    "configure hsm thales add <name>",
    words="<cr> comment=<comment>",
    help="Add a Thales Luna HSM group.",
)
async def cli_add_hsm_thales(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bhsm thales add\s+(\S+)", line)
    if not m:
        print("  Error: Thales group name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.hsm_thaleslunagroup.create(body)


# ---------------------------------------------------------------------------
# Handler: configure hsm thales <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure hsm thales <name> delete",
    words="<cr>",
    help="Delete a Thales Luna HSM group.",
)
async def cli_delete_hsm_thales(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bhsm thales\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: Thales group name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.security.hsm_thaleslunagroup.list(name=name)]
    if not results:
        print(f"  No Thales Luna HSM group found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.hsm_thaleslunagroup.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show hsm thales [<name>]
# ---------------------------------------------------------------------------


@command("show hsm thales", words="<cr> <name>", help="List Thales Luna HSM groups.")
@command(
    "show hsm thales <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific Thales Luna HSM group.",
)
async def cli_show_hsm_thales(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["name", "comment", "status", "hsm_version"] + extra}
    if name_filter:
        kwargs["name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.hsm_thaleslunagroup.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("status"):
            parts.append(f"status={r['status']}")
        if r.get("hsm_version"):
            parts.append(f"version={r['hsm_version']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")
