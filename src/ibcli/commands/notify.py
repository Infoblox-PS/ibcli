# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""ACL and Notification command handlers - Phase 12.

Provides ``configure acl`` / ``show acl`` and
``configure notification`` / ``show notification`` command trees.

Command vocabulary summary
--------------------------
# ACL - namedacl (full CRUD)
configure acl add <name> [access_list=<cidr>,<cidr>...] [comment=<text>]
configure acl <name> delete
configure acl <name> set <key>=<value>
show acl [<name>]

# Notification - REST endpoint (full CRUD)
configure notification endpoint add <name> uri=<url> [comment=<text>]
configure notification endpoint <name> delete
configure notification endpoint <name> set <key>=<value>
show notification endpoint [<name>]

# Notification - REST template (GET/PUT/DELETE - system-generated, no POST)
configure notification template <name> delete
configure notification template <name> set <key>=<value>
show notification template [<name>]

# Notification - Rule (full CRUD)
configure notification rule add <name> event_type=<str> [comment=<text>]
configure notification rule <name> delete
configure notification rule <name> set <key>=<value>
show notification rule [<name>]
"""

from __future__ import annotations

import re

from ibcli import completions as _completions
from ibcli.coerce import coerce as _coerce  # noqa: F401
from ibcli.completions_keys import keys_completer_for_path
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict, format_extra_field, parse_extra_fields

_ACL_KEYS = keys_completer_for_path("acl", "namedacl")
_NOTIF_ENDPOINT_KEYS = keys_completer_for_path("notification", "rest_endpoint")
_NOTIF_TEMPLATE_KEYS = keys_completer_for_path("notification", "rest_template")
_NOTIF_RULE_KEYS = keys_completer_for_path("notification", "rule")


def _acls_with_all(ctx: Context) -> list[tuple[str, str]]:
    """ACL name completions with 'all' prepended so users can dump everything."""
    return [("all", "show every named ACL")] + list(_completions.acls(ctx))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _kv(line: str, key: str) -> str | None:
    """Extract value for *key* from 'key value' or 'key=value' forms."""
    m = re.search(rf"\b{re.escape(key)}[= ](\S+)", line)
    return m.group(1) if m else None


def _comment(line: str) -> str | None:
    """Extract a quoted or unquoted comment value."""
    m = re.search(r'\bcomment[= ]"([^"]+)"', line)
    if m:
        return m.group(1)
    m = re.search(r"\bcomment[= ](\S+)", line)
    return m.group(1) if m else None


def _parse_inline_kvs(line: str, marker: str) -> dict:
    """Parse key/value pairs appearing after *marker* in *line*.

    Handles both ``key=value`` (raw input) and ``key value`` forms.
    """
    idx = line.find(marker)
    if idx == -1:
        return {}
    tail = line[idx + len(marker) :].strip()
    if not tail:
        return {}

    result: dict = {}
    tokens = tail.split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if "=" in tok:
            k, _, v = tok.partition("=")
            if k and v:
                result[k] = _coerce(v)
            i += 1
        elif i + 1 < len(tokens):
            k, v = tok, tokens[i + 1]
            result[k] = _coerce(v)
            i += 2
        else:
            i += 1
    return result


def _not_connected() -> None:
    print("  Not connected")


# ===========================================================================
# Chunk A: ACL - namedacl (full CRUD)
# ===========================================================================

register("configure", words="acl", help="Create, modify or delete grid objects.")
register("show", words="acl", help="Read grid state without modifying anything.")
register(
    "configure acl",
    words="add <name>",
    help="Manage Named ACLs - reusable access-list objects for DNS/DHCP.",
)
register("configure acl add", words="<name>")
register("configure acl add <name>", words="<cr> access_list=<value>|comment=<comment>")

_ACL_ADD_WORDS = "<cr> access_list=<value>|comment=<comment>"


@command(
    "configure acl add <name>",
    words=_ACL_ADD_WORDS,
    help="Add a named ACL.",
)
async def cli_acl_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bacl add (\S+)", line)
    if not m:
        print("  Error: ACL name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    # access_list is a comma-separated list of CIDRs/addresses with permission
    # CLI convenience: access_list=<cidr>,<cidr>... sets address-only entries (ALLOW)
    al_raw = _kv(line, "access_list")
    if al_raw:
        entries = [
            {"_struct": "addressac", "address": addr, "permission": "ALLOW"}
            for addr in al_raw.split(",")
            if addr
        ]
        if entries:
            body["access_list"] = entries
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.acl.namedacl.create(body)


register("configure acl <name>", words="delete set")
register("configure acl <name> delete", words="<cr>")


@command(
    "configure acl <name> delete",
    words="<cr>",
    help="Delete a named ACL.",
)
async def cli_acl_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bacl (\S+) delete", line)
    if not m:
        print("  Error: ACL name required")
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.acl.namedacl.list(name=name, max_results=1)]
    if not results:
        print(f"  No named ACL found: {name}")
        return
    await ctx.client.acl.namedacl.delete(results[0]["_ref"])


register("configure acl <name> set", words="<key>=<value>", dynamic=_ACL_KEYS)


@command(
    "configure acl <name> set",
    words="<key>=<value>",
    help="Set fields on a named ACL.",
)
async def cli_acl_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bacl (\S+) set\b", line)
    if not m:
        print("  Error: ACL name required")
        return
    name = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [as_dict(r) async for r in ctx.client.acl.namedacl.list(name=name, max_results=1)]
    if not results:
        print(f"  No named ACL found: {name}")
        return
    await ctx.client.acl.namedacl.update(results[0]["_ref"], body)


register(
    "show acl",
    words="<cr> <name>",
    dynamic=_acls_with_all,
    help="List Named ACLs. Use 'all' for every ACL, or a name to filter.",
)
register("show acl <name>", words="<cr> fields=<field1,field2,...>")


@command("show acl", words="<cr> <name>", help="Show named ACLs.")
@command(
    "show acl <name>", words="<cr> fields=<field1,field2,...>", help="Show a specific named ACL."
)
async def cli_acl_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show acl [<name>|all]
    name = None
    if len(tokens) >= 3:
        candidate = tokens[2]
        if not candidate.startswith("<") and candidate != "all" and "=" not in candidate:
            name = candidate
    extra = parse_extra_fields(line)
    params: dict = {"return_fields": ["name", "comment", "access_list"]}
    if extra:
        params["return_fields_plus"] = extra
    if name:
        params["name"] = name
    acls = [as_dict(r) async for r in ctx.client.acl.namedacl.list(**params)]
    if not acls:
        if name:
            print(f"  No named ACL found: {name}")
        return
    for a in acls:
        access_list = a.pop("access_list", None) or []
        parts = [f"name={a.get('name', '')}"]
        if a.get("comment"):
            parts.append(f"comment={a['comment']}")
        print(" ".join(parts))
        if access_list:
            perm_w = max((len(str(e.get("permission", ""))) for e in access_list), default=0)
            for entry in access_list:
                perm = str(entry.get("permission", ""))
                addr = entry.get("address") or entry.get("tsig_key_name") or ""
                print(f"    {perm:<{perm_w}}  {addr}")
        for f in extra:
            val = a.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Chunk B: Notification - REST endpoint (full CRUD)
# ===========================================================================

register("configure", words="notification", help="Create, modify or delete grid objects.")
register("show", words="notification", help="Read grid state without modifying anything.")
register(
    "configure notification",
    words="endpoint template rule",
    help="Notification REST endpoints and rules (outbound webhooks).",
)
register(
    "show notification",
    words="endpoint template rule",
    help="Notification endpoints, rules, templates.",
)

# --- endpoint ---
register(
    "configure notification endpoint",
    words="add <name>",
    help="REST webhook endpoint (where notifications POST to).",
)
register("configure notification endpoint add", words="<name>")
register(
    "configure notification endpoint add <name>",
    words="uri=<name>|outbound_member_type=<name>|comment=<comment>",
)

# WAPI requires both uri and outbound_member_type when creating a rest
# endpoint (valid values for the latter are GM and MEMBER). We default to
# GM when the user omits it so the command stays usable on any grid.
_ENDPOINT_ADD_WORDS = "uri=<name>|outbound_member_type=<name>|comment=<comment>"
_DEFAULT_OUTBOUND_MEMBER_TYPE = "GM"


@command(
    "configure notification endpoint add <name>",
    words=_ENDPOINT_ADD_WORDS,
    help="Add a notification REST endpoint.",
)
async def cli_notification_endpoint_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bnotification endpoint add (\S+)", line)
    if not m:
        print("  Error: endpoint name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    uri = _kv(line, "uri")
    if uri:
        body["uri"] = uri
    body["outbound_member_type"] = (
        _kv(line, "outbound_member_type") or _DEFAULT_OUTBOUND_MEMBER_TYPE
    )
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.notification.rest_endpoint.create(body)


register("configure notification endpoint <name>", words="delete set")
register("configure notification endpoint <name> delete", words="<cr>")


@command(
    "configure notification endpoint <name> delete",
    words="<cr>",
    help="Delete a notification REST endpoint.",
)
async def cli_notification_endpoint_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bnotification endpoint (\S+) delete", line)
    if not m:
        print("  Error: endpoint name required")
        return
    name = m.group(1)
    results = [
        as_dict(r)
        async for r in ctx.client.notification.rest_endpoint.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No notification endpoint found: {name}")
        return
    await ctx.client.notification.rest_endpoint.delete(results[0]["_ref"])


register(
    "configure notification endpoint <name> set",
    words="<key>=<value>",
    dynamic=_NOTIF_ENDPOINT_KEYS,
)


@command(
    "configure notification endpoint <name> set",
    words="<key>=<value>",
    help="Set fields on a notification REST endpoint.",
)
async def cli_notification_endpoint_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bnotification endpoint (\S+) set\b", line)
    if not m:
        print("  Error: endpoint name required")
        return
    name = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [
        as_dict(r)
        async for r in ctx.client.notification.rest_endpoint.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No notification endpoint found: {name}")
        return
    await ctx.client.notification.rest_endpoint.update(results[0]["_ref"], body)


register("show notification endpoint", words="<cr> <name>")
register("show notification endpoint <name>", words="<cr> fields=<field1,field2,...>")


@command(
    "show notification endpoint", words="<cr> <name>", help="Show notification REST endpoints."
)
@command(
    "show notification endpoint <name>",
    words="<cr>",
    help="Show a specific notification REST endpoint.",
)
async def cli_notification_endpoint_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show notification endpoint [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    endpoints = [as_dict(r) async for r in ctx.client.notification.rest_endpoint.list(**params)]
    if not endpoints:
        if name:
            print(f"  No notification endpoint found: {name}")
        return
    for ep in endpoints:
        parts = ["type=notification:rest:endpoint"]
        for k, v in ep.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# ===========================================================================
# Chunk C: Notification - REST template (GET/PUT/DELETE, no POST)
#          Notification - Rule (full CRUD)
# ===========================================================================

# --- template (no add - system-generated) ---
register(
    "configure notification template",
    words="<name>",
    help="Body templates for REST notification payloads.",
)
register("configure notification template <name>", words="delete set")
register("configure notification template <name> delete", words="<cr>")


@command(
    "configure notification template <name> delete",
    words="<cr>",
    help="Delete a notification REST template.",
)
async def cli_notification_template_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bnotification template (\S+) delete", line)
    if not m:
        print("  Error: template name required")
        return
    name = m.group(1)
    results = [
        as_dict(r)
        async for r in ctx.client.notification.rest_template.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No notification template found: {name}")
        return
    await ctx.client.notification.rest_template.delete(results[0]["_ref"])


register(
    "configure notification template <name> set",
    words="<key>=<value>",
    dynamic=_NOTIF_TEMPLATE_KEYS,
)


@command(
    "configure notification template <name> set",
    words="<key>=<value>",
    help="Set fields on a notification REST template.",
)
async def cli_notification_template_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bnotification template (\S+) set\b", line)
    if not m:
        print("  Error: template name required")
        return
    name = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [
        as_dict(r)
        async for r in ctx.client.notification.rest_template.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No notification template found: {name}")
        return
    await ctx.client.notification.rest_template.update(results[0]["_ref"], body)


register("show notification template", words="<cr> <name>")
register("show notification template <name>", words="<cr> fields=<field1,field2,...>")


@command(
    "show notification template", words="<cr> <name>", help="Show notification REST templates."
)
@command(
    "show notification template <name>",
    words="<cr>",
    help="Show a specific notification REST template.",
)
async def cli_notification_template_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show notification template [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    templates = [as_dict(r) async for r in ctx.client.notification.rest_template.list(**params)]
    if not templates:
        if name:
            print(f"  No notification template found: {name}")
        return
    for tmpl in templates:
        parts = ["type=notification:rest:template"]
        for k, v in tmpl.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# --- rule (full CRUD) ---
register(
    "configure notification rule",
    words="add <name>",
    help="Rule binding an event type + filter to an endpoint.",
)
register("configure notification rule add", words="<name>")

_RULE_ADD_WORDS = "endpoint=<name>|event_type=<name>|notification_action=<name>|comment=<comment>"

# The @command decorator below registers "configure notification rule add
# <name>" with _RULE_ADD_WORDS; no explicit register() needed.

# WAPI defaults when the user doesn't pass the required fields. These are
# the safest neutral values that let the rule be created and later refined
# via `configure notification rule <name> set …`.
_DEFAULT_EVENT_TYPE = "DB_CHANGE_DNS_RECORD"
_DEFAULT_NOTIFICATION_ACTION = "RESTAPI_TEMPLATE_INSTANCE"


@command(
    "configure notification rule add <name>",
    words=_RULE_ADD_WORDS,
    help="Add a notification rule. endpoint=<name> is required and resolved "
    "to a notification:rest:endpoint reference. event_type and "
    "notification_action default to DB_CHANGE_DNS_RECORD and "
    "RESTAPI_TEMPLATE_INSTANCE respectively - override via kv args.",
)
async def cli_notification_rule_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bnotification rule add (\S+)", line)
    if not m:
        print("  Error: rule name required")
        return
    name = m.group(1)

    endpoint_name = _kv(line, "endpoint")
    if not endpoint_name:
        print("  Error: endpoint=<name> required")
        return

    # Resolve endpoint name to a ref.
    eps = [
        as_dict(r)
        async for r in ctx.client.notification.rest_endpoint.list(
            name=endpoint_name,
            max_results=1,
        )
    ]
    if not eps:
        print(f"  Error: endpoint not found: {endpoint_name}")
        return

    body: dict = {
        "name": name,
        "notification_target": eps[0]["_ref"],
        "event_type": _kv(line, "event_type") or _DEFAULT_EVENT_TYPE,
        "notification_action": (_kv(line, "notification_action") or _DEFAULT_NOTIFICATION_ACTION),
        # WAPI requires expression_list on create; empty list is valid and
        # means "match everything". Users can refine via `configure
        # notification rule <name> set expression_list=…` afterward.
        "expression_list": [],
    }
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.notification.rule.create(body)


register("configure notification rule <name>", words="delete set")
register("configure notification rule <name> delete", words="<cr>")


@command(
    "configure notification rule <name> delete",
    words="<cr>",
    help="Delete a notification rule.",
)
async def cli_notification_rule_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bnotification rule (\S+) delete", line)
    if not m:
        print("  Error: rule name required")
        return
    name = m.group(1)
    results = [
        as_dict(r) async for r in ctx.client.notification.rule.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No notification rule found: {name}")
        return
    await ctx.client.notification.rule.delete(results[0]["_ref"])


register("configure notification rule <name> set", words="<key>=<value>", dynamic=_NOTIF_RULE_KEYS)


@command(
    "configure notification rule <name> set",
    words="<key>=<value>",
    help="Set fields on a notification rule.",
)
async def cli_notification_rule_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bnotification rule (\S+) set\b", line)
    if not m:
        print("  Error: rule name required")
        return
    name = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [
        as_dict(r) async for r in ctx.client.notification.rule.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No notification rule found: {name}")
        return
    await ctx.client.notification.rule.update(results[0]["_ref"], body)


register("show notification rule", words="<cr> <name>")
register("show notification rule <name>", words="<cr> fields=<field1,field2,...>")


@command("show notification rule", words="<cr> <name>", help="Show notification rules.")
@command("show notification rule <name>", words="<cr>", help="Show a specific notification rule.")
async def cli_notification_rule_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show notification rule [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    rules = [as_dict(r) async for r in ctx.client.notification.rule.list(**params)]
    if not rules:
        if name:
            print(f"  No notification rule found: {name}")
        return
    for rule in rules:
        parts = ["type=notification:rule"]
        for k, v in rule.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))
