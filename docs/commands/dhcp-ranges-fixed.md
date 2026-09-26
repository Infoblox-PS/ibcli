# DHCP Ranges and Fixed Addresses

## DHCP Ranges

A DHCP range defines a pool of IPs within a network that the DHCP server dynamically assigns.

### show range

**Syntax:**

```
show range [<n.n.n.n/mm>]
```

**WAPI:** `GET range`

=== "List all ranges"
    ```
    show range
    ```
=== "Output"
    ```
    network=10.1.0.0/24 start=10.1.0.10 end=10.1.0.200 member=10.0.0.1
    network=10.2.0.0/24 start=10.2.0.50 end=10.2.0.150 failover=primary-failover
    ```

=== "Ranges in a specific network"
    ```
    show range 10.1.0.0/24
    ```

### configure network \<cidr\> range add

**Syntax:**

```
configure network <n.n.n.n/mm> range add <startip> <endip>
    [comment=<comment>]
    [member=<ip>]
    [failover=<name>]
    [view=<name>]
```

**WAPI:** `POST range`

=== "Command"
    ```
    configure network 10.1.0.0/24 range add 10.1.0.10 10.1.0.200
    ```
=== "WAPI body"
    ```json
    {
      "network": "10.1.0.0/24",
      "start_addr": "10.1.0.10",
      "end_addr": "10.1.0.200"
    }
    ```

Assign to a specific DHCP member:

```
configure network 10.1.0.0/24 range add 10.1.0.10 10.1.0.200 member=192.168.1.5
```

Assign to a failover association (takes precedence over `member=`):

```
configure network 10.1.0.0/24 range add 10.1.0.10 10.1.0.200 failover=primary-failover
```

With a comment:

```
configure network 10.1.0.0/24 range add 10.1.0.10 10.1.0.200 comment "Server range"
```

### configure network \<cidr\> range delete

**Syntax:**

```
configure network <n.n.n.n/mm> range delete <startip> <endip> [view=<name>]
```

**WAPI:** `GET range?start_addr=<s>&end_addr=<e>` then `DELETE <ref>`

```
configure network 10.1.0.0/24 range delete 10.1.0.10 10.1.0.200
```

---

## Fixed Addresses

A fixed address reserves a specific IP for a host identified by MAC address.

### show fixed

**Syntax:**

```
show fixed [<ip>]
```

**WAPI:** `GET fixedaddress`

=== "List all"
    ```
    show fixed
    ```
=== "Output"
    ```
    network=10.1.0.0/24 ip=10.1.0.50 mac=aa:bb:cc:dd:ee:ff name=printer
    network=10.2.0.0/24 ip=10.2.0.1 mac=11:22:33:44:55:66
    ```

=== "Specific IP"
    ```
    show fixed 10.1.0.50
    ```

### configure network \<cidr\> fixed add

**Syntax:**

```
configure network <n.n.n.n/mm> fixed add <ip> <mac>
    [name=<name>]
    [comment=<comment>]
    [view=<name>]
```

**WAPI:** `POST fixedaddress`

MAC addresses may include colons or be bare hex - ibcli normalises them to colon-separated lowercase.

=== "Command"
    ```
    configure network 10.1.0.0/24 fixed add 10.1.0.50 aa:bb:cc:dd:ee:ff
    ```
=== "WAPI body"
    ```json
    {
      "ipv4addr": "10.1.0.50",
      "mac": "aa:bb:cc:dd:ee:ff",
      "match_client": "MAC_ADDRESS"
    }
    ```

With name and comment:

```
configure network 10.1.0.0/24 fixed add 10.1.0.50 aabbccddeeff \
    name=printer comment="Lobby printer"
```

The bare hex MAC `aabbccddeeff` is normalised to `aa:bb:cc:dd:ee:ff`.

### configure network \<cidr\> fixed delete

**Syntax:**

```
configure network <n.n.n.n/mm> fixed delete <ip> [view=<name>]
```

**WAPI:** `GET fixedaddress?ipv4addr=<ip>` then `DELETE <ref>`

```
configure network 10.1.0.0/24 fixed delete 10.1.0.50
```

---

## Fixed-Address Templates

Templates define a prototype fixed-address with an offset, usable in bulk provisioning.

### show template fixed

**Syntax:**

```
show template fixed [<name>]
```

**WAPI:** `GET fixedaddresstemplate`

```
show template fixed
show template fixed my-printer-template
```

### configure template fixed add

**Syntax:**

```
configure template fixed add <name>
    [offset=<num>]
    [comment=<comment>]
```

**WAPI:** `POST fixedaddresstemplate`

```
configure template fixed add printer-template offset=50 comment="Printer fixed address"
```

### configure template fixed delete

**Syntax:**

```
configure template fixed delete <name>
```

**WAPI:** `GET fixedaddresstemplate?name=<name>` then `DELETE <ref>`

```
configure template fixed delete printer-template
```

## Related commands

- [DHCP Failover](dhcp-failover-options.md) - create the failover associations referenced by `failover=`.
- [MAC Filters](dhcp-mac-filters.md) - alternative to per-IP fixed addresses for class-based assignment.
