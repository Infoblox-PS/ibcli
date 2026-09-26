# Shared Networks

A shared network is a logical grouping of leaf networks that share a single broadcast domain. DHCP serves them as one pool.

## show network shared

**Syntax:**

```
show network shared [<name>] [view=<name>]
```

**WAPI:** `GET sharednetwork`

=== "List all"
    ```
    show network shared
    ```
=== "Output"
    ```
    name=building-a view=default
    name=building-b view=default comment=Annex
    ```

=== "Specific shared network"
    ```
    show network shared building-a
    ```

## configure network add shared

Create a shared network, optionally associating existing member networks.

**Syntax:**

```
configure network add shared <name>
    [comment=<comment>]
    [view=<name>]
    [network=<n.n.n.n/mm> ...]
    [set <key> <value> ...]
```

**WAPI:** `POST sharednetwork`

For each `network=<cidr>` given, ibcli looks up the WAPI `_ref` of that network and adds it to the `networks` list in the POST body.

=== "Create empty shared network"
    ```
    configure network add shared building-a
    ```
=== "With member networks"
    ```
    configure network add shared building-a \
        network=192.168.10.0/24 \
        network=192.168.11.0/24
    ```
=== "With comment and view"
    ```
    configure network add shared building-a comment "Main campus" view=internal
    ```

!!! note
    Member networks must already exist in WAPI. ibcli resolves them by `network=<cidr>` before creating the shared network. If a member network is not found, the command fails before creating the shared network.

## configure shared_network \<name\> delete

Delete a shared network by name.

**Syntax:**

```
configure shared_network <name> delete [view=<name>]
```

**WAPI:** `GET sharednetwork?name=<name>` then `DELETE <ref>`

```
configure shared_network building-a delete
configure shared_network building-b delete view=internal
```

Note the different command shape: deletion uses `configure shared_network` (with underscore), not `configure network shared`.

## Related commands

- [Networks](networks.md) - the leaf networks that belong to a shared network.
- [DHCP Ranges](dhcp-ranges-fixed.md) - ranges are configured on the leaf networks, not the shared network.
