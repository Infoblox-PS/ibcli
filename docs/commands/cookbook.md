# Cookbook

Copy-pasteable command recipes for the common jobs an ibcli operator runs.
Each section lists the command shape (abbreviations are fine - `co g M m a` is
the same as `configure grid <grid> member add`) and, where relevant, notes
what WAPI field the command lands on.

## Conventions

### Placeholders used throughout this page

Anything in angle brackets is a placeholder you substitute with your own
value. The three you'll see most often:

| Placeholder | What to replace with | Example |
|---|---|---|
| `<grid>` | Your NIOS grid name - the string you picked on grid-join, not the master IP. | `Migration` |
| `<fqdn>` | A fully-qualified member host name. | `ibdns01.example.com` |
| `<cidr>` | A CIDR (v4 or v6). | `10.10.1.0/24`, `2001:db8:100:1::/64` |

Commands like `configure grid <grid> member add …` require the grid name verbatim.

Shell snippets additionally assume you've exported three environment
variables identifying your grid - adapt once and the rest of the page is
copy-paste-safe:

```sh
export GRID=grid.example.com       # master IP or DNS name
export USER=admin
export PASSWORD='change-me'
```

---

## Connecting

```sh
# Interactive REPL
ibcli -s "$GRID" -u "$USER" -p "$PASSWORD" -k

# Run a single command and exit
ibcli -s "$GRID" -u "$USER" -p "$PASSWORD" -k -e "show member"

# Batch-process a .ibcli file
ibcli -s "$GRID" -u "$USER" -p "$PASSWORD" -k lab-provision.ibcli

# Same, but treat "already exists" conflicts as skippable - makes a re-run
# land cleanly on a partially-provisioned grid.
ibcli -s "$GRID" -u "$USER" -p "$PASSWORD" -k -i lab-provision.ibcli
```

**Flags worth knowing:**

| Flag | Purpose |
|---|---|
| `-k / --insecure` | Skip TLS verification (lab certs). |
| `-i / --idempotent` | Convert `already exists` conflicts into `Skipped:` warnings. |
| `-e "<cmd>"` | Run one command non-interactively. |
| `-m <ip>` | Set grid master IP (used when connecting via MGMT port). |
| `--wapi-version <ver>` | Override auto-detected WAPI version. |
| `-l` | List every registered match-line and exit. |

**Output conventions** (batch mode):

| Prefix | Meaning |
|---|---|
| `OK:` | Mutating command succeeded; handler had no output of its own. |
| `Skipped:` | `-i` mode: NIOS reported the object already exists. |
| `Deferred:` | Success contingent on grid state that isn't ready yet (e.g. IPv6 loopback waiting for the member). |
| `Error:` | Real failure - stripped of `AdmConDataError: None (…)` wrapper. |

All four prefixes are printed with two leading spaces, so scripts that `grep '  Error:'` still work.

---

## Grid members

### Add a minimal member

```
configure grid <grid> member add ibdns01.example.com \
    ipaddress=192.0.2.101/24 gateway=192.0.2.1 \
    platform=VNIOS hwtype=IB-V1425 \
    license=dns license=nios license=enterprise
```

`license=` repeats; each license appears in the pre-provisioning hardware
spec.

### Add a dual-stack member (IPv4 + IPv6 VIP)

```
configure grid <grid> member add ibdns01.example.com \
    ipaddress=192.0.2.101/24 gateway=192.0.2.1 \
    ipv6addr=2001:db8:64:40::101/64 ipv6gateway=2001:db8:64:40::1 \
    platform=VNIOS hwtype=IB-V1425 \
    license=dns license=nios license=enterprise
```

When `ipv6addr=` is supplied, ibcli automatically sets
`config_addr_type=BOTH` (or `IPV6` if no IPv4) - without that flag NIOS
silently drops `ipv6_setting` on pre-provisioned members.

### Add a member with a MGMT interface (v4 + v6)

```
configure grid <grid> member add ibdns01.example.com \
    ipaddress=192.0.2.101/24 gateway=192.0.2.1 \
    ipv6addr=2001:db8:64:40::101/64 ipv6gateway=2001:db8:64:40::1 \
    mgmt_ipaddress=198.51.100.101/24 mgmt_gateway=198.51.100.1 \
    mgmt_ipv6addr=2001:db8:65:40::101/64 mgmt_ipv6gateway=2001:db8:65:40::1 \
    platform=VNIOS hwtype=IB-V1425 license=dns license=nios license=enterprise
```

MGMT fields land on `node_info[0].mgmt_network_setting` and
`node_info[0].v6_mgmt_network_setting`. The `mgmt_port_setting.enabled` flag
is set to `true` automatically when any MGMT field is supplied.

### Enable DNS / DHCP service on a member

```
configure grid <grid> member ibdns01.example.com dns  enable
configure grid <grid> member ibdns01.example.com dns  disable

configure grid <grid> member ibdhcp01.example.com dhcp enable         # IPv4 only (default)
configure grid <grid> member ibdhcp01.example.com dhcp enable ipv4    # IPv4 only (explicit)
configure grid <grid> member ibdhcp01.example.com dhcp enable ipv6    # IPv6 only
configure grid <grid> member ibdhcp01.example.com dhcp enable both    # IPv4 + IPv6

configure grid <grid> member ibdhcp01.example.com dhcp disable ipv6
```

The `dhcp enable/disable` verb maps to:

| Qualifier | WAPI field toggled |
|---|---|
| `ipv4` (or bare) | `enable_dhcp` |
| `ipv6` | `enable_dhcpv6_service` |
| `both` | both in a single PUT |

### Anycast loopback on a member

```
# Shared DNS anycast address across every DNS member:
configure grid <grid> member ibdns01.example.com anycast add 192.0.2.53
configure grid <grid> member ibdns02.example.com anycast add 192.0.2.53
…

# IPv6 anycast:
configure grid <grid> member ibdns01.example.com anycast add 2001:db8:0:53::53

# Defaults to /32 (v4) or /128 (v6); override with /prefix:
configure grid <grid> member ibdns01.example.com anycast add 192.0.2.0/30

# Removal:
configure grid <grid> member ibdns01.example.com anycast delete 192.0.2.53
```

Each command reads the member's current `additional_ip_list`, appends (or
removes) an interface struct with `interface=LOOPBACK` and `anycast=true`,
and PUTs the full list back.

**IPv6 anycast note:** NIOS requires the member's LAN IPv6 VIP to be live
before it accepts a v6 loopback. On pre-provisioned (not-yet-booted) members
the handler prints `Deferred: v6 anycast <addr> on <member> (waiting for
member to come online with IPv6 LAN)` instead of erroring - re-running once
the member boots will complete it.

---

## Networks and DHCP ranges

### Add a /24 with both DHCP members

```
configure network add 10.10.1.0/24 member 192.0.2.111 member 192.0.2.112
```

### DHCP range bound to a failover group

```
configure network failover add fo-group1 \
    primary ibdhcp01.example.com secondary ibdhcp02.example.com

configure network 10.10.1.0/24 range add 10.10.1.100 10.10.1.200 failover=fo-group1
```

### Swap a range to a different failover group

Previously this required three commands (delete range → move network members →
re-add range). Now it's one:

```
configure network 10.10.4.0/24 range modify 10.10.4.100 10.10.4.200 failover=fo-group2
```

### Set DHCP options on a network

```
configure network 10.10.1.0/24 modify \
    option=routers=10.10.1.1 \
    option=domain-name=example.com \
    option=domain-name-servers=10.10.1.2,10.10.2.2 \
    option=ntp-servers=10.10.1.3 \
    option=Cisco-AP:wlc-address=10.10.99.10,10.10.99.11
```

Space-qualified vendor options use `space:name=value`. To clear every option:
`option=clear`.

### Extensible Attributes on an existing network

