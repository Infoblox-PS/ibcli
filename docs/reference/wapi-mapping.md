# WAPI Object Mapping

This table maps the Perl `Infoblox::*` SDK classes to NIOS WAPI object types used in the Python port.

## DNS Objects

| Perl class | WAPI objtype | ibcli commands |
|---|---|---|
| `Infoblox::DNS::Zone` (auth) | `zone_auth` | `configure zone add`, `show zone` |
| `Infoblox::DNS::Zone` (forward) | `zone_forward` | `configure zone add` with `forward_to=` |
| `Infoblox::DNS::Zone` (delegated) | `zone_delegated` | `configure zone add` with `delegate_to=` |
| `Infoblox::DNS::Zone` (stub) | `zone_stub` | `configure zone add` with `stub_from=` |
| `Infoblox::DNS::Record::A` | `record:a` | `configure zone <z> add a` |
| `Infoblox::DNS::Record::AAAA` | `record:aaaa` | `configure zone <z> add aaaa` |
| `Infoblox::DNS::Record::CNAME` | `record:cname` | `configure zone <z> add cname` |
| `Infoblox::DNS::Record::MX` | `record:mx` | `configure zone <z> add mx` |
| `Infoblox::DNS::Record::TXT` | `record:txt` | `configure zone <z> add txt` |
| `Infoblox::DNS::Record::PTR` | `record:ptr` | `configure zone <z> add ptr` |
| `Infoblox::DNS::Record::SRV` | `record:srv` | `show record srv=<name>` (read-only) |
| `Infoblox::DNS::Host` | `record:host` | `configure zone <z> add host` |
| `Infoblox::DNS::View` | `view` | `configure view add`, `show views` |
| `Infoblox::DNS::NamedACL` | `nsgroup` | `configure nsgroup add` |
| `Infoblox::DNS::SharedRecordGroup` | `sharedrecordgroup` | `configure shared_record_group add` |

## Network Objects

| Perl class | WAPI objtype | ibcli commands |
|---|---|---|
| `Infoblox::DHCP::Network` (IPv4) | `network` | `configure network add`, `show network` |
| `Infoblox::DHCP::Network` (IPv6) | `ipv6network` | auto-detected from CIDR |
| `Infoblox::DHCP::Container` (IPv4) | `networkcontainer` | `configure network container add` |
| `Infoblox::DHCP::Container` (IPv6) | `ipv6networkcontainer` | auto-detected from CIDR |
| `Infoblox::DHCP::SharedNetwork` | `sharednetwork` | `configure network add shared` |
| `Infoblox::DHCP::Range` | `range` | `configure network <cidr> range add` |
| `Infoblox::DHCP::FixedAddr` | `fixedaddress` | `configure network <cidr> fixed add` |
| `Infoblox::DHCP::FixedAddrTemplate` | `fixedaddresstemplate` | `configure template fixed add` |
| `Infoblox::DHCP::NetworkTemplate` | `networktemplate` | `configure template network add` |
| `Infoblox::DHCP::Lease` | `lease` | `show lease` |
| `Infoblox::DHCP::Failover` | `dhcpfailover` | `configure network failover add` |
| `Infoblox::DHCP::OptionSpace` | `optionspace` | `configure option_space add` |
| `Infoblox::DHCP::OptionDef` | `optiondef` | `configure optiondef add` |
| `Infoblox::DHCP::Filter::MAC` | `filtermac` | `configure network macfilter add` |
| `Infoblox::DHCP::MAC` | `macfilteraddress` | `configure network filter <n> add macaddress` |

## Admin and Grid Objects

| Perl class | WAPI objtype | ibcli commands |
|---|---|---|
| `Infoblox::Grid` | `grid` | `show grid` |
| `Infoblox::Grid::Member` | `member` | `configure grid <n> member add` |
| `Infoblox::Grid::Member::DNS` | `member:dns` | `configure grid <n> member <n> dns` |
| `Infoblox::Grid::Member::DHCP` | `member:dhcp` | `configure grid <n> member <n> dhcp` |
| `Infoblox::Grid::DNS` | `grid:dns` | `show grid <n> dns` |
| `Infoblox::Grid::DHCP` | `grid:dhcp` | `show grid <n> dhcp` |
| `Infoblox::Admin::User` | `adminuser` | `configure admin user add` |
| `Infoblox::Admin::Group` | `admingroup` | `configure admin group add` |
| `Infoblox::Admin::Role` | `adminrole` | `configure admin role add` |
| `Infoblox::Admin::Permission` | `permission` | `configure admin permission add` |
| `Infoblox::RADIUS::User` | `radius:user` | `configure radius user add` |
| `Infoblox::RADIUS::NAS` | `radius:nas` | `configure radius device add` |
| `Infoblox::Grid::ExtensibleAttributeDef` | `extensibleattributedef` | `configure grid attribute add` |
| `Infoblox::Grid::ScheduledTask` | `scheduledtask` | `show schedule`, `configure schedule delete` |
| `Infoblox::Grid::RestartServiceStatus` | `restartservicestatus` | `restart status` |

## Batch requests (not currently used - NIOS /request is not transactional)

NIOS exposes a `/request` endpoint that accepts an array of sub-operations. Despite documentation claiming otherwise,
NIOS processes `/request` sub-operations **sequentially but NOT atomically** - if a later operation fails, earlier
operations that already completed are **not rolled back**.

ibcli does not use `/request` for member add + pre-provisioning. Instead it uses a sequential POST then PUT, with an
explicit DELETE rollback if the PUT fails. This gives honest failure semantics the caller can reason about.

**Endpoint:** `POST /wapi/vX.Y/request`

**Body:** JSON array of operation objects. Each operation supports these keys:

| Key | Description |
|-----|-------------|
| `method` | HTTP verb for this operation: `GET`, `POST`, `PUT`, or `DELETE` |
| `object` | WAPI object type (e.g. `member`) or a `##STATE:name:##` reference |
| `data` | Request body for the sub-operation |
| `args` | Query-string parameters for the sub-operation |
| `assign_state` | Map of variable names to response field paths. E.g. `{"new_ref": "_ref"}` captures the returned `_ref` into `new_ref`. |
| `enable_substitution` | Set `true` to enable `##STATE:name:##` template resolution in `object` and `data` fields |
| `discard` | Set `true` to omit this operation's response from the overall reply (keeps the response small) |

**`##STATE:name:##` substitution:** when `enable_substitution` is `true`, any occurrence of `##STATE:name:##` in the
operation's `object` or `data` is replaced at runtime with the value previously captured by `assign_state`. This
allows later operations to reference objects created by earlier ones without a second round-trip.

## Notes

- **IPv4 vs IPv6:** The Python port auto-detects address family from the CIDR notation. IPv6 CIDRs (containing `:`) route to `ipv6network` or `ipv6networkcontainer`.
- **Zone type selection:** NIOS has four separate zone WAPI types where the Perl SDK had one `Infoblox::DNS::Zone`
  class. The Python port selects the correct type based on keywords (`forward_to=`, `delegate_to=`, `stub_from=`) or
  falls back through the four types in order.
- **The `_ref` pattern:** All WAPI objects have a `_ref` field. The Python port performs a GET-by-attribute to find the ref, then issues PUT or DELETE on the ref. This mirrors the Perl `get`-then-mutate pattern.
