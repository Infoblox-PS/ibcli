# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Ops command handlers - Phase 15.

Provides misc-domain command trees for database snapshots, data collection
clusters, CSV import tasks, scavenging tasks, capacity reports, integration
endpoints (TAXII, syslog, PxGrid, DXL, outbound cloud), BFD templates,
Kerberos keys, TFTP file directories, rulesets, and aggregator views.

SDK / WAPI surface notes
------------------------
- dbsnapshot      GET+PUT only (no POST/DELETE) - show only
- datacollectioncluster  full CRUD; 'name' is read-only server-assigned,
                  so add does not accept a name token
- csvimporttask   GET only (tasks spawned by fileop import) - show only
- scavengingtask  all fields read-only - show only (no start)
- capacityreport  GET only aggregate - show only
- taxii           GET+PUT only (name is read-only, server-assigned) - show + set
- syslog_endpoint full CRUD
- pxgrid_endpoint full CRUD
- dxl_endpoint    full CRUD
- outbound_cloudclient  GET+PUT only - show + set
- bfdtemplate     full CRUD
- kerberoskey     GET+DELETE only (no POST/PUT) - show + delete
- tftpfiledir     full CRUD
- ruleset         full CRUD
- allendpoints    GET only aggregate - show only
- deleted_objects GET only - show only
- db_objects      GET only - show only

search / request: deferred - cross-cutting WAPI primitives, not user-facing
commands.

Command vocabulary summary
--------------------------
# DB snapshot (read-only - no POST/DELETE in WAPI)
show db snapshot

# CSV import task (read-only)
show csv_task [<id>]

# Scavenging task (read-only - all fields server-assigned)
show scavenging

# Capacity report (read-only)
show capacity_report [<name>]

# Integrations - TAXII (GET+PUT only)
show integration taxii [<name>]
configure integration taxii <name> set <key>=<value>

# Integrations - syslog (full CRUD)
configure integration syslog add <name> [comment=<text>]
configure integration syslog <name> delete
show integration syslog [<name>]

# Integrations - pxgrid (full CRUD)
configure integration pxgrid add <name> [comment=<text>]
configure integration pxgrid <name> delete
show integration pxgrid [<name>]

# Integrations - dxl (full CRUD)
configure integration dxl add <name> [comment=<text>]
configure integration dxl <name> delete
show integration dxl [<name>]

# Integrations - outbound (GET+PUT only)
show integration outbound [<name>]
configure integration outbound <name> set <key>=<value>

# Aggregate endpoint view
show integration all

# BFD template (full CRUD)
configure bfd_template add <name> [comment=<text>]
configure bfd_template <name> delete
show bfd_template [<name>]

# Kerberos key (GET+DELETE only)
configure kerberos_key <ref> delete
show kerberos_key [<name>]

# TFTP file dir (full CRUD)
configure tftp_dir add <name> [comment=<text>]
configure tftp_dir <name> delete
show tftp_dir [<name>]

# Ruleset (full CRUD)
configure ruleset add <name> [type=<str>] [comment=<text>]
configure ruleset <name> delete
show ruleset [<name>]

# Read-only aggregates
show deleted_objects [<name>]
show db_objects
"""

from __future__ import annotations

import re

from ibcli import completions as _completions
from ibcli.coerce import coerce as _coerce  # noqa: F401
from ibcli.completions_keys import keys_completer_for_path
from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import as_dict

_TAXII_KEYS = keys_completer_for_path("misc", "taxii")
_OUTBOUND_KEYS = keys_completer_for_path("misc", "outbound_cloudclient")

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
# Chunk A: DB snapshot + data collection + CSV task + scavenging + capacity
# ===========================================================================

# ---------------------------------------------------------------------------
# A1: DB snapshot (read-only show - no POST/DELETE in WAPI)
# ---------------------------------------------------------------------------

register("show", words="db", help="Read grid state without modifying anything.")
register("show db", words="snapshot", help="Database snapshot / status info.")
register("show db snapshot", words="<cr>")


@command("show db snapshot", words="<cr>", help="Show database snapshots.")
async def cli_db_snapshot_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    records = [as_dict(r) async for r in ctx.client.misc.dbsnapshot.list()]
    if not records:
        return
    _print_records(records, "dbsnapshot")


# ---------------------------------------------------------------------------
# A2: Data collection cluster (full CRUD; name is server-assigned)
# ---------------------------------------------------------------------------
# Hidden for now - BloxOne / collector registration is not exposed in the CLI.
# Unhide by removing the surrounding `""" ... """` block.
r"""
register("configure", words="data_collection",
         help="Create, modify or delete grid objects.")