```
# Discoverable sibling of `modify set` - specifically for EAs:
configure network 10.10.1.0/24 extattrs set "DC Location" DC1
configure network 10.10.1.0/24 extattrs delete "DC Location"
```

Merges with existing extattrs; accepts quoted EA names with spaces.

---

## DNS zones and records

### Create a zone with an NS group

```
configure nsgroup add ns-group1 \
    primary=ibdns01.example.com \
    secondary=ibdns02.example.com \
    secondary=ibdns03.example.com

configure zone add zone01.example.com ns_group=ns-group1
```

Reverse zones auto-rewrite CIDRs to `in-addr.arpa`/`ip6.arpa`:

```
configure zone add 10.10.1.0/24 ns_group=ns-group1
configure zone add 2001:db8:100:1::/64 ns_group=ns-group1
```

### Add records

```
configure zone zone01.example.com add a     web  10.10.1.10
configure zone zone01.example.com add aaaa  web  2001:db8:100:1::10
configure zone zone01.example.com add cname www  web.zone01.example.com
configure zone zone01.example.com add mx    mail mail.zone01.example.com 10
configure zone zone01.example.com add txt   spf  "v=spf1 mx -all"
configure zone zone01.example.com add host  ns1  10.10.1.1
```

Host records accept multiple IPs, aliases, and host-embedded fixed-addresses:

```
configure zone zone01.example.com add host web01 \
    ip=10.10.1.20 ip=10.10.2.20 ipv6=2001:db8:100:1::20 \
    alias=www.zone01.example.com alias=portal.zone01.example.com \
    fixed mac=aa:bb:cc:00:00:01
```

### Delegation, stub, and forward zones

```
configure zone add child.zone01.example.com \
    delegate_to=ns1,203.0.113.70 delegate_to=ns2,203.0.113.71

configure zone add stub.partner.com       stub_from=ns1,203.0.113.53
configure zone add corp.partner.com       forward_to=ns1,8.8.8.8 forward_to=ns2,8.8.4.4
```

### Views

```
configure view add External comment="External DNS view"
configure zone add ext01.example.net ns_group=ns-external view=External

configure zone ext01.example.net add a web 203.0.113.10 view=External
```

---

## DTC (DNS Traffic Control)

### Build an LBDN from scratch

```
configure dtc server add web1 host=203.0.113.10
configure dtc server add web2 host=203.0.113.20
configure dtc server add web3 host=203.0.113.30

configure dtc monitor icmp add web-icmp
configure dtc monitor http add web-http

configure dtc pool add web-pool lb_preferred_method=round_robin

configure dtc pool web-pool server  add web1
configure dtc pool web-pool server  add web2
configure dtc pool web-pool server  add web3
configure dtc pool web-pool monitor add icmp web-icmp
configure dtc pool web-pool monitor add http web-http

configure dtc lbdn add web-lbdn lb_method=round_robin patterns=www.dtc.example.com

configure dtc lbdn web-lbdn pool add web-pool
```

Each wiring command reads the parent's link array, mutates it, and PUTs it
back. Detach with `server delete`, `monitor delete <proto> <name>`, or
`pool delete`.

---

## Auth services

Handlers fill in NIOS-required defaults (timeout, retries, DC auth_port, etc.)
so minimal commands work against a real grid:

```
configure auth ldap add lab-ldap \
    server=ldap.corp.example.com:636 \
    base_dn="dc=corp,dc=example,dc=com" \
    comment="Lab LDAP"

configure auth ad add lab-ad \
    domain=corp.example.com \
    dc=dc1.corp.example.com dc=dc2.corp.example.com \
    comment="Lab AD"

configure auth radius add lab-radius \
    server=radius.corp.example.com \
    shared_secret=labsecret \
    comment="Lab RADIUS"
```

---

## RPZ

```
configure rpz zone add rpz.lab.local policy=GIVEN comment="Lab RPZ policy zone"

configure rpz record a    add badsite.example.com.rpz.lab.local   127.0.0.1 zone rpz.lab.local
configure rpz record aaaa add badsite6.example.com.rpz.lab.local  ::1       zone rpz.lab.local
```

---

## Named ACLs and grid recursion

```
configure acl add acl-recursion-internal \
    access_list=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16 \
    comment="Networks allowed to recurse via Internal DNS view"

configure grid <grid> dns allow_recursion acl=acl-recursion-internal
# Or without a named ACL:
configure grid <grid> dns allow_recursion any
configure grid <grid> dns allow_recursion ace=10.0.0.0/8 deny_ace=10.99.0.0/16
```

### Inspecting and editing ACLs

```
show acl               # hint line tells you to use `all` or a name
show acl all           # dump every named ACL
show acl <name>        # dump one

# Edit an existing ACL via the generic set verb - uses the ACL
# shortcut syntax (see set-syntax.md):
configure acl <name> set access_list=ALLOW:10.0.0.0/8,DENY:10.99.0.0/16
```

---

## File operations

### Downloads

Per-member dumps (`member=<host_name>` required):

```
download dns_conf            /tmp/dns.cfg   member infoblox.localdomain
download dns_cache           /tmp/dns.cache member ibdns01.example.com
download dns_recursing_cache /tmp/dns.rec   member ibdns01.example.com
download dhcp_conf           /tmp/dhcp.cfg  member ibdhcp01.example.com
download expert_dhcp_conf    /tmp/xdhcp.cfg member ibdhcp01.example.com
download dhcpv6_conf         /tmp/v6.cfg    member ibdhcp01.example.com
download ntp_keys            /tmp/ntp.keys  member ibdns01.example.com
download radius_conf         /tmp/rad.cfg   member infoblox.localdomain
download traffic_capture     /tmp/cap.pcap  member infoblox.localdomain
```

Support bundles and logs:

```
download support_bundle /tmp/sb.tar.gz  member infoblox.localdomain
download log_files      /tmp/logs.tgz syslog  member ibdns01.example.com
download merge_log      /tmp/merge.log
download lease_history  /tmp/leases.csv
```

**Tab-complete the `member` slot.** Pressing `<TAB>` after `member` pulls
live member names from the grid (primed when you connect).

### Uploads

```
upload csv       /tmp/hosts.csv object network
upload database  /tmp/backup.tar.gz
upload expert_dhcp_conf /tmp/xdhcp.cfg member ibdhcp01.example.com
```

---

## Tab completion tips

The completer shows live object names for slots that refer to existing
objects:

