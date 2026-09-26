# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""DTC command handlers - Phase 7.

Provides ``configure dtc`` and ``show dtc`` command trees for managing
DNS Traffic Control resources via the Infoblox WAPI.

Command vocabulary summary
--------------------------
# Grid-level DTC config (singleton, GET/PUT only)
configure dtc set <key>=<value>
show dtc

# Servers
configure dtc server add <name> host=<ip> [comment=<text>]
configure dtc server <name> delete
configure dtc server <name> set <key>=<value>
show dtc server [<name>]

# Pools
configure dtc pool add <name> lb_preferred_method=<method> [comment=<text>]
configure dtc pool <name> delete
configure dtc pool <name> set <key>=<value>
show dtc pool [<name>]

# LBDNs
configure dtc lbdn add <name> [lb_method=<method>] [patterns=<fqdn>[,...]] [comment=<text>]
configure dtc lbdn <name> delete
configure dtc lbdn <name> set <key>=<value>
show dtc lbdn [<name>]

# Monitors - per protocol (http, icmp, tcp, snmp, sip, pdp)
configure dtc monitor http add <name> [port=<num>] [comment=<text>]
configure dtc monitor http <name> delete
configure dtc monitor http <name> set <key>=<value>
show dtc monitor http [<name>]
(same shape for icmp, tcp, snmp, sip, pdp)
show dtc monitor   # aggregated read-only across all monitor types

# Topology
configure dtc topology add <name> [comment=<text>]
configure dtc topology <name> delete
configure dtc topology <name> set <key>=<value>
show dtc topology [<name>]

# Topology labels (GET-only aggregator scoped to a topology)
show dtc topology <topology_name> label

# Topology rules (GET-only aggregator scoped to a topology)
show dtc topology <topology_name> rule

# Certificates (GET/DELETE)
configure dtc certificate <ref> delete
show dtc certificate

# DTC records (read-only, grid-generated)
show dtc record a [<name>]
show dtc record aaaa [<name>]
show dtc record cname [<name>]
show dtc record srv [<name>]
show dtc record naptr [<name>]
show dtc records   # allrecords aggregator

