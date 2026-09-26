# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Threat Insight and Threat Protection commands - Phase 18.

Exposes NIOS Threat Insight and Threat Protection resources via:
  ctx.client.threatinsight.*
  ctx.client.threatprotection.*

SDK / WAPI surface notes
------------------------
Threat Insight:
- threatinsight:allowlist       full CRUD (identified by fqdn; type_ read-only)
- threatinsight:cloudclient     GET + PUT only (singleton; no POST/DELETE)
- threatinsight:insight_allowlist  GET only (fully read-only - uuid/version only)
- threatinsight:moduleset       GET only (fully read-only - uuid/version only)

Threat Protection:
- threatprotection:profile          full CRUD (name, comment)
- threatprotection:profile:rule     GET + PUT only (profile/rule/sid read-only)
- threatprotection:rule             GET + PUT only (member/rule/sid/uuid read-only)
- threatprotection:grid:rule        GET + PUT only (name/ruleset/etc read-only)
- threatprotection:ruleset          GET + PUT only (version/used_by/etc read-only)
- threatprotection:ruletemplate     GET only (fully read-only)
- threatprotection:rulecategory     GET only (fully read-only)
- threatprotection:statistics       GET only (fully read-only)

Command vocabulary
------------------
# Threat Insight - allowlist (CRUD; identified by fqdn, not name)
configure threat_insight allowlist add <name> [comment=<comment>]
configure threat_insight allowlist <name> delete
show threat_insight allowlist [<name>]

# Threat Insight - cloud client (GET + set)
show threat_insight cloud_client
configure threat_insight cloud_client set <key>=<value>

# Threat Insight - insight_allowlist (read-only)
show threat_insight insight_allowlist

# Threat Insight - moduleset (read-only)
show threat_insight moduleset

# Threat Protection - profiles (full CRUD)
configure threat_protection profile add <name> [comment=<comment>]
configure threat_protection profile <name> delete
configure threat_protection profile <name> set <key>=<value>
show threat_protection profile [<name>]

# Threat Protection - profile rules (GET only via profile filter)
show threat_protection profile <name> rule

# Threat Protection - member-level rules (GET only)
show threat_protection rule [<name>]

# Threat Protection - grid-level rules (GET + set)
show threat_protection grid_rule [<name>]
configure threat_protection grid_rule <name> set <key>=<value>

# Threat Protection - rulesets (GET + set)
configure threat_protection ruleset <name> set <key>=<value>
show threat_protection ruleset [<name>]

# Threat Protection - rule templates (read-only)
show threat_protection rule_template [<name>]

# Threat Protection - rule categories (read-only)
show threat_protection rule_category [<name>]