| Slot | Completes from |
|---|---|
| `configure zone <TAB>` | existing zones |
| `configure view <TAB>` | existing DNS views |
| `configure network <TAB>` | existing networks |
| `configure dtc pool <TAB>` | existing DTC pools |
| `configure dtc pool <pool> server add <TAB>` | existing DTC servers |
| `configure dtc pool <pool> monitor add <proto> <TAB>` | monitors of that proto |
| `configure dtc lbdn <lbdn> pool add <TAB>` | existing DTC pools |
| `download … member <TAB>` | grid members (host_names) |
| `configure grid <TAB>` | connected grid name (auto-fills if there's only one) |
| `show grid <TAB>` | connected grid name |
| `show acl <TAB>` | `all` + existing named ACLs |
| `show ca_certificate <TAB>` | existing CA certificates |
| `show auth {ldap,ad,radius,tacacs,saml,certificate} <TAB>` | configured auth services of that type |
| `show capacity_report <TAB>` | grid members (hint line lists available members when none given) |
| `configure … set <TAB>` | writable fields of the target WAPI object, with type labels |

Grey `⟨…⟩` entries are slot hints - they tell you what shape of value the
next token should take (IP, CIDR, name, etc.) without inserting anything.

### Discovering writable fields

Every `configure ... set <key>=<value>` pass-through has tab completion for
the key names (with type hints as metadata - `true/false`, `number`,
`text list`, enum choices, etc.). For the grid-wide service verbs there's
also a dedicated helper:

```
show grid <name> dhcp keys
show grid <name> dns keys
show grid <name> threat_insight keys
show grid <name> threat_protection keys
show grid <name> file_distribution keys
```

which prints the full alphabetical table of writable fields and types.

See the [set value syntax reference](set-syntax.md) for the coercion
rules (bool / int / JSON / ACL shortcut) and example invocations.

---

## Idempotency and re-running

Run a provisioning script twice with `-i` and the second run should land
cleanly - every successful mutation from the first run becomes a `Skipped:`
line on the second.

```sh
ibcli -s "$GRID" -u "$USER" -p "$PASSWORD" -k -i lab-provision.ibcli
```

Typical clean second-run breakdown:

```
Error:    0
OK:       N      (the truly-fresh work, usually 0 on a stable grid)
Skipped:  M      (idempotent no-ops - objects already exist)
Deferred: D      (NIOS preconditions not yet met, e.g. v6 loopback on an offline member)
```

---

## Scenarios

End-to-end recipes for common maintenance jobs. Each one composes the
commands above and calls out the gotchas.

## Move a DHCP range from one failover group to another

The classic pain: a range is pinned to `fo-group1` (two peers), and you
want to move it to `fo-group2` with two different peers. Pre-`range modify`
this required delete → network member swap → re-add. Now it's one line:

```
configure network 10.10.4.0/24 range modify 10.10.4.100 10.10.4.200 failover=fo-group2
```

Full lab-style walkthrough - adding two new DHCP members, creating a
second failover group, and shifting two ranges onto it:

```
# Bring up the new members
configure grid <grid> member add ibdhcp03.example.com ipaddress=192.0.2.113/24 gateway=192.0.2.1 \
    platform=VNIOS hwtype=IB-V1425 license=dhcp license=nios license=enterprise
configure grid <grid> member add ibdhcp04.example.com ipaddress=192.0.2.114/24 gateway=192.0.2.1 \
    platform=VNIOS hwtype=IB-V1425 license=dhcp license=nios license=enterprise

# Create the new failover pair
configure network failover add fo-group2 \
    primary ibdhcp03.example.com secondary ibdhcp04.example.com

# Swap the ranges onto the new group (members come from the failover peers)
configure network 10.10.4.0/24 range modify 10.10.4.100 10.10.4.200 failover=fo-group2
configure network 10.10.5.0/24 range modify 10.10.5.100 10.10.5.200 failover=fo-group2
```

Reverting a range to a single-member setup (detach from failover):

```
configure network 10.10.4.0/24 range modify 10.10.4.100 10.10.4.200 member=192.0.2.113
```

## Add an alias to an existing host record

`configure zone add host …` takes `alias=` at create time. To mutate an
existing record without losing anything, use the companion `modify host`
path - it's a GET-then-PUT that merges with whatever's already there:

```
# Add one
configure zone zone01.example.com modify host web01 add-alias=www

# Add two in one PUT
configure zone zone01.example.com modify host web01 add-alias=www add-alias=portal

# Remove one
configure zone zone01.example.com modify host web01 remove-alias=portal

# Same shape for IP and IPv6 entries
configure zone zone01.example.com modify host web01 add-ip=10.10.1.25 add-ipv6=2001:db8:100:1::25
configure zone zone01.example.com modify host web01 remove-ip=10.10.1.25

# Flip the disable flag, update the comment
configure zone zone01.example.com modify host web01 disable=true comment="Decommissioned 2026-05"

# Cross-view - pass view=<name> when the record lives in a non-default view
configure zone ext01.example.net modify host ns1 add-alias=dns1 view=External
```

Alias names relative to the containing zone are auto-FQDN'd (`www` →
`www.zone01.example.com`); fully-qualified names are left as-is. Empty
modifies print `Nothing to modify (no fields specified)`.

## Decommission a grid member

Tear-down order matters - NIOS refuses to delete a member while anything
still references it. Scenario: retiring `ibdhcp02`.

```
# 1. Show what still references the member. Spot DHCP ranges + any host
#    records that have it in their ipv4addrs or configure_for_dhcp slots.
show range
show fixed

# 2. Re-pin DHCP ranges onto the remaining failover partner or a different
#    member. Ranges bound to a failover group don't need re-pinning - the
#    group already carries the peer list.
configure network 10.10.3.0/24 range modify 10.10.3.100 10.10.3.200 member=192.0.2.111

# 3. If the member was part of a failover pair, the pair has to be rebuilt.
#    Delete the old one, add a new one with the survivor + replacement.
configure network failover delete fo-group1
configure network failover add fo-group1 primary ibdhcp01.example.com secondary ibdhcp05.example.com

# 4. Strip it from any DHCP network member assignments (modify each affected
#    network; see `show network`).
configure network 10.10.1.0/24 modify member=192.0.2.111

# 5. Turn services off so the member stops offering leases/DNS while you
#    finish cleanup.
configure grid <grid> member ibdhcp02.example.com dhcp disable both
configure grid <grid> member ibdhcp02.example.com dns  disable

# 6. Delete.
configure grid <grid> member ibdhcp02.example.com delete
```

Expect `IB.Data.Conflict` errors on step 6 if anything still points at the
member - they tell you exactly which reference is holding on.

## Migrate a zone to a different view

NIOS treats `(zone_fqdn, view)` as the primary key, so "moving" is
delete-then-recreate in the target view. Record data doesn't auto-copy,
but NIOS gives you two clean mechanisms for pulling it in.

### Option A: WAPI `copyzonerecords` (same grid)

Records already exist on this grid (most common - the original zone is
still in a different view). Create the target shell, then clone:

```
configure zone add zone01.example.com ns_group=ns-external view=External

configure zone zone01.example.com copy from zone01.example.com \
    source_view=default view=External

# Sanity check
show zone zone01.example.com view=External

# Drop the original once you've verified the copy
configure zone zone01.example.com delete
```

The `copy from` verb calls `zone_auth?_function=copyzonerecords` under
the hood. A/AAAA/CNAME/MX/TXT/PTR/host records all transfer; NS/SOA
records are re-created by the new zone automatically. Source and
destination don't have to be in different views (you can also clone
between fully-different FQDNs, e.g. for a "template zone" pattern).

### Option B: AXFR import from an external primary

Records live on *another* DNS server (legacy BIND, another vendor,
partner grid) and you want NIOS to pull them in at create time:

```
configure zone add corp.example.com \
    primary=ibdns01.example.com \
    import_from=10.99.0.53 \
    do_host_abstraction=true \
    create_ptr_for_hosts=true
```

- **`import_from=<ip>`** - source DNS server for the AXFR; also sets
  `use_import_from=True` automatically.
- **`primary=<member>`** is required by NIOS before it'll accept
  `import_from` - you're telling it "this grid member will own the zone
  once the transfer completes."
- **`do_host_abstraction=true`** - turn imported A records into host
  records during the import. Handy when migrating from a non-Infoblox
  primary.
- **`create_ptr_for_hosts=true`** - auto-create reverse PTR records for
  the imported hosts.

`import_from` is write-only on NIOS - you won't see it in a `show zone`
after the import completes, but the records will be there. If the
source IP is unreachable, the POST may hang on the initial AXFR
attempt; 198.51.100.x-style unroutable IPs will cause timeouts.

### Option C: CSV export/import (cross-grid / cross-boundary)

When the data source is a CSV or the zones aren't reachable via AXFR:

```
download csv /tmp/zone01.csv object record:host
# (edit the CSV - rewrite view column from "default" to "External")
upload csv /tmp/zone01.csv object record:host operation=MERGE
```

## Attach anycast to a set of DNS members

