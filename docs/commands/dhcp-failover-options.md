# DHCP Failover, Option Spaces, and Option Definitions

## Failover Associations

A failover association pairs two DHCP members (primary + secondary) for high-availability DHCP. Networks and ranges reference the association by name.

### show network failover

**Syntax:**

```
show network failover [<name>]
```

**WAPI:** `GET dhcpfailover`

=== "List all"
    ```
    show network failover
    ```
=== "Output"
    ```
    name=primary-failover primary=192.168.1.5 secondary=192.168.1.6
    name=branch-failover primary=10.0.0.1 secondary=10.0.0.2
    ```

=== "Specific association"
    ```
    show network failover primary-failover
    ```

### configure network failover add

**Syntax:**

```
configure network failover add <name>
    primary <ip>
    secondary <ip>
```

**WAPI:** `POST dhcpfailover`

Both `primary_server_type` and `secondary_server_type` are always set to `GRID`, meaning the primary and secondary IPs
must be VIPs of members belonging to this Grid. Failover associations with an external DHCP server (`EXTERNAL` server
type) are not currently supported by this command.

=== "Command"
    ```
    configure network failover add primary-failover primary 192.168.1.5 secondary 192.168.1.6
    ```
=== "WAPI body"
    ```json
    {
      "name": "primary-failover",
      "primary_server_type": "GRID",
      "secondary_server_type": "GRID",
      "primary": {"_struct": "dhcpmember", "ipv4addr": "192.168.1.5"},
      "secondary": {"_struct": "dhcpmember", "ipv4addr": "192.168.1.6"}
    }
    ```

### configure network failover delete

**Syntax:**

```
configure network failover delete <name>
```

**WAPI:** `GET dhcpfailover?name=<name>` then `DELETE <ref>`

```
configure network failover delete branch-failover
```

---

## DHCP Option Spaces

Custom option spaces group vendor-specific DHCP options.

### configure option_space add

**Syntax:**

```
configure option_space add <name>
```

**WAPI:** `POST optionspace`

```
configure option_space add cisco-phones
```

---

## DHCP Option Definitions

Option definitions declare custom DHCP option codes and their data types within an option space.

### show network options

List all option definitions.

**Syntax:**

```
show network options
```

**WAPI:** `GET optiondef`

=== "Command"
    ```
    show network options
    ```
=== "Output"
    ```
    name=tftp-server code=66 type=text
    name=vendor-class code=43 type=binary space=cisco-phones
    ```

### configure optiondef add

**Syntax:**

```
configure optiondef add <name> code <num> type <type>
    [space=<name>]
```

**WAPI:** `POST optiondef`

Supported types include: `text`, `ip-address`, `boolean`, `integer-8`, `integer-16`, `integer-32`, `binary`.

=== "Command"
    ```
    configure optiondef add tftp-server code 66 type text
    ```
=== "WAPI body"
    ```json
    {"name": "tftp-server", "code": 66, "type": "text"}
    ```

With a custom option space:

```
configure optiondef add vendor-class code 43 type binary space=cisco-phones
```

## Related commands

- [DHCP Ranges](dhcp-ranges-fixed.md) - assign failover associations to ranges with `failover=<name>`.
- [Networks](networks.md) - assign failover associations to networks with `move failover <name>`.
