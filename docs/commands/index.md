# Command Reference

This section documents every command family in the Python port. Commands are organized by domain.

**New here?** The [cookbook](cookbook.md) is a copy-pasteable quick-reference
for the jobs most operators actually run - dual-stack member adds, DHCP
enable/disable (v4/v6/both), anycast, DTC wiring, file downloads, and more.

## Top-level verbs

| Verb | Description |
|---|---|
| `configure` | Create, modify, or delete objects |
| `show` | Display objects |
| `upload` | Upload files to the grid |
| `download` | Download files from the grid |
| `generate` | Generate certificates or CSRs |
| `restart` | Restart grid services |
| `help` | Inline help |
| `quit` / `exit` / `bye` | Exit ibcli |
| `history` | Brief history hint |

## Command families

| Page | Commands |
|---|---|
| [Zones](zones.md) | `configure zone add/modify/delete`, `show zone` |
| [Records](records.md) | `configure zone <z> add/delete host/a/aaaa/cname/mx/txt/ptr`, `show record` |
| [Networks](networks.md) | `configure network add/modify/delete/split/join/move`, `show network`, IPAM |
| [Network Containers](network-containers.md) | `configure network container add/modify/delete`, `show network container` |
| [Shared Networks](shared-networks.md) | `configure network add shared`, `configure shared_network delete`, `show network shared` |
| [Network Templates](network-templates.md) | `configure template network add/delete`, `show template network` |
| [DHCP Ranges & Fixed](dhcp-ranges-fixed.md) | `configure network range/fixed add/delete`, `show range`, `show fixed` |
| [DHCP MAC Filters](dhcp-mac-filters.md) | `configure network macfilter add/delete`, `configure network filter add/delete macaddress`, `show network filter` |
| [DHCP Failover & Options](dhcp-failover-options.md) | `configure network failover`, `configure option_space`, `configure optiondef`, `show network failover/options` |
| [DHCP Leases](dhcp-leases.md) | `show lease` |
| [Admin](admin.md) | `configure admin user/group/role/permission`, `show admin` |
| [RADIUS](radius.md) | `configure radius user/device`, `show radius` |
| [Grid](grid.md) | `configure grid member/nsgroup/view/shared_record_group`, `show grid`, `show views` |
| [Restart](restart.md) | `restart dns/dhcp/dhcpv4/dhcpv6/all/discovery/status`, `show restart`, `show schedule`, `configure schedule delete` |
| [Extensible Attributes](extensible-attributes.md) | `configure grid attribute`, `show grid attribute` |
| [`set` value syntax](set-syntax.md) | Value-coercion rules and tab-completion helpers shared by every `configure … set <key>=<value>` verb |
| [Files](files.md) | `upload/download database/csv/logs/leases/support_bundle/dhcp_conf` |
| [Certificates](certificates.md) | `download/upload cert`, `generate selfsigned cert`, `generate csr` |
| [CSV](csv.md) | `upload csv`, `download csv/csv_errors`, `show csv task` |

## Quick abbreviation reference

All literal words can be abbreviated to any unambiguous prefix:

```
co z a example.com    →  configure zone add example.com
sh z example.com      →  show zone example.com
sh n 10.0.0.0/8       →  show network 10.0.0.0/8
re dn                 →  restart dns
```
