# File Operations

ibcli implements the WAPI three-step fileop protocol for both uploads and downloads.

## Download protocol (three steps)

1. `POST fileop?_function=<function>` with parameters → receives `{"url": "...", "token": "..."}`
2. `GET <url>` with `Content-Type: application/force-download` header → streams the file body via `iter_content`
(chunked, suitable for large files)
3. `POST fileop?_function=downloadcomplete` with `{"token": "..."}` → signals completion

!!! warning "The 415 fix - verified on real NIOS grid"
    Step 2 requires the `Content-Type: application/force-download` header on the GET request. Without it, NIOS returns
    HTTP 415 Unsupported Media Type. This is a known undocumented NIOS behaviour, handled by `stream_download` in
    `src/ibcli/fileop.py`. The fix was confirmed working against a real NIOS grid at 192.0.2.40 (WAPI v2.14) on
    2026-04-17. See [Troubleshooting](../reference/troubleshooting.md#http-415-on-file-downloads) for the full
    debugging story.

## Upload protocol (three steps)

1. `POST fileop?_function=uploadinit` → receives `{"url": "...", "token": "..."}`
2. `POST <url>` with multipart file content → streams the file
3. `POST fileop?_function=<function>` with `{"token": "..."}` → invokes the actual operation

---

## Download commands

### download database

Download a full database backup.

**Syntax:**

```
download database <file>
```

**WAPI:** `fileop?_function=getgriddata` with `type=BACKUP`

=== "Command"
    ```
    download database /tmp/nios-backup.tar.gz
    ```
=== "Output"
    ```
      Downloaded /tmp/nios-backup.tar.gz
    ```

!!! note "Real-grid verified"
    `download database` is the only ibcli command that has been tested against a live NIOS grid. All other commands
    are mocked-only at this time.

### download csv

Download object data as CSV.

**Syntax:**

```
download csv <file> object <object>
```

**WAPI:** `fileop?_function=csv_export`

```
download csv /tmp/zones.csv object zone_auth
download csv /tmp/networks.csv object network
```

### download log_files

Download system log files.

**Syntax:**

```
download log_files <file> <log_type> [member=<ip>]
```

**WAPI:** `fileop?_function=get_log_files`

```
download log_files /tmp/syslog.gz SYSLOG
download log_files /tmp/audit.gz AUDIT member=192.168.1.5
```

### download lease_history

Download the DHCP lease history database.

**Syntax:**

```
download lease_history <file>
```

**WAPI:** `fileop?_function=getleasehistoryfiles`

```
download lease_history /tmp/leases.csv
```

### download support_bundle

Download a support bundle (diagnostic package).

**Syntax:**

```
download support_bundle <file> [member=<ip>]
```

**WAPI:** `fileop?_function=get_support_bundle`

```
download support_bundle /tmp/support.tgz
download support_bundle /tmp/member2-support.tgz member=192.168.1.6
```

### download merge_log

Download the grid merge log.

**Syntax:**

```
download merge_log <file>
```

**WAPI:** `fileop?_function=get_log_files` with `log_type=MERGE`

```
download merge_log /tmp/merge.log
```

### download expert_dhcp_conf

Download the expert DHCP configuration file.

**Syntax:**

```
download expert_dhcp_conf <file>
```

**WAPI:** `fileop?_function=getmemberdata` with `type=DHCP_CONFIG_FILE`

```
download expert_dhcp_conf /tmp/dhcpd.conf
```

### download dhcp_conf

Download the DHCP configuration file.

**Syntax:**

```
download dhcp_conf <file>
```

**WAPI:** `fileop?_function=getmemberdata` with `type=DHCP_CONFIG`

```
download dhcp_conf /tmp/dhcp.conf
```

---

## Upload commands

### upload database

Upload and restore a database backup.

**Syntax:**

```
upload database <file>
```

**WAPI:** `fileop?_function=restoredatabase` with `keep_grid_ip=YES`

```
upload database /tmp/nios-backup.tar.gz
```

!!! warning
    Database restore is disruptive. The grid will restart services and may briefly go offline. Confirm with your team
    before running this command.

### upload csv

Upload a CSV file for bulk import.

**Syntax:**

```
upload csv <file> [object <name>]
```

**WAPI:** `fileop?_function=csv_import`

Without `object`, defaults to `action=INSERT`. With `object`, uses `action=CUSTOM`.

```
upload csv /tmp/zones.csv
upload csv /tmp/hosts.csv object record:host
```

### upload leases

Upload a DHCP leases file.

**Syntax:**

```
upload leases <file>
```

**WAPI:** `fileop?_function=setleasehistoryfiles`

```
upload leases /tmp/leases.csv
```

### upload expert_dhcp_conf

Upload an expert DHCP configuration file.

**Syntax:**

```
upload expert_dhcp_conf <file> [member=<ip>]
```

**WAPI:** `fileop?_function=setmemberdata` with `type=DHCP_CONFIG_FILE`

```
upload expert_dhcp_conf /tmp/dhcpd.conf
upload expert_dhcp_conf /tmp/dhcpd.conf member=192.168.1.5
```

### download csv_errors

Download the error log from a failed or partial CSV import.

**Syntax:**

```
download csv_errors <file> <task_id>
```

**WAPI:** `fileop?_function=csv_error_log` with `import_id=<task_id>`

```
download csv_errors /tmp/import-errors.csv csv_import_task/ZG5z...
  Downloaded /tmp/import-errors.csv
```

The `<task_id>` is the `_ref` returned by `upload csv` or found via `show csv task`. See [CSV](csv.md) for the full
import lifecycle.

---

## URL host rewriting

If NIOS returns a file download URL whose hostname differs from the grid master (e.g., an internal IP vs. the VIP),
ibcli rewrites the URL to use the host it connected to. This ensures the session's TLS and cookie state are applied
correctly.

## Related commands

- [Certificates](certificates.md) - download/upload certificates via the same fileop protocol.
- [CSV](csv.md) - CSV import workflow and error log download.