```
# Shared loopback on every DNS member
for m in ibdns01 ibdns02 ibdns03 ibdns04 ibdns05 ibdns06 ibdns07 ibdns08 ibdns09 ibdns10; do
  echo "configure grid <grid> member ${m}.example.com anycast add 192.0.2.53"
  echo "configure grid <grid> member ${m}.example.com anycast add 2001:db8:0:53::53"
done | ibcli -s "$GRID" -u "$USER" -p "$PASSWORD" -k -i /dev/stdin
```

On pre-provisioned members the v6 line prints `Deferred:` and retries
successfully after first boot - re-run with `-i` once the member is online
and it becomes `Skipped:` (already set) or `OK:`.

## Bulk-apply an EA across networks

```
configure network 10.10.1.0/24  modify set "DC Location" DC1
configure network 10.10.2.0/24  modify set "DC Location" DC1
configure network 10.10.3.0/24  modify set "DC Location" DC2
configure network 10.10.4.0/24  modify set "DC Location" DC2

# Or via the dedicated verb (same effect, clearer for pure-EA edits)
configure network 10.10.1.0/24  extattrs set "DC Location" DC1

# Query back
show network ea="DC Location:DC1"
```

## Share records across zones with a Shared Record Group

A Shared Record Group (SRG) is a named bundle of DNS records that you
define once and then attach to any number of zones. Every zone linked to
the SRG publishes those records under its own apex - handy for common
entries like `www`, `mail`, SPF/DMARC TXT, or service SRVs that should
exist identically across a family of domains.

### 1. Create the group

```
configure shared_record_group add srg-common    comment="Common shared records"
configure shared_record_group add srg-mail      comment="Mail-related shared records"
configure shared_record_group add srg-directory comment="Directory/LDAP shared records"
```

### 2. Populate the group with records

The verb mirrors `configure zone <z> add <type>` but the target is the
group, not a zone:

```
# srg-common - an apex + API entries, v4 + v6 + CNAME + TXT
configure shared_record a    add www    203.0.113.10  group=srg-common
configure shared_record a    add api    203.0.113.20  group=srg-common
configure shared_record aaaa add www    2001:db8::10  group=srg-common
configure shared_record cname add portal www          group=srg-common
configure shared_record txt  add info   "smoke-test"  group=srg-common

# srg-mail - MX + SPF/DMARC
configure shared_record mx  add mail  mail.example.com 10  group=srg-mail
configure shared_record txt add spf   "v=spf1 mx -all"      group=srg-mail
configure shared_record txt add dmarc "v=DMARC1; p=reject"  group=srg-mail

# srg-directory - SRV entries for LDAP / Kerberos
configure shared_record srv add _ldap._tcp     ldap.example.com 0 100 389 group=srg-directory
configure shared_record srv add _kerberos._tcp kdc.example.com  0 100 88  group=srg-directory
```

Supported record types under `configure shared_record …`: `a`, `aaaa`,
`cname`, `mx`, `txt`, `srv`.

### 3. Attach the group to zones

At zone create time, pass `srg=<name>`. You can list it multiple times for
multiple groups on the same zone:

```
configure zone add corp01.example.com ns_group=ns-group1 srg=srg-common srg=srg-mail
configure zone add corp02.example.com ns_group=ns-group1 srg=srg-common srg=srg-mail
configure zone add corp03.example.com ns_group=ns-group1 srg=srg-common srg=srg-directory
```

To attach an SRG to an existing zone, re-run `configure zone <zone> modify
srg=<name>` - repeatable. `modify` replaces the zone's SRG list with what
you pass, so include every group you want attached.

### 4. Inspect

```
# Show every SRG and its attached zones
show zone shared_record_group

# Show a specific SRG
show zone shared_record_group srg-common

# Show records in an SRG, by type
show shared_record a     group=srg-common
show shared_record mx    group=srg-mail
show shared_record txt   group=srg-mail
show shared_record srv   group=srg-directory
```

### 5. Prune and decommission

Remove a single record from the group, or drop the group entirely:

```
# Drop one record from the group (doesn't affect zones)
configure shared_record txt delete info group=srg-common

# Detach the group from a zone (leave the group intact for other zones)
configure zone corp01.example.com modify srg=srg-common  # keep this one
configure zone corp01.example.com modify                 # remove all SRGs from the zone

# Delete the group (only safe once no zones reference it)
configure shared_record_group srg-common delete
```

NIOS refuses the group delete while any zone still points at it -
the error tells you which zone is holding on, so detach those first.

## Stand up DTC from scratch (end-to-end)

```
# 1. Servers
configure dtc server add web1 host=203.0.113.10
configure dtc server add web2 host=203.0.113.20
configure dtc server add web3 host=203.0.113.30

# 2. Health checks
configure dtc monitor icmp add web-icmp
configure dtc monitor http add web-http   comment="HTTP 200 check"

# 3. Pool + attach
configure dtc pool add web-pool lb_preferred_method=round_robin
configure dtc pool web-pool server  add web1
configure dtc pool web-pool server  add web2
configure dtc pool web-pool server  add web3
configure dtc pool web-pool monitor add icmp web-icmp
configure dtc pool web-pool monitor add http web-http

# 4. LBDN + attach pool
configure dtc lbdn add web-lbdn lb_method=round_robin patterns=www.dtc.example.com
configure dtc lbdn web-lbdn pool add web-pool

# 5. Sanity check
show dtc lbdn web-lbdn
show dtc pool web-pool
```

Dismantling runs in reverse: `pool delete` from the LBDN, `monitor delete`
/ `server delete` from the pool, then delete the monitor/server/pool/LBDN
objects themselves.

## Restart services after bulk config changes

```
# Check if a restart is needed and what's pending
show restart status

# Kick it
restart dns
restart dhcp
restart all                 # everything on every member
```

## Save a support bundle from a specific member

```
download support_bundle /tmp/sb-ibdns01.tar.gz member ibdns01.example.com
```

Tab-complete the `member` slot - hostnames with VIPs as meta come straight
from the grid, so no typos.

## Sign a zone with DNSSEC

Two steps: turn DNSSEC on at the grid level (once, grid-wide), then sign
each zone.

```
# 1. Enable DNSSEC + validation grid-wide (idempotent; safe to re-run)
configure grid <grid> dns set dnssec_enabled=True dnssec_validation_enabled=True

# 2. Sign a zone
configure zone zone03.example.com dnssec sign

# 3. Verify: zone_auth now shows dnssec_keys, DNSKEY + RRSIG records appear
show zone zone03.example.com

# Other DNSSEC lifecycle operations
configure zone zone03.example.com dnssec unsign
configure zone zone03.example.com dnssec rollover_ksk
configure zone zone03.example.com dnssec rollover_zsk
```

All four verbs POST `<zone_auth>?_function=dnssec_operation` under the
hood. Add `view=<name>` to target a non-default DNS view.

Trust-anchor management (the `dnssec_trusted_keys` list on `grid:dns`)
isn't yet a native command - set it via `configure grid <g> dns set
dnssec_trusted_keys=…` or the NIOS UI.

## Block a malicious domain with RPZ

An RPZ zone is an authoritative zone whose records tell recursing resolvers
to rewrite or refuse specific queries. Policy semantics:

| RPZ record type | Effect |
|---|---|
| `cname . <qname>.rpz`             | NXDOMAIN |
| `cname *. <qname>.rpz`            | NODATA |
| `cname passthru. <qname>.rpz`     | Passthru (don't block) |
| `a <qname>.rpz 127.0.0.1` (etc.)  | Redirect (local rewrite) |

```
# One-time: create the policy zone
configure rpz zone add rpz.lab.local policy=GIVEN comment="Lab RPZ policy zone"

# Block a domain - redirect to 127.0.0.1 (sinkhole)
configure rpz record a add badsite.example.com.rpz.lab.local 127.0.0.1 zone rpz.lab.local

