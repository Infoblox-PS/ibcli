# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

import asyncio
import re

from ibcli import completions as _completions
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict, format_extra_field, parse_extra_fields

# waypoints
register("configure", words="server master", help="Create, modify or delete grid objects.")
register("configure server", words="<svr>", help="Connect to a grid master by host/user/password.")
register("configure server <svr>", words="user=<name>|password=<value>|master=<ip>")
register(
    "configure master", words="<ip>", help="Set grid-master IP (for MGMT-port-only connections)."
)
# Only `show server version` is implemented. `error` and `message` were
# advertised with nothing behind them, so choosing one answered "Incomplete"
# and re-offered the same dead words.
register("show server", words="version", help="Current server connection info.")
register(
    "show grid",
    words="<cr> <name>",
    dynamic=_completions.grid_name,
    help="Grid-level configuration and metadata. Tab auto-fills the connected grid name.",
)
register("show views", words="<cr> <name>", help="DNS views (plural alias).")


@command(
    "configure server <svr>",
    words="<cr> user=<name>|password=<value>|master=<ip>",
    help="Connect to a grid master.",
)
async def cli_add_server(line: str, ctx: Context) -> None:
    m = re.search(r"\bserver (\S+)", line)
    server_host = m.group(1) if m else None
    m = re.search(r"\buser (\S+)", line)
    user = m.group(1) if m else None
    m = re.search(r"\bpassword (\S+)", line)
    password = m.group(1) if m else None
    m = re.search(r"\bmaster (\S+)", line)
    master = m.group(1) if m else None

    if not (server_host and user and password):
        print("  Error: server, user, and password are all required")
        return

    # Close any existing client connection first.
    if ctx.client is not None:
        try:
            await ctx.client.aclose()
        except Exception:
            pass
        ctx.client = None
        ctx.online = False

    # Imported here, not at module scope: constructing a client is the
    # only thing in this module that needs the SDK, and a module-level
    # import would put it on the startup path for every command.
    from ibx_nios_sdk import NiosClient

    client = NiosClient(
        grid_url=f"https://{server_host}",
        username=user,
        password=password,
        use_session=True,
        # TLS verification follows -k/--insecure (see ibcli.cli). Most NIOS
        # grids ship a self-signed cert, but silently disabling verification
        # would make the flag a lie.
        verify=ctx.verify,
        wapi_version=ctx.wapi_version,
        timeout=ctx.timeout,
        enforce_restrictions=ctx.enforce_restrictions,
    )
    try:
        # Validate credentials eagerly with a real authenticated call. The SDK
        # logs in lazily on first request, so any cheap read does the job and
        # surfaces a bad password here rather than on the operator's first
        # command. `grid` is the one object every NIOS grid has exactly one of.
        await client.grid.grid.list(max_results=1).all()
        ctx.client = client
        ctx.online = True
        ctx.host = server_host
        ctx.user = user
        ctx.prompt = f"{user}@{server_host} > "
        ctx.caches.clear()
        # Prime completion caches in the background so first-tab works.
        from ibcli import completions

        async def _prime() -> None:
            try:
                ctx.caches["members"] = await completions._fetch_members(ctx)
            except Exception:
                pass
            try:
                ctx.caches["grid_name"] = await completions._fetch_grid_name(ctx)
            except Exception:
                pass

        # Hold a reference so the task isn't garbage-collected mid-flight.
        ctx.caches["_prime_task"] = asyncio.create_task(_prime())
        # Store the WAPI version for `show server version`. The SDK has no
        # public accessor for the version it settled on, so fall back to its
        # private attribute when we didn't pin one ourselves.
        ctx.client_rev = ctx.wapi_version or client._http._wapi_version
        if master:
            ctx.master_ip = master
    except Exception as e:
        print(f"  Error: {e}")
        # The failed client still owns an open httpx connection pool; without
        # this every bad-password attempt in the REPL leaks one.
        try:
            await client.aclose()
        except Exception:
            pass
        ctx.client = None
        ctx.online = False


@command(
    "configure master <ip>", help="Set the grid master IP (used when connecting via MGMT port)."
)
async def cli_add_master(line: str, ctx: Context) -> None:
    m = re.search(r"\bmaster (\S+)", line)
    if m:
        ctx.master_ip = m.group(1)


@command("show server version", help="Print the detected WAPI version.")
async def cli_show_server_version(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    print(f" Server Version : {ctx.client_rev}")


@command("show grid", words="<cr> fields=<field1,field2,...>", help="Show grid-level info.")
async def cli_show_grid(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields": ["name"] + extra}
    grids = [as_dict(r) async for r in ctx.client.grid.grid.list(**kwargs)]
    for g in grids:
        print(f"name: {g.get('name', '')}  ref: {g.get('_ref', '')}")
        for f in extra:
            val = g.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


@command("show views", words="<cr> <name>", help="List DNS views.")
@command(
    "show views <name>", words="<cr> fields=<field1,field2,...>", help="Show a specific DNS view."
)
async def cli_show_views(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    tokens = line.split()
    extra = parse_extra_fields(line)
    kwargs: dict = {"return_fields": ["name", "comment", "is_default"] + extra}
    if len(tokens) >= 2 and tokens[1] == "views" and len(tokens) >= 3 and "=" not in tokens[2]:
        kwargs["name"] = tokens[2]
    views = [as_dict(r) async for r in ctx.client.dns.view.list(**kwargs)]
    for v in views:
        parts = [f"name={v.get('name', '')}"]
        if v.get("is_default"):
            parts.append("(default)")
        if v.get("comment"):
            parts.append(f"comment={v['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = v.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")
