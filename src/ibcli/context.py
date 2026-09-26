# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

# Annotation only. `from __future__ import annotations` keeps the hint a
# string at runtime, so a real import here would put 256 SDK modules on
# the startup path purely to satisfy a type.
if TYPE_CHECKING:
    from ibx_nios_sdk import NiosClient


@dataclass
class Context:
    client: NiosClient | None = None
    prompt: str = "server ? > "
    debug_level: int = 0
    master_ip: str | None = None
    client_rev: str = "6.1.0.0"
    online: bool = False
    host: str | None = None
    user: str | None = None
    idempotent: bool = False
    # Connection options set once from argv and applied by every subsequent
    # `configure server` in this process (including the one the -s/-u/-p
    # flags synthesize). Defaults match the SDK's own defaults.
    verify: bool = True
    wapi_version: str | None = None
    # Per-request WAPI timeout in seconds. The SDK defaults to 30s, which a
    # few grid-wide aggregations exceed on a populated grid (e.g.
    # `show threat_protection statistics` measured 30.15s).
    timeout: float = 30.0
    # NIOS restricts read/create/update/delete per object type, and the SDK
    # refuses a restricted call before it leaves the client. The table was
    # built from one NIOS build, so --allow-restricted opts out for grids
    # whose restrictions differ.
    enforce_restrictions: bool = True
    # Sync-accessible completion caches. Populated lazily off the event loop
    # so the prompt_toolkit completer (which runs synchronously) can surface
    # live values - members, views, networks, etc. - without awaiting.
    caches: dict = field(default_factory=dict)

    @asynccontextmanager
    async def connect(
        self,
        *,
        host: str,
        user: str,
        password: str,
        verify: bool | None = None,
        wapi_version: str | None = None,
        timeout: float | None = None,
        enforce_restrictions: bool | None = None,
    ) -> AsyncIterator[Context]:
        """Open a NiosClient and bind it to this Context for the duration
        of the async with block.

        Every connection option defaults to the Context's own field, so this
        builds the same client `configure server` does. Passing one
        explicitly overrides it for this connection only - the Context keeps
        the value argv set.
        """
        if verify is None:
            verify = self.verify
        if wapi_version is None:
            wapi_version = self.wapi_version
        if timeout is None:
            timeout = self.timeout
        if enforce_restrictions is None:
            enforce_restrictions = self.enforce_restrictions
        # Imported at call time: opening a client is the only thing in
        # this module that needs the SDK at runtime.
        from ibx_nios_sdk import NiosClient

        async with NiosClient(
            grid_url=f"https://{host}",
            username=user,
            password=password,
            wapi_version=wapi_version,
            use_session=True,
            verify=verify,
            timeout=timeout,
            enforce_restrictions=enforce_restrictions,
        ) as client:
            self.client = client
            self.online = True
            self.host = host
            self.user = user
            self.prompt = f"{host} > "
            try:
                yield self
            finally:
                self.client = None
                self.online = False
                self.prompt = "server ? > "