# Block all of *.badsite.example.com (wildcard form - prepend *.)
configure rpz record a add *.badsite.example.com.rpz.lab.local 127.0.0.1 zone rpz.lab.local

# IPv6 sinkhole
configure rpz record aaaa add badsite6.example.com.rpz.lab.local ::1 zone rpz.lab.local

# Unblock
configure rpz record a delete badsite.example.com.rpz.lab.local zone rpz.lab.local

# What's currently blocked?
show rpz records zone=rpz.lab.local
```

For NXDOMAIN-style policy (rather than redirect), use the CNAME form with
`.` or `*.` as the target - that's an RPZ convention, not an ibcli shape;
wrap it however feels cleanest for your team.

## Least-privilege admin: network-ops user restricted to DHCP

Scenario: `Alice` is a DHCP operator. She should be able to create/modify
DHCP ranges and fixed addresses, but not touch DNS zones, admin settings,
or grid configuration.

```
# 1. Role - grants the capabilities
configure admin role add lab-dhcp-operator comment="Lab DHCP operator role"

# 2. Group - links users to the role
configure admin group add lab-netops comment="Lab network ops group" role=lab-dhcp-operator

# 3. User - inherits everything from the group
configure admin user add alice password=AliceP@ss123 group=lab-netops \
    comment="Alice - netops"

# 4. Permissions - what can the role actually do?
#    Grant WRITE on DHCP networks and ranges; explicit DENY everywhere else.
configure admin permission add role=lab-dhcp-operator object=networks write
configure admin permission add role=lab-dhcp-operator object=dhcp_range write
configure admin permission add role=lab-dhcp-operator object=fixed_addresses write
configure admin permission add role=lab-dhcp-operator object=dns deny
configure admin permission add role=lab-dhcp-operator object=grid deny
```

To scope further - e.g. Alice can only edit DHCP under `10.10.0.0/16` -
attach an EA-based filter to the permission. That uses the
`*<EA-name>` = value WAPI match form, which is easier to configure from the
NIOS UI (Administration → Administrators → Roles → Permissions), since
it's click-and-select there. The CLI can still list and audit:

```
show admin user       # all users + last-login + group membership
show admin group      # all groups + member count
show admin role       # all roles + comment
```

Rotate Alice's password:

```
configure admin user alice set password=NewAliceP@ss456
```

## Reserve an IP for a server or printer (fixed address)

Quick rule of thumb:

- **Fixed address** (no DNS name): a DHCP binding that always gives a
  specific MAC the same IP. DHCP-only; nothing in DNS.
- **Host record with `fixed` + MAC**: combined DNS + DHCP binding. Creates
  a forward A record, a reverse PTR, *and* a DHCP reservation in one shot.

Use a **fixed address** for things that don't need a DNS name (printers,
industrial gear). Use a **host record** for anything you'll want to look
up by name (servers, appliances).

```
# Fixed address (DHCP only)
configure network 10.10.1.0/24 fixed add 10.10.1.51 aa:bb:cc:10:00:11 \
    name=printer-lobby comment="Lobby printer"

# Host record with embedded fixed (DNS + DHCP)
configure zone zone01.example.com add host lab-printer 10.10.1.52 \
    fixed mac=aa:bb:cc:10:00:12

# Roaming host - DHCP binding not tied to a specific network
configure network roaminghost add laptop-alice 10.10.1.60 aa:bb:cc:de:ad:01

# List everything reserved
show fixed
show fixed 10.10.1.51
```

Delete is symmetric: `configure network 10.10.1.0/24 fixed delete 10.10.1.51`.

## "Who has this IP?"

Incident-response #1 question.

**Interactive REPL (no variable substitution - type the IP each time):**

```
ibcli> show lease             10.10.1.145
ibcli> show fixed             10.10.1.145
ibcli> show record host  ipv4addr=10.10.1.145
ibcli> show record ptr   ipv4addr=10.10.1.145
ibcli> show record a     ipv4addr=10.10.1.145
```

**Shell one-liner (shell does the variable expansion, ibcli sees a fully-
resolved command per `-e`):**

```sh
IP=10.10.1.145
for cmd in \
    "show lease $IP" \
    "show fixed $IP" \
    "show record host ipv4addr=$IP" \
    "show record ptr  ipv4addr=$IP" \
    "show record a    ipv4addr=$IP"
do
    ibcli -s "$GRID" -u "$USER" -p "$PASSWORD" -k -e "$cmd"
done
```

> ibcli itself doesn't have variables, history substitution, or any shell
> features - the parser treats `$IP` as a literal. All the `$IP` /
> `$GRID` patterns in this cookbook only work when bash expands them
> before ibcli sees them. Inside a `.ibcli` batch file, lines are taken
> as-is; inside the interactive REPL, type the value directly.

For the combined aggregator (NIOS's own "all objects at IP" answer),
use the `show address` command - one line, everything:

```
show address 10.10.1.11
# → ip=10.10.1.11 network=10.10.1.0/24 view=default status=USED
#   types=HOST usage=DNS names=web01.zone01.example.com

show address ipv6 2001:db8:100:1::11
```

That surfaces `types` (HOST / LEASE / FIXED_ADDRESS / RESERVATION /
UNMANAGED / RANGE) and `usage` (DNS / DHCP) so you can see every object
class at the IP in one shot.

## Split or join a network

Carve a /23 into two /24s, or merge them back:

```
# Split 10.20.0.0/23 into two /24s (10.20.0.0/24 + 10.20.1.0/24)
configure network 10.20.0.0/23 split /24

# Join two siblings back into one
configure network 10.20.0.0/23 join
```

NIOS refuses a split if ranges/reservations straddle the new boundary -
you'll get a validation error telling you exactly which range is in the
way. Either resize the offending range first or split at a different
prefix.

`configure network <cidr> move` is a DHCP-member swap (`move member <ip>`
or `move failover <group>`), not a cross-view move. NIOS doesn't support
changing a network's `network_view` after creation - to "move" across
views you delete in the source view and recreate in the target view
(see the zone-migration scenario for the same pattern).

### Disambiguating when the same CIDR exists in multiple views

A network view is part of the composite key - the same CIDR can legally
exist in the `default`, `External`, and `production` views simultaneously.
Every `configure network <cidr> …` / `show network <cidr>` / `delete`
command accepts an optional `view=<name>` to pick which one you mean:

```
# Target a specific network view explicitly
configure network 10.10.1.0/24 modify comment="prod only" view=production
configure network 10.10.1.0/24 delete view=External
show network 10.10.1.0/24 view=production
```

Without `view=…` the handler targets the `default` network view, even if
the CIDR exists in other views too. If you're seeing "No network found"
errors when the CIDR is clearly present, add `view=<name>`.

List the views on the grid (and their network counts) to see what's out
there:

```
show network_view
```

For carving a container into subnets via a template:

```
configure template network add lab-net24 cidr 24 comment="Standard /24"
configure network container add 10.50.0.0/20 comment="/20 to subdivide"
configure network add 10.50.1.0/24 template=lab-net24
configure network add 10.50.2.0/24 template=lab-net24
```

## Lock a DHCP range to approved MAC addresses only

A MAC filter is a named allow-list. Create the filter, populate it with
known-good MACs, and attach it to a range:

```
# 1. Create the filter
configure network macfilter add trusted-printers

# 2. Populate with MAC entries
configure network filter trusted-printers add macaddress aa:bb:cc:01:00:01 \
    comment="Printer 1"
configure network filter trusted-printers add macaddress aa:bb:cc:01:00:02 \
    comment="Printer 2"

# 3. Inspect
show network filter trusted-printers

