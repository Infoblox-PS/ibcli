# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

import os
import sys
import time

from ibcli.context import Context
from ibcli.registry import command, register

# ---- top-level waypoints ----
# `test` was carried over from the Perl ibcli but nothing ever registered a
# subtree for it - the dropdown offered it and typing it answered
# "Unknown command: test".
register(
    "NULL",
    words="help quit|bye|exit history configure show upload download restart generate",
    help="ibcli root - type 'configure' or 'show' to start.",
)
register(
    "show",
    words="time debug server grid zone network record views",
    help="Read grid state without modifying anything.",
)
register(
    "show debug",
    words="session commands file pwd",
    help="Debugging helpers (session info, command trees, file paths).",
)
register("help", words="all")


@command("help", help="Show inline help.")
async def print_help(line: str, ctx: Context) -> None:
    print("""  press:
    <tab> for options and word completion
    '\\' to clear the line
    'q' to quit
""")


@command("help all", help="Show full documentation.")
async def print_all_help(line: str, ctx: Context) -> None:
    print("See https://infoblox-ps.github.io/ibcli/ for full documentation.")


async def _exit(line: str, ctx: Context) -> None:
    sys.exit(0)


command("quit", help="Quit the CLI.")(_exit)
command("bye", help="Quit the CLI.")(_exit)
command("exit", help="Quit the CLI.")(_exit)


@command("history", help="Show command history.")
async def cli_history(line: str, ctx: Context) -> None:
    print("history is managed by prompt_toolkit; press Ctrl-R to search, up-arrow to browse")


@command("show time", help="Print the current server-side time.")
async def show_time(line: str, ctx: Context) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S %Z"))


@command("show debug pwd", help="Print the current working directory.")
async def debug_pwd(line: str, ctx: Context) -> None:
    print(os.getcwd())


@command("show debug session", help="Dump the WAPI session object.")
async def debug_session(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    print(f"host={ctx.host} version={ctx.client_rev} online={ctx.online}")


@command("show debug commands", help="Dump the COMMANDS registry.", words="<cr> detailed")
@command("show debug commands detailed", help="Dump the COMMANDS registry in detail.")
async def debug_commands(line: str, ctx: Context) -> None:
    from ibcli.registry import COMMANDS

    detailed = line.endswith("detailed")
    for key in sorted(COMMANDS):
        entry = COMMANDS[key]
        if detailed:
            print(f"{key!r} -> words={entry.words!r} func={entry.func}")
        else:
            print(key)


@command("show debug file", help="Show WAPI session diagnostic info.")
async def debug_file(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    print(f"  host={ctx.host}")
    print(f"  version={ctx.client_rev}")
    http = ctx.client._http
    print(f"  base_url={http.grid_url}/wapi/v{ctx.client_rev}")
