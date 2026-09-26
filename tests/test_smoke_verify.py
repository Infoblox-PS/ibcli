# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VERIFY_PY = REPO / "scripts" / "smoke" / "verify.py"


def _load_verify():
    import sys

    smoke_dir = str(VERIFY_PY.parent)
    if smoke_dir not in sys.path:
        sys.path.insert(0, smoke_dir)
    spec = importlib.util.spec_from_file_location("_smoke_verify", VERIFY_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_wapi_count_follows_paged_results(monkeypatch):
    verify = _load_verify()
    seen_urls: list[str] = []

    def fake_check_output(args, stderr=None, timeout=None):
        url = args[-1]
        seen_urls.append(url)
        if "_page_id=page-2" in url:
            return json.dumps({"result": [{"_ref": "b"}]}).encode()
        return json.dumps(
            {
                "result": [{"_ref": "a"}],
                "next_page_id": "page-2",
            }
        ).encode()

    monkeypatch.setattr(verify.subprocess, "check_output", fake_check_output)

    assert verify.wapi_count("grid.test", "admin", "secret", "record:a", "name~=x") == 2
    assert "_paging=1" in seen_urls[0]
    assert "_return_as_object=1" in seen_urls[0]
    assert "_page_id=page-2" in seen_urls[1]


def test_wapi_count_still_accepts_legacy_list_response(monkeypatch):
    verify = _load_verify()

    def fake_check_output(args, stderr=None, timeout=None):
        return json.dumps([{"_ref": "a"}, {"_ref": "b"}]).encode()

    monkeypatch.setattr(verify.subprocess, "check_output", fake_check_output)

    assert verify.wapi_count("grid.test", "admin", "secret", "view", "name~=smoke") == 2
