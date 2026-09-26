# Grid Management

Grid management covers members, grid-level DNS/DHCP settings, NS groups, DNS views, and shared record groups.

## show grid

Display top-level grid information.

**Syntax:**

```
show grid [<name>]
```

**WAPI:** `GET grid`

```
show grid
name=Infoblox  ref=grid/ZG5zLm5ldHdvcms...
```

## show views

List or show a specific DNS view.

**Syntax:**

```
show views [<name>]
```

**WAPI:** `GET view`

=== "List all"
    ```
    show views
    ```
=== "Output"
    ```
    name=default (default)
    name=external comment=Internet-facing
    name=internal
    ```

=== "Specific view"
    ```
    show views external
    ```

---

## Grid Members

### show grid \<name\> member

**Syntax:**

```
show grid <name> member [<member_name>]
```

**WAPI:** `GET member`

=== "List all members"
    ```
    show grid Infoblox member
    ```
=== "Output"
    ```
    host_name=gm.corp.example address=192.168.1.2
    host_name=member2.corp.example address=192.168.1.3
    ```

=== "Specific member"
    ```
    show grid Infoblox member gm.corp.example
    ```

### show grid \<name\> member \<name\> dns

Show DNS settings for a member.

**Syntax:**

```
show grid <name> member <member_name> dns
```

**WAPI:** `GET member:dns?host_name=<name>`

```
show grid Infoblox member gm.corp.example dns
host_name=gm.corp.example enable_dns=true
```

### show grid \<name\> dns

Show grid-level DNS settings.

**Syntax:**

```
show grid <name> dns
```

**WAPI:** `GET grid:dns`

```
show grid Infoblox dns
allow_recursive_query=true default_ttl=3600 dnssec_enabled=false
```

### show grid \<name\> dhcp

Show grid-level DHCP settings.

**Syntax:**

```
show grid <name> dhcp
show grid <name> dhcp keys     # list writable fields for `dhcp set`
```

**WAPI:** `GET grid:dhcp`

```
show grid Infoblox dhcp
lease_time=86400 domain_name=corp.example authority=true
```

### configure grid \<name\> {dns,dhcp,threat_insight,threat_protection,file_distribution} set

Apply grid-level service settings by key=value pass-through. Each verb
PUTs to the matching WAPI object:

| verb | WAPI object |
|---|---|
| `dns set` | `grid:dns` |
| `dhcp set` | `grid:dhcpproperties` |
| `threat_insight set` | `grid:threatinsight` |
| `threat_protection set` | `grid:threatprotection` |
| `file_distribution set` | `grid:filedistribution` |

**Syntax:**

```
configure grid <name> <domain> set <key>=<value> [<key>=<value> ...]
```

Multiple `key=value` pairs go out in a single PUT. See the [configure …
set value syntax reference](set-syntax.md) for the full coercion rules
(bool / int / JSON / ACL shortcut).

**Tab completion** offers every writable field as `<name>=`, filtered by
the prefix you've typed, with its type as metadata (`true/false`,
`number`, `text`, `text list`, enum choices, etc.).

**Discovering valid keys at the prompt:**

```
show grid <name> dhcp keys
show grid <name> dns keys
show grid <name> threat_insight keys
show grid <name> threat_protection keys
show grid <name> file_distribution keys
```

Each `… keys` variant lists the writable fields (with their types / enum
choices) accepted by the matching `set` verb. The list is resolved from
the SDK pydantic model, so it tracks the WAPI version the SDK is pinned
against.

**DHCP examples:**

=== "DDNS"
    ```
    configure grid Infoblox dhcp set enable_ddns=true
    configure grid Infoblox dhcp set ddns_domainname=corp.example ddns_ttl=3600
    configure grid Infoblox dhcp set ddns_generate_hostname=true ddns_update_fixed_addresses=true
    ```

=== "Thresholds / alerting"
    ```
    configure grid Infoblox dhcp set enable_dhcp_thresholds=true high_water_mark=95
    configure grid Infoblox dhcp set enable_email_warnings=true
    ```

=== "Protocol options"
    ```
    configure grid Infoblox dhcp set authority=true deny_bootp=false
    configure grid Infoblox dhcp set enable_leasequery=true enable_fingerprint=true
    ```

