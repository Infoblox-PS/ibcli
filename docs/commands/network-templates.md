# Network Templates

Network templates define a prototype CIDR size that IPAM uses when allocating new networks from a container. They are referenced by `next_available_network` calls.

## show template network

**Syntax:**

```
show template network [<name>]
```

**WAPI:** `GET networktemplate`

=== "List all"
    ```
    show template network
    ```
=== "Output"
    ```
    name=small-subnet cidr=24
    name=medium-subnet cidr=22 comment=For branch offices
    ```

=== "Specific template"
    ```
    show template network small-subnet
    ```
=== "Output"
    ```
    name=small-subnet cidr=24
    ```

## configure template network add

**Syntax:**

```
configure template network add <name> cidr <num>
    [comment=<comment>]
    [set <key> <value> ...]
```

**WAPI:** `POST networktemplate`

The `cidr` value is the prefix length (integer) for networks allocated from this template.

=== "Command"
    ```
    configure template network add small-subnet cidr 24
    ```
=== "WAPI body"
    ```json
    {"name": "small-subnet", "cidr": 24}
    ```

With comment and extensible attributes:

```
configure template network add branch-office cidr 25 \
    comment "Branch /25 allocation" set Region EU
```

!!! warning "Set-chain depth cap"
    At most 4 `set key=value` pairs are accepted. See [Extensible Attributes](../user-guide/extensible-attributes.md).

## configure template network \<name\> delete

**Syntax:**

```
configure template network <name> delete
```

**WAPI:** `GET networktemplate?name=<name>` then `DELETE <ref>`

```
configure template network small-subnet delete
```

## Related commands

- [Networks - IPAM](networks.md#ipam-next-available-network) - use `next_available_network` to allocate from a container.
- [Network Containers](network-containers.md) - containers hold available address space.
