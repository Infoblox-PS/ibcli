# Service Restart

ibcli can trigger service restarts on the grid and query restart status.

## restart dns / dhcp / dhcpv4 / dhcpv6 / all

Restart one or more grid services.

**Syntax:**

```
restart {dns | dhcp | dhcpv4 | dhcpv6 | all}
    [delay=<num>]
    [mode=<GROUPED|SEQUENTIAL|SIMULTANEOUS>]
    [option=<FORCE_RESTART|RESTART_IF_NEEDED>]
    [member=<name> ...]
```

**WAPI:** `POST grid/<ref>?_function=restartservices`

| Service keyword | WAPI `services` value |
|---|---|
| `dns` | `DNS` |
| `dhcp` | `DHCP` |
| `dhcpv4` | `DHCPV4` |
| `dhcpv6` | `DHCPV6` |
| `all` | `ALL` |

=== "Restart DNS"
    ```
    restart dns
    ```
=== "WAPI body"
    ```json
    {"services": ["DNS"]}
    ```

With options:

```
restart dns mode=SEQUENTIAL option=RESTART_IF_NEEDED delay=10
```

Target a specific member:

```
restart dhcp member=member2.corp.example
```

Multiple members:

```
restart all member=member1.corp.example member=member2.corp.example
```

**Mode values:**

| Mode | Description |
|---|---|
| `GROUPED` | Restart all members in one grouped operation |
| `SEQUENTIAL` | Restart members one at a time |
| `SIMULTANEOUS` | Restart all members simultaneously |

**Option values:**

| Option | Description |
|---|---|
| `FORCE_RESTART` | Restart regardless of whether a restart is pending |
| `RESTART_IF_NEEDED` | Only restart if there is a pending change |

## restart discovery

Start or restart a network discovery task.

**Syntax:**

```
restart discovery
```

**WAPI:** `POST discoverytask` with `action=START`

```
restart discovery
  Discovery started: discoverytask/...
```

## restart status

Show the current service restart status for all grid members.

**Syntax:**

```
restart status [refresh]
```

**WAPI:** `GET restartservicestatus` (and optionally `POST grid/<ref>?_function=requestrestartservicestatus` first)

=== "Show current status"
    ```
    restart status
    ```
=== "Output"
    ```
    member=gm.corp.example service=DNS status=RUNNING
    member=gm.corp.example service=DHCP status=RUNNING
    member=member2.corp.example service=DNS status=NEEDS_RESTART
    ```

=== "Refresh then show"
    ```
    restart status refresh
    ```

The `refresh` keyword triggers a `requestrestartservicestatus` function call on the grid before reading the status, ensuring you see the latest state.

## show restart

An alias for `restart status` (read-only).

**Syntax:**

```
show restart
```

**WAPI:** `GET restartservicestatus`

Output reports one line per member with per-service status (`dns_status`,
`dhcp_status`, `reporting_status`). Service-status values come from the
WAPI enum: `RUNNING`, `RESTARTED`, `NEEDS_RESTART`, `NO_REQUEST`, `OFFLINE`,
`DISABLED`, `NO_PERMISSION`, `CONFIG_ERROR`, `REQUESTING`, `RESTART_PENDING`,
`YES`, `NO`.

```
show restart
member=gm.corp.example dns_status=RUNNING dhcp_status=NO_REQUEST reporting_status=NO_PERMISSION
member=ibdns01.corp.example dns_status=NEEDS_RESTART dhcp_status=NO_PERMISSION reporting_status=NO_PERMISSION
```

---

## Scheduled Tasks

### show schedule

List pending scheduled tasks.

**Syntax:**

```
show schedule
```

**WAPI:** `GET scheduledtask`

=== "Command"
    ```
    show schedule
    ```
=== "Output"
    ```
    task_id=1001 submitter=alice action=CREATE object_type=zone_auth
    task_id=1002 submitter=bob action=DELETE object_type=fixedaddress
    ```

### configure schedule \<id\> delete

Cancel a pending scheduled task.

**Syntax:**

```
configure schedule <num> delete
```

**WAPI:** `GET scheduledtask?task_id=<id>` then `DELETE <ref>`

```
configure schedule 1001 delete
```

## Related commands

- [Grid](grid.md) - `show grid` and member management.