register("show", words="data_collection",
         help="Read grid state without modifying anything.")
register("configure data_collection", words="add <name>",
         help="Data-collection cluster configuration.")
register("configure data_collection add",
         words="<cr> comment=<comment> enable_registration=<value>")


@command(
    "configure data_collection add",
    words="<cr> comment=<comment> enable_registration=<value>",
    help="Add a data collection cluster.",
)
async def cli_data_collection_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    body: dict = {}
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    m = re.search(r"\benable_registration[= ](\S+)", line)
    if m:
        value = _coerce(m.group(1))
        if not isinstance(value, bool):
            print(f"  Error: enable_registration must be true or false (got {m.group(1)!r})")
            return
        body["enable_registration"] = value
    await ctx.client.misc.datacollectioncluster.create(body)


register("configure data_collection <name>", words="delete set")
register("configure data_collection <name> delete", words="<cr>")
register("configure data_collection <name> set",
         words="enable_registration=<value>")
register("configure data_collection <name> set enable_registration",
         words="<value>")
register("configure data_collection <name> set enable_registration <value>",
         words="<cr>")


@command(
    "configure data_collection <name> set enable_registration <value>",
    words="<cr>",
    help="Toggle whether new collectors can register with the cluster.",
)
async def cli_data_collection_set_registration(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdata_collection (\S+) set enable_registration (\S+)", line)
    if not m:
        print("  Error: usage: configure data_collection <name> set enable_registration true|false")
        return
    name, raw = m.group(1), m.group(2)
    value = _coerce(raw)
    if not isinstance(value, bool):
        print(f"  Error: enable_registration must be true or false (got {raw!r})")
        return
    results = [as_dict(r) async for r in ctx.client.misc.datacollectioncluster.list()]
    match = next(
        (r for r in results if r.get("uuid") == name or r.get("name") == name),
        None,
    )
    if match is None:
        print(f"  No data collection cluster found: {name}")
        return
    await ctx.client.misc.datacollectioncluster.update(
        match["_ref"], {"enable_registration": value}
    )


@command(
    "configure data_collection <name> delete",
    words="<cr>",
    help="Delete a data collection cluster.",
)
async def cli_data_collection_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bdata_collection (\S+) delete", line)
    if not m:
        print("  Error: cluster name required")
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.misc.datacollectioncluster.list()]
    match = next(
        (r for r in results if r.get("uuid") == name or r.get("name") == name),
        None,
    )
    if match is None:
        print(f"  No data collection cluster found: {name}")
        return
    await ctx.client.misc.datacollectioncluster.delete(match["_ref"])


register("show data_collection", words="<cr> <name>",
         help="Data-collection cluster state.")
register("show data_collection <name>", words="<cr>")


@command("show data_collection", words="<cr> <name>", help="Show data collection clusters.")
@command("show data_collection <name>", words="<cr>", help="Show a specific data collection cluster.")
async def cli_data_collection_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show data_collection [<name>]
    name = None
    if len(tokens) >= 3:
        candidate = tokens[2]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.misc.datacollectioncluster.list(**params)]
    if not records:
        if name:
            print(f"  No data collection cluster found: {name}")
        return
    _print_records(records, "datacollectioncluster")
