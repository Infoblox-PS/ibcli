# Certificates

ibcli manages TLS certificates on NIOS grid members using the WAPI fileop protocol.

## download cert

Download a certificate from a grid member.

**Syntax:**

```
download cert <file>
    [member=<name>]
    [usage=<name>]
```

**WAPI:** `fileop?_function=downloadcertificate`

Default `usage` is `ADMIN` when not specified.

=== "Download admin cert"
    ```
    download cert /tmp/grid-admin.pem
    ```
=== "Specific member and usage"
    ```
    download cert /tmp/member2-captive.pem \
        member=member2.corp.example usage=CAPTIVE_PORTAL
    ```

Common `usage` values:

| Value | Description |
|---|---|
| `ADMIN` | Grid administration (HTTPS GUI) |
| `CAPTIVE_PORTAL` | Captive portal certificate |
| `SFTP` | SFTP host certificate |

## upload cert

Upload a certificate to a grid member.

**Syntax:**

```
upload cert <file>
    [member=<name>]
    [usage=<name>]
```

**WAPI:** `fileop?_function=uploadcertificate`

Uses the standard three-step upload protocol: `uploadinit` → POST file → `uploadcertificate`.

=== "Upload admin cert"
    ```
    upload cert /tmp/new-admin.pem
    ```
=== "To specific member"
    ```
    upload cert /tmp/new-cert.pem member=member2.corp.example usage=ADMIN
    ```

## generate selfsigned cert

Generate a new self-signed certificate on a grid member.

**Syntax:**

```
generate selfsigned cert <member> <cn>
    [usage=<name>]
    [days=<num>]
```

**WAPI:** `fileop?_function=generateselfsignedcert`

Defaults: `usage=ADMIN`, `days=365`, `algorithm=SHA-256`, `key_size=2048`.

The generated certificate is saved locally as `<cn>.pem`.

=== "Command"
    ```
    generate selfsigned cert gm.corp.example gm.corp.example
    ```
=== "Output"
    ```
      Generated self-signed certificate for gm.corp.example
    ```

=== "Custom validity"
    ```
    generate selfsigned cert gm.corp.example gm.corp.example days=730
    ```

## generate csr

Generate a Certificate Signing Request (CSR) on a grid member.

**Syntax:**

```
generate csr <member> <cn>
    [usage=<name>]
```

**WAPI:** `fileop?_function=generatecsr`

Defaults: `usage=ADMIN`, `algorithm=SHA-256`, `key_size=2048`.

The CSR is saved locally as `<cn>.csr`.

=== "Command"
    ```
    generate csr gm.corp.example gm.corp.example
    ```
=== "Output"
    ```
      Generated CSR for gm.corp.example
    ```

Submit the resulting `.csr` file to your CA. After signing, upload the certificate with `upload cert`.

## Related commands

- [Files](files.md) - database, logs, and other file operations via the same protocol.
