# Batch Mode

ibcli supports non-interactive scripting through two mechanisms: **batch files** and the **`-e` flag**.

## `-e`: single command

Use `-e` to run exactly one command and exit. Useful for cron jobs, CI pipelines, and ad-hoc scripting.

```bash
ibcli -s gm -u admin -p pass -e "show zone corp.example"
type=auth fqdn=corp.example view=default
```

Credentials can be embedded directly:

```bash
ibcli -s gm -u admin -p pass -e "configure zone add new.corp.example"
```

The exit code is 0 on success. Errors are printed to stdout with the `  Error: ` prefix (two leading spaces).

## Batch files

Pass one or more file paths as positional arguments. ibcli reads each file line-by-line and runs every non-blank, non-comment line through `process_line`. It then exits.

```bash
ibcli -s gm -u admin -p pass provision-zones.ibcli
```

During batch processing, ibcli echoes each line before executing it:

```
read line 3: configure zone add zone1.example.com
read line 4: configure zone add zone2.example.com
read line 5: configure zone add zone3.example.com
```

Comment lines (starting with `#`) are written to stdout as-is without the `read line N:` prefix.

### Line continuation

Use `\` at the end of a line to split a long command across multiple lines, just like bash:

```bash
configure grid Infoblox member add dns1.example.com \
    ipaddress 10.0.0.5/24 \
    platform VNIOS hwtype IB-V4126 \
    license enterprise license dns
```

ibcli joins the fragments before tokenising, so this is identical to writing the command on a single line.  A `\` followed only by whitespace (or end-of-file) is also stripped cleanly.

### Example batch file

```bash
# provision-zones.ibcli
# Create three new zones and add records to each

configure zone add zone1.example.com
configure zone add zone2.example.com
configure zone add zone3.example.com

configure zone zone1.example.com add a www 10.0.0.1
configure zone zone2.example.com add a www 10.0.0.2
configure zone zone3.example.com add a www 10.0.0.3
```

Run it:

```bash
ibcli -s gm -u admin -p pass provision-zones.ibcli
read line 4: configure zone add zone1.example.com
read line 5: configure zone add zone2.example.com
read line 6: configure zone add zone3.example.com
read line 8: configure zone zone1.example.com add a www 10.0.0.1
...
```

### Multiple files

Multiple files are processed in order:

```bash
ibcli -s gm -u admin -p pass create-zones.ibcli add-records.ibcli
```

## `.ibcli.cf` auto-load

If a file named `.ibcli.cf` exists in the **current working directory** when ibcli starts, it is read silently before the REPL begins (or before `-e` / batch files run). No prompts, no `read line N:` echo.

This is useful for per-project connection settings:

```bash
# .ibcli.cf in your project directory
configure server gridmaster.corp.example user admin password s3cr3t
configure master 10.0.0.1
```

Lines starting with `#` and blank lines are skipped.

!!! warning "Password in .ibcli.cf"
    Storing plaintext passwords in `.ibcli.cf` is convenient but not secure. Restrict the file to owner-only read (`chmod 600 .ibcli.cf`) and avoid committing it to source control.

## Error handling in batch mode

Each command is independent - an error on line N does not abort lines N+1 and beyond. Errors are printed to stdout with two leading spaces:

```
read line 5: configure zone add duplicate.example.com
  Error: IB.Data.Conflict: The zone already exists in the system.
read line 6: configure zone add next.example.com
```

If you need to abort on error, post-process the output and check for lines matching `^  Error:`.

## Output format

Output in batch mode is identical to interactive mode - the same field=value format on stdout. This makes it straightforward to pipe through `grep`, `awk`, or Python scripts.