# Grid DTC object aggregator (read-only)
show dtc object [<name>]
"""

from __future__ import annotations

import re

from ibcli.coerce import coerce as _coerce  # noqa: F401
from ibcli.completions_keys import keys_completer_for_path
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict

_DTC_KEYS = keys_completer_for_path("dtc", "dtc")
_DTC_SERVER_KEYS = keys_completer_for_path("dtc", "server")
_DTC_POOL_KEYS = keys_completer_for_path("dtc", "pool")
_DTC_LBDN_KEYS = keys_completer_for_path("dtc", "lbdn")
_DTC_TOPOLOGY_KEYS = keys_completer_for_path("dtc", "topology")
_DTC_MONITOR_KEYS = {
    "http": keys_completer_for_path("dtc", "monitor_http"),
    "icmp": keys_completer_for_path("dtc", "monitor_icmp"),
    "tcp": keys_completer_for_path("dtc", "monitor_tcp"),
    "snmp": keys_completer_for_path("dtc", "monitor_snmp"),
    "sip": keys_completer_for_path("dtc", "monitor_sip"),
    "pdp": keys_completer_for_path("dtc", "monitor_pdp"),
}

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

    Handles both ``key=value`` (raw input) and ``key value`` (after tokenizer
    splits the ``=`` away) forms.
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


# ---------------------------------------------------------------------------
# Chunk A: Grid-level DTC config + servers + pools
# ---------------------------------------------------------------------------

register("configure", words="dtc", help="Create, modify or delete grid objects.")
register("show", words="dtc", help="Read grid state without modifying anything.")
register(
    "configure dtc",
    words="set server pool lbdn monitor topology certificate",
    help="Traffic-Director - global server load-balancing via DNS.",
)
register(
    "show dtc",
    words="server pool lbdn monitor topology certificate record records object",
    help="DTC - servers, pools, LBDNs, monitors, topology, certificate.",
)

# --- Grid-level DTC set ---
register("configure dtc set", words="<key>=<value>", dynamic=_DTC_KEYS)


@command("configure dtc set", words="<key>=<value>", help="Set grid-level DTC config fields.")
async def cli_dtc_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    body = _parse_inline_kvs(line, " dtc set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [as_dict(r) async for r in ctx.client.dtc.dtc.list(max_results=1)]
    if not results:
        print("  No DTC global config found")
        return
    ref = results[0]["_ref"]
    await ctx.client.dtc.dtc.update(ref, body)


# --- show dtc (grid-level) ---


@command(
    "show dtc",
    words="server pool lbdn monitor topology certificate record records object",
    help="Show grid-level DTC configuration.",
)
async def cli_dtc_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    # Only handle bare "show dtc" (no additional tokens beyond show dtc)
    tokens = line.split()
    if len(tokens) > 2:
        return  # sub-commands handle these
    results = [as_dict(r) async for r in ctx.client.dtc.dtc.list()]
    for r in results:
        parts = ["type=dtc"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# ---------------------------------------------------------------------------
# DTC Servers
# ---------------------------------------------------------------------------

register(
    "configure dtc server",
    words="add <name>",
    help="DTC back-end servers (real hosts DTC can resolve to).",
)
register("configure dtc server add", words="<name>")

_SERVER_ADD_WORDS = "<cr> host=<name>|comment=<comment>"
register("configure dtc server add <name>", words=_SERVER_ADD_WORDS)


@command("configure dtc server add <name>", words=_SERVER_ADD_WORDS, help="Add a DTC server.")
async def cli_dtc_server_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc server add (\S+)", line)
    if not m:
        print("  Error: server name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    host = _kv(line, "host")
    if host:
        body["host"] = host
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.dtc.server.create(body)


register("configure dtc server <name>", words="delete set")
register("configure dtc server <name> delete", words="<cr>")


@command("configure dtc server <name> delete", words="<cr>", help="Delete a DTC server.")
async def cli_dtc_server_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc server (\S+) delete", line)
    if not m:
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.dtc.server.list(name=name, max_results=1)]
    if not results:
        print(f"  No DTC server found: {name}")
        return
    await ctx.client.dtc.server.delete(results[0]["_ref"])


register("configure dtc server <name> set", words="<key>=<value>", dynamic=_DTC_SERVER_KEYS)


@command(
    "configure dtc server <name> set", words="<key>=<value>", help="Set fields on a DTC server."
)
async def cli_dtc_server_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc server (\S+) set\b", line)
    if not m:
        return
    name = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [as_dict(r) async for r in ctx.client.dtc.server.list(name=name, max_results=1)]
    if not results:
        print(f"  No DTC server found: {name}")
        return
    await ctx.client.dtc.server.update(results[0]["_ref"], body)


register("show dtc server", words="<cr> <name>")
register("show dtc server <name>", words="<cr>")


@command("show dtc server", words="<cr> <name>", help="Show DTC servers.")
@command("show dtc server <name>", words="<cr>", help="Show a specific DTC server.")
async def cli_dtc_server_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    params: dict = {}
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            params["name"] = candidate
    results = [as_dict(r) async for r in ctx.client.dtc.server.list(**params)]
    if not results:
        if params.get("name"):
            print(f"  No DTC server found: {params['name']}")
        return
    for r in results:
        parts = ["type=dtc:server"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# ---------------------------------------------------------------------------
# DTC Pools
# ---------------------------------------------------------------------------

register(
    "configure dtc pool",
    words="add <name>",
    help="Pools of DTC servers with a load-balancing method.",
)
register("configure dtc pool add", words="<name>")

_POOL_ADD_WORDS = "<cr> lb_preferred_method=<name>|comment=<comment>"
register("configure dtc pool add <name>", words=_POOL_ADD_WORDS)


@command("configure dtc pool add <name>", words=_POOL_ADD_WORDS, help="Add a DTC pool.")
async def cli_dtc_pool_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc pool add (\S+)", line)
    if not m:
        print("  Error: pool name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    lb = _kv(line, "lb_preferred_method")
    if lb:
        body["lb_preferred_method"] = lb.upper()
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.dtc.pool.create(body)


register("configure dtc pool <name>", words="delete set")
register("configure dtc pool <name> delete", words="<cr>")


@command("configure dtc pool <name> delete", words="<cr>", help="Delete a DTC pool.")
async def cli_dtc_pool_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc pool (\S+) delete", line)
    if not m:
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.dtc.pool.list(name=name, max_results=1)]
    if not results:
        print(f"  No DTC pool found: {name}")
        return
    await ctx.client.dtc.pool.delete(results[0]["_ref"])


register("configure dtc pool <name> set", words="<key>=<value>", dynamic=_DTC_POOL_KEYS)


@command("configure dtc pool <name> set", words="<key>=<value>", help="Set fields on a DTC pool.")
async def cli_dtc_pool_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc pool (\S+) set\b", line)
    if not m:
        return
    name = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [as_dict(r) async for r in ctx.client.dtc.pool.list(name=name, max_results=1)]
    if not results:
        print(f"  No DTC pool found: {name}")
        return
    await ctx.client.dtc.pool.update(results[0]["_ref"], body)


register("show dtc pool", words="<cr> <name>")
register("show dtc pool <name>", words="<cr>")


@command("show dtc pool", words="<cr> <name>", help="Show DTC pools.")
@command("show dtc pool <name>", words="<cr>", help="Show a specific DTC pool.")
async def cli_dtc_pool_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    params: dict = {}
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            params["name"] = candidate
    results = [as_dict(r) async for r in ctx.client.dtc.pool.list(**params)]
    if not results:
        if params.get("name"):
            print(f"  No DTC pool found: {params['name']}")
        return
    for r in results:
        parts = ["type=dtc:pool"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# ---------------------------------------------------------------------------
# Chunk B: LBDNs + DTC records
# ---------------------------------------------------------------------------

register(
    "configure dtc lbdn",
    words="add <name>",
    help="Load-Balanced Domain Name - DNS name fronted by DTC.",
)
register("configure dtc lbdn add", words="<name>")

_LBDN_ADD_WORDS = "<cr> lb_method=<name>|patterns=<name>|comment=<comment>"
register("configure dtc lbdn add <name>", words=_LBDN_ADD_WORDS)


@command("configure dtc lbdn add <name>", words=_LBDN_ADD_WORDS, help="Add a DTC LBDN.")
async def cli_dtc_lbdn_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc lbdn add (\S+)", line)
    if not m:
        print("  Error: LBDN name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    lb = _kv(line, "lb_method")
    if lb:
        body["lb_method"] = lb.upper()
    patterns_raw = _kv(line, "patterns")
    if patterns_raw:
        body["patterns"] = [p.strip() for p in patterns_raw.split(",") if p.strip()]
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.dtc.lbdn.create(body)


register("configure dtc lbdn <name>", words="delete set")
register("configure dtc lbdn <name> delete", words="<cr>")


@command("configure dtc lbdn <name> delete", words="<cr>", help="Delete a DTC LBDN.")
async def cli_dtc_lbdn_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc lbdn (\S+) delete", line)
    if not m:
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.dtc.lbdn.list(name=name, max_results=1)]
    if not results:
        print(f"  No DTC LBDN found: {name}")
        return
    await ctx.client.dtc.lbdn.delete(results[0]["_ref"])


register("configure dtc lbdn <name> set", words="<key>=<value>", dynamic=_DTC_LBDN_KEYS)


@command("configure dtc lbdn <name> set", words="<key>=<value>", help="Set fields on a DTC LBDN.")
async def cli_dtc_lbdn_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc lbdn (\S+) set\b", line)
    if not m:
        return
    name = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [as_dict(r) async for r in ctx.client.dtc.lbdn.list(name=name, max_results=1)]
    if not results:
        print(f"  No DTC LBDN found: {name}")
        return
    await ctx.client.dtc.lbdn.update(results[0]["_ref"], body)


# ---------------------------------------------------------------------------
# DTC wiring: pool↔server, pool↔monitor, lbdn↔pool
#
# These attach child objects onto their parent's link array. Each command
# reads the parent, mutates the list, and PUTs the whole list back - NIOS
# has no _func-based append for these fields.
# ---------------------------------------------------------------------------

_MON_PROTOS = ("http", "icmp", "tcp", "snmp", "sip", "pdp")


async def _find_dtc_ref(ctx: Context, resource, name: str) -> str | None:
    results = [as_dict(r) async for r in resource.list(name=name, max_results=1)]
    return results[0]["_ref"] if results else None


def _monitor_resource(ctx: Context, proto: str):
    return getattr(ctx.client.dtc, f"monitor_{proto}")


from ibcli import completions as _completions  # noqa: E402

# Bring live pool/lbdn/server/monitor names into tab-complete for the <name>
# slots that select an existing object. The `dynamic` hook goes on the
# waypoint whose `words` string contains the <slot>, not the waypoint keyed
# by the slot - the completer looks it up on the parent.
register(
    "configure dtc pool",
    dynamic=_completions.dtc_pools,
    help="Pools of DTC servers with a load-balancing method.",
)
register(
    "configure dtc lbdn",
    dynamic=_completions.dtc_lbdns,
    help="Load-Balanced Domain Name - DNS name fronted by DTC.",
)
register(
    "configure dtc server",
    dynamic=_completions.dtc_servers,
    help="DTC back-end servers (real hosts DTC can resolve to).",
)


# --- pool ↔ server ----------------------------------------------------------

register("configure dtc pool <name>", words="server monitor")
register("configure dtc pool <name> server", words="add delete")
register("configure dtc pool <name> server add", words="<name>", dynamic=_completions.dtc_servers)
register("configure dtc pool <name> server add <name>", words="<cr> ratio=<value>")
register(
    "configure dtc pool <name> server delete", words="<name>", dynamic=_completions.dtc_servers
)
register("configure dtc pool <name> server delete <name>", words="<cr>")


@command(
    "configure dtc pool <name> server add <name>",
    words="<cr> ratio=<value>",
    help="Attach a DTC server to a pool (appends to servers[]).",
)
async def cli_dtc_pool_server_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc pool (\S+) server add (\S+)", line)
    if not m:
        return
    pool_name, server_name = m.group(1), m.group(2)
    try:
        ratio = int(_kv(line, "ratio") or 1)
    except ValueError:
        print("  Error: ratio must be an integer")
        return

    pool_ref = await _find_dtc_ref(ctx, ctx.client.dtc.pool, pool_name)
    if not pool_ref:
        print(f"  No DTC pool found: {pool_name}")
        return
    server_ref = await _find_dtc_ref(ctx, ctx.client.dtc.server, server_name)
    if not server_ref:
        print(f"  No DTC server found: {server_name}")
        return

    pool = as_dict(await ctx.client.dtc.pool.get(pool_ref, return_fields=["servers"]))
    servers = list(pool.get("servers") or [])
    if any(s.get("server") == server_ref for s in servers):
        print(f"  Skipped: server {server_name} already in pool {pool_name}")
        return
    servers.append({"server": server_ref, "ratio": ratio})
    await ctx.client.dtc.pool.update(pool_ref, {"servers": servers})


@command(
    "configure dtc pool <name> server delete <name>",
    words="<cr>",
    help="Detach a DTC server from a pool.",
)
async def cli_dtc_pool_server_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc pool (\S+) server delete (\S+)", line)
    if not m:
        return
    pool_name, server_name = m.group(1), m.group(2)

    pool_ref = await _find_dtc_ref(ctx, ctx.client.dtc.pool, pool_name)
    if not pool_ref:
        print(f"  No DTC pool found: {pool_name}")
        return
    server_ref = await _find_dtc_ref(ctx, ctx.client.dtc.server, server_name)
    if not server_ref:
        print(f"  No DTC server found: {server_name}")
        return

    pool = as_dict(await ctx.client.dtc.pool.get(pool_ref, return_fields=["servers"]))
    servers = [s for s in (pool.get("servers") or []) if s.get("server") != server_ref]
    await ctx.client.dtc.pool.update(pool_ref, {"servers": servers})


# --- pool ↔ monitor ---------------------------------------------------------

_PROTO_WORDS = " ".join(_MON_PROTOS)
register("configure dtc pool <name> monitor", words="add delete")
register("configure dtc pool <name> monitor add", words=_PROTO_WORDS)
register("configure dtc pool <name> monitor delete", words=_PROTO_WORDS)
_MON_DYNAMIC = {
    "http": _completions.dtc_monitor_http,
    "icmp": _completions.dtc_monitor_icmp,
    "tcp": _completions.dtc_monitor_tcp,
    "snmp": _completions.dtc_monitor_snmp,
    "sip": _completions.dtc_monitor_sip,
    "pdp": _completions.dtc_monitor_pdp,
}
for _proto in _MON_PROTOS:
    _mon = _MON_DYNAMIC[_proto]
    register(f"configure dtc pool <name> monitor add {_proto}", words="<name>", dynamic=_mon)
    register(f"configure dtc pool <name> monitor add {_proto} <name>", words="<cr>")
    register(f"configure dtc pool <name> monitor delete {_proto}", words="<name>", dynamic=_mon)
    register(f"configure dtc pool <name> monitor delete {_proto} <name>", words="<cr>")


async def _pool_monitor_edit(line: str, ctx: Context, *, attach: bool) -> None:
    verb = "add" if attach else "delete"
    m = re.search(rf"\bdtc pool (\S+) monitor {verb} (\w+) (\S+)", line)
    if not m:
        return
    pool_name, proto, monitor_name = m.group(1), m.group(2), m.group(3)
    if proto not in _MON_PROTOS:
        print(f"  Error: unknown monitor protocol '{proto}'")
        return

    pool_ref = await _find_dtc_ref(ctx, ctx.client.dtc.pool, pool_name)
    if not pool_ref:
        print(f"  No DTC pool found: {pool_name}")
        return
    mon_ref = await _find_dtc_ref(ctx, _monitor_resource(ctx, proto), monitor_name)
    if not mon_ref:
        print(f"  No DTC {proto} monitor found: {monitor_name}")
        return

    pool = as_dict(await ctx.client.dtc.pool.get(pool_ref, return_fields=["monitors"]))
    monitors = list(pool.get("monitors") or [])
    if attach:
        if mon_ref in monitors:
            print(f"  Skipped: {proto} monitor {monitor_name} already attached to {pool_name}")
            return
        monitors.append(mon_ref)
    else:
        monitors = [m_ for m_ in monitors if m_ != mon_ref]
    await ctx.client.dtc.pool.update(pool_ref, {"monitors": monitors})


for _proto in _MON_PROTOS:

    @command(
        f"configure dtc pool <name> monitor add {_proto} <name>",
        words="<cr>",
        help=f"Attach a {_proto.upper()} monitor to a pool.",
    )
    async def _add_mon(line: str, ctx: Context) -> None:
        if ctx.client is None:
            _not_connected()
            return
        await _pool_monitor_edit(line, ctx, attach=True)

    @command(
        f"configure dtc pool <name> monitor delete {_proto} <name>",
        words="<cr>",
        help=f"Detach a {_proto.upper()} monitor from a pool.",
    )
    async def _del_mon(line: str, ctx: Context) -> None:
        if ctx.client is None:
            _not_connected()
            return
        await _pool_monitor_edit(line, ctx, attach=False)


# --- lbdn ↔ pool ------------------------------------------------------------

register("configure dtc lbdn <name>", words="pool")
register("configure dtc lbdn <name> pool", words="add delete")
register("configure dtc lbdn <name> pool add", words="<name>", dynamic=_completions.dtc_pools)
register("configure dtc lbdn <name> pool add <name>", words="<cr> ratio=<value>")
register("configure dtc lbdn <name> pool delete", words="<name>", dynamic=_completions.dtc_pools)
register("configure dtc lbdn <name> pool delete <name>", words="<cr>")


@command(
    "configure dtc lbdn <name> pool add <name>",
    words="<cr> ratio=<value>",
    help="Attach a DTC pool to an LBDN (appends to pools[]).",
)
async def cli_dtc_lbdn_pool_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc lbdn (\S+) pool add (\S+)", line)
    if not m:
        return
    lbdn_name, pool_name = m.group(1), m.group(2)
    try:
        ratio = int(_kv(line, "ratio") or 1)
    except ValueError:
        print("  Error: ratio must be an integer")
        return

    lbdn_ref = await _find_dtc_ref(ctx, ctx.client.dtc.lbdn, lbdn_name)
    if not lbdn_ref:
        print(f"  No DTC LBDN found: {lbdn_name}")
        return
    pool_ref = await _find_dtc_ref(ctx, ctx.client.dtc.pool, pool_name)
    if not pool_ref:
        print(f"  No DTC pool found: {pool_name}")
        return

    lbdn = as_dict(await ctx.client.dtc.lbdn.get(lbdn_ref, return_fields=["pools"]))
    pools = list(lbdn.get("pools") or [])
    if any(p.get("pool") == pool_ref for p in pools):
        print(f"  Skipped: pool {pool_name} already in LBDN {lbdn_name}")
        return
    pools.append({"pool": pool_ref, "ratio": ratio})
    await ctx.client.dtc.lbdn.update(lbdn_ref, {"pools": pools})


@command(
    "configure dtc lbdn <name> pool delete <name>",
    words="<cr>",
    help="Detach a DTC pool from an LBDN.",
)
async def cli_dtc_lbdn_pool_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc lbdn (\S+) pool delete (\S+)", line)
    if not m:
        return
    lbdn_name, pool_name = m.group(1), m.group(2)

    lbdn_ref = await _find_dtc_ref(ctx, ctx.client.dtc.lbdn, lbdn_name)
    if not lbdn_ref:
        print(f"  No DTC LBDN found: {lbdn_name}")
        return
    pool_ref = await _find_dtc_ref(ctx, ctx.client.dtc.pool, pool_name)
    if not pool_ref:
        print(f"  No DTC pool found: {pool_name}")
        return

    lbdn = as_dict(await ctx.client.dtc.lbdn.get(lbdn_ref, return_fields=["pools"]))
    pools = [p for p in (lbdn.get("pools") or []) if p.get("pool") != pool_ref]
    await ctx.client.dtc.lbdn.update(lbdn_ref, {"pools": pools})


register("show dtc lbdn", words="<cr> <name>")
register("show dtc lbdn <name>", words="<cr>")


@command("show dtc lbdn", words="<cr> <name>", help="Show DTC LBDNs.")
@command("show dtc lbdn <name>", words="<cr>", help="Show a specific DTC LBDN.")
async def cli_dtc_lbdn_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    params: dict = {}
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            params["name"] = candidate
    results = [as_dict(r) async for r in ctx.client.dtc.lbdn.list(**params)]
    if not results:
        if params.get("name"):
            print(f"  No DTC LBDN found: {params['name']}")
        return
    for r in results:
        parts = ["type=dtc:lbdn"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# --- DTC records (read-only: a, aaaa, cname, srv, naptr) ---

register("show dtc record", words="a aaaa cname srv naptr")

_DTC_RECORD_TYPES: dict[str, str] = {
    "a": "record_a",
    "aaaa": "record_aaaa",
    "cname": "record_cname",
    "srv": "record_srv",
    "naptr": "record_naptr",
}

for _rt in _DTC_RECORD_TYPES:
    register(f"show dtc record {_rt}", words="<name>")
    register(f"show dtc record {_rt} <name>", words="<cr>")


def _bind_dtc_record_show(rtype: str, sdk_attr: str) -> None:
    @command(
        f"show dtc record {rtype}",
        words="<name>",
        help=f"Show DTC {rtype.upper()} records for a DTC server.",
    )
    @command(f"show dtc record {rtype} <name>", words="<cr>")
    async def _show(line: str, ctx: Context) -> None:
        if ctx.client is None:
            _not_connected()
            return
        tokens = line.split()
        dtc_server: str | None = None
        if len(tokens) >= 5:
            candidate = tokens[4]
            if not candidate.startswith("<"):
                dtc_server = candidate
        if not dtc_server:
            print(f"  Error: dtc_server required (usage: show dtc record {rtype} <dtc_server>)")
            return
        resource = getattr(ctx.client.dtc, sdk_attr)
        results = [as_dict(r) async for r in resource.list(dtc_server=dtc_server)]
        for r in results:
            parts = [f"type=dtc:record:{rtype}"]
            for k, v in r.items():
                if not k.startswith("_"):
                    parts.append(f"{k}={v}")
            print(" ".join(parts))


for _rt, _sa in _DTC_RECORD_TYPES.items():
    _bind_dtc_record_show(_rt, _sa)


# --- show dtc records (allrecords aggregator) ---
register("show dtc records", words="<name>")
register("show dtc records <name>", words="<cr>")


@command(
    "show dtc records", words="<name>", help="Show all DTC records for a DTC zone (aggregate)."
)
@command("show dtc records <name>", words="<cr>")
async def cli_dtc_allrecords_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    zone: str | None = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            zone = candidate
    if not zone:
        print("  Error: zone required (usage: show dtc records <zone>)")
        return
    results = [as_dict(r) async for r in ctx.client.dtc.allrecords.list(zone=zone)]
    for r in results:
        parts = []
        rtype = r.get("type") or r.get("type_")
        if rtype:
            parts.append(f"type={rtype}")
        for k, v in r.items():
            if not k.startswith("_") and k not in ("type", "type_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# ---------------------------------------------------------------------------
# Chunk C: Monitors (base aggregator + 6 protocol-specific)
# ---------------------------------------------------------------------------

register(
    "configure dtc monitor",
    words="http icmp tcp snmp sip pdp",
    help="DTC health monitors (http/icmp/tcp/snmp/sip/pdp).",
)
register("show dtc monitor", words="<cr> http icmp tcp snmp sip pdp")


@command(
    "show dtc monitor",
    words="<cr> http icmp tcp snmp sip pdp",
    help="Show all DTC monitors (aggregate read-only).",
)
async def cli_dtc_monitor_show_all(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    # Only handle bare "show dtc monitor"
    tokens = line.split()
    if len(tokens) > 3:
        return  # protocol-specific handlers take over
    results = [as_dict(r) async for r in ctx.client.dtc.monitor.list()]
    for r in results:
        parts = ["type=dtc:monitor"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# Protocol-specific monitor map: cli_name -> sdk_attr on ctx.client.dtc
_MONITOR_PROTOCOLS: dict[str, str] = {
    "http": "monitor_http",
    "icmp": "monitor_icmp",
    "tcp": "monitor_tcp",
    "snmp": "monitor_snmp",
    "sip": "monitor_sip",
    "pdp": "monitor_pdp",
}

_MON_ADD_WORDS = "<cr> port=<name>|comment=<comment>"

for _proto in _MONITOR_PROTOCOLS:
    register(f"configure dtc monitor {_proto}", words="add <name>")
    register(f"configure dtc monitor {_proto} add", words="<name>")
    register(f"configure dtc monitor {_proto} add <name>", words=_MON_ADD_WORDS)
    register(f"configure dtc monitor {_proto} <name>", words="delete set")
    register(f"configure dtc monitor {_proto} <name> delete", words="<cr>")
    register(
        f"configure dtc monitor {_proto} <name> set",
        words="<key>=<value>",
        dynamic=_DTC_MONITOR_KEYS[_proto],
    )
    register(f"show dtc monitor {_proto}", words="<cr> <name>")
    register(f"show dtc monitor {_proto} <name>", words="<cr>")


def _bind_monitor_protocol(proto: str, sdk_attr: str) -> None:
    """Close over proto and sdk_attr to create per-protocol handlers."""

    def make_add(p=proto, sa=sdk_attr):
        async def _h(line: str, ctx: Context) -> None:
            if ctx.client is None:
                _not_connected()
                return
            m = re.search(rf"\bdtc monitor {re.escape(p)} add (\S+)", line)
            if not m:
                print("  Error: monitor name required")
                return
            name = m.group(1)
            body: dict = {"name": name}
            port = _kv(line, "port")
            if port and port.isdigit():
                body["port"] = int(port)
            cmt = _comment(line)
            if cmt:
                body["comment"] = cmt
            await getattr(ctx.client.dtc, sa).create(body)

        return _h

    def make_delete(p=proto, sa=sdk_attr):
        async def _h(line: str, ctx: Context) -> None:
            if ctx.client is None:
                _not_connected()
                return
            m = re.search(rf"\bdtc monitor {re.escape(p)} (\S+) delete", line)
            if not m:
                return
            name = m.group(1)
            resource = getattr(ctx.client.dtc, sa)
            results = [as_dict(r) async for r in resource.list(name=name, max_results=1)]
            if not results:
                print(f"  No DTC {p} monitor found: {name}")
                return
            await resource.delete(results[0]["_ref"])

        return _h

    def make_set(p=proto, sa=sdk_attr):
        async def _h(line: str, ctx: Context) -> None:
            if ctx.client is None:
                _not_connected()
                return
            m = re.search(rf"\bdtc monitor {re.escape(p)} (\S+) set\b", line)
            if not m:
                return
            name = m.group(1)
            body = _parse_inline_kvs(line, " set ")
            if not body:
                print("  Error: specify at least one key=value pair")
                return
            resource = getattr(ctx.client.dtc, sa)
            results = [as_dict(r) async for r in resource.list(name=name, max_results=1)]
            if not results:
                print(f"  No DTC {p} monitor found: {name}")
                return
            await resource.update(results[0]["_ref"], body)

        return _h

    def make_show(p=proto, sa=sdk_attr):
        async def _h(line: str, ctx: Context) -> None:
            if ctx.client is None:
                _not_connected()
                return
            tokens = line.split()
            params: dict = {}
            # tokens: show dtc monitor <proto> [<name>]
            if len(tokens) >= 5:
                candidate = tokens[4]
                if not candidate.startswith("<"):
                    params["name"] = candidate
            resource = getattr(ctx.client.dtc, sa)
            results = [as_dict(r) async for r in resource.list(**params)]
            if not results:
                if params.get("name"):
                    print(f"  No DTC {p} monitor found: {params['name']}")
                return
            for r in results:
                parts = [f"type=dtc:monitor:{p}"]
                for k, v in r.items():
                    if not k.startswith("_"):
                        parts.append(f"{k}={v}")
                print(" ".join(parts))

        return _h

    command(
        f"configure dtc monitor {proto} add <name>",
        words=_MON_ADD_WORDS,
        help=f"Add a DTC {proto.upper()} monitor.",
    )(make_add())
    command(
        f"configure dtc monitor {proto} <name> delete",
        words="<cr>",
        help=f"Delete a DTC {proto.upper()} monitor.",
    )(make_delete())
    command(
        f"configure dtc monitor {proto} <name> set",
        words="<key>=<value>",
        help=f"Set fields on a DTC {proto.upper()} monitor.",
    )(make_set())
    command(
        f"show dtc monitor {proto}",
        words="<cr> <name>",
        help=f"Show DTC {proto.upper()} monitors.",
    )(make_show())
    command(
        f"show dtc monitor {proto} <name>",
        words="<cr>",
        help=f"Show a specific DTC {proto.upper()} monitor.",
    )(make_show())


for _proto, _sa in _MONITOR_PROTOCOLS.items():
    _bind_monitor_protocol(_proto, _sa)


# ---------------------------------------------------------------------------
# Chunk D: Topology (group + rules + labels)
# ---------------------------------------------------------------------------

register(
    "configure dtc topology",
    words="add <name>",
    help="Geo/topology rulesets for DTC client steering.",
)
register("configure dtc topology add", words="<name>")

_TOPO_ADD_WORDS = "<cr> comment=<comment>"
register("configure dtc topology add <name>", words=_TOPO_ADD_WORDS)


@command("configure dtc topology add <name>", words=_TOPO_ADD_WORDS, help="Add a DTC topology.")
async def cli_dtc_topology_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc topology add (\S+)", line)
    if not m:
        print("  Error: topology name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.dtc.topology.create(body)


register("configure dtc topology <name>", words="delete set label rule")
register("configure dtc topology <name> delete", words="<cr>")


@command("configure dtc topology <name> delete", words="<cr>", help="Delete a DTC topology.")
async def cli_dtc_topology_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc topology (\S+) delete", line)
    if not m:
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.dtc.topology.list(name=name, max_results=1)]
    if not results:
        print(f"  No DTC topology found: {name}")
        return
    await ctx.client.dtc.topology.delete(results[0]["_ref"])


register("configure dtc topology <name> set", words="<key>=<value>", dynamic=_DTC_TOPOLOGY_KEYS)


@command(
    "configure dtc topology <name> set", words="<key>=<value>", help="Set fields on a DTC topology."
)
async def cli_dtc_topology_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc topology (\S+) set\b", line)
    if not m:
        return
    name = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [as_dict(r) async for r in ctx.client.dtc.topology.list(name=name, max_results=1)]
    if not results:
        print(f"  No DTC topology found: {name}")
        return
    await ctx.client.dtc.topology.update(results[0]["_ref"], body)


register("show dtc topology", words="<cr> <name>")
register("show dtc topology <name>", words="<cr> label rule")


@command("show dtc topology", words="<cr> <name>", help="Show DTC topologies.")
@command("show dtc topology <name>", words="<cr> label rule", help="Show a specific DTC topology.")
async def cli_dtc_topology_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    params: dict = {}
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            params["name"] = candidate
    results = [as_dict(r) async for r in ctx.client.dtc.topology.list(**params)]
    if not results:
        if params.get("name"):
            print(f"  No DTC topology found: {params['name']}")
        return
    for r in results:
        parts = ["type=dtc:topology"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# --- Topology labels (GET-only) ---

register("configure dtc topology <name> label", words="add <name>")
register("configure dtc topology <name> label add", words="<name>")
register("configure dtc topology <name> label add <name>", words="<cr>")
register("configure dtc topology <name> label <name>", words="delete")
register("configure dtc topology <name> label <name> delete", words="<cr>")
register("show dtc topology <name> label", words="<cr>")


@command("show dtc topology <name> label", words="<cr>", help="Show labels for a DTC topology.")
async def cli_dtc_topology_label_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bshow dtc topology (\S+) label", line)
    if not m:
        return
    topo_name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.dtc.topology_label.list(topology=topo_name)]
    for r in results:
        parts = ["type=dtc:topology:label"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# --- Topology rules (GET-only) ---

register("configure dtc topology <name> rule", words="add <name>")
register("configure dtc topology <name> rule add", words="<name>")
register("configure dtc topology <name> rule add <name>", words="<cr>")
register("configure dtc topology <name> rule <name>", words="delete")
register("configure dtc topology <name> rule <name> delete", words="<cr>")
register("show dtc topology <name> rule", words="<cr>")


@command("show dtc topology <name> rule", words="<cr>", help="Show rules for a DTC topology.")
async def cli_dtc_topology_rule_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bshow dtc topology (\S+) rule", line)
    if not m:
        return
    topo_name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.dtc.topology_rule.list(topology=topo_name)]
    for r in results:
        parts = ["type=dtc:topology:rule"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# ---------------------------------------------------------------------------
# Chunk E: Certificates + DTC object aggregator
# ---------------------------------------------------------------------------

# --- Certificates ---

register("configure dtc certificate", words="<name>")
register("configure dtc certificate <name>", words="delete")
register("configure dtc certificate <name> delete", words="<cr>")
register("show dtc certificate", words="<cr>")


@command(
    "configure dtc certificate <name> delete", words="<cr>", help="Delete a DTC certificate by ref."
)
async def cli_dtc_certificate_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdtc certificate (\S+) delete", line)
    if not m:
        print("  Error: DTC certificate ref required")
        return
    ref = m.group(1)
    # dtc:certificate carries no name field to search on, so only a real _ref
    # can identify one. Say so instead of letting the SDK raise ValueError.
    if not ref.startswith("dtc:certificate/"):
        print(
            f"  Error: not a dtc:certificate ref: {ref} (use `show dtc certificate` to list refs)"
        )
        return
    await ctx.client.dtc.certificate.delete(ref)


@command("show dtc certificate", words="<cr>", help="Show DTC certificates.")
async def cli_dtc_certificate_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    results = [as_dict(r) async for r in ctx.client.dtc.certificate.list()]
    for r in results:
        parts = ["type=dtc:certificate"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))


# --- DTC object aggregator (read-only) ---

register("show dtc object", words="<cr> <name>")
register("show dtc object <name>", words="<cr>")


@command("show dtc object", words="<cr> <name>", help="Show DTC objects (aggregate).")
@command("show dtc object <name>", words="<cr>")
async def cli_dtc_object_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    params: dict = {}
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            params["name"] = candidate
    results = [as_dict(r) async for r in ctx.client.dtc.object.list(**params)]
    for r in results:
        parts = ["type=dtc:object"]
        for k, v in r.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))