**DNS examples:**

=== "Scalars"
    ```
    configure grid Infoblox dns set allow_recursion=true
    configure grid Infoblox dns set default_ttl=3600 dnssec_enabled=true
    configure grid Infoblox dns set forwarders_only=false
    ```

=== "ACL-style fields (struct list)"
    ```
    # Shortcut syntax - comma-separated <PERM>:<cidr> entries.
    configure grid Infoblox dns set allow_query=ALLOW:10.0.0.0/8,DENY:192.168.0.0/16

    # Single entry (permission defaults to ALLOW):
    configure grid Infoblox dns set allow_query=10.0.0.0/8

    # Reference a named ACL by ref:
    configure grid Infoblox dns set allow_query=acl:namedacl/Li5hY2w..:trusted

    # Clear the list:
    configure grid Infoblox dns set allow_query=[]
    ```

    These expand automatically to the `addressac` / `_ref` structs the
    WAPI expects. See [set-syntax.md](set-syntax.md) for full details and
    the JSON fallback.

!!! note
    Per-field semantics (valid combinations, defaults, side-effects) are
    not documented here - consult the Infoblox *NIOS Administrator Guide*
    or the WAPI reference for the target object.

### configure grid \<name\> member add

**Syntax:**

```
configure grid <name> member add <fqdn>
    [ipaddress=<ip/prefix>] [gateway=<ip>] [vlan_id=<1-4094>]
    [ipv6addr=<addr/prefix>] [ipv6gateway=<ip6>]
    [comment=<comment>]
    [platform <platform>]
    [hwtype <hwtype>] [model <hwmodel>] [serial <serial>]
    [license <name> ...]
    [node <hwtype>[,<hwmodel>[,<serial>]] ...]
    # MGMT port
    [mgmt_ipaddress=<ip/prefix>] [mgmt_gateway=<ip>] [mgmt_vlan_id=<1-4094>]
    [mgmt_ipv6addr=<addr/prefix>] [mgmt_ipv6gateway=<ip6>]
    # HA pair
    [router_id=<1-255>]
    [ha_node=<lan1_ip>,<ha_ip>[,<mgmt_ip>] ...]   # exactly two
    [master_candidate=<true|false>]
    # LAN2 port
    [lan2_ipaddress=<ip/prefix>] [lan2_gateway=<ip>]
    [lan2_vlan_id=<1-4094>] [lan2_router_id=<1-255>]
    # Port redundancy (LAN1/LAN2 failover)
    [port_redundancy=<true|false>] [port_redundancy_primary=<true|false>]
    [default_route_failover=<true|false>]
```

**WAPI:** `POST member`

=== "Command"
    ```
    configure grid Infoblox member add newmember.corp.example \
        ipaddress=192.168.1.10/24 gateway=192.168.1.1
    ```
=== "WAPI body"
    ```json
    {
      "host_name": "newmember.corp.example",
      "vip_setting": {
        "address": "192.168.1.10",
        "subnet_mask": "255.255.255.0",
        "gateway": "192.168.1.1"
      }
    }
    ```

