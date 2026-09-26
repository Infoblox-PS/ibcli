# Known Quirks

This page documents parser edge cases, depth limits, and other non-obvious behaviours in the Python port.

## Pagination is transparent - no silent truncation

**What it is:** All `show *` commands that list objects (e.g., `show zone`, `show network`, `show record`) iterate an
`ibx-nios-sdk` resource `.list()`, which follows the WAPI `_paging`/`next_page_id` protocol automatically. Every page
is fetched and merged before output is displayed.

**Why it matters:** A single unpaged request which NIOS caps at 1000 objects by default. On grids with more than 1000
objects of a given type, the old behaviour would return exactly 1000 results with no warning. This silent truncation
could cause `show zone` on a large production grid to appear complete when it was not.

**Current behaviour:** No silent truncation. If a grid has 5000 networks, `show network` will issue as many paged
requests as needed and display all 5000. The only observable side effect is that large grids take longer to respond.
Use a specific filter to narrow results:

```
show network 10.0.0.0/8
show zone corp.example
```

**Affected commands:** All list-mode `show` commands. Single-object lookups (e.g., `show zone example.com`) are unaffected - they never needed pagination.

---

## Set-chain depth cap

**What it is:** The `set key value` pattern for extensible attributes is implemented via a static chain of
`register()` calls in each command module. The chain is registered to depth 16 - meaning up to 16 `set key value`
pairs per command.

**Why:** The `COMMANDS` dict is flat and keyed by the full match-line string. To support `set key value` at arbitrary
depth, the module registers depths 1..16 up front (each depth costs ~3 entries per endpoint). 16 was chosen as a
practical limit that covers any realistic EA load with negligible overhead (`COMMANDS` has ~2,300 entries total).

**Effect:** A command with more than 16 `set key value` pairs:

```
configure zone add example.com set k1 v1 ... set k17 v17
```

will fail at the 17th `set` with:

```
                                                             ^--- Unknown argument at marker
```

**Workaround:** Split across two commands:

```
configure zone add example.com set k1 v1 ... set k16 v16
configure zone example.com modify set k17 v17 ...
```

Or just bump the `range(16)` / `range(1, 17)` constants in `src/ibcli/commands/*.py` and re-run the tests.

**Affected commands:** `configure zone add`, `configure zone modify`, `configure zone <z> add host`, `configure
network add`, `configure network modify`, `configure network container add/modify`, `configure template network add`.

---

## Tokenizer `key=value` splitting

**What it is:** The tokenizer (`parser._tokenize`) splits bare `key=value` tokens on the first `=`:

```
configure zone add example.com comment=hello
→ tokens: ["configure", "zone", "add", "example.com", "comment", "hello"]
```

**Why:** The Perl original used the same two-token convention, and the word list registers `key=<special>` pairs that expand into two-token contexts.

**Effect 1 - Values containing `=`:** A value like `Owner=alice` typed as `set Owner=alice` is split into `set`,
`Owner`, `alice`. This is correct. But a value that contains `=` in the value itself (e.g., a base64 string) must be
quoted:

```
# Wrong - splits on first = in value
set checksum=abc=def

# Correct - quoted
set checksum "abc=def"
```

**Effect 2 - `<name=value>` SPECOPS never fires:** The `<name=value>` SPECOPS token (regex `^\S+=\S+$`) is in the
registry for completeness but effectively never matches in normal user input, because the tokenizer splits the token
before the parser sees it. Direct programmatic calls to `expand_word` with a `key=value` string will match
`<name=value>`.

---

## IPv4 vs IPv6 routing

**What it is:** Several commands accept `<n.n.n.n/mm>` as a CIDR argument. The SPECOPS regex for this token accepts
both IPv4 CIDRs (`10.0.0.0/8`) and IPv6 CIDRs (`2001:db8::/32`). The address family is detected at the handler level
using `cidr_family()` from `utils.py`.

**Effect:** The tab-completion menu shows `<n.n.n.n/mm>` for both IPv4 and IPv6 inputs. There is no separate `<ipv6/prefix>` token - the single token covers both families.

IPv6 is routed to `ipv6network`, `ipv6networkcontainer`, etc. automatically. No user action is needed.

---

## Reverse-zone CIDR auto-conversion

**What it is:** When a zone name looks like an IPv4 CIDR (e.g., `192.168.1.0/24`), ibcli converts it to arpa form before sending to WAPI:

```
192.168.1.0/24  →  1.168.192.in-addr.arpa
```

**Where:** In `zone.py`'s `cli_add_zone`, `cli_show_zone`, `cli_modify_zone`, and `cli_delete_zone`, using `net_to_arpa()` from `utils.py`.

**Why:** WAPI expects arpa form; the Perl tool accepted CIDR form as a convenience.

---

## Zone type fallback order

**What it is:** When `show zone` or `configure zone <z> delete/modify` is called without explicit type keywords, ibcli
searches zone types in the order: `zone_auth` → `zone_forward` → `zone_delegated` → `zone_stub`.

**Effect:** If a zone exists in two types with the same FQDN (unusual but possible), the `zone_auth` entry is always
found first. To target a specific type, use the appropriate keyword (`forward`, `delegate_to=`, etc.).

---

## ~~`configure server` always uses `verify=False`~~ (fixed)

**What it was:** `cli_add_server` hardcoded `verify=False`, and the
`-k`/`--insecure` flag never reached it - so TLS verification was always
off regardless of the flag, and the flag itself was inert.

**Now:** `-k` sets `ctx.verify`, which `cli_add_server` passes to
`NiosClient(verify=...)`. TLS is verified by default; `-k` opts out. The
same change wired up `--wapi-version`, which was also parsed and ignored.

---

## Pre-provisioning members needs a valid grid-wide licence

