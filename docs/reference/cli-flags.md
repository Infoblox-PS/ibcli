# CLI Flags Reference

Complete reference for all `ibcli` command-line flags.

## Usage

```
ibcli [-h] [-s SERVER] [-u USER] [-p PASSWORD] [-m MASTER]
           [-e EXEC_CMD] [-d DEBUG] [-l] [-V] [-k] [-i]
           [--wapi-version V] [file ...]
```

## Flags

### `-s SERVER`

**WAPI host** - hostname or IP address of the NIOS grid master.

Used in combination with `-u` and optionally `-p` to auto-connect on startup. If `-s` and `-u` are given without `-p`,
ibcli prompts for the password with `getpass` (no echo).

```bash
ibcli -s gridmaster.corp.example -u admin
Password: ****
```

Can also be set interactively: `configure server gridmaster.corp.example user admin password ***`

---

### `-u USER`

**Username** for WAPI authentication.

---

### `-p PASSWORD`

**Password** for WAPI authentication. If omitted when `-s` and `-u` are present, ibcli prompts via `getpass`.

!!! warning
    Passing passwords on the command line exposes them in shell history and `ps` output. Prefer the interactive prompt
    or `.ibcli.cf` with restricted file permissions.

---

### `-m MASTER` / `--master MASTER`

**Grid master IP override.** Use this when connecting through the MGMT port, which routes to a different interface
than the VIP. The master IP is stored in `ctx.master_ip` but is currently used for reference only - all WAPI calls go
to the `-s` host.

---

### `-e CMD`

**Execute a single command and exit.** The command string is passed through `process_line` exactly as typed. Credentials must already be set (via `-s`/`-u`/`-p` or `.ibcli.cf`).

```bash
ibcli -s gm -u admin -p pass -e "show zone corp.example"
```

Exit code is 0 on success (even if the command prints an error).

---

### `-d N`

**Debug level** (integer 0-5). All output goes to stderr, so it never
pollutes a piped command result.

| Level | Output |
|---|---|
| 0 | Silent (default) |
| 1 | Dispatch trace - the expanded line and the grammar node it matched |
| 2 | Adds HTTP method + URL + response status (httpx) |
| 3 | Adds SDK request detail - WAPI params, retries, 401 re-login |
| 4-5 | Same as 3; parser word-expansion tracing is not implemented |

Levels 2 and 3 work by enabling the `httpx` and `ibx_nios_sdk` loggers,
which are otherwise silent. At level 3 and above an unexpected exception is
re-raised with its traceback instead of being reported as a one-line error,
so handler bugs stay diagnosable.

```bash
ibcli -k -s gm -u admin -p pass -d 3 -e "show grid"
[d1] dispatch: 'show grid' -> 'show grid'
[d3] GET https://gm/wapi/v2.14//grid params={'_return_fields+': 'name'}
[d2] HTTP Request: GET https://gm/wapi/v2.14/grid?... "HTTP/1.1 200 OK"
```

---

### `-l`

**List commands.** Prints all registered match-line keys from the `COMMANDS` dict, sorted alphabetically, and exits. Useful for scripting or documentation.

```bash
ibcli -l | head -5
configure grid <name> member <name> delete
configure grid <name> member <name> dhcp
configure grid <name> member <name> dhcp disable
configure grid <name> member <name> dhcp enable
configure grid <name> member <name> dns
```

---

### `-V` / `--version`

Print the ibcli version and exit.

```bash
ibcli -V
ibcli 1.0.0
```

---

### `-k` / `--insecure`

**Skip TLS certificate verification.** Required for grids with self-signed certificates (the default NIOS configuration).

The flag sets `ctx.verify = False`, which `configure server` passes to the SDK's `NiosClient(verify=...)` - so it
applies both to the auto-connect performed by `-s`/`-u` and to any `configure server` typed later in the same session.

Without it, TLS is verified against the system CA bundle and a self-signed grid certificate will fail to connect with
a `NiosConnectionError` naming the TLS failure.

```bash
ibcli -k -s gridmaster.corp.example -u admin
```

---

### `-i` / `--idempotent`

**Demote "already exists" conflicts to skips.** WAPI conflict errors (and the several ways NIOS phrases them as
plain 400s) print as `Skipped: ...` instead of `Error: ...`, and batch processing continues. Intended for
re-runnable provisioning scripts.

---

### `--wapi-version V`

**Pin the WAPI version.** Without it, the SDK's default WAPI version is used. The value is passed to
`NiosClient(wapi_version=...)` and becomes the `/wapi/vN.N/` path prefix on every request.

```bash
ibcli --wapi-version 2.12 -s gm -u admin
```

`show server version` reports the version actually in use.

---

### `file ...`

**Batch files.** One or more file paths processed in order. Each non-blank, non-comment line is run through
`process_line`. ibcli echoes `read line N: <line>` before each command. After all files are processed, ibcli
exits.

```bash
ibcli -s gm -u admin -p pass create.ibcli cleanup.ibcli
```

---

### `-b` / `-f FILE` (rejected)

These flags existed in the Perl version for backup-file browsing: the Perl ibcli read a
`Data::Dumper` snapshot in-process. The Python port rejects them with exit code 2.

There is no WAPI equivalent, and there is not meant to be. Browsing a backup is an offline read of
a local file, whereas every ibcli command maps to a call against a live grid - the two share no
code and no dependencies. Use whatever offline tooling your team standardises on.

ibcli's part in that workflow is retrieving the backup in the first place:

```bash
ibcli -k -s <gm> -u admin -p "$PASSWORD" -e "download database grid.bak"
```