# Threat Protection - statistics (read-only)
show threat_protection statistics [<member>]
"""

from __future__ import annotations

import re

from ibcli.coerce import coerce as _coerce  # noqa: F401
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict

# ---------------------------------------------------------------------------
# Shared helpers (mirrors pattern in ms.py / discovery.py)
# ---------------------------------------------------------------------------


def _comment(line: str) -> str | None:
    """Extract a quoted or bare comment value."""
    m = re.search(r'\bcomment[= ]"([^"]+)"', line)
    if m:
        return m.group(1)
    m = re.search(r"\bcomment[= ](\S+)", line)
    return m.group(1) if m else None


def _parse_inline_kvs(line: str, marker: str) -> dict:
    """Parse key/value pairs appearing after *marker* in *line*."""
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


def _print_records(records: list, prefix: str) -> None:
    """Print a list of record dicts with a type= prefix."""
    for rec in records:
        parts = [f"type={prefix}"]
        for k, v in rec.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# ===========================================================================
# Register top-level token groups
# ===========================================================================

register(
    "configure",
    words="threat_insight threat_protection",
    help="Create, modify or delete grid objects.",
)
register(
    "show",
    words="threat_insight threat_protection",
    help="Read grid state without modifying anything.",
)

# ===========================================================================
# Chunk A: Threat Insight - allowlist
# Full CRUD. The primary identifier in the WAPI is 'fqdn' (no 'name' field).
# The CLI token <name> maps to 'fqdn' throughout.
# ===========================================================================

register(
    "configure threat_insight",
    words="allowlist cloud_client",
    help="Threat Insight configuration (DNS tunneling detection).",
)
register("show threat_insight", words="allowlist cloud_client insight_allowlist moduleset")

register("configure threat_insight allowlist", words="add <name>")
register("configure threat_insight allowlist add", words="<name>")
register("configure threat_insight allowlist add <name>", words="<cr> comment=<comment>")


@command(
    "configure threat_insight allowlist add <name>",
    words="<cr> comment=<comment>",
    help="Add a threat insight allowlist entry (fqdn).",
)
async def cli_ti_allowlist_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\ballowlist add (\S+)", line)
    if not m:
        print("  Error: fqdn required")
        return
    fqdn = m.group(1)
    body: dict = {"fqdn": fqdn}
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.threatinsight.allowlist.create(body)


register("configure threat_insight allowlist <name>", words="delete")
register("configure threat_insight allowlist <name> delete", words="<cr>")


@command(
    "configure threat_insight allowlist <name> delete",
    words="<cr>",
    help="Delete a threat insight allowlist entry.",
)
async def cli_ti_allowlist_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\ballowlist (\S+) delete", line)
    if not m:
        print("  Error: fqdn required")
        return
    fqdn = m.group(1)
    results = [
        as_dict(r) async for r in ctx.client.threatinsight.allowlist.list(fqdn=fqdn, max_results=1)
    ]
    if not results:
        print(f"  No allowlist entry found: {fqdn}")
        return
    await ctx.client.threatinsight.allowlist.delete(results[0]["_ref"])


register("show threat_insight allowlist", words="<cr> <name>")
register("show threat_insight allowlist <name>", words="<cr>")


@command(
    "show threat_insight allowlist",
    words="<cr> <name>",
    help="Show threat insight allowlist entries.",
)
@command(
    "show threat_insight allowlist <name>",
    words="<cr>",
    help="Show a specific threat insight allowlist entry.",
)
async def cli_ti_allowlist_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show threat_insight allowlist [<fqdn>]
    fqdn = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            fqdn = candidate
    params: dict = {}
    if fqdn:
        params["fqdn"] = fqdn
    records = [as_dict(r) async for r in ctx.client.threatinsight.allowlist.list(**params)]
    if not records:
        if fqdn:
            print(f"  No allowlist entry found: {fqdn}")
        return
    _print_records(records, "threatinsight:allowlist")


# ===========================================================================
# Chunk A (cont.): Threat Insight - cloud client
# Singleton - GET + PUT only (no POST/DELETE).
# ===========================================================================

register("show threat_insight cloud_client", words="<cr>")
register("configure threat_insight cloud_client", words="set")
register("configure threat_insight cloud_client set", words="<key>=<value>")


@command(
    "show threat_insight cloud_client",
    words="<cr>",
    help="Show threat insight cloud client configuration.",
)
async def cli_ti_cloudclient_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    records = [as_dict(r) async for r in ctx.client.threatinsight.cloudclient.list()]
    if not records:
        return
    _print_records(records, "threatinsight:cloudclient")


@command(
    "configure threat_insight cloud_client set",
    words="<key>=<value>",
    help="Set fields on the threat insight cloud client configuration.",
)
async def cli_ti_cloudclient_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [as_dict(r) async for r in ctx.client.threatinsight.cloudclient.list(max_results=1)]
    if not results:
        print("  No cloud client configuration found")
        return
    await ctx.client.threatinsight.cloudclient.update(results[0]["_ref"], body)


# ===========================================================================
# Chunk A (cont.): Threat Insight - insight_allowlist (read-only)
# ===========================================================================

register("show threat_insight insight_allowlist", words="<cr>")


@command(
    "show threat_insight insight_allowlist",
    words="<cr>",
    help="Show threat insight per-insight allowlist (read-only aggregate).",
)
async def cli_ti_insight_allowlist_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    records = [as_dict(r) async for r in ctx.client.threatinsight.insight_allowlist.list()]
    if not records:
        return
    _print_records(records, "threatinsight:insight_allowlist")


# ===========================================================================
# Chunk A (cont.): Threat Insight - moduleset (read-only)
# ===========================================================================

register("show threat_insight moduleset", words="<cr>")


@command(
    "show threat_insight moduleset",
    words="<cr>",
    help="Show threat insight module sets (read-only).",
)
async def cli_ti_moduleset_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    records = [as_dict(r) async for r in ctx.client.threatinsight.moduleset.list()]
    if not records:
        return
    _print_records(records, "threatinsight:moduleset")


# ===========================================================================
# Chunk B: Threat Protection - profiles (full CRUD)
# ===========================================================================

register(
    "configure threat_protection",
    words="profile grid_rule ruleset",
    help="Advanced DNS Protection (ADP) rule configuration.",
)
register(
    "show threat_protection",
    words="profile rule grid_rule ruleset rule_template rule_category statistics",
)

register("configure threat_protection profile", words="add <name>")
register("configure threat_protection profile add", words="<name>")
register("configure threat_protection profile add <name>", words="<cr> comment=<comment>")


@command(
    "configure threat_protection profile add <name>",
    words="<cr> comment=<comment>",
    help="Add a threat protection profile.",
)
async def cli_tp_profile_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bprofile add (\S+)", line)
    if not m:
        print("  Error: profile name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.threatprotection.profile.create(body)


register("configure threat_protection profile <name>", words="delete set")
register("configure threat_protection profile <name> delete", words="<cr>")


@command(
    "configure threat_protection profile <name> delete",
    words="<cr>",
    help="Delete a threat protection profile.",
)
async def cli_tp_profile_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bprofile (\S+) delete", line)
    if not m:
        print("  Error: profile name required")
        return
    name = m.group(1)
    results = [
        as_dict(r) async for r in ctx.client.threatprotection.profile.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No threat protection profile found: {name}")
        return
    await ctx.client.threatprotection.profile.delete(results[0]["_ref"])


register("configure threat_protection profile <name> set", words="<key>=<value>")


@command(
    "configure threat_protection profile <name> set",
    words="<key>=<value>",
    help="Set fields on a threat protection profile.",
)
async def cli_tp_profile_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bprofile (\S+) set\b", line)
    if not m:
        print("  Error: profile name required")
        return
    name = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [
        as_dict(r) async for r in ctx.client.threatprotection.profile.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No threat protection profile found: {name}")
        return
    await ctx.client.threatprotection.profile.update(results[0]["_ref"], body)


register("show threat_protection profile", words="<cr> <name>")
register("show threat_protection profile <name>", words="<cr> rule")


@command(
    "show threat_protection profile", words="<cr> <name>", help="Show threat protection profiles."
)
@command(
    "show threat_protection profile <name>",
    words="<cr> rule",
    help="Show a specific threat protection profile.",
)
async def cli_tp_profile_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show threat_protection profile [<name>]
    # but stop before 'rule' subcommand
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<") and candidate != "rule":
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.threatprotection.profile.list(**params)]
    if not records:
        if name:
            print(f"  No threat protection profile found: {name}")
        return
    _print_records(records, "threatprotection:profile")


# ===========================================================================
# Chunk B (cont.): Threat Protection - profile rules (GET only)
# profile_rule links a profile to a rule; no POST/DELETE from CLI.
# ===========================================================================

register("show threat_protection profile <name> rule", words="<cr>")


@command(
    "show threat_protection profile <name> rule",
    words="<cr>",
    help="Show rules attached to a threat protection profile.",
)
async def cli_tp_profile_rule_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bprofile (\S+) rule", line)
    if not m:
        print("  Error: profile name required")
        return
    profile_name = m.group(1)
    records = [
        as_dict(r)
        async for r in ctx.client.threatprotection.profile_rule.list(profile=profile_name)
    ]
    if not records:
        print(f"  No rules found for profile: {profile_name}")
        return
    _print_records(records, "threatprotection:profile:rule")


# ===========================================================================
# Chunk B (cont.): Threat Protection - member-level rules (GET only)
# ===========================================================================

register("show threat_protection rule", words="<cr> <name>")
register("show threat_protection rule <name>", words="<cr>")


@command(
    "show threat_protection rule",
    words="<cr> <name>",
    help="Show threat protection member-level rules.",
)
@command(
    "show threat_protection rule <name>",
    words="<cr>",
    help="Show a specific threat protection member-level rule.",
)
async def cli_tp_rule_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show threat_protection rule [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["rule"] = name
    records = [as_dict(r) async for r in ctx.client.threatprotection.rule.list(**params)]
    if not records:
        if name:
            print(f"  No threat protection rule found: {name}")
        return
    _print_records(records, "threatprotection:rule")


# ===========================================================================
# Chunk B (cont.): Threat Protection - grid-level rules (GET + set)
# Most fields are read-only; writable: comment, config, disabled, template.
# ===========================================================================

register("show threat_protection grid_rule", words="<cr> <name>")
register("show threat_protection grid_rule <name>", words="<cr>")
register("configure threat_protection grid_rule", words="<name>")
register("configure threat_protection grid_rule <name>", words="set")
register("configure threat_protection grid_rule <name> set", words="<key>=<value>")


@command(
    "show threat_protection grid_rule",
    words="<cr> <name>",
    help="Show threat protection grid-level rules.",
)
@command(
    "show threat_protection grid_rule <name>",
    words="<cr>",
    help="Show a specific threat protection grid-level rule.",
)
async def cli_tp_grid_rule_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show threat_protection grid_rule [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.threatprotection.grid_rule.list(**params)]
    if not records:
        if name:
            print(f"  No threat protection grid rule found: {name}")
        return
    _print_records(records, "threatprotection:grid:rule")


@command(
    "configure threat_protection grid_rule <name> set",
    words="<key>=<value>",
    help="Set writable fields on a threat protection grid-level rule.",
)
async def cli_tp_grid_rule_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bgrid_rule (\S+) set\b", line)
    if not m:
        print("  Error: rule name required")
        return
    name = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [
        as_dict(r)
        async for r in ctx.client.threatprotection.grid_rule.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No threat protection grid rule found: {name}")
        return
    await ctx.client.threatprotection.grid_rule.update(results[0]["_ref"], body)


# ===========================================================================
# Chunk C: Threat Protection - rulesets (GET + set)
# version/used_by/add_type/added_time/is_factory_reset_enabled/uuid are
# read-only; writable fields: comment, do_not_delete.
# No POST/DELETE - rulesets are NIOS-managed.
# ===========================================================================

register("configure threat_protection ruleset", words="<name>")
register("configure threat_protection ruleset <name>", words="set")
register("configure threat_protection ruleset <name> set", words="<key>=<value>")
register("show threat_protection ruleset", words="<cr> <name>")
register("show threat_protection ruleset <name>", words="<cr>")


@command(
    "show threat_protection ruleset", words="<cr> <name>", help="Show threat protection rule sets."
)
@command(
    "show threat_protection ruleset <name>",
    words="<cr>",
    help="Show a specific threat protection rule set.",
)
async def cli_tp_ruleset_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show threat_protection ruleset [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["version"] = name
    records = [as_dict(r) async for r in ctx.client.threatprotection.ruleset.list(**params)]
    if not records:
        if name:
            print(f"  No threat protection ruleset found: {name}")
        return
    _print_records(records, "threatprotection:ruleset")


@command(
    "configure threat_protection ruleset <name> set",
    words="<key>=<value>",
    help="Set writable fields on a threat protection ruleset (comment, do_not_delete).",
)
async def cli_tp_ruleset_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bruleset (\S+) set\b", line)
    if not m:
        print("  Error: ruleset version required")
        return
    version = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [
        as_dict(r)
        async for r in ctx.client.threatprotection.ruleset.list(version=version, max_results=1)
    ]
    if not results:
        print(f"  No threat protection ruleset found: {version}")
        return
    await ctx.client.threatprotection.ruleset.update(results[0]["_ref"], body)


# ===========================================================================
# Chunk C (cont.): Threat Protection - rule templates (read-only)
# ===========================================================================

register("show threat_protection rule_template", words="<cr> <name>")
register("show threat_protection rule_template <name>", words="<cr>")


@command(
    "show threat_protection rule_template",
    words="<cr> <name>",
    help="Show threat protection rule templates (read-only).",
)
@command(
    "show threat_protection rule_template <name>",
    words="<cr>",
    help="Show a specific threat protection rule template.",
)
async def cli_tp_ruletemplate_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show threat_protection rule_template [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.threatprotection.ruletemplate.list(**params)]
    if not records:
        if name:
            print(f"  No rule template found: {name}")
        return
    _print_records(records, "threatprotection:ruletemplate")


# ===========================================================================
# Chunk C (cont.): Threat Protection - rule categories (read-only)
# ===========================================================================

register("show threat_protection rule_category", words="<cr> <name>")
register("show threat_protection rule_category <name>", words="<cr>")


@command(
    "show threat_protection rule_category",
    words="<cr> <name>",
    help="Show threat protection rule categories (read-only).",
)
@command(
    "show threat_protection rule_category <name>",
    words="<cr>",
    help="Show a specific threat protection rule category.",
)
async def cli_tp_rulecategory_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show threat_protection rule_category [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.threatprotection.rulecategory.list(**params)]
    if not records:
        if name:
            print(f"  No rule category found: {name}")
        return
    _print_records(records, "threatprotection:rulecategory")


# ===========================================================================
# Chunk C (cont.): Threat Protection - statistics (read-only)
# Optional filter by member name.
# ===========================================================================

register("show threat_protection statistics", words="<cr> <name>")
register("show threat_protection statistics <name>", words="<cr>")


@command(
    "show threat_protection statistics",
    words="<cr> <name>",
    help="Show threat protection statistics.",
)
@command(
    "show threat_protection statistics <name>",
    words="<cr>",
    help="Show threat protection statistics for a specific member.",
)
async def cli_tp_statistics_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show threat_protection statistics [<member>]
    member = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            member = candidate
    params: dict = {}
    if member:
        params["member"] = member
    records = [as_dict(r) async for r in ctx.client.threatprotection.statistics.list(**params)]
    if not records:
        if member:
            print(f"  No statistics found for member: {member}")
        return
    _print_records(records, "threatprotection:statistics")