**What it is:** `configure grid <name> member add ...` fails with:

```
Error: The master does not have a valid Grid license installed for the member <ip>.
```

This is NIOS refusing to admit *any* new member, not a CLI or SDK problem -
a bare `POST /wapi/v2.14/member` with no `pre_provisioning` block at all
fails identically. The IP quoted in the message is NIOS-internal and does
not correspond to the address you submitted, which makes the error look
like a client bug when it is not.

**How to confirm it is licensing:** check the master's own licences and
their expiry. On an HA pair each node has its own bundle, and one expired
node is enough to fail the check:

```bash
curl -sk -u admin:PASS "https://<gm>/wapi/v2.14/member:license?_return_fields=type,hwid,expiry_date"
curl -sk -u admin:PASS "https://<gm>/wapi/v2.14/license:gridwide"
```

A `GRID` entry whose `expiry_date` is in the past - or an empty
`license:gridwide` - explains the refusal. Install a current licence on the
master; there is no client-side workaround.

**Unaffected:** enabling DNS and DHCP *services* on members that already
exist (`configure grid <name> member <fqdn> dns enable`,
`... dhcp enable ipv4`) works normally - that is a service toggle, not
member admission.

---

## Some operations are refused before they reach the grid

**What it is:** NIOS restricts read/create/update/delete per object type.
Since ibx-nios-sdk 0.2.0 the SDK knows the table and refuses locally:

```
show dtc
  Error: WAPI object type 'dtc' does not support read;
         re-run with --allow-restricted to send it anyway
```

This is the same verdict the grid gives - `Operation read not allowed for
dtc` - just delivered without a round trip. Confirmed against NIOS 9.1 for
every affected command, by calling the raw WAPI endpoint directly.

Affected commands, and the operation NIOS forbids:

| Command | Object type | Op |
|---|---|---|
| `show dtc` | `dtc` | read |
| `show deleted_objects` | `deleted_objects` | read |
| `show network_discovery` | `network_discovery` | read |
| `configure license_gridwide add` | `license:gridwide` | create |
| `configure grid <n> member <m> license add` | `member:license` | create |
| `configure mastergrid add` / `delete` | `mastergrid` | create/delete |
| `configure parental_control subscriber add` / `delete` | `parentalcontrol:subscriber` | create/delete |
| `configure grid certificate delete` | `grid:x509certificate` | delete |
| `configure hostname_policy add` / `delete` | `hostnamerewritepolicy` | create/delete |
| `configure discovery diagnostic start` | `discovery:diagnostictask` | create |
| `restart discovery` | `discoverytask` | create |

**Workaround:** `--allow-restricted` sends the request regardless. The
restriction table was built from a single NIOS build (9.1.0-54969), so a
different version may permit some of these - the flag exists for that case.
On a 9.1 grid the request simply fails at NIOS instead of at the client.

The commands are kept rather than removed (unlike the RADIUS ones, whose
object types no longer exist at all) because the restriction is
version-specific, not absolute.

---

## WAPI functions look like model fields

**What it is:** `ibx-nios-sdk` declares callable WAPI operations - `upgrade`,
`restartservices`, `empty_recycle_bin`, `run_scavenging`, `task_control` and
46 others across 10 models - as pydantic fields annotated `object | None`,
and does not list them in `READONLY_FIELDS`.

They are neither settable nor readable. Requesting one as a return field
makes NIOS answer with an internal error such as
`.com.infoblox.one.cluster has no member .reqversion`.

**How ibcli handles it:** anything annotated `object | None` is treated as a
function and excluded from `set <key>=<value>` completions and from the deep
sweep's field list (`_is_wapi_function` in `completions_keys.py`). Real data
fields always carry a concrete annotation, so the bare `object` type is a
reliable marker. Call these through their own commands
(`restart …`, `upgrade …`) instead.

---

## SDK model mismatches on some NIOS versions

**What it is:** `ibx-nios-sdk` pins a hand-written pydantic model per WAPI
object. Where a model's type disagrees with what a given NIOS build actually
returns, the response fails to deserialise:

```
show grid fields=restart_status
  Error: ValidationError: the SDK model for Grid does not match what this
  grid returned: restart_status (string_type). …
```

Known case, now fixed: `Grid.restart_status` was typed `str | None` in
ibx-nios-sdk 0.1.1 while NIOS 9.1 answers with a `grid:servicerestart:status`
struct. Resolved by pinning the SDK to v0.1.6, whose models were corrected
against a live 9.1 grid. The pin matters - an unpinned `git+…` dependency
keeps whatever was installed first and will silently drift back.

**Workaround:** drop the offending field from `fields=`. The rest of the
command works - only the named field is unparseable. The fix belongs
upstream in the SDK model.

**How to find more:** the deep field sweep asks for every SDK-declared field
on every `show` command and reports what the grid rejects or fails to parse:

```bash
scripts/sweep-show.sh -s <gm> -u admin -p <pw> --deep
```

---

## Write-only fields are not readable

`secret`, `old_password` and `execute_now` exist on their models - you can
set them - but NIOS refuses to return them (`Field is not readable: secret`).
They are excluded from the deep sweep's field list rather than reported as
findings each run.

---

## `help all` points to the docs site

**What it is:** `help all` prints:

```
See https://infoblox-ps.github.io/ibcli/ for full documentation.
```

The string is hard-coded in `src/ibcli/commands/system.py`. If the docs
ever move, update it there.

---

## `backup_file` flag exits with code 2

**What it is:** Passing `-b` or `-f` to the Python port exits immediately with code 2 and an error message. Scripts that check for non-zero exit codes will detect this as a failure.

The Perl version silently opened a backup file browser. The Python port does not implement this feature.
