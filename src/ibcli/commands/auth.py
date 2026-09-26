# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Auth-service configuration commands - Phase 5.

Command shapes:

  configure auth ldap add <name> [server=<host>[:port] ...] [comment=<text>]
  configure auth ldap <name> delete
  configure auth ldap <name> set <key>=<value>
  show auth ldap [<name>]

  configure auth ad add <name> [domain=<domain>] [comment=<text>]
  configure auth ad <name> delete
  configure auth ad <name> set <key>=<value>
  show auth ad [<name>]

  configure auth radius add <name> [server=<host>[:port] ...] [comment=<text>]
  configure auth radius <name> delete
  configure auth radius <name> set <key>=<value>
  show auth radius [<name>]

  configure auth tacacs add <name> [server=<host>[:port] ...] [comment=<text>]
  configure auth tacacs <name> delete
  configure auth tacacs <name> set <key>=<value>
  show auth tacacs [<name>]

  configure auth saml add <name> [comment=<text>]
  configure auth saml <name> delete
  configure auth saml <name> set <key>=<value>
  show auth saml [<name>]

  configure auth certificate add <name> [comment=<text>]
  configure auth certificate <name> delete
  configure auth certificate <name> set <key>=<value>
  show auth certificate [<name>]

  configure auth localuser
  show auth localuser

  configure auth policy set <key>=<value>
  show auth policy

SDK resources (all under ctx.client.security.*):
  ldap_auth_service, ad_auth_service, radius_authservice, tacacsplus_authservice,
  saml_authservice, certificate_authservice, localuser_authservice, authpolicy
