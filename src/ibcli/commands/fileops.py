# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Upload / download commands implementing the WAPI fileop multi-step protocol.

Command shapes registered:

  upload csv <file> [object <name>]
  upload leases <file>
  upload database <file>
  upload expert_dhcp_conf <file> [member <name>]

  download csv <file> object <object>
  download database <file>
  download log_files <file> <value> [member <name>]
  download lease_history <file>
  download support_bundle <file> [member <name>]
  download merge_log <file>

  # Per-member getmemberdata dumps (member=<host_name> required):
  download dhcp_conf         <file> member <name>   # DHCP_CFG
  download dhcpv6_conf       <file> member <name>   # DHCPV6_CFG
  download expert_dhcp_conf  <file> member <name>   # DHCP_EXPERT_MODE_CFG
  download dns_conf          <file> member <name>   # DNS_CFG
  download dns_cache         <file> member <name>   # DNS_CACHE
  download dns_accel_cache   <file> member <name>   # DNS_ACCEL_CACHE
  download dns_recursing_cache <file> member <name> # DNS_RECURSING_CACHE
  download dns_stats         <file> member <name>   # DNS_STATS
  download ntp_keys          <file> member <name>   # NTP_KEY_FILE
  download radius_conf       <file> member <name>   # RADIUS_CFG
  download traffic_capture   <file> member <name>   # TRAFFIC_CAPTURE_FILE

  download csv_errors <file> <name>

  show csv task <name>
