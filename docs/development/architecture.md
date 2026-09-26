# Architecture

## Module layout

```
pyproject.toml              metadata, runtime deps, `ibcli` console-script entry point
src/ibcli/
├── __init__.py             version string
├── __main__.py             python -m ibcli
├── cli.py                  argparse, startup, REPL loop, batch/exec modes
├── registry.py             COMMANDS dict, @command / register() decorators, SPECOPS, ALIASES
├── parser.py               expand_line, expand_word, abbrev, get_context
├── completer.py            prompt_toolkit IbcliCompleter (async-aware)
├── dispatcher.py           process_line: alias sub + expand_line + dispatch + error unwrap
├── context.py              Context dataclass (client, prompt, online, host, caches, …)
├── completions.py          Dynamic completions (members, zones, views) sourced live from the grid
├── debug.py                debug_cli level-gated logging
├── utils.py                cidr_family, normalize_cidr_any, net_to_arpa, as_dict
└── commands/               One module per functional domain - see README for the full list
    ├── __init__.py         imports every module so @command / register() decorators fire
    ├── system.py           help / quit / history / show time / show debug
    ├── server.py           configure server / master (connect)
    ├── zone.py             authoritative zones + classic records (A/AAAA/CNAME/MX/TXT/PTR/HOST)
    ├── zone_modern.py      Phase-3 records (CAA, DNAME, ALIAS, NAPTR, TLSA, HTTPS, SVCB, shared)
    ├── dns.py              DDNS principal clusters, DNS64, RPZ order, all-records aggregator
    ├── network.py          networks (v4+v6), containers, shared networks
    ├── ipam.py             address inventory, network views, VLAN, superhosts, bulkhosts
    ├── dhcp.py             ranges, fixed, MAC filters, IPv6 DHCP, all 5 filter types
    ├── grid.py             members, licensing, DNS/DHCP enable, HA, restart
    ├── grid_ext.py         grid DNS/DHCP properties, threat feeds, file distribution, GMC
    ├── admin.py            admin users/groups/roles, RADIUS legacy objects
    ├── auth.py             auth services (LDAP, AD, RADIUS, TACACS+, SAML, cert, policy)
    ├── auth_ext.py         approval workflow, FTP/SNMP users, parental control, HSM
    ├── cert.py             member certs, CSR, self-signed, upload/download
    ├── dtc.py              DTC servers/pools/LBDNs/monitors/topology/records
    ├── rpz.py              RPZ zones + records (A, CNAME, TXT, IP, client-IP, …)
    ├── notify.py           notification endpoints + rules + templates; ACLs
    ├── ops.py              DB snapshot, CSV tasks, capacity, integrations, BFD, TFTP
    ├── fileops.py          upload/download - CSV, backups, support bundles, per-member dumps
    ├── discovery.py        network discovery, SDN networks, vDiscovery
    ├── ea.py               Extensible Attribute definitions
    ├── ms.py               Microsoft DNS/DHCP integration
    ├── threat.py           Threat Insight, ADP, analytics
    ├── upgrade.py          upgrade groups, schedules, status
    └── template.py         network and range templates
```

## Data flow

```
User input
    │
    ▼
cli.py : _run_repl / _run_batch / -e
    │
    ▼
dispatcher.py : process_line(line, ctx)
    ├── apply ALIASES prefix substitution
    ├── parser.expand_line(line) → (expanded, error, match_line)
    │   ├── tokenize (handles quotes, splits key=value)
    │   └── per-token: get_context → expand_word → update match_line
    ├── if error  → print error, return
    ├── if entry is an intermediate waypoint → print "Incomplete : …"
    ├── if mutating verb → tee stdout into a buffer so we can synthesise "OK"
    │     when the handler finishes silently
    └── await COMMANDS[match_line].func(expanded, ctx)
            │
            ▼
       handler in commands/*.py (async)
            │
            ├── extract args from expanded line (regex + _parse_kv helpers)
            ├── await ctx.client.<resource>.list / create / update / delete
            │       │
            │       ▼
            │   ibx_nios_sdk.NiosClient → httpx.AsyncClient
            │   (cookie auth, async pagination, streaming fileop)
            └── print output
```

When a handler raises `NiosError`, the dispatcher unwraps nested
`AdmConDataError(...)` / `IBDataConflictError(...)` envelopes and prints
either `  Error: <clean msg>` or, in idempotent mode on a conflict,
`  Skipped: <clean msg>`.

