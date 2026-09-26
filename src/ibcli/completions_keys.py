# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Dynamic key= completions for generic `... set <key>=<value>` verbs.

Each SDK resource class exposes `_model` (a pydantic class) and
`_readonly_fields` (names the server won't accept on write). Walking the
model's `model_fields` produces a sorted list of `name=` completions with
their types as metadata - the same data the dispatcher's
`configure ... set <key>=<value>` pass-throughs actually accept.

No grid RPC is required: the list is static per SDK version.
"""

from __future__ import annotations

import functools
import importlib
import re
from collections.abc import Callable
from typing import Any

from ibcli.context import Context


@functools.cache
def resource_for(service: str, attr: str) -> Any:
    """Return the SDK resource class behind ``client.<service>.<attr>``.

    The SDK exposes its per-domain services publicly (``DtcService``,
    ``MicrosoftserverService``, ...) but most subpackages do not re-export the
    individual ``*Resource`` classes, and the services' return annotations sit
    behind ``TYPE_CHECKING`` so they cannot be resolved from the annotation
    alone. Importing ``ibx_nios_sdk.dtc._dtc_lbdn`` directly would work but
    binds us to a private module path.

    A service can be constructed with a ``None`` HTTP client - nothing touches
    it until a request is actually made - so reading the attribute off a
    throwaway instance yields the real class through public API only, with no
    client, no credentials and no network.

    Args:
        service: Public service attribute on ``NiosClient`` (e.g. ``"dtc"``),
            which is also the SDK subpackage name.
        attr: Resource attribute on that service (e.g. ``"lbdn"``).

    Returns:
        The resource class, carrying ``_model`` and ``_readonly_fields``.

    Raises:
        AttributeError: If the subpackage exports no ``*Service`` class, more
            than one, or the resource attribute does not exist - a typo or an
            upstream rename should fail loudly at import time, not produce an
            empty completion list at the prompt.
    """
    module = importlib.import_module(f"ibx_nios_sdk.{service}")
    # Each subpackage exports exactly one. Picking the first match instead
    # would silently take whichever sorts first in `dir()`, so an added
    # `BaseService` would quietly win and yield the wrong resource classes.
    names = [n for n in dir(module) if n.endswith("Service")]
    if len(names) != 1:
        raise AttributeError(
            f"expected exactly one *Service class in ibx_nios_sdk.{service}, found {names}"
        )
    return type(getattr(getattr(module, names[0])(None), attr))


def _fmt_type(annotation: Any) -> str:
    """Render a pydantic field annotation as a short human-readable type."""
    s = str(annotation).replace("typing.", "")
    # Strip fully-qualified module paths: "ibx_nios_sdk._common.models.ExtAttrValue" -> "ExtAttrValue"
    s = re.sub(r"(?:[\w]+\.)+([A-Z]\w*)", r"\1", s)
    s = re.sub(r"\s*\|\s*None\b", "", s)
    s = re.sub(r"\s*\|\s*str\b", "", s)

    # Inline `Literal[...]` → `a|b|c` wherever it appears (including inside list[...]).
    def _lit(m: re.Match) -> str:
        return m.group(1).replace("'", "").replace('"', "").replace(", ", "|")

    s = re.sub(r"Literal\[([^\[\]]+)\]", _lit, s)

    # Friendlier labels for very common shapes
    s = s.replace("dict[str, ExtAttrValue]", "extattrs map")
    s = s.replace("dict[str, Any]", "struct")
    # Translate Python type-hint syntax into ops-friendly labels
    s = re.sub(r"\blist\[([^\[\]]+)\]", r"\1 list", s)
    s = re.sub(r"\bstr\b", "text", s)
    s = re.sub(r"\bbool\b", "true/false", s)
    s = re.sub(r"\bint\b", "number", s)
    s = s.replace(" | ", " or ")
    return s


def _is_wapi_function(field: Any) -> bool:
    """True when a model field is really a WAPI function, not a data field.

    The SDK declares callable WAPI operations (``upgrade``, ``restartservices``,
    ``empty_recycle_bin``, ``run_scavenging`` …) as model fields annotated
    ``object | None`` - 49 of them across 10 models - and does not list them
    in ``READONLY_FIELDS``. They are not settable and not readable: offering
    ``upgrade=`` in a ``set`` dropdown points the operator at a call that
    cannot work, and asking for one in ``_return_fields`` makes NIOS answer
    ``.com.infoblox.one.cluster has no member .reqversion``.

    Real data fields all carry a concrete annotation, so the bare ``object``
    type is a reliable marker.
    """
    return str(field.annotation) == "object | None"


def list_settable_keys(model_cls: Any, readonly: Any = frozenset()) -> list[tuple[str, str]]:
    """Return (name, type) pairs for writable fields on a pydantic model."""
    ro = set(readonly or ())
    items: list[tuple[str, str]] = []
    for name, field in model_cls.model_fields.items():
        if name == "ref" or name in ro or _is_wapi_function(field):
            continue
        # Prefer the WAPI alias. Pydantic escapes names that collide with
        # Python builtins - `type` becomes `type_` on 18 SDK models - and
        # NIOS rejects the escaped spelling with "Unknown argument/field:
        # 'type_'". The alias is what the wire actually accepts.
        items.append((field.alias or name, _fmt_type(field.annotation)))
    return sorted(items)


def keys_completer_for(resource_cls: Any) -> Callable[[Context], list[tuple[str, str]]]:
    """Build a sync completer that yields `name=` entries for a resource."""
    items = [
        (f"{name}=", t)
        for name, t in list_settable_keys(
            resource_cls._model, getattr(resource_cls, "_readonly_fields", frozenset())
        )
    ]

    def _fn(_ctx: Context) -> list[tuple[str, str]]:
        return items

    return _fn


def keys_completer_for_path(service: str, attr: str) -> Callable[[Context], list[tuple[str, str]]]:
    """``keys_completer_for`` addressed by public service path instead of class.

    Preferred over importing a ``*Resource`` class from a private SDK module.

    Resolution is deferred to the first completion. Command modules build
    these at import time, and resolving eagerly meant importing that SDK
    domain - and building its pydantic models - just to have the CLI start.
    The key list is only ever needed once someone presses Tab on this
    subtree, so it is computed then and cached for the process.
    """
    cached: list[tuple[str, str]] = []
    resolved = False

    def _fn(ctx: Context) -> list[tuple[str, str]]:
        nonlocal resolved
        if not resolved:
            cached.extend(keys_completer_for(resource_for(service, attr))(ctx))
            resolved = True
        return cached

    return _fn


def lazy_keys_completer(
    loader: Callable[[], tuple[Any, Any]],
) -> Callable[[Context], list[tuple[str, str]]]:
    """Defer a model-based completer behind a loader callable.

    For call sites that need a specific model class rather than a service
    path. ``loader`` returns ``(model_cls, readonly)`` and is not called until
    the first completion, so the SDK import it performs stays off the startup
    path. The result is cached for the process.
    """
    cached: list[tuple[str, str]] = []
    resolved = False

    def _fn(ctx: Context) -> list[tuple[str, str]]:
        nonlocal resolved
        if not resolved:
            model, readonly = loader()
            cached.extend(keys_completer_from_model(model, readonly)(ctx))
            resolved = True
        return cached

    return _fn


def keys_completer_from_model(
    model_cls: Any, readonly: Any = frozenset()
) -> Callable[[Context], list[tuple[str, str]]]:
    """Same as keys_completer_for but takes a model class + readonly set directly.

    Useful for resources accessed through a generic HTTP client that doesn't
    expose the model on the resource class.
    """
    items = [(f"{name}=", t) for name, t in list_settable_keys(model_cls, readonly)]

    def _fn(_ctx: Context) -> list[tuple[str, str]]:
        return items

    return _fn


def print_keys(name_type_pairs: list[tuple[str, str]]) -> None:
    """Pretty-print a list of (name, type) pairs as an aligned table."""
    if not name_type_pairs:
        print("  No writable fields found.")
        return
    width = max(len(n) for n, _ in name_type_pairs)
    for n, t in name_type_pairs:
        print(f"    {n:<{width}}  {t}")
