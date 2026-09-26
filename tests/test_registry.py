# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from ibcli.registry import COMMANDS, command, register

# The match-line strings below are unique sentinels (prefixed `__test_reg_`)
# so these tests don't collide with real command-tree entries registered by
# production command modules like commands/server.py, commands/zone.py.


def test_command_decorator_registers_entry():
    @command("__test_reg_add", words="<cr> comment=<comment>", help="Add a zone.")
    def handler(line, ctx):
        return "ok"

    entry = COMMANDS["__test_reg_add"]
    assert entry.func is handler
    assert entry.words == "<cr> comment=<comment>"
    assert entry.help == "Add a zone."


def test_register_adds_waypoint_without_func():
    register("__test_reg_waypoint", words="<name> schedule attribute device_type")
    entry = COMMANDS["__test_reg_waypoint"]
    assert entry.func is None
    assert entry.words == "<name> schedule attribute device_type"


def test_command_decorator_merges_over_register():
    register("__test_reg_merge", words="<cr> <zone>|view=<name>")

    @command("__test_reg_merge", help="Show a zone.")
    def handler(line, ctx):
        pass

    entry = COMMANDS["__test_reg_merge"]
    assert entry.words == "<cr> <zone>|view=<name>"  # preserved from register
    assert entry.func is handler
    assert entry.help == "Show a zone."


def test_register_merges_word_lists_from_multiple_callers():
    register("__test_reg_union", words="server master")
    register("__test_reg_union", words="zone server")  # 'server' dedup, 'zone' added
    tokens = COMMANDS["__test_reg_union"].words.split()
    assert set(tokens) == {"server", "master", "zone"}
