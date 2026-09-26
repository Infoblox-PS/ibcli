# First Connection

## Connecting to a grid

Use the `configure server` command (or the `-s`/`-u`/`-p` flags) to authenticate against a NIOS grid master.

=== "REPL (interactive)"
    ```
    ibcli
    ( press <tab> for help )

    ibcli > configure server gridmaster.corp.example user admin password s3cr3t
    admin@gridmaster.corp.example >
    ```

=== "CLI flags"
    ```bash
    ibcli -s gridmaster.corp.example -u admin -p s3cr3t
    ```

=== "Password prompt"
    ```bash
    ibcli -s gridmaster.corp.example -u admin
    Password: ****
    ```

The prompt changes to `user@host >` when the connection succeeds.

## What happens on connect

1. `ibcli` hands credentials to `ibx-nios-sdk`'s `NiosClient`, which probes `GET /wapi/v2.14/?_schema=1` to discover the supported WAPI versions.
2. It picks the highest version the grid advertises, or uses `--wapi-version` if specified.
3. NIOS sets an `ibapauth` cookie on the probe response. All subsequent requests reuse that cookie - no per-request basic auth.
4. The prompt updates to `user@host >` to signal the connection is live. `ctx.online` becomes `True` and `ctx.client_rev` holds the negotiated WAPI version.

## Self-signed certificates

Most NIOS appliances ship with self-signed TLS certificates. Use `-k` / `--insecure` to skip verification:

```bash
ibcli -k -s gridmaster.corp.example -u admin
```

!!! warning "Security"
    `--insecure` disables all TLS certificate verification. Use it only on trusted internal networks where you control the grid.

## Running a first command

Once connected, list all authoritative zones:

```
admin@gridmaster.corp.example > show zone
fqdn=corp.example view=default
fqdn=1.168.192.in-addr.arpa view=default
```

Show a specific zone:

```
admin@gridmaster.corp.example > show zone corp.example
fqdn=corp.example view=default comment=Main corporate zone
```

Add a zone:

```
admin@gridmaster.corp.example > configure zone add test.corp.example comment="test zone"
  OK: configure zone add test.corp.example comment test zone
admin@gridmaster.corp.example > show zone test.corp.example
fqdn=test.corp.example view=default comment="test zone"
```

## One-shot execution

Use `-e` for scripting without entering the REPL:

```bash
ibcli -s gm -u admin -p pass -e "show zone corp.example"
type=auth fqdn=corp.example view=default
```

## Grid master override

If you connect via the MGMT port (which routes to a different internal IP), set the grid master VIP separately:

```
ibcli > configure server 192.168.1.1 user admin password pass master 10.0.0.1
```

Or with flags:

```bash
ibcli -s 192.168.1.1 -u admin -m 10.0.0.1
```

## Adding a grid member

Once connected you can register a new grid member with `configure grid`:

```
admin@gridmaster.corp.example > configure grid Infoblox member add ns1.corp.example \
    ipaddress 192.168.1.10/24 gateway 192.168.1.1
```

For full member management - including pre-provisioning hardware identity and licenses before an appliance boots - see the [Grid Management](../commands/grid.md) reference.

## Error messages

WAPI errors are printed with two leading spaces - the same format as the original Perl ibcli, so scripts that `grep '  Error:'` still work:

```
  Error: AdmConDataError: None (IBDataConflictError): IB.Data.Conflict:
         The zone already exists in the system.
```
