# Adding Commands

This guide walks through adding a new command family to ibcli. As an example, we will add a hypothetical `configure vlan add <name> id <num>` command.

## Step 1: Create a module under `commands/`

Create `python/src/ibcli/commands/vlan.py`:

```python
from __future__ import annotations

import re

from ibcli.context import Context
from ibcli.registry import command, register


# Register intermediate waypoints first (no handler, just a next-words list).
register("configure", words="vlan")           # adds "vlan" to configure's context
register("configure vlan", words="add <name>")
register("configure vlan add", words="<name>")
register("configure vlan add <name>", words="id")
register("configure vlan add <name> id", words="<num>")


@command(
    "configure vlan add <name> id <num>",
    words="<cr> comment=<comment>",
    help="Add a VLAN.",
)
def cli_add_vlan(line: str, ctx: Context) -> None:
    if ctx.session is None:
        print("  Not connected")
        return

    m = re.search(r"\bvlan add\s+(\S+)\s+id\s+(\d+)", line)
    if not m:
        print("  Error: name and id required")
        return
    name, vlan_id = m.group(1), int(m.group(2))

    from ibcli.session import WapiError
    try:
        ctx.session.create("vlan", name=name, id=vlan_id)
    except WapiError as e:
        print(f"  Error: {e.message}")
```

## Step 2: Import the module in `commands/__init__.py`

```python
from ibcli.commands import vlan  # noqa: F401
```

This ensures the decorators fire at import time. Without this import, the module is never loaded and the commands are never registered.

## Step 3: Add `show` support (optional)

Add a `show vlan` command to the same module:

```python
register("show", words="vlan")
register("show vlan", words="<cr> <name>")


@command("show vlan", words="<cr> <name>", help="List VLANs.")
@command("show vlan <name>", words="<cr>", help="Show a specific VLAN.")
def cli_show_vlan(line: str, ctx: Context) -> None:
    if ctx.session is None:
        print("  Not connected")
        return

    tokens = line.split()
    params: dict = {"_return_fields": ["name", "id", "comment"]}
    if len(tokens) >= 3 and not tokens[2].startswith("<"):
        params["name"] = tokens[2]

    from ibcli.session import WapiError
    try:
        results = ctx.session.get("vlan", **params)
    except WapiError as e:
        print(f"  Error: {e.message}")
        return

    for r in results:
        parts = [f"name={r.get('name', '')}", f"id={r.get('id', '')}"]
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
```

## Step 4: Write tests

Create `tests/test_commands_vlan.py`:

```python
import json
from contextlib import asynccontextmanager

import httpx

from ibcli.commands import vlan  # noqa: F401 - trigger registration
from ibcli.context import Context
from ibcli.dispatcher import process_line
from tests.conftest import make_client


@asynccontextmanager
async def connected_ctx(handler=None):
    """A Context holding a real NiosClient wired to a mock transport."""
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test")


async def test_add_vlan():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        seen.append(request)
        if request.method == "POST" and "vlan" in request.url.path:
            return httpx.Response(201, json="vlan/abc123")
        return None  # delegate to the default login handler

    async with connected_ctx(handler) as ctx:
        await process_line("configure vlan add mgmt id 100", ctx)

    posts = [r for r in seen if r.method == "POST" and "vlan" in r.url.path]
    assert len(posts) == 1
    assert json.loads(posts[0].content) == {"name": "mgmt", "id": 100}


async def test_show_vlan(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "vlan" in request.url.path:
            # Note the paged shape - a bare list will not deserialise.
            return httpx.Response(200, json={"result": [
                {"_ref": "vlan/abc", "name": "mgmt", "id": 100},
            ]})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show vlan", ctx)

    assert "mgmt" in capsys.readouterr().out
```

Tests are `async def` with no decorator - `asyncio_mode = "auto"` is set in
`pyproject.toml`. You do not need to add the command to any sweep list:
`tests/test_all_handlers_sweep.py` discovers every registered handler and
asserts it cannot leak an exception, so a new command is covered the moment
it is registered.

## Step 5: Run the tests

```bash
pytest tests/test_commands_vlan.py -v
```

## Patterns and conventions

### Match-line format

Match-lines use literal words and `<special>` tokens separated by spaces:

- Literals: `configure`, `zone`, `add`, `delete`, `modify`
- Specials: `<zone>`, `<ip>`, `<n.n.n.n/mm>`, `<name>`, `<num>`, `<cr>`, `<comment>`

The full SPECOPS table is in [Parser Reference](../reference/parser.md).

### `words=` format

The `words` parameter to `@command` and `register` is a space-separated string of next-valid tokens. Use `|` for alternates and `key=<special>` for key-value pairs:

```python
words="<cr> comment=<comment>|view=<name>|set"
```

### `<cr>` token

Including `<cr>` in `words` signals that pressing Enter here (with no more tokens) is valid. Without `<cr>`, the command is treated as incomplete and `process_line` prints an "Incomplete" message.

### Set-chain pattern

For commands that accept `set key value` EA pairs, register a static chain up to depth 16 (the project-wide standard - see `docs/development/known-quirks.md`):

```python
_BASE = "configure vlan add <name> id <num>"
for _depth in range(16):
    _pfx = _BASE + (" set <name> <value>" * _depth)
    register(f"{_pfx} set", words="<name>")
    register(f"{_pfx} set <name>", words="<value>")
    register(f"{_pfx} set <name> <value>", words=_WORDS)
```

Then bind the handler to each chain endpoint:

```python
for _depth in range(1, 5):
    _ml = _BASE + (" set <name> <value>" * _depth)
    command(_ml, words=_WORDS)(cli_add_vlan)
```

### Parsing handler arguments

Use `re.search` to extract values from the expanded `line` string. The line has already been through `expand_line` - literal words are fully expanded, values are as the user typed them.

Helpers like `_parse_kv(line, "key")` and `_parse_comment(line)` are duplicated in each module to keep modules independent. This is a deliberate design choice (no shared utility module for handlers).

## Before you commit

Every handler that constructs a WAPI request body needs real-grid verification, not just mocked tests. See the [pre-commit workflow](testing.md#pre-commit-workflow) in the testing guide - in short:

1. Pass `pytest tests/` (mocked).
2. Pass `pytest tests/integration -v` (real grid, with `IBCLI_TEST_GRID` / `USER` / `PASS` env vars).
3. If you fixed a real-grid bug, add an integration test that would have caught it.

WAPI shape bugs are invisible to mocks. Don't rely on the mocked suite alone for correctness claims.
