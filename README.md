# ibcli

**An async Python CLI for Infoblox NIOS - tab-completion, batch mode, a live REPL, and a WAPI-native command surface.**

[![Tests](https://github.com/Infoblox-PS/ibcli/actions/workflows/ci.yml/badge.svg)](https://github.com/Infoblox-PS/ibcli/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-GPL%20v3-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/Infoblox-PS/ibcli)](https://github.com/Infoblox-PS/ibcli/releases)
[![Docs](https://img.shields.io/badge/docs-zensical-green.svg)](https://infoblox-ps.github.io/ibcli/) [![Tests
passing](https://img.shields.io/badge/tests-3%2C284%20passing-brightgreen.svg)](https://github.com/Infoblox-PS/ibcli/actions/workflows/ci.yml)
[![Commands](https://img.shields.io/badge/commands-1063-blue.svg)](docs/commands/index.md)

---

## What it is

`ibcli` is a ground-up Python rewrite of the original Perl `ibcli`, built as a thin async CLI over the
Infoblox-published [`ibx-nios-sdk`](https://github.com/Infoblox-PS/ibx-nios-sdk). It covers the full day-to-day
operational surface of a NIOS grid:

- **DNS** - authoritative zones (forward + reverse), all record types (A, AAAA, CNAME, MX, TXT, PTR, SRV, CAA, NAPTR,
  TLSA, HTTPS, SVCB, DNAME, ALIAS), shared records, host records, RPZ firewalling, DNS64, GSS-TSIG principal allowlists.
- **IPAM / DHCP** - IPv4 and IPv6 networks, network containers, shared networks, DHCP ranges, fixed addresses, MAC
  filters, fingerprint / option / NAC / relay-agent filters, failover pairs, network and range templates, option spaces
  and definitions.
- **Grid** - members (pre-provisioned and online), HA pairs, NS groups, views, attributes, schedules, upgrade groups,
  restart status, GMC clusters.
- **Security** - admin users/groups/roles, auth services (LDAP, AD, RADIUS, TACACS+, SAML, certificate), approval
  workflows, HSM groups, parental controls, CA certificates.
- **DTC** - DNS Traffic Director: servers, pools, LBDNs, monitors (HTTP, ICMP, TCP, SNMP, SIP, PDP), topology rules.
- **Ops** - CSV import/export, grid backup/restore, support bundles, log files, scheduled distributions, notification
  endpoints + rules, integrations (TAXII, syslog, PxGrid, DXL, outbound).

It preserves the Cisco-IOS-style UX that network engineers expect: **unambiguous prefix abbreviation at every
position**, a persistent REPL with history and line continuation, and a readable command vocabulary that maps one-to-one
to NIOS concepts.

Because the command surface is wide (1,063 registered commands spanning 2,249 grammar nodes), the abbreviation engine is
central to usability. Any unambiguous prefix is accepted, so `co z a example.com` expands to `configure zone add
example.com`. Tab at any point shows context-appropriate completions with inline descriptions.

---

## Features

### Command surface

- **1,063 commands** across 12 functional domains, covering DNS, IPAM, DHCP, grid, admin, auth, DTC, RPZ, notifications,
  templates, and file operations.
- **Abbreviation engine** - any unambiguous prefix of a keyword is accepted at every position (`co n a 10.0.0.0/24`).
- **Context-sensitive tab completion** via `prompt_toolkit` - each candidate carries a tooltip describing what the
  subtree does.
- **Grammar-level validation** - malformed or nonsensical command chains are rejected with positional `^---` markers
  before touching WAPI.

### Invocation modes

- **Interactive REPL** - persistent history, `\` line continuation, configurable key bindings.
- **Single-command mode** (`-e "cmd"`) - for shell pipelines and CI scripts.
- **Batch file mode** (`ibcli script.ibcli`) - batch files are positional arguments; run an ordered list of
  commands, optionally `-i` to demote "already exists" conflicts to skips.
- **`.ibcli.cf` auto-load** on startup for per-user defaults and aliases.
- **Aliases** - short prefixes (`pwd`, `info`) substituted before parsing.

### Reliability

- **Cookie-based auth** with session reuse across commands.
- **Streaming file I/O** for backups, support bundles, and log dumps.
- **Strict TLS** by default; `-k / --insecure` opt-out for lab environments.
- **Idempotent mode** (`-i`) demotes NIOS "already exists" errors to `Skipped` so batch re-runs are safe.
- **Structured WAPI error handling** - unwraps nested `AdmConDataError` / `IBDataConflictError` envelopes into a clean
  one-line message.

### Automation tooling

- **`scripts/sweep-show.sh`** - runs every no-arg `show` command against a live grid, classifies errors as
  friendly-usage / grid-config / CLI-bug, exits non-zero on any suspected bug. Suitable for CI gates.
- **`scripts/smoke/`** - parameterised build / verify / teardown harness that can create up to ~10,000 objects across
  30+ types against a live grid, verify counts via WAPI, and clean up on request.

### Extensibility

- **`@command` decorator** - adding a new command is a single Python decorator plus a handler function; the parser,
  tab-completion, and help pipeline pick it up automatically.
- **Per-domain modules** in `src/ibcli/commands/` keep each subject area isolated.

---

## Install

### From PyPI

```bash
pip install ibcli
```

That is everything: [`ibx-nios-sdk`](https://github.com/Infoblox-PS/ibx-nios-sdk) 1.0.0 or newer is a declared
dependency and comes with it. ibcli still checks the SDK version at startup and exits with an explanatory message
if an environment somehow has one that is too old.

### From source

```bash
git clone https://github.com/Infoblox-PS/ibcli.git
cd ibcli
pip install -e .
# or, for development (pytest + lint tooling):
pip install --group dev -e .     # pip 25.1+; otherwise: poetry install --with dev
```

`dev` and `lint` are PEP 735 dependency groups, not extras, so `pip install -e '.[dev]'` does not
install them - older pip versions only warn about the unknown extra and carry on with nothing added.

### With Poetry

Poetry 2.0+ reads the PEP 621 `[project]` metadata directly, so there's nothing Poetry-specific in `pyproject.toml` -
just point Poetry at the repo:

```bash
git clone https://github.com/Infoblox-PS/ibcli.git
cd ibcli
poetry install               # creates .venv, installs deps, writes poetry.lock
poetry run ibcli --help      # invoke without activating the venv
```

Python 3.11 or newer is required. The runtime dependencies are `ibx-nios-sdk` and `prompt_toolkit`; `httpx`
arrives with the SDK.

---

## Quick start

```bash
# Grid coordinates (adapt to your environment)
export GRID=gm.corp.example
export USER=admin
export PASSWORD='change-me'

# One-shot command
ibcli -s "$GRID" -u "$USER" -p "$PASSWORD" -k -e "show grid"

# Interactive REPL (TLS verification disabled for a lab grid with -k)
ibcli -s "$GRID" -u "$USER" -p "$PASSWORD" -k
```

**Common flags**

| Flag | Purpose |
|---|---|
| `-s <host>` | Grid master IP or FQDN |
| `-u <user>` / `-p <pw>` | Credentials |
| `-k / --insecure` | Skip TLS certificate verification |
| `-e "<cmd>"` | Run one command and exit |
| `<file.ibcli> ...` | Batch-execute one or more script files (positional) |
| `-i / --idempotent` | Treat "already exists" conflicts as Skipped |
| `-d <0-5>` | Debug-level output |
| `-l` | List all registered commands and exit |
| `--wapi-version <v>` | Override auto-detected WAPI version |

---

## Interactive REPL

```
$ ibcli -s gm.corp.example -u admin -p 'secret' -k

admin@gm.corp.example > show grid
name: corp-grid  ref: grid/b25lLmNsdXN0ZXIkMA:corp-grid

admin@gm.corp.example > show memb                                 # tab
admin@gm.corp.example > show member                               # abbrev expansion
host_name=gm.corp.example  address=10.0.1.1 platform=VNIOS hwmodel=IB-V1425
host_name=ns1.corp.example address=10.0.1.2 platform=VNIOS hwmodel=IB-V1425
...

admin@gm.corp.example > co z a corp.example.com
                        # tab: configure zone add corp.example.com
                        # dropdown shows "<cr>  set  view=<name>  comment=<comment>"
admin@gm.corp.example > configure zone add corp.example.com view=Internal
  OK: configure zone add corp.example.com view Internal

admin@gm.corp.example > exit
```

Line continuation with `\`:

```
admin@gm.corp.example > configure grid Migration member add ibdns07.corp.example \
...                       ipaddress=10.0.1.27/24 gateway=10.0.1.1 \
...                       platform=VNIOS hwtype=IB-V1425 license=dns license=nios
  Added member ibdns07.corp.example
  Pre-provisioned ibdns07.corp.example
```

---

## Batch mode

Create a script (idempotency-friendly - re-runs are safe with `-i`):

```ibcli
# provision.ibcli - sample grid buildout
configure grid Migration member add ibdns01.corp.example \
    ipaddress=10.0.1.11/24 gateway=10.0.1.1 platform=VNIOS hwtype=IB-V1425 \
    license=dns license=nios license=enterprise

configure network add 10.10.0.0/24 member ibdhcp01.corp.example
configure network 10.10.0.0/24 range add 10.10.0.100 10.10.0.200

configure zone add corp.example.com view=Internal
configure zone corp.example.com add host web01 10.10.0.50 alias=www
configure zone corp.example.com add a api 10.10.0.60
configure zone corp.example.com add mx mail mail.corp.example.com 10
```

Run it:

```bash
ibcli -s gm.corp.example -u admin -p 'secret' -k -i provision.ibcli
```

Idempotent mode (`-i`) converts NIOS "already exists" errors into `Skipped` lines, so the same script can safely bring a
grid from scratch to steady state or reconcile drift.

---

## Architecture

```
src/ibcli/
├── cli.py              CLI entry - argv parsing, session bring-up, dispatch mode
├── dispatcher.py       Routes parsed tokens → handlers; error unwrap; idempotent
├── parser.py           Tokeniser + abbreviation engine + grammar tree walker
├── completer.py        prompt_toolkit integration - feeds REPL tab completion
├── registry.py         @command / register() decorators; SPECOPS regex table
├── context.py          Per-session state (client, host, user, caches, idempotent)
├── completions.py      Dynamic completions (members, zones, views) from the grid
├── utils.py            CIDR normalisation, arpa conversion, pydantic-to-dict
├── debug.py            Debug-level logging
└── commands/
    ├── zone.py            Authoritative zones + classic records (A/AAAA/CNAME/MX/TXT/PTR)
    ├── zone_modern.py     Phase-3 DNS records (CAA, DNAME, ALIAS, NS, NAPTR, TLSA, HTTPS, SVCB, shared records)
    ├── dns.py             DDNS principal clusters, DNS64, RPZ order, all-records aggregator
    ├── network.py         Networks (v4+v6), containers, shared networks, move/modify/delete
    ├── ipam.py            IPv4/IPv6 address inventory, network views, VLAN, superhosts, bulkhosts
    ├── dhcp.py            Ranges, fixed, MAC filters, option spaces, IPv6 DHCP, all 5 filter types
    ├── grid.py            Members, licensing, DNS/DHCP enable, HA, pre-provisioning, restart
    ├── grid_ext.py        Grid DNS/DHCP properties, threat feeds, file distribution, GMC
    ├── admin.py           Admin users/groups/roles, RADIUS legacy objects
    ├── auth.py            Authentication services (LDAP, AD, RADIUS, TACACS+, SAML, cert, policy)
    ├── auth_ext.py        Approval workflow, FTP/SNMP users, parental control, HSM, CA certs
    ├── cert.py            Member certificates, CSR, self-signed, upload/download
    ├── dtc.py             DTC servers/pools/LBDNs/monitors/topology/record-types
    ├── rpz.py             RPZ zones + records (A, CNAME, TXT, IP-address, client-IP, …)
    ├── notify.py          Notification endpoints + rules + templates; ACLs
    ├── ops.py             DB snapshot, CSV tasks, scavenging, capacity, integrations, BFD, TFTP, rulesets
    ├── fileops.py         Upload/download - CSV, backups, support bundles, per-member dumps
    ├── discovery.py       Network discovery, SDN networks, vDiscovery jobs
    ├── ea.py              Extensible Attribute definitions
    ├── ms.py              Microsoft DNS/DHCP integration
    ├── threat.py          Threat Insight, ADP, analytics
    ├── upgrade.py         Upgrade groups, schedules, status (grid/group/vnode/pnode)
    ├── template.py        Network and range templates
    ├── system.py          help / show debug / top-level housekeeping
    └── server.py          configure server / master - grid connect commands

scripts/
├── sweep-show.sh           Live-grid sweep of every no-arg `show` command
└── smoke/
    ├── smoke.sh            Orchestrator: --build / --verify / --teardown / --all
    ├── build.py            Generate smoke-build.ibcli (tiny/small/full scale)
    ├── verify.py           Count objects via WAPI, compare to expected
    └── teardown.py         Generate reverse-dependency delete script

tests/                      3,284 unit tests (mocked WAPI via httpx.MockTransport)
```

The `parser.py` abbreviation engine does the heavy UX lifting: it builds a dictionary of every unambiguous prefix at
each grammar node and resolves typed input to the canonical command, returning a positional `^---` marker on ambiguity
or unknown-word errors.

The `registry.py` module exposes `@command(match_line, words=..., help=...)` and `register(match_line, words=...,
help=...)` - the former for leaf handlers, the latter for intermediate waypoints. Both merge into `COMMANDS`, a single
dict keyed by canonical match-line.

---

## Tooling

### Live-grid sweep

```bash
scripts/sweep-show.sh -s <host> -u <user> -p <pw>
```

Generates the full list of no-arg `show` commands from `ibcli -l`, runs them all against the grid, and classifies each
error:

- **friendly usage** - our own `"Error: X required (usage: …)"` for commands that need an arg; expected, not a bug
- **grid-config** - feature disabled, service offline, object type missing in the running WAPI version
- **suspected CLI bug** - everything else; exit code 1

Artifacts (per-command preview, raw output, summary TSV, human-readable report) land in a per-run `mktemp` dir,
overridable with `-o <dir>`. Ideal as a CI gate after WAPI-surface changes.

### Smoke harness

```bash
scripts/smoke/smoke.sh -s <host> -u <user> -p <pw> --scale full --tag v1 --all
```

Parameterised build / verify / teardown across three scales:

| Scale   | Objects   | Use case                                    |
|---------|-----------|---------------------------------------------|
| `tiny`  | ~100      | Plumbing smoke - "does each phase run?"     |
| `small` | ~1,000    | Quick regression after a WAPI-surface change |
| `full`  | ~10,000   | Stress + full-surface coverage              |

Ten phases, individually selectable via `--phases 3,4`:

1. Members (pre-provisioned on a dedicated subnet)
2. Infrastructure - views, NS groups, ACLs, EA definitions
3. DHCP - networks (v4+v6), ranges, fixed, MAC filters, failover
4. DNS zones - forward + reverse
5. DNS records - A/AAAA/CNAME/MX/TXT/CAA/NAPTR/TLSA per zone
6. Host records + shared record groups
7. RPZ zones + records
8. DTC - servers, pools, LBDNs, monitors (HTTP/ICMP/TCP)
9. Admin users, groups, roles
10. DHCP extras - option spaces, filters (option/nac/ipv6option/relayagent), network/range templates
11. Notification endpoints

All smoke objects carry a `smoke-` name prefix; ones that support EAs additionally carry `Smoke=<tag>`. Teardown is
opt-in (`--teardown` / `--all`), reverse-dependency ordered, and cascades through zone-deletes so per-record cleanup is
implicit.

---

## Testing

### Mocked suite

The primary test suite runs entirely against a mocked WAPI using `httpx.MockTransport`. No grid access required.

```bash
pytest                    # 3,284 tests, ~9 seconds
pytest -k "zone"          # subset by name
pytest --cov              # with coverage (~93%)
```

### Live-grid smoke

```bash
scripts/sweep-show.sh -s <lab-grid> -u admin -p <pw>   # show-command sweep
scripts/smoke/smoke.sh  -s <lab-grid> -u admin -p <pw> --scale tiny --all
```

### Integration tests

Gated behind environment variables, skipped automatically when unset:

```bash
export IBCLI_TEST_GRID=192.0.2.10
export IBCLI_TEST_USER=admin
export IBCLI_TEST_PASS='change-me'
pytest tests/integration -v
```

The integration suite locks in NIOS-specific behavioural contracts (fileop content-type, pre-provisioning two-step,
license case sensitivity, failover-by-FQDN, dict-vs-string ref returns) that the mocked suite cannot catch.

> **Warning**: the integration tests and the smoke harness make live changes. Point them at a dedicated test grid,
> never production.

See [`docs/development/testing.md`](docs/development/testing.md) for the full breakdown.

---

## Documentation

Full docs are published at **[https://infoblox-ps.github.io/ibcli/](https://infoblox-ps.github.io/ibcli/)**.

| Section | Contents |
|---|---|
| **Getting Started** | Installation, first connection, tab-completion tour |
| **User Guide** | Invocation modes, REPL, aliases, batch mode, extensible attributes |
| **Commands** | Per-domain reference (`docs/commands/`), plus the [Cookbook](docs/commands/cookbook.md) cheat-sheet |
| **Reference** | WAPI endpoint mapping, parser internals, CLI flags, troubleshooting, real-grid status matrix |
| **Development** | Architecture deep-dive, adding commands, testing workflow, known NIOS quirks |

**Quick reference**: the [Commands Cookbook](docs/commands/cookbook.md) is the fastest way in - copy-pasteable recipes
for the common jobs (member add with dual-stack, MGMT interfaces, DHCP enable/disable per protocol, anycast loopbacks,
DTC wiring, batch idempotency, DNS cleanup).

---

## Contributing

Contributions are welcome. A few house rules:

1. **Mocked tests alone aren't enough.** If your change touches a WAPI request body, response parser, or endpoint path,
   add (or run) an integration test against a real grid before merging. Every real-grid bug this project has ever hit
   passed the mocked suite.
2. **Smoke-test breaking grammar changes.** If you modify a command shape, run `scripts/sweep-show.sh` against a lab
   grid and post the summary in the PR description.
3. **Update CHANGELOG.md** - under `## [Unreleased]` with `Added` / `Changed` / `Removed` / `Fixed` sections.
4. **Keep commands in their domain module.** New DNS record types go in `zone.py` or `zone_modern.py`; new DHCP shapes
   in `dhcp.py`. Cross-domain helpers live in `utils.py`.

See [`docs/development/`](https://infoblox-ps.github.io/ibcli/development/) for the full architecture guide and the
`@command` / `register()` pattern.

Bug reports and feature requests: [issue tracker](https://github.com/Infoblox-PS/ibcli/issues).

---

## Related

- [`ibx-nios-sdk`](https://github.com/Infoblox-PS/ibx-nios-sdk) - the Infoblox-published async Python SDK that ibcli
  sits on top of.
- [Infoblox NIOS WAPI documentation](https://docs.infoblox.com/) - object schemas and field semantics.
- Perl `ibcli` - the original tool this project ports. The command vocabulary and abbreviation UX are inherited from it;
  the implementation is entirely new.

---

## Trademarks

INFOBLOX is a trademark of Infoblox Inc. or its affiliated companies, registered in the United States and other
countries. Infoblox Grid is a trademark of Infoblox Inc. NIOS and other product names used here are marks of
Infoblox Inc. or its affiliated companies, used descriptively to identify the products this tool operates against.

## License

GNU General Public License v3.0 or later - see [LICENSE](LICENSE).

ibcli is free software: you may redistribute and modify it under the terms of the GPL. It
comes with **no warranty**. Run `ibcli --license` for the full notice.

Note that the GPL is a copyleft license: if you distribute a modified version, or software that
incorporates this code, that work must also be released under the GPL. Simply *using* the CLI to
manage a grid places no obligation on you.
