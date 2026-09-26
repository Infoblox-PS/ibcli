# Network Containers

Network containers are supernet CIDRs used as IPAM parent blocks. They do not serve DHCP - they act as organisational buckets from which sub-networks can be carved.

## show network container

**Syntax:**

```
show network container [<n.n.n.n/mm>] [view=<name>]
```

**WAPI:** `GET networkcontainer` / `GET ipv6networkcontainer` (paginated)

=== "List all"
    ```
    show network container
    ```
=== "Output"
    ```
    network=10.0.0.0/8 view=default comment=RFC1918 block
    network=172.16.0.0/12 view=default
    network=2001:db8::/32 view=default
    ```

=== "Specific container"
    ```
    show network container 10.0.0.0/8
    ```
=== "Output"
    ```
    network=10.0.0.0/8 view=default comment=RFC1918 block
    ```

## configure network container add

**Syntax:**

```
configure network container add <n.n.n.n/mm>
    [comment=<comment>]
    [view=<name>]
    [set <key> <value> ...]
```

**WAPI:** `POST networkcontainer` (IPv4) or `POST ipv6networkcontainer` (IPv6)

=== "IPv4 container"
    ```
    configure network container add 10.0.0.0/8 comment "RFC1918"
    ```
=== "IPv6 container"
    ```
    configure network container add 2001:db8::/32
    ```

The address family is auto-detected from the CIDR format. IPv6 CIDRs are routed to `ipv6networkcontainer`.

With extensible attributes:

```
configure network container add 172.16.0.0/12 set Region EU
```

## configure network container \<cidr\> modify

**Syntax:**

```
configure network container <n.n.n.n/mm> modify
    [comment=<comment>]
    [view=<name>]
    [set <key> <value> ...]
```

**WAPI:** `GET networkcontainer?network=<cidr>` then `PUT <ref>`

```
configure network container 10.0.0.0/8 modify comment "Main RFC1918 block"
```

## configure network container \<cidr\> delete

**Syntax:**

```
configure network container <n.n.n.n/mm> delete [view=<name>]
```

**WAPI:** `GET networkcontainer?network=<cidr>` then `DELETE <ref>`

```
configure network container 172.16.0.0/12 delete
```

## IPAM: next available network from a container

Use `show network <cidr> ipam next_network` to find the next free sub-network within a container. See [Networks - IPAM](networks.md#ipam-next-available-network) for details.

## Related commands

- [Networks](networks.md) - leaf-level networks within containers.
- [Shared Networks](shared-networks.md) - logical groupings that span multiple leaf networks.