"""

from __future__ import annotations

import re

from ibcli.completions import members as _members_completer
from ibcli.context import Context
from ibcli.fileop import multipart_upload, stream_download
from ibcli.registry import command, register

# ---------------------------------------------------------------------------
# Waypoints - upload
# ---------------------------------------------------------------------------

register(
    "upload",
    words="csv leases database expert_dhcp_conf",
    help="Upload a file (CSV, database backup, leases, certificate) to NIOS.",
)

register("upload csv", words="<file>")
_CSV_UPLOAD_WORDS = (
    "<cr> object=<name>|"
    "operation=<name>|"  # INSERT | OVERRIDE | MERGE | DELETE | CUSTOM
    "update_method=<name>|"  # MERGE | OVERRIDE  (applies to OVERRIDE/MERGE)
    "on_error=<name>|"  # STOP | CONTINUE
    "mode=<name>"  # START | TEST  (TEST = dry-run, default START)
)
register("upload csv <file>", words=_CSV_UPLOAD_WORDS)
register("upload csv <file> object", words="<name>")
register("upload csv <file> object <name>", words=_CSV_UPLOAD_WORDS)

register("upload leases", words="<file>")
register("upload leases <file>", words="<cr>")

register("upload database", words="<file>")
register("upload database <file>", words="<cr>")

register("upload expert_dhcp_conf", words="<file>")
register("upload expert_dhcp_conf <file>", words="<cr> member=<name>")
register("upload expert_dhcp_conf <file> member", words="<name>", dynamic=_members_completer)
register("upload expert_dhcp_conf <file> member <name>", words="<cr>")

# ---------------------------------------------------------------------------
# Waypoints - download
# ---------------------------------------------------------------------------

register(
    "download",
    words=(
        "csv csv_snapshot database log_files lease_history support_bundle "
        "merge_log expert_dhcp_conf dhcp_conf dhcpv6_conf dns_conf "
        "dns_cache dns_accel_cache dns_recursing_cache dns_stats "
        "ntp_keys radius_conf traffic_capture"
    ),
    help="Download a file (CSV export, support bundle, logs, backup) from NIOS.",
)

register("download csv", words="<file>")
register("download csv <file>", words="object=<object>")
register("download csv <file> object", words="<object>")
register("download csv <file> object <object>", words="<cr>")

register("download csv_snapshot", words="<file>")
register("download csv_snapshot <file>", words="<cr> token=<value>")
register("download csv_snapshot <file> token", words="<value>")
register("download csv_snapshot <file> token <value>", words="<cr>")

register("download database", words="<file>")
register("download database <file>", words="<cr>")

register("download log_files", words="<file>")
register("download log_files <file>", words="<value>")
register("download log_files <file> <value>", words="<cr> member=<name>")
register("download log_files <file> <value> member", words="<name>", dynamic=_members_completer)
register("download log_files <file> <value> member <name>", words="<cr>")

register("download lease_history", words="<file>")
register("download lease_history <file>", words="<cr>")

register("download support_bundle", words="<file>")
register("download support_bundle <file>", words="<cr> member=<name>")
register("download support_bundle <file> member", words="<name>", dynamic=_members_completer)
register("download support_bundle <file> member <name>", words="<cr>")

register("download merge_log", words="<file>")
register("download merge_log <file>", words="<cr>")

# Per-member config / cache / stats dumps (all ride on getmemberdata).
#   alias          -> WAPI `type` enum value
_MEMBERDATA_ALIASES: dict[str, str] = {
    "expert_dhcp_conf": "DHCP_EXPERT_MODE_CFG",
    "dhcp_conf": "DHCP_CFG",
    "dhcpv6_conf": "DHCPV6_CFG",
    "dns_conf": "DNS_CFG",
    "dns_cache": "DNS_CACHE",
    "dns_accel_cache": "DNS_ACCEL_CACHE",
    "dns_recursing_cache": "DNS_RECURSING_CACHE",
    "dns_stats": "DNS_STATS",
    "ntp_keys": "NTP_KEY_FILE",
    "radius_conf": "RADIUS_CFG",
    "traffic_capture": "TRAFFIC_CAPTURE_FILE",
}

for _alias in _MEMBERDATA_ALIASES:
    register(f"download {_alias}", words="<file>")
    # getmemberdata always needs a member name, so require it in the grammar
    # rather than printing an error at runtime.
    register(f"download {_alias} <file>", words="member=<name>")
    register(f"download {_alias} <file> member", words="<name>", dynamic=_members_completer)
    register(f"download {_alias} <file> member <name>", words="<cr>")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _arg(line: str, keyword: str) -> str | None:
    """Return the token following *keyword* in *line*, or None."""
    m = re.search(rf"\b{re.escape(keyword)}\s+(\S+)", line)
    return m.group(1) if m else None


async def _fileop_download(ctx: Context, function: str, dest_path: str, **params) -> None:
    """3-step fileop download: init → stream GET → downloadcomplete."""
    result = await ctx.client.misc.fileop.call(function, **params)
    url = result.get("url")
    token = result.get("token")
    if not url or not token:
        print(f"  Error: {function} response missing url or token")
        return
    await stream_download(ctx.client, url, dest_path)
    await ctx.client.misc.fileop.download_complete(token=token)


async def _fileop_upload(ctx: Context, function: str, source_path: str, **params) -> dict:
    """3-step fileop upload: uploadinit → multipart POST bytes → invoke function.

    The multipart POST and its Basic-auth requirement live in
    :mod:`ibcli.fileop` - see that module for why the ``http_direct_file_io``
    endpoint needs credentials the WAPI endpoints do not.
    """
    init = await ctx.client.misc.fileop.upload_init()
    url = init.get("url")
    token = init.get("token")
    if not url or not token:
        print("  Error: uploadinit response missing url or token")
        return {}
    await multipart_upload(ctx.client, url, source_path)
    return await ctx.client.misc.fileop.call(function, token=token, **params)


# ===========================================================================
# Handlers - upload
# ===========================================================================


@command("upload csv <file>", words="<cr> object=<name>", help="Upload CSV file.")
@command(
    "upload csv <file> object <name>",
    words="<cr>",
    help="Upload CSV file for a specific object type.",
)
async def cli_upload_csv(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bcsv\s+(\S+)", line)
    if not m:
        print("  Error: filename required")
        return
    source_path = m.group(1)
    object_name = _arg(line, "object")

    # Explicit keywords override the implicit "object= → CUSTOM" heuristic.
    operation = (_arg(line, "operation") or "").upper() or None
    update_method = (_arg(line, "update_method") or "").upper() or None
    on_error = (_arg(line, "on_error") or "STOP").upper()
    mode = (_arg(line, "mode") or "START").upper()

    _VALID_OPS = {"INSERT", "OVERRIDE", "MERGE", "DELETE", "CUSTOM"}
    _VALID_UPDATE = {"MERGE", "OVERRIDE"}
    _VALID_MODES = {"START", "TEST"}
    if operation and operation not in _VALID_OPS:
        print(f"  Error: operation must be one of {sorted(_VALID_OPS)}")
        return
    if update_method and update_method not in _VALID_UPDATE:
        print("  Error: update_method must be MERGE or OVERRIDE")
        return
    if mode not in _VALID_MODES:
        print(f"  Error: mode must be one of {sorted(_VALID_MODES)}")
        return

    if operation is None:
        # Backward-compatible default: CUSTOM when object= is given, else INSERT.
        operation = "CUSTOM" if object_name else "INSERT"

    # WAPI's csv_import fileop splits the run into two concepts:
    #   - action    = START | TEST          (commit vs. dry-run)
    #   - operation = INSERT | OVERRIDE |
    #                 MERGE | DELETE |
    #                 CUSTOM                (how rows are applied)
    # Earlier releases of this CLI sent the operation as `action`, which NIOS
    # rejects with "Invalid value for action". We now pass both fields.
    params: dict = {"action": mode, "operation": operation, "on_error": on_error}
    if object_name:
        params["_object"] = object_name
    if update_method:
        params["update_method"] = update_method

    await _fileop_upload(ctx, "csv_import", source_path, **params)
    print(f"  Uploaded {source_path}")


@command("upload leases <file>", words="<cr>", help="Upload DHCP leases file.")
async def cli_upload_leases(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bleases\s+(\S+)", line)
    if not m:
        print("  Error: filename required")
        return
    source_path = m.group(1)
    await _fileop_upload(ctx, "setleasehistoryfiles", source_path)
    print(f"  Uploaded {source_path}")


@command("upload database <file>", words="<cr>", help="Upload database backup.")
async def cli_upload_database(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bdatabase\s+(\S+)", line)
    if not m:
        print("  Error: filename required")
        return
    source_path = m.group(1)
    await _fileop_upload(ctx, "restoredatabase", source_path, keep_grid_ip="YES")
    print(f"  Uploaded {source_path}")


@command(
    "upload expert_dhcp_conf <file>",
    words="<cr> member=<name>",
    help="Upload expert DHCP config.",
)
@command(
    "upload expert_dhcp_conf <file> member <name>",
    words="<cr>",
    help="Upload expert DHCP config to a specific member.",
)
async def cli_upload_expert_dhcp_conf(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bexpert_dhcp_conf\s+(\S+)", line)
    if not m:
        print("  Error: filename required")
        return
    source_path = m.group(1)
    member = _arg(line, "member")

    params: dict = {"type": "DHCP_EXPERT_MODE_CFG"}
    if member:
        params["member"] = member

    await _fileop_upload(ctx, "setmemberdata", source_path, **params)
    print(f"  Uploaded {source_path}")


# ===========================================================================
# Handlers - download
# ===========================================================================


@command(
    "download csv <file> object <object>",
    words="<cr>",
    help="Download CSV for an object type.",
)
async def cli_download_csv(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bcsv\s+(\S+)", line)
    if not m:
        print("  Error: filename required")
        return
    dest_path = m.group(1)
    object_name = _arg(line, "object")
    params: dict = {}
    if object_name:
        params["_object"] = object_name
    await _fileop_download(ctx, "csv_export", dest_path, **params)
    print(f"  Downloaded {dest_path}")


@command(
    "download csv_snapshot <file>",
    words="<cr> token=<value>",
    help="Download a previously generated CSV snapshot file.",
)
@command(
    "download csv_snapshot <file> token <value>",
    words="<cr>",
    help="Download a CSV snapshot by token.",
)
async def cli_download_csv_snapshot(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bcsv_snapshot\s+(\S+)", line)
    if not m:
        print("  Error: filename required")
        return
    dest_path = m.group(1)
    token = _arg(line, "token")
    params: dict = {}
    if token:
        params["token"] = token
    await _fileop_download(ctx, "csv_snapshot_file", dest_path, **params)
    print(f"  Downloaded {dest_path}")


@command("download database <file>", words="<cr>", help="Download database backup.")
async def cli_download_database(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bdatabase\s+(\S+)", line)
    if not m:
        print("  Error: filename required")
        return
    dest_path = m.group(1)
    await _fileop_download(ctx, "getgriddata", dest_path, type="BACKUP")
    print(f"  Downloaded {dest_path}")


@command(
    "download log_files <file> <value>",
    words="<cr> member=<name>",
    help="Download log files.",
)
@command(
    "download log_files <file> <value> member <name>",
    words="<cr>",
    help="Download log files from a specific member.",
)
async def cli_download_log_files(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\blog_files\s+(\S+)\s+(\S+)", line)
    if not m:
        print("  Error: filename and log_type required")
        return
    dest_path = m.group(1)
    log_type = m.group(2)
    member = _arg(line, "member")

    params: dict = {"log_type": log_type}
    if member:
        params["member"] = member

    await _fileop_download(ctx, "get_log_files", dest_path, **params)
    print(f"  Downloaded {dest_path}")


@command("download lease_history <file>", words="<cr>", help="Download DHCP lease history.")
async def cli_download_lease_history(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\blease_history\s+(\S+)", line)
    if not m:
        print("  Error: filename required")
        return
    dest_path = m.group(1)
    await _fileop_download(ctx, "getleasehistoryfiles", dest_path)
    print(f"  Downloaded {dest_path}")


@command(
    "download support_bundle <file>",
    words="<cr> member=<name>",
    help="Download support bundle.",
)
@command(
    "download support_bundle <file> member <name>",
    words="<cr>",
    help="Download support bundle from a specific member.",
)
async def cli_download_support_bundle(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bsupport_bundle\s+(\S+)", line)
    if not m:
        print("  Error: filename required")
        return
    dest_path = m.group(1)
    member = _arg(line, "member")

    params: dict = {}
    if member:
        params["member"] = member

    await _fileop_download(ctx, "get_support_bundle", dest_path, **params)
    print(f"  Downloaded {dest_path}")


@command("download merge_log <file>", words="<cr>", help="Download merge log.")
async def cli_download_merge_log(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\bmerge_log\s+(\S+)", line)
    if not m:
        print("  Error: filename required")
        return
    dest_path = m.group(1)
    await _fileop_download(ctx, "get_log_files", dest_path, log_type="MERGE")
    print(f"  Downloaded {dest_path}")


def _bind_memberdata_handler(alias: str, wapi_type: str) -> None:
    """Register `download <alias> <file> [member <name>]` against getmemberdata."""

    async def _handler(line: str, ctx: Context) -> None:
        if ctx.client is None:
            print("  Not connected")
            return
        m = re.search(rf"\b{re.escape(alias)}\s+(\S+)", line)
        if not m:
            print("  Error: filename required")
            return
        dest_path = m.group(1)
        member = _arg(line, "member")
        if not member:
            print(f"  Error: member=<host_name> is required for {alias}")
            return
        await _fileop_download(
            ctx,
            "getmemberdata",
            dest_path,
            type=wapi_type,
            member=member,
        )
        print(f"  Downloaded {dest_path}")

    command(
        f"download {alias} <file> member <name>",
        words="<cr>",
        help=f"Download {alias.replace('_', ' ')} ({wapi_type}).",
    )(_handler)


for _alias, _wapi_type in _MEMBERDATA_ALIASES.items():
    _bind_memberdata_handler(_alias, _wapi_type)


# ===========================================================================
# CSV task status + error log (Gap 3)
# ===========================================================================

# Waypoints
register(
    "download",
    words="csv_errors",
    help="Download a file (CSV export, support bundle, logs, backup) from NIOS.",
)
register("download csv_errors", words="<file>")
register("download csv_errors <file>", words="<name>")
register("download csv_errors <file> <name>", words="<cr>")

register("show", words="csv", help="Read grid state without modifying anything.")
register("show csv", words="task", help="List running CSV import tasks.")
register("show csv task", words="<name>")
register("show csv task <name>", words="<cr>")


@command(
    "download csv_errors <file> <name>",
    words="<cr>",
    help="Download CSV import error log for a given import task ID.",
)
async def cli_download_csv_errors(line: str, ctx: Context) -> None:
    """POST fileop?_function=csv_error_log with import_id, then download."""
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bcsv_errors\s+(\S+)\s+(\S+)", line)
    if not m:
        print("  Error: file and task_id required")
        return
    dest_path, task_id = m.group(1), m.group(2)

    await _fileop_download(ctx, "csv_error_log", dest_path, import_id=task_id)
    print(f"  Downloaded {dest_path}")


@command(
    "show csv task <name>",
    words="<cr>",
    help="Show status of a CSV import task by its object reference.",
)
async def cli_show_csv_task(line: str, ctx: Context) -> None:
    """GET the csv_import_task ref and print key status fields."""
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bcsv task\s+(\S+)", line)
    if not m:
        print("  Error: task reference required")
        return
    task_ref = m.group(1)

    result = await ctx.client._http.get(
        task_ref,
        params={
            "_return_fields": ",".join(
                [
                    "status",
                    "lines_processed",
                    "lines_failed",
                    "start_time",
                    "end_time",
                ]
            )
        },
    )

    if not result:
        print(f"  No CSV task found: {task_ref}")
        return

    # result may be a list or a dict depending on the ref style
    task = result[0] if isinstance(result, list) else result
    parts = []
    if task.get("status"):
        parts.append(f"status={task['status']}")
    if task.get("lines_processed") is not None:
        parts.append(f"lines_processed={task['lines_processed']}")
    if task.get("lines_failed") is not None:
        parts.append(f"lines_failed={task['lines_failed']}")
    if task.get("start_time"):
        parts.append(f"start_time={task['start_time']}")
    if task.get("end_time"):
        parts.append(f"end_time={task['end_time']}")
    print(" ".join(parts) if parts else f"  {task}")
