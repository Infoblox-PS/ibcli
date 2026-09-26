# CSV Import/Export

ibcli supports bulk data import and export via CSV files, and provides commands to track the status of import tasks.

## CSV export

Download WAPI objects as CSV for bulk editing or reporting.

### download csv

**Syntax:**

```
download csv <file> object <object>
```

**WAPI:** `fileop?_function=csv_export`

```
download csv /tmp/zones.csv object zone_auth
download csv /tmp/hosts.csv object record:host
download csv /tmp/networks.csv object network
```

The `object` argument is the WAPI object type name. Common values:

| WAPI object | Description |
|---|---|
| `zone_auth` | Authoritative zones |
| `record:host` | Host records |
| `record:a` | A records |
| `network` | Networks |
| `fixedaddress` | Fixed addresses |
| `range` | DHCP ranges |

## CSV import

Upload a CSV file to create or update objects in bulk.

### upload csv

**Syntax:**

```
upload csv <file> [object <name>]
```

**WAPI:** `fileop?_function=csv_import`

Without `object`: uses `action=INSERT` (add new records).

With `object`: uses `action=CUSTOM` for the specified object type.

=== "Insert new zones"
    ```
    upload csv /tmp/new-zones.csv
    ```
=== "Custom object type"
    ```
    upload csv /tmp/hosts.csv object record:host
    ```

On success:

```
  Uploaded /tmp/new-zones.csv
```

The import runs asynchronously. Use `show csv task <ref>` to check status.

## Checking import status

### show csv task

**Syntax:**

```
show csv task <ref>
```

**WAPI:** `GET <ref>` (the csv_import_task object reference)

The `<ref>` is the `_ref` string returned by the WAPI in the upload response body, or found by browsing the WAPI.

=== "Command"
    ```
    show csv task csv_import_task/ZG5z...
    ```
=== "Output"
    ```
    status=COMPLETE lines_processed=142 lines_failed=0
    ```
=== "Partial failure"
    ```
    status=FAILED lines_processed=95 lines_failed=47 start_time=1234567890 end_time=1234568000
    ```

## Downloading CSV errors

If a CSV import has failures, download the error log for details.

### download csv_errors

**Syntax:**

```
download csv_errors <file> <task_id>
```

**WAPI:** `fileop?_function=csv_error_log` with `import_id=<task_id>`

```
download csv_errors /tmp/import-errors.csv csv_import_task/ZG5z...
  Downloaded /tmp/import-errors.csv
```

The error CSV includes the offending rows and error descriptions, allowing you to fix and re-import only the failed records.

## Typical workflow

1. Export existing data: `download csv /tmp/zones.csv object zone_auth`
2. Edit the CSV in a spreadsheet.
3. Import the edited file: `upload csv /tmp/zones-updated.csv`
4. Note the task reference from the response.
5. Check status: `show csv task <ref>`
6. If errors: `download csv_errors /tmp/errors.csv <ref>`, fix, and re-import.

## Related commands

- [Files](files.md) - other file operations (database backup, logs).
