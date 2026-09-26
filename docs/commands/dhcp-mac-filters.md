# DHCP MAC Filters

MAC filters let you permit or deny DHCP leases based on hardware address. A filter is a named list of MAC addresses; networks and ranges reference the filter by name.

## MAC Filter lifecycle

1. Create the filter: `configure network macfilter add <name>`
2. Add MAC addresses to it: `configure network filter <name> add macaddress <mac>`
3. Assign the filter to a range or network (via the WAPI GUI or a direct WAPI call - ibcli does not yet have a `configure network range set filter` command).

---

## show network filter

List all MAC filters, or show MAC addresses in a specific filter.

**Syntax:**

```
show network filter [<name>]
```

**WAPI:** `GET filtermac` (list) or `GET macfilteraddress?filter=<ref>` (addresses)

=== "List all filters"
    ```
    show network filter
    ```
=== "Output"
    ```
    name=allowed-printers
    name=blocked-devices comment=Blacklist
    ```

=== "Show addresses in a filter"
    ```
    show network filter allowed-printers
    ```
=== "Output"
    ```
    mac=aa:bb:cc:dd:ee:ff
    mac=11:22:33:44:55:66 comment=Lobby printer
    ```

---

## configure network macfilter add

Create a new MAC filter.

**Syntax:**

```
configure network macfilter add <name>
```

**WAPI:** `POST filtermac`

```
configure network macfilter add allowed-printers
configure network macfilter add blocked-devices
```

## configure network macfilter delete

Delete a MAC filter (and all its MAC address entries).

**Syntax:**

```
configure network macfilter delete <name>
```

**WAPI:** `GET filtermac?name=<name>` then `DELETE <ref>`

```
configure network macfilter delete blocked-devices
```

!!! note
    Deleting a filter while it is referenced by a range or network may leave those objects with a dangling filter reference. Remove the filter reference from the range first.

---

## configure network filter \<name\> add macaddress

Add a MAC address to an existing filter.

**Syntax:**

```
configure network filter <name> add macaddress <mac>
    [comment=<comment>]
```

**WAPI:** Resolves the filter `_ref`, then `POST macfilteraddress`

MAC addresses are normalised to colon-separated lowercase by ibcli.

=== "Command"
    ```
    configure network filter allowed-printers add macaddress aa:bb:cc:dd:ee:ff
    ```
=== "With comment"
    ```
    configure network filter allowed-printers add macaddress aa:bb:cc:dd:ee:ff \
        comment "Lobby printer"
    ```
=== "Bare hex (normalised)"
    ```
    configure network filter allowed-printers add macaddress aabbccddeeff
    ```

## configure network filter \<name\> delete macaddress

Remove a MAC address from a filter.

**Syntax:**

```
configure network filter <name> delete macaddress <mac>
```

**WAPI:** Resolves the filter `_ref`, looks up `macfilteraddress?mac=<mac>&filter=<ref>`, then `DELETE <addr_ref>`

```
configure network filter allowed-printers delete macaddress aa:bb:cc:dd:ee:ff
```

## Related commands

- [DHCP Ranges](dhcp-ranges-fixed.md) - ranges that reference MAC filters for access control.
- [Fixed Addresses](dhcp-ranges-fixed.md) - per-IP reservations (alternative to filter-based assignment).