## Design decisions

### Decorator-driven registration

Commands register themselves via `@command(match_line, words=..., help=...)` at import time. No external config files,
no discovery phase. `src/ibcli/commands/__init__.py` imports every command module so all decorators fire before
`main()` runs.

Adding a new command domain:

1. Drop a new file in `src/ibcli/commands/`.
2. Add an import to `commands/__init__.py`.
3. Write `@command(...)` handlers. Tab completion and help metadata pick up automatically.

### Flat `COMMANDS` dict

The command tree is stored as a flat dict keyed by canonical match-line strings:

```python
COMMANDS["configure zone add <zone>"] = CommandEntry(func=cli_add_zone, words="…", help="…")
COMMANDS["configure zone"]             = CommandEntry(words="add <zone>")
```

Intermediate waypoints (no handler) use `register(match_line, words=..., help=...)`. Depth is encoded in the key string; no tree structure to walk. Lookups are O(1).

### Async end-to-end

Every handler is `async def`. `NiosClient` is built on `httpx.AsyncClient`; list/create/update/delete calls are
awaited. `prompt_toolkit` integrates via its asyncio event loop, and `cli._run_repl` runs inside `asyncio.run`.

This matches the shape of modern NIOS use cases (lots of I/O, occasional parallelism via `asyncio.gather`) without forcing the REPL into a thread.

### `Context` object

A single `Context` dataclass flows through the session. Key fields:

| Field | Purpose |
|---|---|
| `client: NiosClient \| None` | `None` until `configure server` succeeds |
| `host / user` | Current connection's identity |
| `client_rev` | Negotiated WAPI version (used as default for version-gated calls) |
| `prompt` | Displayed by the REPL; updates on connect/disconnect |
| `debug_level` | Toggled via `-d <0-5>` or the `debug` command |
| `online` | Connection flag the REPL checks before issuing WAPI calls |
| `idempotent` | When set by `-i`, the dispatcher demotes conflicts to Skipped |
| `caches` | Sync-accessible completion caches (members, zones, views) populated lazily off the event loop |

Handlers mutate `ctx` directly (e.g. `ctx.client = NiosClient(...)` on connect).

### WAPI via `ibx-nios-sdk`

The HTTP layer is not in-tree. It lives in the Infoblox-published [`ibx-nios-sdk`](https://github.com/Infoblox-PS/ibx-nios-sdk), which:

- Detects the WAPI version via `GET /wapi/v2.14/?_schema=1`.
- Persists the `ibapauth` cookie returned on login.
- Provides typed resources under `ctx.client.<domain>.<object>` (e.g. `ctx.client.dns.record_a`, `ctx.client.ipam.network`).
- Handles pagination, fileop multi-step protocols, and error unwrapping.

ibcli stays thin: it constructs WAPI bodies, awaits the SDK's CRUD calls, and formats results.

### Tab completion via `prompt_toolkit`

`IbcliCompleter` subclasses `prompt_toolkit.completion.Completer`. On every `<Tab>`:

1. Parse the line so far via `expand_line`.
2. If parsing errored with "Unknown", suppress completions.
3. Use `lastarg` to identify the current partial word.
4. Call `get_context(match_line)` for the valid next-tokens.
5. Call `expand_word(lastarg, words)` to filter + rank.
6. Yield `Completion` objects. Each entry's `display_meta` pulls `help=` from the registry, giving the tooltip you see in the dropdown.

Complete-while-typing is disabled (`complete_while_typing=False`) - completions fire only on `<Tab>`, matching the Perl UX.

Dynamic completions (member FQDNs, zone names, view names) come from the `ctx.caches` dict, populated asynchronously on connect so the sync completer has data to surface without awaiting.

## Key design constraints

- **Async end-to-end.** Every handler is `async def`; the REPL runs in `asyncio.run`.
- **No plugin system.** Commands register at import time only.
- **Python 3.11+.** Uses `str | None` union syntax, `asyncio.Runner`, and other 3.11-era features.
- **Single `Context` per process.** No multi-grid state; switching grids means calling `configure server` again.
- **Flat registry.** No tree traversal; match-lines are the source of truth for grammar.
- **Thin over the SDK.** ibcli builds bodies and prints output; it does not reimplement WAPI semantics.
