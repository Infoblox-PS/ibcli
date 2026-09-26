# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""End-to-end: batch-mode script drives zone CRUD through a mocked WAPI."""

import sys
import textwrap

import pytest

from ibcli import cli


@pytest.mark.skip(
    reason="Blocked by command module conversions (Task 9+): test relies on "
    "requests-mock and WapiSession-based command handlers (configure zone, "
    "show zone) that have not yet been ported to ibx-nios-sdk / MockTransport."
)
def test_full_zone_crud_batch(tmp_path, monkeypatch, capsys):
    script = tmp_path / "batch.cf"
    script.write_text(
        textwrap.dedent("""\
        # set up
        configure zone add demo.com
        configure zone demo.com add host web 1.2.3.4
        show zone demo.com
        configure zone demo.com delete host web
        configure zone demo.com delete
    """)
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ibcli",
            "-s",
            "grid",
            "-u",
            "admin",
            "-p",
            "pw",
            "-k",
            str(script),
        ],
    )
    cli.main()

    out = capsys.readouterr().out
    assert "read line" in out
