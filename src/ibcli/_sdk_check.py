# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Fail clearly when the ibx-nios-sdk prerequisite is missing or too old.

The SDK is a documented prerequisite rather than a declared dependency, so a
missing one would otherwise surface as an ``ImportError`` from somewhere deep
in the import graph. This module turns it into one line that says what to
install. See the Install section of README.md.
"""

from __future__ import annotations

# The oldest SDK this CLI works against. 1.0.0 is the first public release and
# the version this CLI's test suite runs against; earlier ones were internal.
MINIMUM_SDK = "1.0.0"

_INSTALL_HINT = (
    "ibcli requires the ibx-nios-sdk package, which is not installed.\n"
    "\n"
    "Install it, then re-run:\n"
    "\n"
    f"    pip install 'ibx-nios-sdk>={MINIMUM_SDK}'\n"
)


def _parse(version: str) -> tuple[int, ...]:
    """Best-effort numeric tuple for a version string.

    Stops at the first non-numeric component so a suffix like ``0.2.0rc1`` or
    ``0.2.0+local`` compares as ``(0, 2)`` rather than raising - a version we
    cannot parse must never be the reason the CLI refuses to start.
    """
    parts: list[int] = []
    for chunk in version.split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def require_sdk() -> None:
    """Raise SystemExit with an actionable message if the SDK is unusable.

    Called for its side effect at import of :mod:`ibcli`, so every entry
    point - the console script, ``python -m ibcli``, and a bare ``import
    ibcli`` - gets the same message.
    """
    try:
        import ibx_nios_sdk  # noqa: F401
    except ImportError as exc:
        raise SystemExit(f"  Error: {_INSTALL_HINT}") from exc

    installed = getattr(ibx_nios_sdk, "__version__", None)
    if not installed:
        # An SDK that does not advertise a version is not grounds to refuse;
        # the import worked, so let the operator get on with it.
        return
    if _parse(installed) < _parse(MINIMUM_SDK):
        raise SystemExit(
            f"  Error: ibcli requires ibx-nios-sdk >= {MINIMUM_SDK}, "
            f"but {installed} is installed.\n"
            f"  Upgrade with: pip install --upgrade 'ibx-nios-sdk>={MINIMUM_SDK}'"
        )
