# DHCP Leases

The `show lease` command provides read-only access to active DHCP lease information.

## show lease

**Syntax:**

```
show lease [<ip>]
```

**WAPI:** `GET lease`

=== "List all leases"
    ```
    show lease
    ```
=== "Output"
    ```
    address=10.1.0.15 state=ACTIVE mac=aa:bb:cc:dd:ee:ff hostname=laptop01
    address=10.1.0.22 state=ACTIVE mac=11:22:33:44:55:66 hostname=workstation07
    address=10.2.0.100 state=EXPIRED mac=00:11:22:33:44:55
    ```

=== "Specific IP"
    ```
    show lease 10.1.0.15
    ```
=== "Output"
    ```
    address=10.1.0.15 state=ACTIVE mac=aa:bb:cc:dd:ee:ff hostname=laptop01
    ```

## Output fields

| Field | Description |
|---|---|
| `address` | Leased IP address |
| `state` | Binding state: `ACTIVE`, `EXPIRED`, `RELEASED`, etc. |
| `mac` | Hardware address |
| `hostname` | Client-supplied hostname (when available) |

## Notes

!!! note
    Lease data is read-only. ibcli provides no command to create or force-expire leases; those operations must be done through the NIOS GUI or direct WAPI calls.

!!! warning
    On large grids, `show lease` without a filter can return thousands of records. The `get` call (no pagination)
    is used for leases, so very large grids may time out. Use the specific-IP form for targeted lookups.

## Download lease history

To download the full historical lease database (not just currently active leases), use the file operations commands:

```
download lease_history /tmp/lease-history.csv
```

See [Files](files.md) for details.

## Related commands

- [DHCP Ranges](dhcp-ranges-fixed.md) - configure the ranges that generate these leases.
- [Files](files.md) - download historical lease data.