# 4. Attach the filter to a range (via range modify - add `filter=` alongside
#    member/failover). The underlying WAPI field is mac_filter_rules; ibcli's
#    range modify will accept `filter=<name>` where supported, otherwise set
#    it via `configure network <cidr> range modify set mac_filter_rules ...`
configure network 10.10.1.0/24 range modify 10.10.1.100 10.10.1.200 set mac_filter_rules "<filter trusted-printers>"
```

Removing a MAC later:

```
configure network filter trusted-printers delete macaddress aa:bb:cc:01:00:01
```

## Rename a host record

A host's FQDN is part of its `_ref`, so NIOS treats a name change as a
rename, not a field update. ibcli exposes this as a separate verb:

```
# Rename within the same zone (relative name → resolved to zone)
configure zone zone01.example.com rename host web01 web-prod01

# Cross-zone rename: pass the new name fully-qualified
configure zone zone01.example.com rename host web01 web-prod01.zone02.example.com

# Non-default view
configure zone ext01.example.net rename host ns1 dns1 view=External
```

The operation is a GET-then-PUT - IPs, aliases, EAs, and comment are all
preserved across the rename.

## Find every record pointing at a decommissioned IP

Before removing an IP from service, sweep for references. As with "Who has
this IP?" above, ibcli itself doesn't expand variables - let bash do it.

**Shell sweep (v4 + v6):**

```sh
IP=10.10.1.145
V6=2001:db8:100:1::145
CRED=(-s "$GRID" -u "$USER" -p "$PASSWORD" -k)

for cmd in \
    "show record host ipv4addr=$IP" \
    "show record a    ipv4addr=$IP" \
    "show record ptr  ipv4addr=$IP" \
    "show fixed       $IP" \
    "show lease       $IP" \
    "show record host ipv6addr=$V6" \
    "show record aaaa ipv6addr=$V6"
do
    echo "=== $cmd ==="
    ibcli "${CRED[@]}" -e "$cmd"
done
```

**One-liner aggregator** (simpler, but only shows summary fields - not
full record details):

```sh
ibcli -s "$GRID" -u "$USER" -p "$PASSWORD" -k -e "show address 10.10.1.145"
```

## Pre-provision an HA member pair

Two-node HA member: both nodes share a VIP, and each node has its own
hardware profile. `node=<hwtype>,<hwmodel>,<serial>` is repeatable - first
occurrence is node 1, second is node 2. When ≥ 2 `node=` entries are
present, ibcli sets `enable_ha=true` automatically.

```
configure grid <grid> member add ibdns-ha01.example.com \
    ipaddress=192.0.2.130/24 gateway=192.0.2.1 \
    ipv6addr=2001:db8:64:40::130/64 ipv6gateway=2001:db8:64:40::1 \
    mgmt_ipaddress=198.51.100.130/24 mgmt_gateway=198.51.100.1 \
    platform=VNIOS \
    node=IB-V1425,VNIOS,SER-NODE-1-12345 \
    node=IB-V1425,VNIOS,SER-NODE-2-12346 \
    license=dns license=nios license=enterprise
```

After the POST + PUT sequence the member shows up with
`node_info=[{node 1 hwdetails}, {node 2 hwdetails}]` and `enable_ha=true`.
Each physical node will try to join and one becomes active, one standby.

To promote a node or change HA state later, the commands live under
`configure grid <grid> member <fqdn> preprovision …` for pre-boot edits,
or via WAPI `member?_function=promote_member_to_master` once both nodes
are online.

## Schedule a delayed service restart

ibcli supports relative-time restart via `delay=<seconds>`. Absolute-time
scheduling (change-window at 02:00) needs a scheduled task - ibcli lists
and cancels them but creating one is a WAPI `scheduledtask` POST.

```
# Relative: restart DNS in 30 minutes
restart dns delay=1800

# Absolute time - accepts epoch seconds or ISO-8601 (local TZ):
restart dns at=2026-05-01T02:00:00
restart dhcp at=1735689600

# Restart only one member immediately
restart dns member=ibdns01.example.com

# Restart everything with a specific mode (GROUPED, SIMULTANEOUS, SEQUENTIAL)
restart all mode=SEQUENTIAL

# List scheduled / pending restart requests
show grid <grid> restart request

# Cancel a scheduled task
show schedule                            # list by ID
configure schedule 12345 delete          # cancel it
```

**NIOS-version note:** the `delay`/`at=` parameters require a NIOS build
that honors `delay` on the `restartservices` WAPI function. On older
releases the function returns `Unknown argument/field: 'delay'` - in that
case the restart fires immediately and you'll need the NIOS UI (or a
`scheduledtask` POST) to schedule for a future window.

## Bulk-import host records via CSV

For anything more than a handful of records, CSV beats hand-typing.

```
# Export current state to use as a template
download csv /tmp/hosts.csv object record:host

# Edit /tmp/hosts.csv - each row is a host record

# Upload. The mode defaults to INSERT (error on duplicates). To upsert
# existing rows (common when re-syncing), pass operation=MERGE.
upload csv /tmp/hosts.csv object record:host operation=MERGE

# Monitor the import task
show csv task             # lists all recent imports with status
show csv task 42          # specific task

# If anything failed, download the error report for that task
download csv_errors /tmp/hosts-errors.csv 42
```

### Import `operation` modes

Pick one per upload via `operation=<mode>` (defaults to `INSERT`):

| Mode       | Effect |
|---|---|
| `INSERT`   | Create new objects; **fail** rows where the key already exists. |
| `MERGE`    | Upsert - insert if absent, update fields in place if present. |
| `OVERRIDE` | Replace matching objects wholesale (see `update_method` below). |
| `DELETE`   | Delete every matching row. |
| `CUSTOM`   | Take the per-row action from the `*` column on each row (see table below). |

### `update_method` (only with `MERGE` or `OVERRIDE`)

`update_method=MERGE` (default) keeps fields that aren't in the CSV;
`update_method=OVERRIDE` drops them. So "overwrite wholesale" is:

```
upload csv /tmp/hosts.csv object record:host operation=OVERRIDE update_method=OVERRIDE
```

### Per-row flags (only when `operation=CUSTOM`)

NIOS reads the `*` column on each row and applies that flag to just that
row - lets you mix create/modify/delete in one file:

| `*` column | Action for that row |
|---|---|
| `I` or `IR` | Insert (fail if exists) |
| `M`  | Modify (fail if missing) |
| `IM` | Insert if absent, modify if present (per-row upsert) |
| `D`  | Delete |
| `O`  | Override (wholesale replace) |

### Also on the upload command

| Keyword | Values | Default |
|---|---|---|
| `object=<type>` | `record:host`, `network`, etc. | inferred from CSV header |
| `operation=<mode>` | See table above | `INSERT` (or `CUSTOM` if only `object=` is given) |
| `update_method=<mode>` | `MERGE` or `OVERRIDE` | `MERGE` |
| `on_error=<action>` | `STOP` or `CONTINUE` | `STOP` |

`download csv` without `object=` gets you every type - useful as a grid
backup you can diff. `download csv` with `object=record:host` (or any
other WAPI object type) scopes the dump.

## Daily health-check batch file

A one-file smoke-test you can point at a cron or run before a change
window. Redirect its output into a ticket or Slack.

Save as `health-check.ibcli`:

```
# ==== Grid service status ====
show grid <grid> restart status
show grid <grid> dns
show grid <grid> dhcp

# ==== Member status ====
show member

# ==== DHCP failover (anything not NORMAL is suspicious) ====
show network failover

# ==== DTC pool health ====
show dtc pool
show dtc lbdn

# ==== DNS zone discrepancies (zones with replication drift) ====
show zone discrepancy
```

Run it:

```sh
ibcli -s "$GRID" -u "$USER" -p "$PASSWORD" -k health-check.ibcli \
    > /tmp/health-$(date +%F).log 2>&1
