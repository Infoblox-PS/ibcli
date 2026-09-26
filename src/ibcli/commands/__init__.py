# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Command modules. Each module registers handlers via the @command decorator.

During the SDK refactor, modules are re-enabled one at a time after
conversion. Commented-out imports correspond to the tasks that enable them.
"""

# Re-enabled incrementally:
from ibcli.commands import (
    admin,  # noqa: F401  Task 13
    auth,  # noqa: F401  Phase 5
    auth_ext,  # noqa: F401  Phase 14
    cert,  # noqa: F401  Task 14
    dhcp,  # noqa: F401  Task 15
    discovery,  # noqa: F401  Phase 16
    dns,  # noqa: F401  Phase 11
    dtc,  # noqa: F401  Phase 7
    ea,  # noqa: F401  Task 16
    fileops,  # noqa: F401  Task 17
    grid,  # noqa: F401  Task 18
    grid_ext,  # noqa: F401  Phase 13
    ipam,  # noqa: F401  Phase 8
    ms,  # noqa: F401  Phase 17
    network,  # noqa: F401  Task 19
    notify,  # noqa: F401  Phase 12
    ops,  # noqa: F401  Phase 15
    rpz,  # noqa: F401  Phase 6
    server,  # noqa: F401  Task 20
    system,  # noqa: F401  Task 21
    template,  # noqa: F401  Task 22
    threat,  # noqa: F401  Phase 18
    upgrade,  # noqa: F401  Phase 9
    zone,  # noqa: F401  Task 11
    zone_modern,  # noqa: F401  Phase 3
)