"""

from __future__ import annotations

import re

from ibcli import completions as _completions
from ibcli.coerce import coerce as _coerce_value  # noqa: F401
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict, format_extra_field, parse_extra_fields

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_kv(line: str, key: str) -> str | None:
    """Extract value for key from key=value or 'key value' form."""
    m = re.search(rf"\b{re.escape(key)}[= ](\S+)", line)
    return m.group(1) if m else None


def _parse_kv_all(line: str, key: str) -> list[str]:
    """Extract all values for a repeated key=value / 'key value' pair."""
    return re.findall(rf"\b{re.escape(key)}[= ](\S+)", line)


def _parse_comment(line: str) -> str | None:
    """Extract comment value, supporting quoted and unquoted forms."""
    m = re.search(r'\bcomment[= ]"([^"]+)"', line)
    if m:
        return m.group(1)
    m = re.search(r"\bcomment[= ](\S+)", line)
    return m.group(1) if m else None


def _parse_set_kvs(line: str) -> dict:
    """Parse key=value pairs from a 'set key=value ...' tail.

    Handles both 'key=value' and (after tokeniser expansion) 'key value' forms.
    Returns a dict with values coerced via _coerce_value.
    """
    # Find 'set' keyword; everything after it is kv pairs.
    m = re.search(r"\bset\s+(.*)", line)
    if not m:
        return {}
    tail = m.group(1).strip()
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
                result[k] = _coerce_value(v)
            i += 1
        elif i + 1 < len(tokens) and "=" not in tokens[i + 1]:
            result[tok] = _coerce_value(tokens[i + 1])
            i += 2
        else:
            i += 1
    return result


def _parse_servers(line: str, default_port: int) -> list[dict] | None:
    """Parse repeatable server=<host>[:port] from line.

    Returns a list of {"address": host, "port": port} dicts, or None if
    no server= entries are present.
    """
    servers: list[dict] = []
    for m in re.finditer(r"\bserver[= ](\S+)", line):
        raw = m.group(1)
        if ":" in raw:
            host, _, port_str = raw.rpartition(":")
            try:
                port = int(port_str)
            except ValueError:
                host = raw
                port = default_port
        else:
            host = raw
            port = default_port
        servers.append({"address": host, "port": port})
    return servers if servers else None


# ===========================================================================
# Chunk A - LDAP + AD
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - configure auth / show auth (top-level, shared across all chunks)
# ---------------------------------------------------------------------------

register("configure", words="auth", help="Create, modify or delete grid objects.")
register(
    "configure auth",
    words="ldap ad radius tacacs saml certificate localuser policy",
    help="Authentication services - LDAP, AD, RADIUS, TACACS+, SAML, cert.",
)
register("show", words="auth", help="Read grid state without modifying anything.")
register(
    "show auth",
    words="ldap ad radius tacacs saml certificate localuser policy",
    help="Show authentication services.",
)

# ---------------------------------------------------------------------------
# Waypoints - LDAP
# ---------------------------------------------------------------------------

register("configure auth ldap", words="add <name>", help="LDAP authentication service definitions.")
register("configure auth ldap add", words="<name>")
_LDAP_ADD_WORDS = (
    "<cr> server=<value> timeout=<value> retries=<value> "
    "recovery_interval=<value> base_dn=<value> user_attr=<value> "
    "encryption=<value> comment=<comment>"
)
register("configure auth ldap add <name>", words=_LDAP_ADD_WORDS)
register("configure auth ldap <name>", words="delete set")
register("configure auth ldap <name> delete", words="<cr>")
register(
    "configure auth ldap <name> set",
    words="<cr> <key>=<value>",
)
register("show auth ldap", words="<cr> <name>", dynamic=_completions.auth_ldap)
register("show auth ldap <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure auth ldap add <name>
# ---------------------------------------------------------------------------


@command(
    "configure auth ldap add <name>",
    words=_LDAP_ADD_WORDS,
    help=(
        "Add an LDAP authentication service. Sensible defaults are applied "
        "for timeout/retries/recovery_interval/user_attr and per-server "
        "port/encryption/base_dn so a minimal `server=<host>` works."
    ),
)
async def cli_add_auth_ldap(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth ldap add\s+(\S+)", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    body: dict = {
        "name": name,
        "timeout": 5,
        "retries": 2,
        "recovery_interval": 30,
        "ldap_user_attribute": "uid",
    }

    base_dn = _parse_kv(line, "base_dn") or ""
    encryption = (_parse_kv(line, "encryption") or "NONE").upper()

    servers = _parse_servers(line, default_port=389)
    if servers:
        for s in servers:
            s.setdefault("encryption", encryption)
            s.setdefault("base_dn", base_dn)
        body["servers"] = servers

    for int_key in ("timeout", "retries", "recovery_interval"):
        val = _parse_kv(line, int_key)
        if val is not None:
            try:
                body[int_key] = int(val)
            except ValueError:
                print(f"  Error: {int_key} must be an integer (got {val!r})")
                return

    user_attr = _parse_kv(line, "user_attr")
    if user_attr:
        body["ldap_user_attribute"] = user_attr

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.ldap_auth_service.create(body)


# ---------------------------------------------------------------------------
# Handler: configure auth ldap <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure auth ldap <name> delete",
    words="<cr>",
    help="Delete an LDAP authentication service.",
)
async def cli_delete_auth_ldap(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth ldap\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.security.ldap_auth_service.list(name=name)]
    if not results:
        print(f"  No LDAP auth service found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.ldap_auth_service.delete(ref)


# ---------------------------------------------------------------------------
# Handler: configure auth ldap <name> set key=value
# ---------------------------------------------------------------------------


@command(
    "configure auth ldap <name> set",
    words="<cr> <key>=<value>",
    help="Set a field on an LDAP auth service (GET-then-PUT).",
)
async def cli_set_auth_ldap(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth ldap\s+(\S+)\s+set\b", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    updates = _parse_set_kvs(line)
    if not updates:
        print("  Error: at least one key=value pair is required")
        return

    results = [as_dict(r) async for r in ctx.client.security.ldap_auth_service.list(name=name)]
    if not results:
        print(f"  No LDAP auth service found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.ldap_auth_service.update(ref, updates)


# ---------------------------------------------------------------------------
# Handler: show auth ldap [<name>]
# ---------------------------------------------------------------------------


@command("show auth ldap", words="<cr> <name>", help="List LDAP auth services.")
@command(
    "show auth ldap <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific LDAP auth service.",
)
async def cli_show_auth_ldap(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    # "show auth ldap [<name>]" → tokens[3] if present
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["name", "comment", "mode", "servers"] + extra}
    if name_filter:
        kwargs["name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.ldap_auth_service.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("mode"):
            parts.append(f"mode={r['mode']}")
        if r.get("servers"):
            addrs = [s.get("address", "") for s in r["servers"] if isinstance(s, dict)]
            parts.append(f"servers={','.join(addrs)}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Waypoints - AD
# ---------------------------------------------------------------------------

register(
    "configure auth ad",
    words="add <name>",
    help="Active Directory authentication service definitions.",
)
register("configure auth ad add", words="<name>")
_AD_ADD_WORDS = (
    "<cr> domain=<value> dc=<value> timeout=<value> "
    "encryption=<value> auth_port=<value> comment=<comment>"
)
register("configure auth ad add <name>", words=_AD_ADD_WORDS)
register("configure auth ad <name>", words="delete set")
register("configure auth ad <name> delete", words="<cr>")
register(
    "configure auth ad <name> set",
    words="<cr> <key>=<value>",
)
register("show auth ad", words="<cr> <name>", dynamic=_completions.auth_ad)
register("show auth ad <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure auth ad add <name>
# ---------------------------------------------------------------------------


@command(
    "configure auth ad add <name>",
    words=_AD_ADD_WORDS,
    help=(
        "Add an Active Directory authentication service. Each dc=<host> "
        "gets auth_port/encryption/mgmt_port defaults filled in."
    ),
)
async def cli_add_auth_ad(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth ad add\s+(\S+)", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    body: dict = {"name": name, "timeout": 5}
    domain = _parse_kv(line, "domain")
    if domain:
        body["ad_domain"] = domain

    encryption = (_parse_kv(line, "encryption") or "NONE").upper()
    try:
        auth_port = int(_parse_kv(line, "auth_port") or 389)
    except ValueError:
        print("  Error: auth_port must be an integer")
        return
    timeout = _parse_kv(line, "timeout")
    if timeout is not None:
        try:
            body["timeout"] = int(timeout)
        except ValueError:
            print(f"  Error: timeout must be an integer (got {timeout!r})")
            return

    dcs = _parse_kv_all(line, "dc")
    if dcs:
        body["domain_controllers"] = [
            {
                "fqdn_or_ip": d,
                "auth_port": auth_port,
                "encryption": encryption,
                "mgmt_port": False,
            }
            for d in dcs
        ]

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.ad_auth_service.create(body)


# ---------------------------------------------------------------------------
# Handler: configure auth ad <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure auth ad <name> delete",
    words="<cr>",
    help="Delete an Active Directory authentication service.",
)
async def cli_delete_auth_ad(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth ad\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.security.ad_auth_service.list(name=name)]
    if not results:
        print(f"  No AD auth service found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.ad_auth_service.delete(ref)


# ---------------------------------------------------------------------------
# Handler: configure auth ad <name> set key=value
# ---------------------------------------------------------------------------


@command(
    "configure auth ad <name> set",
    words="<cr> <key>=<value>",
    help="Set a field on an AD auth service (GET-then-PUT).",
)
async def cli_set_auth_ad(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth ad\s+(\S+)\s+set\b", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    updates = _parse_set_kvs(line)
    if not updates:
        print("  Error: at least one key=value pair is required")
        return

    results = [as_dict(r) async for r in ctx.client.security.ad_auth_service.list(name=name)]
    if not results:
        print(f"  No AD auth service found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.ad_auth_service.update(ref, updates)


# ---------------------------------------------------------------------------
# Handler: show auth ad [<name>]
# ---------------------------------------------------------------------------


@command("show auth ad", words="<cr> <name>", help="List AD auth services.")
@command(
    "show auth ad <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific AD auth service.",
)
async def cli_show_auth_ad(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    # "show auth ad [<name>]" → tokens[3] if present
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["name", "comment", "ad_domain", "disabled"] + extra}
    if name_filter:
        kwargs["name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.ad_auth_service.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("ad_domain"):
            parts.append(f"domain={r['ad_domain']}")
        if r.get("disabled") is not None:
            parts.append(f"disabled={r['disabled']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Chunk B - RADIUS auth service + TACACS+
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - RADIUS auth service
# ---------------------------------------------------------------------------

register(
    "configure auth radius",
    words="add <name>",
    help="RADIUS authentication service definitions (password + PAP/CHAP).",
)
register("configure auth radius add", words="<name>")
_RADIUS_ADD_WORDS = "<cr> server=<value> shared_secret=<value> auth_port=<value> comment=<comment>"
register("configure auth radius add <name>", words=_RADIUS_ADD_WORDS)
register("configure auth radius <name>", words="delete set")
register("configure auth radius <name> delete", words="<cr>")
register(
    "configure auth radius <name> set",
    words="<cr> <key>=<value>",
)
register("show auth radius", words="<cr> <name>", dynamic=_completions.auth_radius)
register("show auth radius <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure auth radius add <name>
# ---------------------------------------------------------------------------


@command(
    "configure auth radius add <name>",
    words=_RADIUS_ADD_WORDS,
    help=(
        "Add a RADIUS authentication service. shared_secret= applies to "
        "every server unless the server= token embeds per-server overrides."
    ),
)
async def cli_add_auth_radius(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth radius add\s+(\S+)", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    servers = _parse_servers(line, default_port=1812)
    shared_secret = _parse_kv(line, "shared_secret")
    if not shared_secret and servers:
        print("  Error: shared_secret=<value> is required when adding servers")
        return
    try:
        auth_port = int(_parse_kv(line, "auth_port") or 1812)
    except ValueError:
        print("  Error: auth_port must be an integer")
        return
    if servers:
        # RADIUS server struct uses auth_port, not `port`. Convert.
        for s in servers:
            s["shared_secret"] = shared_secret
            s["auth_port"] = s.pop("port", auth_port)
        body["servers"] = servers
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.radius_authservice.create(body)


# ---------------------------------------------------------------------------
# Handler: configure auth radius <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure auth radius <name> delete",
    words="<cr>",
    help="Delete a RADIUS authentication service.",
)
async def cli_delete_auth_radius(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth radius\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.security.radius_authservice.list(name=name)]
    if not results:
        print(f"  No RADIUS auth service found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.radius_authservice.delete(ref)


# ---------------------------------------------------------------------------
# Handler: configure auth radius <name> set key=value
# ---------------------------------------------------------------------------


@command(
    "configure auth radius <name> set",
    words="<cr> <key>=<value>",
    help="Set a field on a RADIUS auth service (GET-then-PUT).",
)
async def cli_set_auth_radius(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth radius\s+(\S+)\s+set\b", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    updates = _parse_set_kvs(line)
    if not updates:
        print("  Error: at least one key=value pair is required")
        return

    results = [as_dict(r) async for r in ctx.client.security.radius_authservice.list(name=name)]
    if not results:
        print(f"  No RADIUS auth service found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.radius_authservice.update(ref, updates)


# ---------------------------------------------------------------------------
# Handler: show auth radius [<name>]
# ---------------------------------------------------------------------------


@command("show auth radius", words="<cr> <name>", help="List RADIUS auth services.")
@command(
    "show auth radius <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific RADIUS auth service.",
)
async def cli_show_auth_radius(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    # "show auth radius [<name>]" → tokens[3] if present
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["name", "comment", "mode", "servers"] + extra}
    if name_filter:
        kwargs["name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.radius_authservice.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("mode"):
            parts.append(f"mode={r['mode']}")
        if r.get("servers"):
            addrs = [s.get("address", "") for s in r["servers"] if isinstance(s, dict)]
            parts.append(f"servers={','.join(addrs)}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Waypoints - TACACS+
# ---------------------------------------------------------------------------

register(
    "configure auth tacacs", words="add <name>", help="TACACS+ authentication service definitions."
)
register("configure auth tacacs add", words="<name>")
register(
    "configure auth tacacs add <name>",
    words="<cr> server=<value> comment=<comment>",
)
register("configure auth tacacs <name>", words="delete set")
register("configure auth tacacs <name> delete", words="<cr>")
register(
    "configure auth tacacs <name> set",
    words="<cr> <key>=<value>",
)
register("show auth tacacs", words="<cr> <name>", dynamic=_completions.auth_tacacs)
register("show auth tacacs <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure auth tacacs add <name>
# ---------------------------------------------------------------------------


@command(
    "configure auth tacacs add <name>",
    words="<cr> server=<value> comment=<comment>",
    help="Add a TACACS+ authentication service.",
)
async def cli_add_auth_tacacs(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth tacacs add\s+(\S+)", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    servers = _parse_servers(line, default_port=49)
    if servers:
        body["servers"] = servers
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.tacacsplus_authservice.create(body)


# ---------------------------------------------------------------------------
# Handler: configure auth tacacs <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure auth tacacs <name> delete",
    words="<cr>",
    help="Delete a TACACS+ authentication service.",
)
async def cli_delete_auth_tacacs(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth tacacs\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.security.tacacsplus_authservice.list(name=name)]
    if not results:
        print(f"  No TACACS+ auth service found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.tacacsplus_authservice.delete(ref)


# ---------------------------------------------------------------------------
# Handler: configure auth tacacs <name> set key=value
# ---------------------------------------------------------------------------


@command(
    "configure auth tacacs <name> set",
    words="<cr> <key>=<value>",
    help="Set a field on a TACACS+ auth service (GET-then-PUT).",
)
async def cli_set_auth_tacacs(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth tacacs\s+(\S+)\s+set\b", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    updates = _parse_set_kvs(line)
    if not updates:
        print("  Error: at least one key=value pair is required")
        return

    results = [as_dict(r) async for r in ctx.client.security.tacacsplus_authservice.list(name=name)]
    if not results:
        print(f"  No TACACS+ auth service found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.tacacsplus_authservice.update(ref, updates)


# ---------------------------------------------------------------------------
# Handler: show auth tacacs [<name>]
# ---------------------------------------------------------------------------


@command("show auth tacacs", words="<cr> <name>", help="List TACACS+ auth services.")
@command(
    "show auth tacacs <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific TACACS+ auth service.",
)
async def cli_show_auth_tacacs(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    # "show auth tacacs [<name>]" → tokens[3] if present
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["name", "comment", "servers"] + extra}
    if name_filter:
        kwargs["name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.tacacsplus_authservice.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("servers"):
            addrs = [s.get("address", "") for s in r["servers"] if isinstance(s, dict)]
            parts.append(f"servers={','.join(addrs)}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Chunk C - SAML + Certificate + LocalUser
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - SAML
# ---------------------------------------------------------------------------

register("configure auth saml", words="add <name>", help="SAML SSO identity-provider definitions.")
register("configure auth saml add", words="<name>")
register(
    "configure auth saml add <name>",
    words="<cr> comment=<comment>",
)
register("configure auth saml <name>", words="delete set")
register("configure auth saml <name> delete", words="<cr>")
register(
    "configure auth saml <name> set",
    words="<cr> <key>=<value>",
)
register("show auth saml", words="<cr> <name>", dynamic=_completions.auth_saml)
register("show auth saml <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure auth saml add <name>
# ---------------------------------------------------------------------------


@command(
    "configure auth saml add <name>",
    words="<cr> comment=<comment>",
    help="Add a SAML authentication service.",
)
async def cli_add_auth_saml(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth saml add\s+(\S+)", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.saml_authservice.create(body)


# ---------------------------------------------------------------------------
# Handler: configure auth saml <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure auth saml <name> delete",
    words="<cr>",
    help="Delete a SAML authentication service.",
)
async def cli_delete_auth_saml(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth saml\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.security.saml_authservice.list(name=name)]
    if not results:
        print(f"  No SAML auth service found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.saml_authservice.delete(ref)


# ---------------------------------------------------------------------------
# Handler: configure auth saml <name> set key=value
# ---------------------------------------------------------------------------


@command(
    "configure auth saml <name> set",
    words="<cr> <key>=<value>",
    help="Set a field on a SAML auth service (GET-then-PUT).",
)
async def cli_set_auth_saml(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth saml\s+(\S+)\s+set\b", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    updates = _parse_set_kvs(line)
    if not updates:
        print("  Error: at least one key=value pair is required")
        return

    results = [as_dict(r) async for r in ctx.client.security.saml_authservice.list(name=name)]
    if not results:
        print(f"  No SAML auth service found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.saml_authservice.update(ref, updates)


# ---------------------------------------------------------------------------
# Handler: show auth saml [<name>]
# ---------------------------------------------------------------------------


@command("show auth saml", words="<cr> <name>", help="List SAML auth services.")
@command(
    "show auth saml <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific SAML auth service.",
)
async def cli_show_auth_saml(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    # "show auth saml [<name>]" → tokens[3] if present
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["name", "comment", "session_timeout"] + extra}
    if name_filter:
        kwargs["name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.saml_authservice.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("session_timeout") is not None:
            parts.append(f"session_timeout={r['session_timeout']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Waypoints - Certificate auth service
# ---------------------------------------------------------------------------

register(
    "configure auth certificate",
    words="add <name>",
    help="Client-certificate authentication services.",
)
register("configure auth certificate add", words="<name>")
register(
    "configure auth certificate add <name>",
    words="<cr> comment=<comment>",
)
register("configure auth certificate <name>", words="delete set")
register("configure auth certificate <name> delete", words="<cr>")
register(
    "configure auth certificate <name> set",
    words="<cr> <key>=<value>",
)
register("show auth certificate", words="<cr> <name>", dynamic=_completions.auth_certificate)
register("show auth certificate <name>", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure auth certificate add <name>
# ---------------------------------------------------------------------------


@command(
    "configure auth certificate add <name>",
    words="<cr> comment=<comment>",
    help="Add a certificate authentication service.",
)
async def cli_add_auth_certificate(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth certificate add\s+(\S+)", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.security.certificate_authservice.create(body)


# ---------------------------------------------------------------------------
# Handler: configure auth certificate <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure auth certificate <name> delete",
    words="<cr>",
    help="Delete a certificate authentication service.",
)
async def cli_delete_auth_certificate(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth certificate\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    results = [
        as_dict(r) async for r in ctx.client.security.certificate_authservice.list(name=name)
    ]
    if not results:
        print(f"  No certificate auth service found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.certificate_authservice.delete(ref)


# ---------------------------------------------------------------------------
# Handler: configure auth certificate <name> set key=value
# ---------------------------------------------------------------------------


@command(
    "configure auth certificate <name> set",
    words="<cr> <key>=<value>",
    help="Set a field on a certificate auth service (GET-then-PUT).",
)
async def cli_set_auth_certificate(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bauth certificate\s+(\S+)\s+set\b", line)
    if not m:
        print("  Error: service name required")
        return
    name = m.group(1)

    updates = _parse_set_kvs(line)
    if not updates:
        print("  Error: at least one key=value pair is required")
        return

    results = [
        as_dict(r) async for r in ctx.client.security.certificate_authservice.list(name=name)
    ]
    if not results:
        print(f"  No certificate auth service found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.certificate_authservice.update(ref, updates)


# ---------------------------------------------------------------------------
# Handler: show auth certificate [<name>]
# ---------------------------------------------------------------------------


@command("show auth certificate", words="<cr> <name>", help="List certificate auth services.")
@command(
    "show auth certificate <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific certificate auth service.",
)
async def cli_show_auth_certificate(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    name_filter = None
    # "show auth certificate [<name>]" → tokens[3] if present
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        name_filter = tokens[3]

    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": ["name", "comment", "auto_populate_login", "disabled"] + extra
    }
    if name_filter:
        kwargs["name"] = name_filter

    results = [as_dict(r) async for r in ctx.client.security.certificate_authservice.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("auto_populate_login"):
            parts.append(f"auto_populate_login={r['auto_populate_login']}")
        if r.get("disabled") is not None:
            parts.append(f"disabled={r['disabled']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Waypoints - LocalUser auth service (read-only singleton; show only)
# ---------------------------------------------------------------------------

register("configure auth localuser", words="<cr>")
register("show auth localuser", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure auth localuser  (informational only)
# ---------------------------------------------------------------------------


@command(
    "configure auth localuser",
    words="<cr>",
    help="Show the built-in local-user auth service (read-only singleton).",
)
async def cli_configure_auth_localuser(line: str, ctx: Context) -> None:
    """The localuser auth service is a WAPI read-only singleton.

    All fields (name, comment, disabled) are readOnly - modification
    is not supported via ibcli. This handler just explains that.
    """
    print("  Note: the local-user auth service is a read-only singleton.")
    print("  Use 'show auth localuser' to view its current state.")


# ---------------------------------------------------------------------------
# Handler: show auth localuser
# ---------------------------------------------------------------------------


@command(
    "show auth localuser",
    words="<cr> fields=<field1,field2,...>",
    help="Show the local-user auth service.",
)
async def cli_show_auth_localuser(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields_plus": ["name", "comment", "disabled"] + extra}
    results = [as_dict(r) async for r in ctx.client.security.localuser_authservice.list(**kwargs)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("disabled") is not None:
            parts.append(f"disabled={r['disabled']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Chunk D - Auth policy (singleton)
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - auth policy
# ---------------------------------------------------------------------------

register(
    "configure auth policy",
    words="set",
    help="Global auth-policy order and the active service list.",
)
register("configure auth policy set", words="<cr> <key>=<value>")
register("show auth policy", words="<cr> fields=<field1,field2,...>")

# ---------------------------------------------------------------------------
# Handler: configure auth policy set key=value
# ---------------------------------------------------------------------------


@command(
    "configure auth policy set",
    words="<cr> <key>=<value>",
    help="Update the grid authentication policy (singleton GET-then-PUT).",
)
async def cli_set_auth_policy(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    updates = _parse_set_kvs(line)
    if not updates:
        print("  Error: at least one key=value pair is required")
        return

    # authpolicy is a singleton - get the single record's ref then PUT.
    results = [as_dict(r) async for r in ctx.client.security.authpolicy.list()]
    if not results:
        print("  Error: no authpolicy object found in the grid")
        return
    ref = results[0]["_ref"]
    await ctx.client.security.authpolicy.update(ref, updates)


# ---------------------------------------------------------------------------
# Handler: show auth policy
# ---------------------------------------------------------------------------


@command(
    "show auth policy",
    words="<cr> fields=<field1,field2,...>",
    help="Show the grid authentication policy.",
)
async def cli_show_auth_policy(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    extra = parse_extra_fields(line)
    kwargs: dict = {
        "return_fields_plus": ["auth_services", "default_group", "admin_groups", "usage_type"]
        + extra
    }
    results = [as_dict(r) async for r in ctx.client.security.authpolicy.list(**kwargs)]

    for r in results:
        if r.get("auth_services"):
            svcs = r["auth_services"]
            print(f"auth_services={','.join(svcs) if isinstance(svcs, list) else svcs}")
        if r.get("default_group"):
            print(f"default_group={r['default_group']}")
        if r.get("admin_groups"):
            groups = r["admin_groups"]
            print(f"admin_groups={','.join(groups) if isinstance(groups, list) else groups}")
        if r.get("usage_type"):
            print(f"usage_type={r['usage_type']}")
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")