```

Batch output is plain-text line-oriented - easy to `grep` for specific
services or to diff between consecutive runs with `diff` or `difft`.

---

## Notifications (outbound webhooks)

Ship NIOS events out to a webhook receiver - object-change feeds, DNS RPZ hits, ADP alerts, scheduled-task completions.
Two objects are involved: **endpoint** (where to POST) and **rule** (which events and optional filters trigger
the POST).

### Create a REST endpoint

```sh
# Required: uri, outbound_member_type (GM or MEMBER). Defaults to GM if omitted.
configure notification endpoint add prod-webhook \
    uri=https://events.corp.example.com/ibx \
    outbound_member_type=GM
```

### Create a rule bound to that endpoint

```sh
# endpoint=<name> is required. notification_action and expression_list
# get safe defaults (RESTAPI_TEMPLATE_INSTANCE + empty list = "match everything").
configure notification rule add dns-changes \
    endpoint=prod-webhook \
    event_type=DB_CHANGE_DNS_RECORD
```

### List / delete

```sh
show notification endpoint
show notification rule
configure notification rule dns-changes delete
configure notification endpoint prod-webhook delete
```

### Event types most people reach for

| `event_type=`                          | Fires on                           |
|----------------------------------------|------------------------------------|
| `DB_CHANGE_DNS_RECORD`                 | any DNS record created/modified/deleted |
| `DB_CHANGE_DNS_ZONE`                   | zone mutations (add/modify/delete) |
| `DB_CHANGE_DHCP_NETWORK_IPV4` / `_IPV6`| network edits                      |
| `DB_CHANGE_DHCP_RANGE_IPV4` / `_IPV6`  | range edits                        |
| `DB_CHANGE_DHCP_FIXED_ADDRESS_IPV4` / `_IPV6` | fixed-addr edits            |
| `DNS_RPZ`                              | RPZ policy hit on a resolver       |
| `DHCP_LEASES`                          | lease changes                      |
| `ANALYTICS_DNS_TUNNEL`                 | Threat Insight detection           |
| `SECURITY_ADP`                         | ADP rule match                     |
| `SCHEDULE`                             | scheduled task completion          |

Expression-list filters (per-field predicates like "only RPZ hits for clients in 10.0.0.0/8") are set after creation
via `configure notification rule <name> set expression_list=…`. The shape is event-type-specific - see the Infoblox
WAPI docs for the object schema.

---

## Upgrade groups and upgrade status

### Inspect status by type

The type selector is required - it maps to the WAPI `type=` filter.

```sh
show upgrade_status grid                        # grid-wide rollout state
show upgrade_status group                       # one row per upgrade group
show upgrade_status group <group-name>          # one specific group
show upgrade_status vnode                       # every virtual member
show upgrade_status vnode <member-fqdn>         # one virtual member
show upgrade_status pnode                       # physical appliances
show upgrade_status pnode <member-fqdn>
```

Group rows surface rollout progress, step counts, and schedule flags:

```text
group=Default       type=GROUP status=OFFLINE members=0/16
group=Grid Master   type=GROUP status=WORKING members=0/1 steps=1/1
```

### Manage upgrade groups

```sh
configure upgrade_group add night-maintenance \
    upgrade_policy=SEQUENTIALLY distribution_policy=SIMULTANEOUSLY

configure upgrade_group night-maintenance set members="m1.example.com,m2.example.com"
configure upgrade_group night-maintenance delete

show upgrade_group
show upgrade_group night-maintenance
```

### Schedules (singleton objects - one per grid)

```sh
show upgrade_schedule
configure upgrade_schedule set start_time=1776816000 time_zone=UTC

show distribution_schedule
configure distribution_schedule set start_time=1776729600 time_zone=UTC
```

---

## DHCP request filters (all five types)

NIOS DHCP can match incoming requests against five filter categories. Each uses its own WAPI object type; CLI grammar
is parallel across them.

### Fingerprint filter - match by client OS/device

```sh
configure fingerprint add windows-10 vendor_id='MSFT 5.0'
configure filter fingerprint add office-windows fp=windows-10
show filter fingerprint
```

### Option filter - match on DHCP option values

```sh
configure filter option add cisco-aps
show filter option
configure filter option cisco-aps delete
```

### NAC filter - match on NAC posture

```sh
configure filter nac add compliant-endpoints
show filter nac
```

### Relay-agent filter - match option-82 circuit/remote ID

```sh
# ANY + ANY is rejected by NIOS; at least one side must be non-ANY.
configure filter relayagent add floor3-ap \
    is_circuit_id=ANY \
    is_remote_id=MATCHES_VALUE \
    remote_id_name=ap-floor3 \
    is_remote_id_substring=false

show filter relayagent
```

### IPv6 option filter

```sh
configure filter ipv6option add v6-enterprise
show filter ipv6option
```

### Attach filters to a MAC filter (for policy enforcement on a network)

```sh
configure network macfilter add office-floor3
configure network filter office-floor3 add macaddress aa:bb:cc:00:00:11
configure network filter office-floor3 add macaddress aa:bb:cc:00:00:12
show network macfilter
```

---

## Option spaces and option definitions

Custom vendor-scoped DHCP options live under user-defined **option spaces**. Individual option codes are **option
definitions** scoped to a space.

```sh
# Create a space for Cisco VoIP options.
configure option_space add cisco-voip

# Define option 150 (TFTP server list) inside that space.
configure optiondef add tftp-servers \
    code 150 \
    type array_of_ip \
    space=cisco-voip

# Inspect.
show option_space
show optiondef

# Tear down (option defs must be deleted before their space).
configure optiondef tftp-servers delete
configure option_space cisco-voip delete
```

IPv6 equivalents live under separate grammar - `configure ipv6optionspace add …`, `configure ipv6optiondef add …`.

---

## Network and range templates

Templates let you stamp out pre-configured DHCP networks or ranges. Useful when you need dozens of subnets that all
share the same options / failover / members.

### Network template

```sh
configure template network add office-subnet cidr 24
# options and extattrs get applied to networks that clone this template
configure template network office-subnet set comment "standard office /24"

show template network
```

### Range template

```sh
configure template range add guest-range \
    number_of_addresses=50 \
    offset=100

show template range
```

### Use a template when creating a network

```sh
configure network add 10.10.7.0/24 template=office-subnet
configure network 10.10.7.0/24 range add template=guest-range
```

---

## DDNS principal clusters (GSS-TSIG)

Authorize Kerberos principals (typically AD Domain Controllers or DHCP relays) to perform **authenticated** dynamic
DNS updates against NIOS zones.

!!! note
    This is **not** grid DHCP DDNS behaviour (see `configure grid <g> dhcp set ddns_…`) and **not** per-zone update
    ACLs (see `configure zone <z> set allow_update=…`). This subtree only configures who the GSS-TSIG principal
    allowlists are.

```sh
# Create an allowlist ("cluster") of authorized principals.
configure ddns cluster add ad-prod \
    principals=dhcpserver$@CORP.EXAMPLE.COM,dnsadmin@CORP.EXAMPLE.COM \
    comment="AD production DCs authorized for DDNS"

# Create a group of clusters - a zone's update policy can evaluate them in order.
configure ddns cluster_group add prod-forest

