# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

__version__ = "1.0.0"

# NOTE: the ibx-nios-sdk prerequisite check deliberately does NOT run here.
# Importing this package used to call it, which meant `import ibcli.registry`
# - pure Python, no SDK needed - pulled in 256 SDK modules and cost ~280ms.
# `ibcli.cli.main` runs the check instead, so the CLI still reports a missing
# or outdated SDK as one actionable line, while library importers and the
# argv-only paths (--version, --license, -l) pay nothing.
