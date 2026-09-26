# Zones

DNS zone management covers authoritative, forward, delegated, and stub zones.

## show zone

List all zones or show a specific zone.

**Syntax:**

```
show zone [<zone>] [view=<name>] [forward] [secondary] [detailed]
```

**WAPI:** `GET zone_auth` / `zone_forward` / `zone_delegated` / `zone_stub`

Without arguments, ibcli queries all four zone types in fallback order and prints every zone found.

=== "Command"
    ```
    show zone
    ```
=== "Output"
    ```
    type=auth fqdn=corp.example view=default
    type=auth fqdn=1.168.192.in-addr.arpa view=default
    type=forward fqdn=external.corp.example view=default
    ```

Show a specific zone:

=== "Command"
    ```
    show zone corp.example
    ```
=== "Output"
    ```
    type=auth fqdn=corp.example view=default comment=Main corporate zone
    ```

Show only forward zones:

=== "Command"
    ```
    show zone forward
    ```
=== "Output"
    ```
    type=forward fqdn=external.corp.example view=default
    ```

Filter by view:

```
show zone view=external
```

## configure zone add

Add a new DNS zone.

**Syntax:**

```
configure zone add <zone>
    [comment=<comment>]
    [primary=<name>]
    [secondary=<name>]
    [ns_group=<name>]
    [view=<name>]
    [forward_to=<name,ip>]
    [delegate_to=<name,ip>]
    [stub_from=<name,ip>]
    [set <key> <value> ...]
```

**WAPI:** `POST zone_auth` / `zone_forward` / `zone_delegated` / `zone_stub` (selected automatically)

**Zone type selection:**

| Keyword present | WAPI object |
|---|---|
| `forward_to=` | `zone_forward` |
| `delegate_to=` | `zone_delegated` |
| `stub_from=` | `zone_stub` |
| (none of the above) | `zone_auth` |

**Examples:**

Add an authoritative zone:

=== "Command"
    ```
    configure zone add example.com
    ```
=== "Equivalent WAPI"
    ```
    POST /wapi/v2.12/zone_auth
    {"fqdn": "example.com"}
    ```

Add a zone with a comment and NS group:

```
configure zone add example.com comment "Primary zone" ns_group=primary-ns
```

Add a forward zone:

```
configure zone add external.example.com forward_to=ns1.upstream.net,1.2.3.4
```

Multiple forwarders:

```
configure zone add external.example.com \
    forward_to=ns1.upstream.net,1.2.3.4 \
    forward_to=ns2.upstream.net,1.2.3.5
```

Add a reverse zone (CIDR auto-converts to arpa form):

=== "Command"
    ```
    configure zone add 192.168.1.0/24
    ```
=== "Effective zone name"
    ```
    1.168.192.in-addr.arpa
    ```

Add an authoritative zone with secondary members:

```
configure zone add example.com primary=member1.corp.example secondary=member2.corp.example
```

!!! note "Set-chain depth cap"
    Up to 16 `set key=value` pairs are accepted per command. See [Extensible Attributes](../user-guide/extensible-attributes.md).

## configure zone \<zone\> modify

Modify an existing zone.

**Syntax:**

```
configure zone <zone> modify
    [comment=<comment>]
    [primary=<name>]
    [secondary=<name>]
    [ns_group=<name>]
    [view=<name>]
    [set <key> <value> ...]
```

**WAPI:** `GET <zone_type>?fqdn=<zone>` then `PUT <ref>`

ibcli looks up the zone reference across all four zone types (auth → forward → delegated → stub) before issuing the PUT.

=== "Command"
    ```
    configure zone example.com modify comment "Updated zone"
    ```
=== "Steps"
    ```
    GET zone_auth?fqdn=example.com  → ref
    PUT zone_auth/<ref> {"comment": "Updated zone"}
    ```

Change the NS group:

```
configure zone example.com modify ns_group=secondary-ns
```

## configure zone \<zone\> delete

Delete a zone.

**Syntax:**

```
configure zone <zone> delete [view=<name>]
```

**WAPI:** `GET <zone_type>?fqdn=<zone>` then `DELETE <ref>`

=== "Command"
    ```
    configure zone old.example.com delete
    ```
=== "With view"
    ```
    configure zone old.example.com delete view=external
    ```

!!! note
    The zone type is auto-detected by searching zone_auth, then zone_forward, zone_delegated, zone_stub. The first match is deleted.

## show zone ns_group

List or show a specific NS group.

**Syntax:**

```
show zone ns_group [<name>]
```

**WAPI:** `GET nsgroup`

```
show zone ns_group
show zone ns_group primary-ns
```

## show zone shared_record_group

**Syntax:**

```
show zone shared_record_group [<name>]
```

**WAPI:** `GET sharedrecordgroup`

## Related commands

- [Records](records.md) - add/delete DNS records within zones.
- [Grid](grid.md) - configure NS groups and views.
