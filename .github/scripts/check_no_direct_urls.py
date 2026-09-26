#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.
"""Fail if a built wheel declares a direct URL dependency.

PyPI rejects any distribution whose ``Requires-Dist`` metadata carries a direct
URL reference (``name @ git+https://...``), in ``dependencies`` or in any
extra. ``twine check`` does not catch it - that only renders the README - so
the upload fails at the very end of a release, after the GitHub release has
already been published. This runs before anything is uploaded.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def direct_url_requirements(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".dist-info/METADATA"))
        metadata = zf.read(name).decode()
    return [
        line
        for line in metadata.splitlines()
        if line.startswith("Requires-Dist:") and " @ " in line
    ]


def main(argv: list[str]) -> int:
    dist = Path(argv[1] if len(argv) > 1 else "dist")
    wheels = sorted(dist.glob("*.whl"))
    if not wheels:
        print(f"no wheel found in {dist}/", file=sys.stderr)
        return 1

    failed = False
    for wheel in wheels:
        offenders = direct_url_requirements(wheel)
        if offenders:
            failed = True
            for line in offenders:
                print(
                    f"::error title=Direct URL dependency::{wheel.name}: {line} - "
                    "PyPI will reject this upload. Replace it with a version constraint.",
                )
        else:
            print(f"{wheel.name}: no direct URL dependencies")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