"""


# ---------------------------------------------------------------------------
# A3: CSV import task (read-only)
# ---------------------------------------------------------------------------

register("show", words="csv_task", help="Read grid state without modifying anything.")
register("show csv_task", words="<cr> <name>", help="List CSV import tasks (with history).")
register("show csv_task <name>", words="<cr>")


@command("show csv_task", words="<cr> <name>", help="Show CSV import tasks.")
@command("show csv_task <name>", words="<cr>", help="Show a specific CSV import task.")
async def cli_csv_task_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show csv_task [<id>]
    task_id = None
    if len(tokens) >= 3:
        candidate = tokens[2]
        if not candidate.startswith("<"):
            task_id = candidate
    params: dict = {
        "return_fields": [
            "import_id",
            "status",
            "file_name",
            "start_time",
            "end_time",
            "lines_processed",
            "lines_failed",
            "lines_warning",
        ],
    }
    if task_id:
        params["import_id"] = task_id
    records = [as_dict(r) async for r in ctx.client.misc.csvimporttask.list(**params)]
    if not records:
        if task_id:
            print(f"  No CSV import task found: {task_id}")
        return
    _print_records(records, "csvimporttask")


# ---------------------------------------------------------------------------
# A4: Scavenging task (read-only - all fields server-assigned)
# ---------------------------------------------------------------------------

register("show", words="scavenging", help="Read grid state without modifying anything.")
register("show scavenging", words="<cr>", help="Scavenging (stale-record cleanup) tasks.")


@command("show scavenging", words="<cr>", help="Show scavenging tasks.")
async def cli_scavenging_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    records = [as_dict(r) async for r in ctx.client.misc.scavengingtask.list()]
    if not records:
        return
    _print_records(records, "scavengingtask")


# ---------------------------------------------------------------------------
# A5: Capacity report (read-only)
# ---------------------------------------------------------------------------

register("show", words="capacity_report", help="Read grid state without modifying anything.")
register(
    "show capacity_report",
    words="<cr> <member>",
    dynamic=_completions.members,
    help="Per-member capacity / utilization report.",
)
register("show capacity_report <member>", words="<cr>")


@command("show capacity_report", words="<cr> <member>", help="Show capacity reports.")
@command("show capacity_report <member>", words="<cr>", help="Show capacity report for a member.")
async def cli_capacity_report_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show capacity_report [<member>]
    name = None
    if len(tokens) >= 3:
        candidate = tokens[2]
        if not candidate.startswith("<"):
            name = candidate
    if not name:
        members = [as_dict(m) async for m in ctx.client.grid.member.list()]
        print("  Error: member name required (usage: show capacity_report <member>)")
        if members:
            print("  Available members:")
            for m in members:
                host = m.get("host_name") or m.get("name") or "?"
                addr = m.get("address") or m.get("vip_setting", {}).get("address", "")
                suffix = f"  ({addr})" if addr else ""
                print(f"    {host}{suffix}")
        return
    records = [
        as_dict(r)
        async for r in ctx.client.misc.capacityreport.list(
            name=name,
            return_fields_plus=["max_capacity", "object_counts", "role"],
        )
    ]
    if not records:
        print(f"  No capacity report found: {name}")
        return
    for rec in records:
        object_counts = rec.pop("object_counts", None) or []
        parts = ["type=capacityreport"]
        for k, v in rec.items():
            if not k.startswith("_"):
                parts.append(f"{k}={v}")
        print(" ".join(parts))
        if object_counts:
            print("  object_counts:")
            width = max((len(str(o.get("type_name", ""))) for o in object_counts), default=0)
            for obj in sorted(object_counts, key=lambda o: str(o.get("type_name", ""))):
                print(f"    {str(obj.get('type_name', '')):<{width}}  {obj.get('count', 0)}")


# ===========================================================================
# Chunk B: Integrations (TAXII, syslog, PxGrid, DXL, outbound + allendpoints)
# ===========================================================================

register("configure", words="integration", help="Create, modify or delete grid objects.")
register("show", words="integration", help="Read grid state without modifying anything.")
register(
    "configure integration",
    words="taxii syslog pxgrid dxl outbound",
    help="Outbound integrations (TAXII, syslog, PxGrid, DXL, cloud).",
)
register(
    "show integration",
    words="taxii syslog pxgrid dxl outbound all",
    help="Outbound integrations (taxii, syslog, pxgrid, dxl).",
)

# ---------------------------------------------------------------------------
# B1: TAXII (GET+PUT only - show + set only)
# ---------------------------------------------------------------------------

register("configure integration taxii", words="<name>")
register("configure integration taxii <name>", words="set")
register("configure integration taxii <name> set", words="<key>=<value>", dynamic=_TAXII_KEYS)


@command(
    "configure integration taxii <name> set",
    words="<key>=<value>",
    help="Set fields on a TAXII endpoint.",
)
async def cli_integration_taxii_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bintegration taxii (\S+) set\b", line)
    if not m:
        print("  Error: TAXII name required")
        return
    name = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [as_dict(r) async for r in ctx.client.misc.taxii.list(name=name, max_results=1)]
    if not results:
        print(f"  No TAXII endpoint found: {name}")
        return
    await ctx.client.misc.taxii.update(results[0]["_ref"], body)


register("show integration taxii", words="<cr> <name>")
register("show integration taxii <name>", words="<cr>")


@command("show integration taxii", words="<cr> <name>", help="Show TAXII endpoints.")
@command("show integration taxii <name>", words="<cr>", help="Show a specific TAXII endpoint.")
async def cli_integration_taxii_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show integration taxii [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.misc.taxii.list(**params)]
    if not records:
        if name:
            print(f"  No TAXII endpoint found: {name}")
        return
    _print_records(records, "taxii")


# ---------------------------------------------------------------------------
# B2: Syslog endpoint (full CRUD)
# ---------------------------------------------------------------------------

register("configure integration syslog", words="add <name>")
register("configure integration syslog add", words="<name>")
register("configure integration syslog add <name>", words="<cr> comment=<comment>")


@command(
    "configure integration syslog add <name>",
    words="<cr> comment=<comment>",
    help="Add a syslog endpoint.",
)
async def cli_integration_syslog_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bintegration syslog add (\S+)", line)
    if not m:
        print("  Error: syslog endpoint name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.misc.syslog_endpoint.create(body)


register("configure integration syslog <name>", words="delete")
register("configure integration syslog <name> delete", words="<cr>")


@command(
    "configure integration syslog <name> delete",
    words="<cr>",
    help="Delete a syslog endpoint.",
)
async def cli_integration_syslog_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bintegration syslog (\S+) delete", line)
    if not m:
        print("  Error: syslog endpoint name required")
        return
    name = m.group(1)
    results = [
        as_dict(r) async for r in ctx.client.misc.syslog_endpoint.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No syslog endpoint found: {name}")
        return
    await ctx.client.misc.syslog_endpoint.delete(results[0]["_ref"])


register("show integration syslog", words="<cr> <name>")
register("show integration syslog <name>", words="<cr>")


@command("show integration syslog", words="<cr> <name>", help="Show syslog endpoints.")
@command("show integration syslog <name>", words="<cr>", help="Show a specific syslog endpoint.")
async def cli_integration_syslog_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show integration syslog [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.misc.syslog_endpoint.list(**params)]
    if not records:
        if name:
            print(f"  No syslog endpoint found: {name}")
        return
    _print_records(records, "syslog:endpoint")


# ---------------------------------------------------------------------------
# B3: PxGrid endpoint (full CRUD)
# ---------------------------------------------------------------------------

register("configure integration pxgrid", words="add <name>")
register("configure integration pxgrid add", words="<name>")
register("configure integration pxgrid add <name>", words="<cr> comment=<comment>")


@command(
    "configure integration pxgrid add <name>",
    words="<cr> comment=<comment>",
    help="Add a pxGrid endpoint.",
)
async def cli_integration_pxgrid_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bintegration pxgrid add (\S+)", line)
    if not m:
        print("  Error: pxGrid endpoint name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.misc.pxgrid_endpoint.create(body)


register("configure integration pxgrid <name>", words="delete")
register("configure integration pxgrid <name> delete", words="<cr>")


@command(
    "configure integration pxgrid <name> delete",
    words="<cr>",
    help="Delete a pxGrid endpoint.",
)
async def cli_integration_pxgrid_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bintegration pxgrid (\S+) delete", line)
    if not m:
        print("  Error: pxGrid endpoint name required")
        return
    name = m.group(1)
    results = [
        as_dict(r) async for r in ctx.client.misc.pxgrid_endpoint.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No pxGrid endpoint found: {name}")
        return
    await ctx.client.misc.pxgrid_endpoint.delete(results[0]["_ref"])


register("show integration pxgrid", words="<cr> <name>")
register("show integration pxgrid <name>", words="<cr>")


@command("show integration pxgrid", words="<cr> <name>", help="Show pxGrid endpoints.")
@command("show integration pxgrid <name>", words="<cr>", help="Show a specific pxGrid endpoint.")
async def cli_integration_pxgrid_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show integration pxgrid [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.misc.pxgrid_endpoint.list(**params)]
    if not records:
        if name:
            print(f"  No pxGrid endpoint found: {name}")
        return
    _print_records(records, "pxgrid:endpoint")


# ---------------------------------------------------------------------------
# B4: DXL endpoint (full CRUD)
# ---------------------------------------------------------------------------

register("configure integration dxl", words="add <name>")
register("configure integration dxl add", words="<name>")
register("configure integration dxl add <name>", words="<cr> comment=<comment>")


@command(
    "configure integration dxl add <name>",
    words="<cr> comment=<comment>",
    help="Add a DXL endpoint.",
)
async def cli_integration_dxl_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bintegration dxl add (\S+)", line)
    if not m:
        print("  Error: DXL endpoint name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.misc.dxl_endpoint.create(body)


register("configure integration dxl <name>", words="delete")
register("configure integration dxl <name> delete", words="<cr>")


@command(
    "configure integration dxl <name> delete",
    words="<cr>",
    help="Delete a DXL endpoint.",
)
async def cli_integration_dxl_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bintegration dxl (\S+) delete", line)
    if not m:
        print("  Error: DXL endpoint name required")
        return
    name = m.group(1)
    results = [
        as_dict(r) async for r in ctx.client.misc.dxl_endpoint.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No DXL endpoint found: {name}")
        return
    await ctx.client.misc.dxl_endpoint.delete(results[0]["_ref"])


register("show integration dxl", words="<cr> <name>")
register("show integration dxl <name>", words="<cr>")


@command("show integration dxl", words="<cr> <name>", help="Show DXL endpoints.")
@command("show integration dxl <name>", words="<cr>", help="Show a specific DXL endpoint.")
async def cli_integration_dxl_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show integration dxl [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.misc.dxl_endpoint.list(**params)]
    if not records:
        if name:
            print(f"  No DXL endpoint found: {name}")
        return
    _print_records(records, "dxl:endpoint")


# ---------------------------------------------------------------------------
# B5: Outbound cloud client (GET+PUT only - show + set)
# ---------------------------------------------------------------------------

register("configure integration outbound", words="<name>")
register("configure integration outbound <name>", words="set")
register("configure integration outbound <name> set", words="<key>=<value>", dynamic=_OUTBOUND_KEYS)


@command(
    "configure integration outbound <name> set",
    words="<key>=<value>",
    help="Set fields on an outbound cloud client.",
)
async def cli_integration_outbound_set(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bintegration outbound (\S+) set\b", line)
    if not m:
        print("  Error: outbound member name required")
        return
    name = m.group(1)
    body = _parse_inline_kvs(line, " set ")
    if not body:
        print("  Error: specify at least one key=value pair")
        return
    results = [
        as_dict(r)
        async for r in ctx.client.misc.outbound_cloudclient.list(grid_member=name, max_results=1)
    ]
    if not results:
        print(f"  No outbound cloud client found: {name}")
        return
    await ctx.client.misc.outbound_cloudclient.update(results[0]["_ref"], body)


register("show integration outbound", words="<cr> <name>")
register("show integration outbound <name>", words="<cr>")


@command("show integration outbound", words="<cr> <name>", help="Show outbound cloud clients.")
@command(
    "show integration outbound <name>",
    words="<cr>",
    help="Show a specific outbound cloud client.",
)
async def cli_integration_outbound_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show integration outbound [<name>]
    name = None
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["grid_member"] = name
    records = [as_dict(r) async for r in ctx.client.misc.outbound_cloudclient.list(**params)]
    if not records:
        if name:
            print(f"  No outbound cloud client found: {name}")
        return
    _print_records(records, "outbound:cloudclient")


# ---------------------------------------------------------------------------
# B6: Aggregate endpoint view (allendpoints - GET only)
# ---------------------------------------------------------------------------

register("show integration all", words="<cr>")


@command("show integration all", words="<cr>", help="Show all integration endpoints.")
async def cli_integration_all_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    records = [as_dict(r) async for r in ctx.client.misc.allendpoints.list()]
    if not records:
        return
    _print_records(records, "allendpoints")


# ===========================================================================
# Chunk C: BFD template + Kerberos key + TFTP dir + Ruleset
# ===========================================================================

# ---------------------------------------------------------------------------
# C1: BFD template (full CRUD)
# ---------------------------------------------------------------------------

register("configure", words="bfd_template", help="Create, modify or delete grid objects.")
register("show", words="bfd_template", help="Read grid state without modifying anything.")
register(
    "configure bfd_template",
    words="add <name>",
    help="BFD (Bidirectional Forwarding Detection) templates.",
)
register("configure bfd_template add", words="<name>")
register("configure bfd_template add <name>", words="<cr> comment=<comment>")


@command(
    "configure bfd_template add <name>",
    words="<cr> comment=<comment>",
    help="Add a BFD template.",
)
async def cli_bfd_template_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bbfd_template add (\S+)", line)
    if not m:
        print("  Error: BFD template name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.misc.bfdtemplate.create(body)


register("configure bfd_template <name>", words="delete")
register("configure bfd_template <name> delete", words="<cr>")


@command(
    "configure bfd_template <name> delete",
    words="<cr>",
    help="Delete a BFD template.",
)
async def cli_bfd_template_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bbfd_template (\S+) delete", line)
    if not m:
        print("  Error: BFD template name required")
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.misc.bfdtemplate.list(name=name, max_results=1)]
    if not results:
        print(f"  No BFD template found: {name}")
        return
    await ctx.client.misc.bfdtemplate.delete(results[0]["_ref"])


register("show bfd_template", words="<cr> <name>", help="List BFD templates.")
register("show bfd_template <name>", words="<cr>")


@command("show bfd_template", words="<cr> <name>", help="Show BFD templates.")
@command("show bfd_template <name>", words="<cr>", help="Show a specific BFD template.")
async def cli_bfd_template_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show bfd_template [<name>]
    name = None
    if len(tokens) >= 3:
        candidate = tokens[2]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.misc.bfdtemplate.list(**params)]
    if not records:
        if name:
            print(f"  No BFD template found: {name}")
        return
    _print_records(records, "bfdtemplate")


# ---------------------------------------------------------------------------
# C2: Kerberos key (GET+DELETE only - no POST/PUT per WAPI)
# ---------------------------------------------------------------------------

register("configure", words="kerberos_key", help="Create, modify or delete grid objects.")
register("show", words="kerberos_key", help="Read grid state without modifying anything.")
register(
    "configure kerberos_key",
    words="<name>",
    help="Grid Kerberos keytab entries (delete only - read-only otherwise).",
)
register("configure kerberos_key <name>", words="delete")
register("configure kerberos_key <name> delete", words="<cr>")


@command(
    "configure kerberos_key <name> delete",
    words="<cr>",
    help="Delete a Kerberos key by ref.",
)
async def cli_kerberos_key_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bkerberos_key (\S+) delete", line)
    if not m:
        print("  Error: Kerberos key ref or principal required")
        return
    token = m.group(1)

    # Accept either a WAPI _ref or the principal shown by `show kerberos_key`.
    # A bare principal handed to the SDK raises ValueError, so resolve first.
    if token.startswith("kerberoskey/"):
        ref = token
    else:
        results = [as_dict(r) async for r in ctx.client.misc.kerberoskey.list(principal=token)]
        if not results:
            print(f"  No Kerberos key found: {token}")
            return
        ref = results[0]["_ref"]
    await ctx.client.misc.kerberoskey.delete(ref)


register("show kerberos_key", words="<cr> <name>", help="Grid Kerberos keytab entries.")
register("show kerberos_key <name>", words="<cr>")


@command("show kerberos_key", words="<cr> <name>", help="Show Kerberos keys.")
@command("show kerberos_key <name>", words="<cr>", help="Show Kerberos keys for a principal.")
async def cli_kerberos_key_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show kerberos_key [<name>]
    name = None
    if len(tokens) >= 3:
        candidate = tokens[2]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["principal"] = name
    records = [as_dict(r) async for r in ctx.client.misc.kerberoskey.list(**params)]
    if not records:
        if name:
            print(f"  No Kerberos key found: {name}")
        return
    _print_records(records, "kerberoskey")


# ---------------------------------------------------------------------------
# C3: TFTP file dir (full CRUD)
# ---------------------------------------------------------------------------

register("configure", words="tftp_dir", help="Create, modify or delete grid objects.")
register("show", words="tftp_dir", help="Read grid state without modifying anything.")
register("configure tftp_dir", words="add <name>", help="TFTP-served directories on grid members.")
register("configure tftp_dir add", words="<name>")
register("configure tftp_dir add <name>", words="<cr> comment=<comment>")


@command(
    "configure tftp_dir add <name>",
    words="<cr> comment=<comment>",
    help="Add a TFTP file directory.",
)
async def cli_tftp_dir_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\btftp_dir add (\S+)", line)
    if not m:
        print("  Error: TFTP directory name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.misc.tftpfiledir.create(body)


register("configure tftp_dir <name>", words="delete")
register("configure tftp_dir <name> delete", words="<cr>")


@command(
    "configure tftp_dir <name> delete",
    words="<cr>",
    help="Delete a TFTP file directory.",
)
async def cli_tftp_dir_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\btftp_dir (\S+) delete", line)
    if not m:
        print("  Error: TFTP directory name required")
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.misc.tftpfiledir.list(name=name, max_results=1)]
    if not results:
        print(f"  No TFTP file directory found: {name}")
        return
    await ctx.client.misc.tftpfiledir.delete(results[0]["_ref"])


register("show tftp_dir", words="<cr> <name>", help="TFTP-served directories.")
register("show tftp_dir <name>", words="<cr>")


@command("show tftp_dir", words="<cr> <name>", help="Show TFTP file directories.")
@command("show tftp_dir <name>", words="<cr>", help="Show a specific TFTP file directory.")
async def cli_tftp_dir_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show tftp_dir [<directory>]
    name = None
    if len(tokens) >= 3:
        candidate = tokens[2]
        if not candidate.startswith("<"):
            name = candidate
    if not name:
        print("  Error: directory required (usage: show tftp_dir <directory>)")
        return
    params: dict = {"directory": name}
    records = [as_dict(r) async for r in ctx.client.misc.tftpfiledir.list(**params)]
    if not records:
        if name:
            print(f"  No TFTP file directory found: {name}")
        return
    _print_records(records, "tftpfiledir")


# ---------------------------------------------------------------------------
# C4: Ruleset (full CRUD)
# ---------------------------------------------------------------------------

register("configure", words="ruleset", help="Create, modify or delete grid objects.")
register("show", words="ruleset", help="Read grid state without modifying anything.")
register(
    "configure ruleset",
    words="add <name>",
    help="Named rulesets (used by scavenging, notification filters).",
)
register("configure ruleset add", words="<name>")
register("configure ruleset add <name>", words="<cr> type=<value>|comment=<comment>")


@command(
    "configure ruleset add <name>",
    words="<cr> type=<value>|comment=<comment>",
    help="Add a ruleset.",
)
async def cli_ruleset_add(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bruleset add (\S+)", line)
    if not m:
        print("  Error: ruleset name required")
        return
    name = m.group(1)
    body: dict = {"name": name}
    rtype = _kv(line, "type")
    if rtype:
        body["type"] = rtype
    cmt = _comment(line)
    if cmt:
        body["comment"] = cmt
    await ctx.client.misc.ruleset.create(body)


register("configure ruleset <name>", words="delete")
register("configure ruleset <name> delete", words="<cr>")


@command(
    "configure ruleset <name> delete",
    words="<cr>",
    help="Delete a ruleset.",
)
async def cli_ruleset_delete(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bruleset (\S+) delete", line)
    if not m:
        print("  Error: ruleset name required")
        return
    name = m.group(1)
    results = [as_dict(r) async for r in ctx.client.misc.ruleset.list(name=name, max_results=1)]
    if not results:
        print(f"  No ruleset found: {name}")
        return
    await ctx.client.misc.ruleset.delete(results[0]["_ref"])


register("show ruleset", words="<cr> <name>", help="Rulesets (scavenging, notification filters).")
register("show ruleset <name>", words="<cr>")


@command("show ruleset", words="<cr> <name>", help="Show rulesets.")
@command("show ruleset <name>", words="<cr>", help="Show a specific ruleset.")
async def cli_ruleset_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show ruleset [<name>]
    name = None
    if len(tokens) >= 3:
        candidate = tokens[2]
        if not candidate.startswith("<"):
            name = candidate
    params: dict = {}
    if name:
        params["name"] = name
    records = [as_dict(r) async for r in ctx.client.misc.ruleset.list(**params)]
    if not records:
        if name:
            print(f"  No ruleset found: {name}")
        return
    _print_records(records, "ruleset")


# ===========================================================================
# Chunk D: Read-only aggregates (deleted_objects, db_objects)
# ===========================================================================

# ---------------------------------------------------------------------------
# D1: Deleted objects (read-only)
# ---------------------------------------------------------------------------

register("show", words="deleted_objects", help="Read grid state without modifying anything.")
register(
    "show deleted_objects",
    words="<cr> <name>",
    help="Tombstones for objects deleted recently (if enabled).",
)
register("show deleted_objects <name>", words="<cr>")


@command("show deleted_objects", words="<cr> <name>", help="Show deleted objects.")
@command("show deleted_objects <name>", words="<cr>", help="Show deleted objects of a type.")
async def cli_deleted_objects_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    tokens = line.split()
    # tokens: show deleted_objects [<type>]
    obj_type = None
    if len(tokens) >= 3:
        candidate = tokens[2]
        if not candidate.startswith("<"):
            obj_type = candidate
    params: dict = {}
    if obj_type:
        params["object_type"] = obj_type
    records = [as_dict(r) async for r in ctx.client.misc.deleted_objects.list(**params)]
    if not records:
        if obj_type:
            print(f"  No deleted objects found: {obj_type}")
        return
    _print_records(records, "deleted_objects")


# ---------------------------------------------------------------------------
# D2: DB objects (read-only)
# ---------------------------------------------------------------------------

register("show", words="db_objects", help="Read grid state without modifying anything.")
register(
    "show db_objects",
    words="<cr> object_types=<name> version=<name>",
    help="Tracked database objects (requires objects tracking to be on).",
)


# NIOS only advertises object-type tracking at these discrete WAPI versions;
# the default picks the newest. The WAPI endpoint rejects any other value
# (including the grid's current WAPI version, e.g. "2.14").
_DB_OBJECTS_VERSIONS = ("2.5", "2.7", "2.13.7")


@command(
    "show db_objects",
    words="<cr> object_types=<name> version=<name>",
    help=f"Show database objects. Optional object_types=<type[,type…]> filter, "
    f"or version=<v> for all types in a given WAPI version "
    f"(one of {', '.join(_DB_OBJECTS_VERSIONS)}; default "
    f"{_DB_OBJECTS_VERSIONS[-1]}).",
)
async def cli_db_objects_show(line: str, ctx: Context) -> None:
    if ctx.client is None:
        _not_connected()
        return
    m = re.search(r"\bobject_types?[= ](\S+)", line)
    if m:
        params: dict = {"object_types": m.group(1)}
    else:
        mv = re.search(r"\bversion[= ](\S+)", line)
        version = mv.group(1) if mv else _DB_OBJECTS_VERSIONS[-1]
        params = {"all_object_types_supported_in_version": version}
    records = [as_dict(r) async for r in ctx.client.misc.db_objects.list(**params)]
    if not records:
        return
    _print_records(records, "db_objects")
