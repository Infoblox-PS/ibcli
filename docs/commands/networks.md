# Networks

Network management covers IPv4 and IPv6 networks, IPAM operations (next available IP/network), and network reassignment.

## show network

List all networks or show a specific network.

**Syntax:**

```
show network [<n.n.n.n/mm>] [view=<name>]
```

**WAPI:** `GET network` / `GET ipv6network` (paginated)

=== "List all"
    ```
    show network
    ```
=== "Output"
    ```
    network=10.0.0.0/8 view=default
    network=192.168.1.0/24 view=default comment=Server subnet
    network=2001:db8::/32 view=default
    ```

=== "Specific network"
    ```
    show network 192.168.1.0/24
    ```
=== "Output"
    ```
    network=192.168.1.0/24 view=default comment=Server subnet
    ```

IPv4 vs IPv6 is auto-detected from the CIDR address family.

## configure network add

Add a new network.

**Syntax:**

```
configure network add <n.n.n.n/mm>
    [comment=<comment>]
    [view=<name>]
    [set <key> <value> ...]
    [member <ip> [member <ip> ...]]
```

**WAPI:** `POST network` (IPv4) or `POST ipv6network` (IPv6)

=== "IPv4"
    ```
    configure network add 10.1.0.0/24 comment "Dev network"
    ```
=== "IPv6"
    ```
    configure network add 2001:db8:1::/48
    ```
=== "With view"
    ```
    configure network add 172.16.0.0/16 view=internal
    ```
=== "With DHCP members"
    ```
    configure network add 10.1.0.0/24 comment "subnet-01" member 10.0.0.1 member 10.0.0.2
    ```

With extensible attributes:

```
configure network add 10.2.0.0/24 set Site NYC set Team ops
```

### Assigning DHCP members at creation time

The `member <ip>` keyword is repeatable - you can specify up to 5 member IPs on a
single `add` line. Each IP is submitted as a `dhcpmember` struct in the WAPI POST body.

!!! note "Failover-backed ranges"
    For failover-backed DHCP ranges, **both** failover peers must be assigned as
    members on the network before a range using that failover association can be
    created. Using `member` at creation time sets this up in a single command,
    eliminating the separate `configure network <cidr> move member …` step.

    ```
    configure network add 10.1.0.0/24 comment "subnet-01" member 10.0.0.1 member 10.0.0.2
    configure network 10.1.0.0/24 range add 10.1.0.10 10.1.0.200 failover mainfo
    ```

## configure network \<cidr\> modify

Modify an existing network's comment or extensible attributes.

**Syntax:**

```
configure network <n.n.n.n/mm> modify
    [comment=<comment>]
    [view=<name>]
    [set <key> <value> ...]
```

**WAPI:** `GET network?network=<cidr>` then `PUT <ref>`

```
configure network 10.1.0.0/24 modify comment "Updated dev network"
configure network 10.1.0.0/24 modify set Owner alice
```

## configure network \<cidr\> delete

Delete a network.

**Syntax:**

```
configure network <n.n.n.n/mm> delete [view=<name>]
```

**WAPI:** `GET network?network=<cidr>` then `DELETE <ref>`

```
configure network 10.1.0.0/24 delete
configure network 10.1.0.0/24 delete view=internal
```

## configure network \<cidr\> split

Split a network into sub-networks at a new prefix length.

**Syntax:**

```
configure network <n.n.n.n/mm> split <num>
```

**WAPI:** `POST <ref>?_function=split_network` with `cidr=<new_prefix>`

=== "Command"
    ```
    configure network 10.0.0.0/23 split 24
    ```
=== "Effect"
    ```
    10.0.0.0/23  →  10.0.0.0/24 + 10.0.1.0/24
    ```

`<num>` is the new prefix length (must be larger than the current prefix).

## configure network \<cidr\> join

Join two adjacent sibling networks into their parent CIDR.

**Syntax:**

```
configure network <n.n.n.n/mm> join <n.n.n.n/mm>
```

**WAPI:** Deletes both child networks, then creates the parent.

=== "Command"
    ```
    configure network 10.0.0.0/24 join 10.0.1.0/24
    ```
=== "Effect"
    ```
    10.0.0.0/24 + 10.0.1.0/24  →  10.0.0.0/23
    ```

!!! warning "Partial state risk"
    If deletion of the second network fails after the first has been deleted, ibcli prints a `PARTIAL STATE` error with instructions to recover manually. The operation is not atomic.

The two networks must:

- Have the same prefix length.
- Be adjacent siblings (same parent supernet).
- Both exist in WAPI.

## configure network \<cidr\> move

Reassign DHCP member(s) or a failover association to a network.

**Syntax (member):**

```
configure network <n.n.n.n/mm> move member <ip> [member <ip> ...]
```

**Syntax (failover):**

```
configure network <n.n.n.n/mm> move failover <name>
```

**WAPI:** `PUT <ref>` with updated `members` or `failover_association`

=== "Single member"
    ```
    configure network 10.1.0.0/24 move member 192.168.1.5
    ```
=== "Multiple members"
    ```
    configure network 10.1.0.0/24 move member 192.168.1.5 member 192.168.1.6
    ```
=== "Failover association"
    ```
    configure network 10.1.0.0/24 move failover primary-failover
    ```

## IPAM - next available IP

Find the next available IP address in a network.

**Syntax:**

```
show network <n.n.n.n/mm> ipam next_available [<num>]
```

**WAPI:** `POST <ref>?_function=next_available_ip`

=== "One IP"
    ```
    show network 10.1.0.0/24 ipam next_available
    ```
=== "Output"
    ```
      10.1.0.5
    ```

=== "Multiple IPs"
    ```
    show network 10.1.0.0/24 ipam next_available 3
    ```
=== "Output"
    ```
      10.1.0.5
      10.1.0.6
      10.1.0.7
    ```

## IPAM - next available network

Find the next available sub-network from a container.

**Syntax:**

```
show network <n.n.n.n/mm> ipam next_network </cidr>
```

**WAPI:** `POST networkcontainer/<ref>?_function=next_available_network`

=== "Command"
    ```
    show network 10.0.0.0/8 ipam next_network /24
    ```
=== "Output"
    ```
      10.0.0.0/24
    ```

## show network statistics

Show IPAM utilization statistics for a network.

**Syntax:**

```
show network <n.n.n.n/mm> statistics
show network statistics <n.n.n.n/mm>
```

**WAPI:** `GET ipam:statistics?network=<cidr>`

=== "Command"
    ```
    show network 10.1.0.0/24 statistics
    ```
=== "Output"
    ```
      total_count=254
      used_count=42
      unmanaged_count=0
    ```

## Related commands

- [Network Containers](network-containers.md) - supernet containers for IPAM.
- [Shared Networks](shared-networks.md) - logical groupings across subnets.
- [DHCP Ranges](dhcp-ranges-fixed.md) - add DHCP ranges within networks.
