# DNS Records

ibcli manages DNS records within zones using the `configure zone <zone> add/delete` subcommands and the standalone `show record` command.

## show record

Search for records by type and name (or IP for PTR).

**Syntax:**

```
show record {a_record|aaaa|cname|mx|txt|ptr|srv|info}=<name> [view=<name>]
```

| Keyword | WAPI object | Search field |
|---|---|---|
| `a_record` | `record:a` | `name` |
| `aaaa` | `record:aaaa` | `name` |
| `cname` | `record:cname` | `name` |
| `mx` | `record:mx` | `name` |
| `txt` | `record:txt` | `name` |
| `srv` | `record:srv` | `name` |
| `ptr` | `record:ptr` | `ipv4addr` |
| `info` | `record:host` + `record:a` + `record:aaaa` + `record:cname` | `name` |

=== "Show A record"
    ```
    show record a_record=www.corp.example
    ```
=== "Output"
    ```
    type=a name=www.corp.example ipv4addr=10.0.0.10 view=default
    ```

=== "Show PTR by IP"
    ```
    show record ptr=10.0.0.10
    ```
=== "Output"
    ```
    type=ptr ipv4addr=10.0.0.10 ptrdname=www.corp.example view=default
    ```

Find any record by name across multiple types:

```
show record info=www.corp.example
```

## Host records

### configure zone \<zone\> add host

**Syntax:**

```
configure zone <zone> add host <name> <ip>
    [mac=<mac>]
    [comment=<comment>]
    [view=<name>]
    [set <key> <value> ...]
```

**WAPI:** `POST record:host`

The `name` is automatically qualified with the zone FQDN if not already:

=== "Command"
    ```
    configure zone corp.example add host www 10.0.0.10
    ```
=== "WAPI body"
    ```json
    {
      "name": "www.corp.example",
      "ipv4addrs": [{"ipv4addr": "10.0.0.10"}]
    }
    ```

With MAC and comment:

```
configure zone corp.example add host printer 10.0.0.50 mac=aa:bb:cc:dd:ee:ff comment="Printer in lobby"
```

### configure zone \<zone\> delete host

**Syntax:**

```
configure zone <zone> delete host <name> [view=<name>]
```

**WAPI:** `GET record:host?name=<fqdn>` then `DELETE <ref>`

```
configure zone corp.example delete host www
configure zone corp.example delete host www view=external
```

## A records

### configure zone \<zone\> add a

**Syntax:**

```
configure zone <zone> add a <name> <ip> [view=<name>]
```

**WAPI:** `POST record:a`

=== "Command"
    ```
    configure zone corp.example add a mail 10.0.0.25
    ```
=== "WAPI body"
    ```json
    {"name": "mail.corp.example", "ipv4addr": "10.0.0.25"}
    ```

### configure zone \<zone\> delete a

**Syntax:**

```
configure zone <zone> delete a <name>
```

**WAPI:** `GET record:a?name=<fqdn>` then `DELETE <ref>`

```
configure zone corp.example delete a mail
```

## AAAA records (IPv6 A records)

### configure zone \<zone\> add aaaa

**Syntax:**

```
configure zone <zone> add aaaa <name> <ipv6> [view=<name>]
```

**WAPI:** `POST record:aaaa`

```
configure zone corp.example add aaaa www 2001:db8::10
```

### configure zone \<zone\> delete aaaa

```
configure zone corp.example delete aaaa www
```

## CNAME records

### configure zone \<zone\> add cname

**Syntax:**

```
configure zone <zone> add cname <name> <canonical> [view=<name>]
```

**WAPI:** `POST record:cname`

```
configure zone corp.example add cname alias www.corp.example
```

### configure zone \<zone\> delete cname

```
configure zone corp.example delete cname alias
```

## TXT records

### configure zone \<zone\> add txt

**Syntax:**

```
configure zone <zone> add txt <name> <text> [view=<name>]
```

**WAPI:** `POST record:txt`

TXT values containing spaces must be quoted:

```
configure zone corp.example add txt _spf "v=spf1 include:mailgun.org ~all"
```

### configure zone \<zone\> delete txt

```
configure zone corp.example delete txt _spf
```

## MX records

### configure zone \<zone\> add mx

**Syntax:**

```
configure zone <zone> add mx <name> <mail_exchanger> <preference> [view=<name>]
```

**WAPI:** `POST record:mx`

=== "Command"
    ```
    configure zone corp.example add mx corp.example mail.corp.example 10
    ```
=== "WAPI body"
    ```json
    {
      "name": "corp.example",
      "mail_exchanger": "mail.corp.example",
      "preference": 10
    }
    ```

### configure zone \<zone\> delete mx

**Syntax:**

```
configure zone <zone> delete mx <name>
```

```
configure zone corp.example delete mx corp.example
```

## PTR records

### configure zone \<zone\> add ptr

**Syntax:**

```
configure zone <zone> add ptr <ip> <ptrdname> [view=<name>]
```

**WAPI:** `POST record:ptr`

```
configure zone 1.168.192.in-addr.arpa add ptr 10.0.0.10 www.corp.example
```

### configure zone \<zone\> delete ptr

**Syntax:**

```
configure zone <zone> delete ptr <ip>
```

```
configure zone 1.168.192.in-addr.arpa delete ptr 10.0.0.10
```

## Notes

!!! note
    For simple record types (A, AAAA, CNAME, TXT), the `name` argument is auto-qualified with the zone FQDN using the pattern `name.zone` unless the name already ends with `.zone` or equals the zone name.

!!! note
    The `show record` command uses the `key=value` syntax: `show record a_record=www.corp.example`, not a positional `<zone>` argument. This mirrors the Perl original.

## Related commands

- [Zones](zones.md) - create and manage zones that hold these records.
