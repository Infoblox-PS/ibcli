# Testing

ibcli uses `pytest` with `httpx.MockTransport` for its primary test suite.  A real-grid integration suite lives in
`tests/integration/` - see [Real Grid Status](../reference/real-grid-status.md) and the [Real-grid integration
tests](#real-grid-integration-tests) section below.

## Running the tests

```bash
# From the repo root
pytest python/tests/

# With verbose output
pytest python/tests/ -v

# Run a specific file
pytest python/tests/test_commands_zone.py -v

# Run tests matching a pattern
pytest python/tests/ -k "zone"
```

## Test organisation

```
python/tests/
├── test_parser.py             # Pure logic: abbrev, expand_word, expand_line, aliases
├── test_completer.py          # IbcliCompleter: completion yields
├── test_all_handlers_sweep.py # Every registered handler: must not leak exceptions
├── test_dispatcher.py         # process_line: aliases, errors, idempotent mode
├── test_commands_zone.py      # Zone/record handlers against mocked WAPI
├── test_commands_network.py   # Network handlers
├── test_commands_dhcp.py      # DHCP handlers
├── test_commands_admin.py     # Admin/RADIUS handlers
├── test_commands_grid.py      # Grid handlers
├── test_commands_ea.py        # Extensible attribute handlers
├── test_commands_fileops.py   # File operation handlers
├── test_commands_cert.py      # Certificate handlers
├── test_commands_template.py  # Template handlers
└── test_repl.py               # End-to-end: process_line through full stack
```

## Parser tests (no network)

Parser tests need no mocking - they exercise pure Python logic:

```python
from ibcli.parser import abbrev, expand_word, expand_line

def test_abbrev_unique():
    result = abbrev(["configure", "show", "set"])
    assert result["co"] == "configure"
    assert result["sh"] == "show"
    # "s" is ambiguous between show and set → not in result
    assert "s" not in result

def test_expand_line_zone_add():
    expanded, error, match_line = expand_line("co z a foo.com")
    assert error == ""
    assert expanded == "configure zone add foo.com"
    assert match_line == "configure zone add <zone>"

def test_unknown_word():
    expanded, error, match_line = expand_line("show badword")
    assert "Unknown argument at marker" in error
```

## SDK client tests (`httpx.MockTransport`)

The CLI talks to NIOS through `ibx-nios-sdk`, so tests inject a fake
transport rather than patching a session object. `tests/conftest.py`
provides `make_client(handler)`, which builds a real `NiosClient` wired to
an `httpx.MockTransport`. The handler returns a response, or `None` to fall
through to the default that answers the SDK's login probe.

```python
import httpx
import pytest
from ibx_nios_sdk import NiosError

from tests.conftest import make_client


async def test_create_returns_ref():
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "POST" and request.url.path.endswith("/zone_auth"):
            return httpx.Response(201, json="zone_auth/abc123")
        return None  # delegate to the default login handler

    async with make_client(handler) as client:
        ref = await client.dns.zone_auth.create({"fqdn": "foo.com"})
        assert "zone_auth/abc123" in str(ref)


async def test_error_propagation():
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and request.url.path.endswith("/zone_auth"):
            return httpx.Response(400, json={
                "Error": "IBDataError", "text": "Not found",
                "code": "Client.Ibap.Data",
            })
        return None

    async with make_client(handler) as client:
        with pytest.raises(NiosError) as exc:
            [z async for z in client.dns.zone_auth.list(fqdn="missing.com")]
        assert "Not found" in str(exc.value)
```

List responses must use the paged shape the SDK expects -
`{"result": [...]}` - not a bare array. Most command test modules define a
`_list()` helper for this.

## Command handler tests

Handler tests build a `Context` around a mocked client and call
`process_line`. `asyncio_mode = "auto"` is set in `pyproject.toml`, so
`async def` tests need no decorator.

```python
from contextlib import asynccontextmanager

import httpx

from ibcli.context import Context
from ibcli.dispatcher import process_line
from tests.conftest import make_client


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test")


async def test_add_zone():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        seen.append(request)
        if request.method == "POST" and "zone_auth" in request.url.path:
            return httpx.Response(201, json="zone_auth/abc123")
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone add example.com", ctx)

    posts = [r for r in seen if r.method == "POST" and "zone_auth" in r.url.path]
    assert len(posts) == 1


async def test_show_zone(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method != "GET":
            return None
        if "zone_auth" in request.url.path:
            return httpx.Response(200, json={"result": [
                {"_ref": "zone_auth/abc", "fqdn": "example.com",
                 "view": "default"},
            ]})
        # `show zone` also sweeps forward/delegated/stub - stub them empty.
        return httpx.Response(200, json={"result": []})

    async with connected_ctx(handler) as ctx:
        await process_line("show zone example.com", ctx)

    assert "fqdn=example.com" in capsys.readouterr().out
```

Two whole-surface sweeps back these up:
`tests/test_all_handlers_sweep.py` dispatches **every** registered handler
against a permissive mock and fails if any leaks an exception, and
`tests/test_not_connected_sweep.py` covers the `ctx.client is None` guard.
A new command is covered by both automatically.

## Completer tests

```python
from prompt_toolkit.document import Document
from ibcli.completer import IbcliCompleter

def completions(text):
    c = IbcliCompleter()
    doc = Document(text, len(text))
    return [comp.text for comp in c.get_completions(doc, None)]

def test_empty_line():
    result = completions("")
    assert "configure" in result
    assert "show" in result

def test_configure_prefix():
    result = completions("co ")
    assert "zone" in result
    assert "server" in result

def test_unknown_word_no_completions():
    result = completions("show unknownword ")
    assert result == []
```

## Test count

Current count: **3,284 tests passing** in the mocked suite, all in ~3 seconds.

```bash
pytest python/tests/ --tb=no -q
578 passed in 0.54s
```

---

## Real-grid integration tests

### Overview

`tests/integration/` contains tests that execute against a live NIOS grid.
They are **skipped by default** when the required env vars are absent, so
`pytest tests/` always shows the full mocked count with no failures.

Every test in `tests/integration/` is automatically marked `real_grid`.

### Environment variables

| Variable | Description |
|---|---|
| `IBCLI_TEST_GRID` | Grid master IP or hostname |
| `IBCLI_TEST_USER` | WAPI user (usually `admin`) |
| `IBCLI_TEST_PASS` | WAPI password |

### Running the integration suite

```bash
# Run all integration tests against a real grid
IBCLI_TEST_GRID=192.0.2.40 IBCLI_TEST_USER=admin IBCLI_TEST_PASS='<password>' \
    pytest tests/integration -v

# Run only integration tests by marker (skipped if env vars not set)
pytest -m real_grid -v

# Show what would run without executing
pytest tests/integration --collect-only
```

### What they cover

| Test file | What it locks in |
|---|---|
| `test_provision_workflow.py` | Member add (plain and pre-provisioned), gateway warning, license case, failover with FQDN peers, network+range+failover sequencing, fileop force-download header |
| `test_full_provision.py` | Full end-to-end: 2 members → failover → network with members → failover-backed range; all lessons exercised in sequence |

### When to add a new integration test

Add a test in `tests/integration/` whenever:

1. A real-grid bug is fixed that mocked tests didn't catch (the mocked test
   should also be updated to match the real behaviour).
