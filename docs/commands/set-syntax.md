# `configure ... set` value syntax

Most configuration subtrees in ibcli expose a generic pass-through verb
of the form:

```
configure <subtree> set <key>=<value> [<key>=<value> ...]
```

The handler parses the key/value pairs, coerces each value to a typed
Python / JSON value, and PUTs them against the matching WAPI object.
Multiple pairs in one line go out as a single PUT.

This page documents the value-coercion rules and the tab-completion
helpers that are shared across every `... set` site. They are
implemented in [`src/ibcli/coerce.py`](https://github.com/Infoblox-PS/ibcli/blob/main/src/ibcli/coerce.py)
and [`src/ibcli/completions_keys.py`](https://github.com/Infoblox-PS/ibcli/blob/main/src/ibcli/completions_keys.py).

---

## Value coercion

Rules are applied in order. The first match wins.

| input | becomes | notes |
|---|---|---|
| `true` / `false` (case-insensitive) | Python `bool` | `TRUE`, `False` etc. all work |
| digits (optional leading `-`) | `int` | `42`, `-1`, `0` |
| starts with `{` or `[` | JSON-decoded | fallback to string if JSON invalid |
| ACL shortcut (see below) | `list[dict]` of addressac / ref entries | for allow_query / allow_transfer / … |
| anything else | `str` | left unchanged |

### ACL shortcut

WAPI ACL-style fields (`allow_query`, `allow_transfer`, `allow_update`, …)
expect a list of structured entries like:

```json
[
  {"address": "10.0.0.0/8", "permission": "ALLOW", "_struct": "addressac"},
  {"_ref": "namedacl/..:trusted"}
]
```

Instead of typing that, you can use a comma-separated shortcut:

```
<PERM>:<cidr>[,<PERM>:<cidr>...]
acl:<ref>
```

Examples:

```
allow_query=ALLOW:10.0.0.0/8
allow_query=DENY:192.168.0.0/16
allow_query=ALLOW:10.0.0.0/8,DENY:192.168.0.0/16
allow_query=10.0.0.0/8                              # permission defaults to ALLOW
allow_query=ALLOW:10.0.0.0/8,acl:namedacl/..:trusted
allow_query=[]                                      # clear the list
```

Permissions are case-insensitive. Both IPv4 and IPv6 CIDRs are accepted.
If a value doesn't match the shortcut pattern it falls through to the
string rule (so plain string fields still work).

### JSON fallback

When a field needs a shape the shortcut can't express - e.g. TSIG keys,
forwarders with names and addresses, DHCP option lists - pass JSON:

```
# struct
configure grid Infoblox dhcp set gss_tsig_keys={"name":"k1","algorithm":"HMAC-SHA1","secret":"..."}

# struct list
configure grid Infoblox dns set forwarders=[{"name":"ns1","address":"10.0.0.1"},{"name":"ns2","address":"10.0.0.2"}]
```

!!! warning "No whitespace inside JSON"
    The inline-kv parser splits on whitespace, so compact JSON (no
    spaces) is required. Pretty-printed JSON will break.

!!! warning "Shell quoting"
    On bash/zsh, braces and quotes need shell-level escaping - usually
    easiest to wrap the whole `-e` argument in single quotes:

    ```
    poetry run ibcli -s <grid> -u <user> -p <pw> -k \
        -e 'configure grid Infoblox dns set allow_query=ALLOW:10.0.0.0/8'
    ```

    Inside the REPL no extra quoting is needed.

---

## Discovering valid keys

Every `… set` verb has two aids:

1. **Tab completion.** Hit `Tab` after the `set ` and you'll get every
   writable field as a `name=` completion, with its type as metadata
   (`true/false`, `number`, `text list`, enum choices, etc.). Type a
   prefix like `enable_` and the list filters to match.

2. **`… keys` helper (grid only).** For the grid-level service verbs,
   ibcli also exposes:

   ```
   show grid <name> dns keys
   show grid <name> dhcp keys
   show grid <name> threat_insight keys
   show grid <name> threat_protection keys
   show grid <name> file_distribution keys
   ```

   which prints a full alphabetical table of writable fields with types.

Both are driven by the SDK's pydantic models, so the list tracks the
WAPI version the SDK is pinned against.

### Type labels

The metadata shown in the dropdown (and the `… keys` table) uses these
ops-friendly labels rather than raw Python type hints:

| label | meaning |
|---|---|
| `true/false` | boolean |
| `number` | integer |
| `text` | string |
| `text list` | list of strings (repeat the key, or JSON-encode) |
| `A\|B\|C` | enum - one of these literal choices |
| `A\|B\|C list` | list whose entries are one of the choices |
| `extattrs map` | Extensible Attribute map - pass as JSON |
| `struct` | nested object - pass as JSON |
| `struct list` | list of nested objects - pass as JSON or use ACL shortcut |
| `<ClassName>` / `<ClassName> list` | custom pydantic sub-model - pass as JSON |

---

## Where this applies

Every verb in the table below accepts the syntax above. Tab completion
is wired on all of them.

| subtree | verb | WAPI target |
|---|---|---|
| **grid-wide** | `configure grid <g> dns set` | `grid:dns` |
| | `configure grid <g> dhcp set` | `grid:dhcpproperties` |
| | `configure grid <g> threat_insight set` | `grid:threatinsight` |
| | `configure grid <g> threat_protection set` | `grid:threatprotection` |
| | `configure grid <g> file_distribution set` | `grid:filedistribution` |
| **per-member** | `configure grid <g> member <m> dns set` | `member:dns` |
| | `configure grid <g> member <m> dhcp set` | `member:dhcpproperties` |
| | `configure grid <g> member <m> threat_insight set` | `member:threatinsight` |
| | `configure grid <g> member <m> threat_protection set` | `member:threatprotection` |
| | `configure grid <g> member <m> file_distribution set` | `member:filedistribution` |
| **ACL** | `configure acl <name> set` | `namedacl` |
| **notifications** | `configure notification endpoint <name> set` | `notification:rest:endpoint` |
| | `configure notification template <name> set` | `notification:rest:template` |
| | `configure notification rule <name> set` | `notification:rule` |
| **DTC** | `configure dtc set` | `dtc` |
| | `configure dtc server <name> set` | `dtc:server` |
| | `configure dtc pool <name> set` | `dtc:pool` |
| | `configure dtc lbdn <name> set` | `dtc:lbdn` |
| | `configure dtc topology <name> set` | `dtc:topology` |
| | `configure dtc monitor {http,icmp,tcp,snmp,sip,pdp} <name> set` | `dtc:monitor:<proto>` |
| **discovery** | `configure discovery credential_group <name> set` | `discovery:credentialgroup` |
| | `configure discovery grid_properties set` | `discovery:gridproperties` |
| | `configure discovery member_properties <name> set` | `discovery:memberproperties` |
| **MS server** | `configure ms_server <ip> set` | `msserver` |
| | `configure ms_server <ip> dhcp set` | `msserver:dhcp` |
| | `configure ms_server <ip> dns set` | `msserver:dns` |
| | `configure ms_superscope <name> set` | `mssuperscope` |
| **upgrade** | `configure upgrade_group <name> set` | `upgradegroup` |
| | `configure upgrade_schedule set` | `upgradeschedule` |
| | `configure distribution_schedule set` | `distributionschedule` |
| **integrations** | `configure integration taxii <name> set` | `taxii` |
| | `configure integration outbound <name> set` | `outboundcloudclient` |
