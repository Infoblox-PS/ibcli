# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

import pytest

from ibcli.registry import ALIASES, SPECOPS


@pytest.mark.parametrize(
    "spec,value,ok",
    [
        ("<ip>", "1.2.3.4", True),
        ("<ip>", "1.2.3", True),  # incomplete form is allowed
        ("<ip>", "notanip", False),
        ("<n.n.n.n/mm>", "1.2.3.0/24", True),
        ("<n.n.n.n/mm>", "1.2.3.0", False),
        ("<cidr>", "1.2.3.0/24", True),
        ("</cidr>", "/24", True),
        ("</cidr>", "24", False),
        ("<mac>", "aa:bb:cc:dd:ee:ff", True),
        ("<num>", "123", True),
        ("<num>", "12a", False),
        ("<name=value>", "foo=bar", True),
        ("<name=value>", "foo", False),
        ("<zone>", "foo.bar.com", True),
        ("<zone>", "foo bar", False),
        ("<port>", "53", True),
    ],
)
def test_specops_regex(spec, value, ok):
    pattern = SPECOPS[spec]
    assert bool(pattern.search(value)) is ok, f"{spec} on {value!r}"


def test_aliases_core_entries():
    assert ALIASES["pwd"] == "show debug pwd"
    assert ALIASES["info"] == "show debug session"
    # The legacy 'cd' / 'ls' / 'prop' aliases were removed because their
    # target subtree (show file / configure file) was never implemented.
    assert "cd" not in ALIASES
    assert "ls" not in ALIASES
    assert "prop" not in ALIASES