2. A new command family is verified against a live grid for the first time.
3. A NIOS version upgrade reveals a new API quirk.

The pattern to follow:

```python
class TestMyNewFeature:
    def test_thing_that_failed_on_real_grid(
        self, grid_ctx, test_prefix, cleanup_<resource>, capsys
    ):
        # ... create resource, assert, cleanup fixture handles deletion
        process_line("configure ...", grid_ctx)
        out = capsys.readouterr().out
        assert "Error" not in out
        # Verify via WAPI GET
        results = grid_ctx.session.get("objtype", field=value)
        assert len(results) == 1
```

Always use the `test_prefix` fixture for resource names to avoid collisions
between parallel runs, and register every created resource with a `cleanup_*`
fixture so the grid is left clean even when a test fails.

### Pre-commit workflow

!!! warning "Mocked tests alone aren't enough"
    Every real-grid bug we've hit (`415 Unsupported Media Type`,
    `primary_server_type` missing, FQDN-not-IP, `pre_provisioning` rejected
    in POST, dict-vs-string ref responses) passed all the mocked tests.
    Mocked tests verify we send what **we** think WAPI wants; only the
    integration suite verifies we send what NIOS **actually** accepts.

Before committing changes that touch any of the following, run the
integration suite against a lab grid:

- `python/src/ibcli/session.py` - HTTP layer, auth, fileop, ref coercion
- `python/src/ibcli/commands/grid.py` - member CRUD, pre-provisioning
- `python/src/ibcli/commands/dhcp.py` - ranges, fixed, failover
- `python/src/ibcli/commands/network.py` - network CRUD, move, IPv4/IPv6 routing
- `python/src/ibcli/commands/fileops.py` - upload/download
- `python/src/ibcli/commands/cert.py` - certificate operations
- Any code that constructs a WAPI request body shape

Concrete command:

```bash
cd python
IBCLI_TEST_GRID=<lab-ip> IBCLI_TEST_USER=<user> IBCLI_TEST_PASS=<pass> \
    pytest tests/integration -v
```

Both must pass:

1. `pytest tests/` → all mocked tests green
2. `pytest tests/integration -v` with env vars → all integration tests green

If you don't have access to a lab grid, push your branch and ask a
maintainer with lab access to run the suite before merging. Don't merge
WAPI-shape changes based on mocked-only coverage.

### Adding a test after fixing a real-grid bug

Every real-grid bug fix should come with a companion integration test. The
reason: the next regression of that same bug won't be caught by the mocked
suite (mocks were what let it ship in the first place). Flow:

1. Reproduce the bug against the grid, capture the WAPI error.
2. Fix the code; update the mocked test to match the corrected shape.
3. **Add an integration test** in `tests/integration/` that would have
   failed before the fix. Name it for the lesson, e.g.
   `test_failover_uses_fqdn_not_ip`.
4. Run both suites - mocked and integration - green before committing.
5. Update `reference/real-grid-status.md` if this elevates a command from
   "mocked only" to "verified on real grid."

## Live-grid audit tooling

Two harnesses in `scripts/` complement the pytest suites and run only
against a live NIOS grid. Use them when you want coverage the mocked tests
can't provide: "do our commands actually work end-to-end?" and "do `show`
commands produce useful output?"

### `scripts/sweep-show.sh` - show-command sweep

Generates the full list of no-arg `show` commands from `ibcli -l`, runs
them all against a live grid, and classifies each error as:

- **friendly usage hint** - our own `"Error: X required (usage: …)"`
  messages for commands that need an arg
- **grid-config** - feature disabled / service offline on the grid
- **suspected CLI bug** - everything else

The script exits 1 if any suspected bugs appear, making it suitable for
CI once a lab grid is wired up.

```bash
scripts/sweep-show.sh -s <host> -u <user> -p <pw>
# or env-based
IBCLI_HOST=... IBCLI_USER=... IBCLI_PASS=... scripts/sweep-show.sh
```

Artifacts land in a per-run `mktemp` dir (overridable with `-o <dir>`):
`sweep.ibcli` (commands), `sweep.out` (raw output), `summary.tsv`
(per-command status + preview), `report.txt` (human-readable summary).

### `scripts/smoke/` - object-build smoke harness

Generates, executes, verifies, and tears down a comprehensive smoke
population of ~10,000 objects across ~30 object types. Parameterised by
scale (`tiny` ≈ 100 objects, `small` ≈ 1,000, `full` ≈ 10,000) and by
phase (1 = infra, 2 = DHCP, 3 = zones, …, 10 = DHCP extras + templates).

```bash
# Full cycle - build, verify counts, tear down
scripts/smoke/smoke.sh -s <host> -u <user> -p <pw> --scale full --tag v1 --all

# Build only (leave objects on grid for manual inspection)
scripts/smoke/smoke.sh -s <host> -u <user> -p <pw> --scale tiny --build

# Phase-by-phase
scripts/smoke/smoke.sh ... --phases 3,4 --build    # zones + records only

# Point at a grid whose name isn't the default, and pre-provision 200 members
scripts/smoke/smoke.sh -s <host> -u <user> -p <pw> \
    --scale full --grid Infoblox --members 200 --build
```

`--grid` must match what `show grid` reports on the target: phase 0 emits
`configure grid <name> member add ...`, which fails outright on a name
mismatch. It defaults to `$IBCLI_SMOKE_GRID`, then `Migration`.

`--members` overrides the scale's member count for build, verify and
teardown together - passing it to only one of the three leaves
pre-provisioned members behind. Pre-provisioned members are database
records on a dedicated subnet (`$IBCLI_SMOKE_MEMBER_NET`, default
`10.63.50`), so their addresses never need to be reachable and cannot
collide with the real grid master. Use `--members 0` on a grid that cannot
admit members - see [Pre-provisioning members needs a valid grid-wide
licence](known-quirks.md#pre-provisioning-members-needs-a-valid-grid-wide-licence);
DHCP failover pairs are skipped automatically when there are fewer than two
members.

The harness runs `ibcli` from `$IBCLI` if set, else the repo's
`.venv/`, else `poetry run` - so it works without Poetry installed.

!!! warning "Members are torn down last for a reason"
    NIOS refuses to delete a member anything still points at - *"cannot be
    removed because it is the DHCP failover primary in `<fo>`"* (phase 2) or
    *"is a primary server for NS Group `<group>`"* (phase 1). The full
    teardown order already accounts for this, but
    `--teardown --phases 0` on its own will fail on exactly those members.
    `teardown.py` warns when phase 0 is requested without phases 1 and 2.

All smoke-created objects carry the `smoke-` name prefix, and objects that
support EAs additionally carry the `Smoke=<tag>` EA. The teardown phase is
reverse-dependency-ordered (notifications → admin → DTC → RPZ → hosts →
zones → DHCP extras → DHCP → infra → members), so cascades resolve
cleanly. Teardown is opt-in via `--teardown` or `--all` - it never runs by
default.

**Why it's useful:** the sweep-show harness verifies `show` commands work
on whatever state the grid happens to have. The smoke harness builds
*known* state so a re-run comparison is meaningful ("the same `show
network` that returned 40 rows after build returns 0 after teardown").
Every real CLI bug caught during this session (grammar gaps, missing
required WAPI fields, wrong WAPI object names, broken return-field lists)
was surfaced by running one of these two scripts.