See [Pre-Provisioning](#pre-provisioning) below for adding hardware identity and licenses during member creation.

#### VLAN tagging

`vlan_id=` tags LAN1 (the VIP interface); `lan2_vlan_id=` tags LAN2.

```
configure grid Infoblox member add tagged.corp.example \
    ipaddress=10.70.10.5/24 gateway=10.70.10.1 vlan_id=110
```

!!! note "MGMT VLAN is accepted but ignored"
    `mgmt_vlan_id=` is in the WAPI schema and is sent, but NIOS 9.x silently
    drops it - the MGMT port comes back with no `vlan_id`. The request still
    succeeds, so nothing fails loudly; verify with
    `show grid <name> member <fqdn>` if you depend on it.

#### HA pairs

An HA member needs a shared VRRP id and, for each of the two physical nodes,
its LAN1 address and its HA-port address. Pass one `ha_node=` per node:

```
configure grid Infoblox member add ha1.corp.example \
    ipaddress=10.70.20.5/24 gateway=10.70.20.1 router_id=55 \
    ha_node=10.70.20.6,10.70.20.8 \
    ha_node=10.70.20.7,10.70.20.9 \
    platform=VNIOS node=IB-V1425 node=IB-V1425 license=dns license=nios
```

`enable_ha` is set for you. Both nodes' LAN1 and HA addresses must be in the
same subnet as the VIP, or NIOS answers *"Send HA and Grid communication
requires valid LAN1 IPv4 addresses."*

To give an HA member a MGMT port, add a third field to each `ha_node` - the
two nodes need **different** MGMT addresses, in the same subnet as
`mgmt_gateway`:

```
configure grid Infoblox member add ha2.corp.example \
    ipaddress=10.70.20.5/24 gateway=10.70.20.1 router_id=55 \
    ha_node=10.70.20.6,10.70.20.8,10.71.20.6 \
    ha_node=10.70.20.7,10.70.20.9,10.71.20.7 \
    mgmt_ipaddress=10.71.20.5/24 mgmt_gateway=10.71.20.1
```

Sharing one MGMT address across both nodes fails with *"The node 2 address
&lt;ip&gt; is already in use by node 1."*

#### Port redundancy

`port_redundancy=true` makes LAN2 a standby for LAN1. A standby port carries
no address of its own, so do not give it one - NIOS accepts the request and
drops `lan2_ipaddress` silently; the CLI warns when you pass both.

```
configure grid Infoblox member add red1.corp.example \
    ipaddress=10.70.60.5/24 gateway=10.70.60.1 \
    port_redundancy=true port_redundancy_primary=true
```

`port_redundancy` and `default_route_failover` are mutually exclusive - NIOS
rejects the pair, and the CLI catches it before the round trip. Use
`lan2_ipaddress=` (without port redundancy) when LAN2 should be an
independently addressed interface instead of a standby.

!!! note "Hardware fields vary by NIOS version"
    `pre_provisioning.hardware_info` accepts only `hwtype` on NIOS 9.x;
    `hwmodel` and `serial_number` are rejected, and an unknown field aborts
    the whole request. The CLI reads the target grid's schema and drops
    unsupported fields with a warning, so `model=` / `serial=` are safe to
    pass either way.

### configure grid \<name\> member \<name\> modify

**Syntax:**

```
configure grid <name> member <member_name> modify
    [ipaddress=<ip/prefix>]
    [gateway=<ip>]
    [comment=<comment>]
    [name=<new_fqdn>]
```

**WAPI:** `GET member?host_name=<name>` then `PUT <ref>`

```
configure grid Infoblox member gm.corp.example modify comment "Primary grid master"
```

### configure grid \<name\> member \<name\> delete

**Syntax:**

```
configure grid <name> member <member_name> delete
```

**WAPI:** `GET member?host_name=<name>` then `DELETE <ref>`

```
configure grid Infoblox member oldmember.corp.example delete
```

### configure grid \<name\> member \<name\> dns enable/disable

Enable or disable DNS service on a member.

**Syntax:**

```
configure grid <name> member <member_name> dns [enable | disable]
```

**WAPI:** `GET member:dns?host_name=<name>` then `PUT <ref>` with `enable_dns=true/false`

```
configure grid Infoblox member member2.corp.example dns enable
configure grid Infoblox member member2.corp.example dns disable
```

### configure grid \<name\> member \<name\> dhcp enable/disable

Enable or disable DHCP service on a member.

**Syntax:**

```
configure grid <name> member <member_name> dhcp [enable | disable]
```

**WAPI:** `GET member:dhcp?host_name=<name>` then `PUT <ref>` with `enable_dhcp=true/false`

```
configure grid Infoblox member member2.corp.example dhcp enable
```

---

## NS Groups

### show zone ns_group

**Syntax:**

```
show zone ns_group [<name>]
```

**WAPI:** `GET nsgroup`

```
show zone ns_group
name=primary-ns
name=secondary-ns comment=Offsite secondaries
```

### configure nsgroup add

**Syntax:**

```
configure nsgroup add <name>
    [primary=<fqdn>]
    [secondary=<fqdn> ...]
```

**WAPI:** `POST nsgroup`

```
configure nsgroup add primary-ns \
    primary=gm.corp.example \
    secondary=member2.corp.example
```

### configure nsgroup \<name\> modify

**Syntax:**

```
configure nsgroup <name> modify
    [primary=<fqdn>]
    [secondary=<fqdn> ...]
```

**WAPI:** `GET nsgroup?name=<name>` then `PUT <ref>`

```
configure nsgroup primary-ns modify secondary=member3.corp.example
```

### configure nsgroup \<name\> delete

**Syntax:**

```
configure nsgroup <name> delete
```

**WAPI:** `GET nsgroup?name=<name>` then `DELETE <ref>`

```
configure nsgroup primary-ns delete
```

---

## DNS Views

### configure view add

**Syntax:**

```
configure view add <name> [comment=<comment>]
```

**WAPI:** `POST view`

```
configure view add external comment "Internet-facing view"
configure view add internal
```

### configure view \<name\> delete

**Syntax:**

```
configure view <name> delete
```

**WAPI:** `GET view?name=<name>` then `DELETE <ref>`

```
configure view external delete
```

---

## Shared Record Groups

### show zone shared_record_group

**Syntax:**

```
show zone shared_record_group [<name>]
```

**WAPI:** `GET sharedrecordgroup`

### configure shared_record_group add

**Syntax:**

```
configure shared_record_group add <name> [comment=<comment>]
```

**WAPI:** `POST sharedrecordgroup`

```
configure shared_record_group add common-records comment "Shared across all views"
```

### configure shared_record_group \<name\> delete

**Syntax:**

```
configure shared_record_group <name> delete
```

**WAPI:** `GET sharedrecordgroup?name=<name>` then `DELETE <ref>`

```
configure shared_record_group common-records delete
```

---

## Pre-Provisioning

!!! note "Two-step operation with rollback"
    Pre-provisioning runs as POST (create member) then PUT (set
    pre_provisioning/platform/enable_ha). If the PUT fails, ibcli
    DELETEs the just-created member to clean up - you won't be
    left with a half-configured member on most failures. If the
    cleanup DELETE also fails, ibcli prints a manual-delete hint.

NIOS lets you register a member's hardware identity and licenses in the grid master **before** the appliance
physically boots. When the appliance powers on and phones home, it matches the pre-provisioning record and receives
its configuration automatically.

!!! note "platform vs hwtype"
    NIOS uses two separate enums:

    - **`platform`** - the broad category at the member top level.
      Values: `INFOBLOX` (physical), `VNIOS` (virtual), `CISCO`,
      `RIVERBED`, `IBVM`.
    - **`hwtype`** - the specific hardware SKU inside
      `pre_provisioning.hardware_info`. Values: `IB-815`, `IB-V4126`,
      `CP-V1405`, etc. - see your grid's schema for the full list.

    You need to specify BOTH when pre-provisioning a typical member.
    Example: `platform VNIOS hwtype IB-V4126`.

### Keywords

| Keyword | Description |
|---------|-------------|
| `platform <platform>` | Top-level member platform category (passed verbatim to NIOS). Values: `INFOBLOX` (physical appliance), `VNIOS` (virtual), `CISCO`, `RIVERBED`, `IBVM`. |
| `hwtype <hwtype>` | Hardware SKU for `pre_provisioning.hardware_info[0].hwtype` (passed verbatim to NIOS). Values: `IB-815`, `IB-V4126`, `CP-V1405`, etc. - see your grid's schema. |
| `model <hwmodel>` | Hardware model for `pre_provisioning.hardware_info[0].hwmodel`, e.g. `IB-V1425`, `TE-825` (case-sensitive) |
| `serial <serial>` | Serial number of the appliance (case-sensitive) |
| `license <name>` | License to activate (repeatable; value passed verbatim to NIOS). |
| `node <hwtype>,<hwmodel>,<serial>` | Additional hardware entry (repeatable, for HA pairs). The first element is the hardware SKU (`hwtype`), not the platform category. All values are passed verbatim to NIOS. |

If any of `hwtype`, `model`, `serial`, `license`, or `node` is present, a `pre_provisioning` block is added to the WAPI body. `platform` alone sets only the top-level field with no `pre_provisioning`.

When two or more hardware entries are present (i.e. `hwtype`/`model`/`serial` plus one or more `node` keywords), `enable_ha: true` is automatically set at the top level of the member body.

!!! warning "License values are case-sensitive"
    NIOS license enum values are lowercase. Valid values include
    (verify against your grid's pool): `dns`, `dhcp`, `nios`, `vnios`,
    `enterprise`, `cloud_api`, `dtc`, `rpz`, `fireeye`, `ms_management`,
    `sw_tp`, `tp_sub`. Pass them exactly as NIOS expects them. If
    you pass an unknown or wrong-case value, the PUT will fail and
    ibcli will delete the just-created member.

### Single node - add with pre-provisioning

```
configure grid Infoblox member add dns1.example.com \
    ipaddress 10.0.0.5/24 gateway 10.0.0.1 \
    platform VNIOS hwtype IB-V4126 license enterprise license dns license dhcp
```

**Step 1 - `POST /wapi/vX.Y/member`:**

```json
{
  "host_name": "dns1.example.com",
  "vip_setting": {"address": "10.0.0.5", "subnet_mask": "255.255.255.0", "gateway": "10.0.0.1"}
}
```

**Step 2 - `PUT /wapi/vX.Y/<returned-ref>`:**

```json
{
  "platform": "VNIOS",
  "pre_provisioning": {
    "hardware_info": [
      {"hwtype": "IB-V4126"}
    ],
    "licenses": ["enterprise", "dns", "dhcp"]
  }
}
```

If the PUT fails, ibcli immediately issues `DELETE <ref>` to remove the member created in step 1.

### HA pair - two hardware_info entries

Use `node <hwtype>,<hwmodel>,<serial>` to add the second node. The primary node is described by
`hwtype`/`model`/`serial`; each `node` keyword adds a further entry. Note: the first element of the `node` triple is
the hardware SKU (`hwtype`), not the `platform` category.

```
configure grid Infoblox member add dns1.example.com \
    ipaddress 10.0.0.5/24 gateway 10.0.0.1 \
    platform VNIOS hwtype IB-V4126 model IB-V1425 serial primary-sn \
    node IB-V4126,IB-V1425,secondary-sn \
    license vnios license enterprise
```

!!! warning "Always set `gateway` when you set `ipaddress`"
    Without a default route the member will boot but can't reach the grid master to complete joining. ibcli prints a warning if `ipaddress` is set without `gateway`.

**Step 1 - `POST /wapi/vX.Y/member`:**

```json
{
  "host_name": "dns1.example.com",
  "vip_setting": {"address": "10.0.0.5", "subnet_mask": "255.255.255.0"}
}
```

**Step 2 - `PUT /wapi/vX.Y/<returned-ref>`:**

```json
{
  "platform": "VNIOS",
  "enable_ha": true,
  "pre_provisioning": {
    "hardware_info": [
      {"hwtype": "IB-V4126", "hwmodel": "IB-V1425", "serial_number": "primary-sn"},
      {"hwtype": "IB-V4126", "hwmodel": "IB-V1425", "serial_number": "secondary-sn"}
    ],
    "licenses": ["vnios", "enterprise"]
  }
}
```

### configure grid \<name\> member \<name\> preprovision

Set (or update) pre-provisioning on an **existing** member - useful when the appliance arrives after the member was already created.

**Syntax:**

```
configure grid <name> member <member_name> preprovision
    [platform <platform>]
    [hwtype <hwtype>]
    [model <hwmodel>]
    [serial <serial>]
    [license <name> ...]
    [node <hwtype>,<hwmodel>,<serial> ...]
```

**WAPI:** `GET member?host_name=<name>` then `PUT <ref>` with `pre_provisioning`

```
configure grid Infoblox member dns1.example.com preprovision \
    platform VNIOS hwtype IB-V4126 model IB-V1425 serial abc123 \
    license vnios license dns
```

### show grid \<name\> member output

When a member has pre-provisioning data, `show grid <name> member <name>` prints it below the host line:

```
host_name=dns1.example.com address=10.0.0.5
  pre_provisioning:
    hardware: IB-VNIOS / IB-V1425 / abc123
    hardware: IB-VNIOS / IB-V1425 / secondary-sn
    licenses: vnios enterprise dns dhcp
```

---

## Related commands

- [Zones](zones.md) - `ns_group=` parameter references NS groups created here.
- [Restart](restart.md) - restart DNS/DHCP services on grid members.
