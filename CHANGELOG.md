# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic
Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [1.0.0] - 2026-09-26

First public release.

ibcli is an async Python CLI for Infoblox NIOS. It speaks the WAPI through `ibx-nios-sdk` and covers DNS, IPAM,
DHCP, grid administration, DTC, certificates, bulk data and service control from one prompt. Python 3.11 or newer;
`ibx-nios-sdk` 0.2.0 or newer is a prerequisite.

### Interface

- **REPL** with an abbreviation engine: any unambiguous prefix of a keyword is accepted at every position, so
  `co n a 192.0.2.0/24` is `configure network add 192.0.2.0/24`. Line continuation, persistent history in
  `~/.ibcli_history`, and standard key bindings.
- **Dynamic tab completion** that resolves live NIOS object names on first Tab - grid members, views, zones,
  networks, NS groups, named ACLs, failover groups, DTC servers, pools, LBDNs and per-protocol monitors.
  `configure server` primes the member cache at connect time so the first Tab is immediate. Roughly 350 waypoints
  carry dropdown help so every level of the tree describes itself.
- **Batch mode** for command files, `-e` for a single command, and `.ibcli.cf` auto-loaded at startup.
- **`-i` / `--idempotent`** demotes genuine "already exists" conflicts to `Skipped:` so batch scripts re-run
  cleanly, while a real HTTP 409 still counts as a failure.
- A uniform `OK:` line confirms mutating commands that produce no output of their own; read-only commands stay
  silent.
- **`-d` tracing** at three levels: dispatch, httpx request logging, and the SDK's own DEBUG records. At `-d 3` an
  unexpected exception is re-raised with its traceback; lower levels trace only and never turn a handler bug into a
  dead REPL.
- **`--timeout <seconds>`** (default 30) raises the per-request WAPI timeout, which grid-wide aggregations on a
  populated grid can exceed.
- `-k` / `--insecure` for the self-signed certificates most grids present, and `--wapi-version` to pin the
  negotiated version.

### DNS

- CRUD for `zone_auth`, `zone_forward`, `zone_delegated` and `zone_stub`, and for A, AAAA, CNAME, MX, PTR, TXT and
  HOST records.
- **DNSSEC operations**: `configure zone <zone> dnssec sign|unsign|rollover_ksk|rollover_zsk`.
- **Zone copy** clones records between zones, with `view=` and `source_view=` support.
- **Host rename** preserves addresses, aliases, extensible attributes and comment.
- **Incremental host modify** with `add-alias` / `remove-alias`, `add-ip` / `remove-ip`, `add-ipv6` /
  `remove-ipv6`, `comment=` and `disable=`, read-only fields stripped on the way through.
- **AXFR import** via `configure zone add <zone> import_from=<ip>`, with optional host abstraction and PTR
  creation.
- Response policy zones and RPZ records.

### IPAM and DHCP

- IPv4 and IPv6 networks and network containers, shared networks, templates, split, move, and IPAM
  `next_available` allocation.
- Ranges including in-place `range modify`, which makes a `failover=` swap a single command rather than a delete,
  move and add sequence.
- Fixed addresses, MAC filters, failover associations, option spaces, and lease inspection.
- Relay agent filters across the full WAPI field set - circuit ID and remote ID names, substring matching, offsets
  and lengths.
- Network extensible attributes with `extattrs set|delete`, merging with what is already there and accepting
  quoted names.
- `show address` and `show address ipv6` surface the aggregator's `types` and `usage` fields.

### Grid

- **Member provisioning and pre-provisioning**, including HA pairs, `master_candidate=`, dual-stack
  (`ipv6addr=` sets `config_addr_type` automatically), MGMT and LAN2 interfaces, 802.1Q VLAN tagging, port
  redundancy and default-route failover. Verified end to end against NIOS 9.x.
- **Adaptive pre-provisioning**: the CLI reads the target grid's `member` schema and drops `hardware_info` fields
  it does not accept, because an unknown field aborts the request and rolls the new member back.
- **Anycast loopbacks** with `member <fqdn> anycast add|delete`, defaulting to /32 and /128. Known NIOS
  preconditions surface as `Deferred:` rather than `Error:`.
- Per-protocol DHCP service control: `member <fqdn> dhcp enable|disable [ipv4|ipv6|both]`.
- Views, NS groups, shared record groups and scheduled tasks.
- **Service restarts** with mode, option, member selection and delay, plus absolute scheduling via
  `at=<iso8601|epoch>` and `restart status`.
- `show upgrade_status group` reports member rollout progress and step counts.
- `show db_objects` accepts `object_types=` and `version=`.

### DTC

- Pool, server, monitor and LBDN wiring: `dtc pool <name> server add|delete`,
  `dtc pool <name> monitor add|delete <proto> <name>`, and `dtc lbdn <name> pool add|delete <pool>`.

### Administration and security

- Admin users, groups, roles and permissions; RADIUS users and devices.
- Certificates: download, upload, generate self-signed, and generate a CSR.
- Notification endpoints and rules, including `outbound_member_type=` and endpoint name resolution.

### Files and bulk data

- **CSV** export, and import with operation modes (`INSERT`, `OVERRIDE`, `MERGE`, `DELETE`, `CUSTOM`), update
  method, error policy, task polling and error-log download.
- Grid backup and restore, log files, support bundles and lease history.
- Per-member `getmemberdata` downloads across every NIOS-supported type, from `dns_conf` and the DNS caches
  through `dhcpv6_conf`, `radius_conf`, `ntp_keys` and `traffic_capture`.
- A dedicated transfer layer for the `http_direct_file_io` protocol the SDK does not model, including the
  `application/force-download` content type NIOS requires on the GET.

### Session handling

- Automatic WAPI version detection, cookie authentication, pagination through `get_paginated`, streaming file I/O,
  and strict TLS verification by default.
- Set-chains of up to 16 key/value pairs per command.

### Documentation and testing

- 3,278 mocked tests that need no grid, plus an env-gated real-grid suite that locks in NIOS-specific quirks.
- **Grammar and documentation guards**: every waypoint word must have a node behind it, every registered handler is
  dispatched against a mock grid, and every command and abbreviation printed in the operator playbook is re-checked
  against the live grammar, so a new sibling command cannot silently make a published abbreviation ambiguous.
- **Live-grid audit tooling** that runs every no-arg `show` command and classifies failures as friendly usage, grid
  configuration or suspected bug.
- **Object-build smoke harness** with parameterised build, verify and teardown of up to ~10,000 objects across 30+
  types at three scales, with reverse-dependency-ordered teardown.
- A full documentation site covering commands, an operator playbook, a cookbook, troubleshooting and development
  guides.

[Unreleased]: https://github.com/Infoblox-PS/ibcli/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Infoblox-PS/ibcli/releases/tag/v1.0.0
