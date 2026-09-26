# Invocation

## Synopsis

```
ibcli [-s HOST] [-u USER] [-p PASS] [-m MASTER] [-e CMD]
           [-d LEVEL] [-k] [--wapi-version V] [-l] [-V] [file ...]
```

## Flags reference

| Flag | Long form | Type | Default | Description |
|---|---|---|---|---|
| `-s HOST` | | string | - | WAPI grid master hostname or IP |
| `-u USER` | | string | - | WAPI username |
| `-p PASS` | | string | - | Password (prompted via `getpass` if `-s` and `-u` are given without `-p`) |
| `-m MASTER` | `--master` | string | - | Grid master IP override (for MGMT-port connections) |
| `-e CMD` | | string | - | Run a single command and exit |
| `-d N` | | int | `0` | Debug level 0-5 (see below) |
| `-k` | `--insecure` | flag | off | Skip TLS certificate verification |
| `--wapi-version V` | | string | auto | Override WAPI version (e.g. `2.12`); disables auto-detection |
| `-l` | | flag | - | List all registered commands and exit |
| `-V` | `--version` | flag | - | Print version and exit |
| `-h` | `--help` | flag | - | Print usage and exit |
| `file ...` | | path(s) | - | Batch file(s) to process, then exit |

!!! note "Removed flags"
    `-b` and `-f` (backup-file browsing) are **rejected** with exit code 2. The Perl ibcli read a
    `Data::Dumper` snapshot in-process; browsing a backup is an offline read of a local file rather
    than a grid call, so it is out of scope for a WAPI client.

    ibcli's part is fetching the backup:

    ```bash
    ibcli -k -s <gm> -u admin -p "$PASSWORD" -e "download database grid.bak"
    ```

## Startup order

ibcli performs the following steps in order on startup:

1. Parse command-line arguments.
2. If `-l`: print all command keys sorted alphabetically, then exit.
3. If `.ibcli.cf` exists in the current working directory: read and execute it silently (comments and blank lines skipped).
4. If `-s` and `-u` are both present: call `configure server` automatically.
5. If `-m` is present: call `configure master` to set the grid master IP.
6. If `-e` is present: run the command and exit.
7. If positional file arguments are present: run in batch mode and exit.
8. Otherwise: print the banner and enter the interactive REPL.

## The `.ibcli.cf` config file

If a file named `.ibcli.cf` exists in the **current working directory** when ibcli starts, every non-blank,
non-comment line is executed silently - no prompts, no echo. This is the same behaviour as the Perl original.

Example `.ibcli.cf`:

```
# Auto-connect on startup
configure server gridmaster.corp.example user admin password s3cr3t
configure master 10.0.0.1
```

Lines starting with `#` are skipped. There is no `~/.ibclirc` equivalent - only the CWD file is checked.

## Debug levels

The `-d` flag sets the debug level (integer 0-5). Higher levels produce more verbose output on stderr.

| Level | What is logged |
|---|---|
| 0 | Nothing (default) |
| 1 | Top-level `process_line` call trace |
| 2 | HTTP method + URL for every WAPI request; response status |
| 3 | Full request/response bodies (truncated at 500 chars) |
| 4-5 | Word-expansion internals (parser debug) |

Level 2 is the most useful for diagnosing connectivity issues:

```bash
ibcli -d 2 -e "show grid"
[wapi] GET https://grid/wapi/v2.12/grid?name=...
[wapi]   -> 200 application/json
name=Infoblox  ref=grid/ZG5z...
```

## WAPI version override

ibcli auto-detects the highest `2.x` WAPI version supported by the grid. To pin a specific version:

```bash
ibcli --wapi-version 2.5 -s grid -u admin
```

This can be useful if the auto-detected version has changed behaviour you depend on.

## Environment variables

There are no ibcli-specific environment variables in the current implementation. The HTTP
client is `httpx`, and it is constructed with `trust_env` left at its default, so these are
honoured:

| Variable | Effect |
|---|---|
| `SSL_CERT_FILE` | CA bundle file used to verify the grid certificate |
| `SSL_CERT_DIR` | Directory of CA certificates, used if `SSL_CERT_FILE` is unset |
| `HTTPS_PROXY` / `https_proxy` | Proxy for the WAPI connection |
| `NO_PROXY` / `no_proxy` | Hosts to reach directly, bypassing the proxy |

`REQUESTS_CA_BUNDLE` is **not** honoured - that variable is specific to the `requests` library,
which this project does not use. Setting it has no effect. Use `SSL_CERT_FILE` instead, or
`-k`/`--insecure` to skip verification entirely (see [CLI flags](../reference/cli-flags.md)).