# Inspect.
show ddns cluster
show ddns cluster_group
show ddns cluster ad-prod
```

Reference a cluster from a zone's update policy via `configure zone <z> set update_forwarding=…`. Shape depends on
your policy model; see the Infoblox WAPI docs for the update-policy schema.

---

## Integrations and outbound

Forward NIOS telemetry to third-party platforms.

### TAXII feed consumption

```sh
configure integration taxii name=taxii-server-1 set service_enabled=true
show integration taxii
```

### Syslog endpoints

```sh
configure integration syslog add primary-siem
configure integration syslog primary-siem set remote_server=10.0.0.100 local_severity=INFO
show integration syslog
```

### PxGrid (Cisco ISE)

```sh
configure integration pxgrid add ise-controller-1
show integration pxgrid
```

### DXL (McAfee Data Exchange Layer)

```sh
configure integration dxl add dxl-broker-1
show integration dxl
```

### Outbound cloud client (summary read-only)

```sh
show integration outbound
configure integration outbound default set interval=60 enable=true
```

### All endpoints aggregated (read-only)

```sh
show integration all
```

---

## Discovery (NetMRI-lite)

### Credential groups

```sh
configure discovery credential_group add lab-snmp-creds
show discovery credential_group
```

### SDN network registration (VMware / OpenStack)

```sh
configure discovery sdn_network add vcenter-lab type=VCENTER
show discovery sdn_network
```

### Grid-wide discovery properties + per-member properties

```sh
show discovery grid_properties
show discovery member_properties
show discovery member_properties ibdns01.example.com
```

### vDiscovery (cloud adaptors)

```sh
configure vdiscovery add aws-prod
show vdiscovery
configure vdiscovery aws-prod delete
```

### Read-only queries

```sh
show discovery device
show discovery device <device-name>
show discovery device <device-name> component
show discovery device <device-name> interface
show discovery device <device-name> neighbor
show discovery diagnostic
show discovery status <network-view>   # network_view is required by WAPI
```

---

## Threat Insight and ADP

### Threat Insight configuration (DNS tunneling detection)

```sh
show threat_insight
configure threat_insight set enable=true
```

### Threat Protection (ADP) rules

```sh
show threat_protection
configure threat_protection set disable_multiple_dns_tcp_request=false
```

---

## BFD templates, rulesets, and other ops objects

### BFD (Bidirectional Forwarding Detection) templates

```sh
configure bfd_template add anycast-bfd set detection_multiplier=3 min_rx_interval=100
show bfd_template
configure bfd_template anycast-bfd delete
```

### Rulesets (used by scavenging + notification filters)

```sh
configure ruleset add stale-hosts-30d type=SCAVENGING
show ruleset
configure ruleset stale-hosts-30d delete
```

### Scavenging tasks (read-only)

```sh
show scavenging
```

### TFTP-served directories

```sh
configure tftp_dir add /boot comment "PXE boot images"
show tftp_dir /boot                    # name is required by WAPI
configure tftp_dir /boot delete
```

### Database snapshots (read-only)

```sh
show db snapshot
```

---

## Required-filter `show` commands

A handful of read-only queries require a filter argument - WAPI rejects the bare form. ibcli prints a friendly usage
hint when you forget it.

| Command                                  | Required argument                                     |
|------------------------------------------|-------------------------------------------------------|
| `show capacity_report <member>`          | member host_name                                      |
| `show dhcp_statistics <member>`          | member host_name                                      |
| `show ordered_range <n.n.n.n/mm>`        | network CIDR                                          |
| `show record all zone=<zone>`            | zone FQDN (`[<name>]` optional extra filter)          |
| `show rpz records zone=<zone>`           | RPZ zone FQDN                                         |
| `show rpz_order view=<view>`             | DNS view name                                         |
| `show superhostchild <parent>`           | parent superhost name                                 |
| `show tftp_dir <directory>`              | directory name                                        |
| `show dtc record a <dtc_server>`         | DTC server name (same for aaaa / cname / srv / naptr) |
| `show dtc records <zone>`                | DTC zone                                              |
| `show discovery status <network-view>`   | network view                                          |
| `show upgrade_status {grid\|group\|vnode\|pnode} [<name>]` | type selector              |
| `show db_objects` | optional `object_types=<t>` or `version=<v>`; default sends `all_object_types_supported_in_version=2.13.7`. |

---

## Live-grid audit tooling

Two helpers in `scripts/` complement the pytest suite by exercising the CLI against a real grid.

### `scripts/sweep-show.sh` - show-command audit

Runs every no-arg `show` command from `ibcli -l` against the grid, classifies each error as *friendly-usage* /
*grid-config* / *suspected CLI bug*, and exits 1 on any suspected bug. Good as a CI gate after WAPI-surface changes.

```sh
scripts/sweep-show.sh -s 192.0.2.10 -u admin -p 'secret'

# Or via env:
IBCLI_HOST=192.0.2.10 IBCLI_USER=admin IBCLI_PASS='secret' \
    scripts/sweep-show.sh

# Keep artifacts in a named directory:
scripts/sweep-show.sh -s gm -u admin -p pw -o /tmp/sweep-$(date +%F)
```

Artifacts per run:

| File                | Contents                                               |
|---------------------|--------------------------------------------------------|
| `sweep.ibcli`       | the generated batch file                               |
| `sweep.out`         | raw ibcli output, one command per block                |
| `summary.tsv`       | per-command status + first two lines of output         |
| `errors.txt`        | errored commands paired with their error message       |
| `report.txt`        | human-readable summary (shown on stdout too)           |

### `scripts/smoke/` - object-build smoke harness

Parameterised build → verify → teardown across 11 phases, three scales.

```sh
# Quick plumbing check (~100 objects):
scripts/smoke/smoke.sh -s gm -u admin -p pw --scale tiny --tag v1 --all

# Full-surface (~10,000 objects), keep build artifacts:
scripts/smoke/smoke.sh -s gm -u admin -p pw --scale full --tag v1 --all \
    -o /tmp/smoke-$(date +%F)

# Build only (leave on grid for manual inspection):
scripts/smoke/smoke.sh -s gm -u admin -p pw --scale small --build

# Run a subset of phases (zones + records only):
scripts/smoke/smoke.sh -s gm -u admin -p pw --scale full --phases 3,4 --build
```

Phases (all selectable via `--phases`):

| # | Phase                                                       |
|---|-------------------------------------------------------------|
| 0 | Pre-provisioned members                                     |
| 1 | Views, NS groups, ACLs, EA definitions                      |
| 2 | DHCP - networks, ranges, fixed, MAC filters, failover       |
| 3 | DNS zones (forward + reverse)                               |
| 4 | DNS records (A / AAAA / CNAME / MX / TXT / CAA / NAPTR / TLSA) |
| 5 | Host records + shared record groups                         |
| 6 | RPZ zones + records                                         |
| 7 | DTC - servers, pools, LBDNs, monitors                       |
| 8 | Admin users, groups, roles                                  |
| 9 | Notification endpoints                                      |
| 10 | DHCP extras - option spaces, filters, templates            |

All smoke objects carry a `smoke-` name prefix (and `Smoke=<tag>` EA on objects that support it). Teardown is opt-in
(`--teardown` / `--all`) and reverse-dependency ordered.

---

## Audit: find commands that error against your grid

Run the show-sweep, then grep the report for suspected bugs:

```sh
scripts/sweep-show.sh -s "$GRID" -u "$USER" -p "$PASSWORD" -o /tmp/audit \
    || true   # we want to inspect the output regardless of exit code

grep -E "^--- BUGS" -A100 /tmp/audit/report.txt | head -40
```

Anything in the `BUGS` block is worth filing; the `USAGE HINTS` and `GRID-CONFIG` blocks are expected on most grids.

---

## Change-review diff between two grid states

Use the batch mode to dump state before and after, then `diff`:

```sh
# Before a change window
scripts/sweep-show.sh -s "$GRID" -u "$USER" -p "$PASSWORD" -o /tmp/before

# Apply changes
ibcli -s "$GRID" -u "$USER" -p "$PASSWORD" -k -i change-window.ibcli

# After
scripts/sweep-show.sh -s "$GRID" -u "$USER" -p "$PASSWORD" -o /tmp/after

# What changed
diff /tmp/before/sweep.out /tmp/after/sweep.out | less
```

`summary.tsv` is more diff-friendly than `sweep.out` because it's one line per command with a short preview:

```sh
diff /tmp/before/summary.tsv /tmp/after/summary.tsv
```
