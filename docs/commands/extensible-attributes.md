# Extensible Attribute Definitions

Extensible attribute (EA) definitions specify the name and type of metadata fields that can be attached to WAPI objects. Before setting `set key=value` on a zone or network, the key must be defined here.

## show grid attribute

List or show EA definitions.

**Syntax:**

```
show grid attribute [<name>]
```

**WAPI:** `GET extensibleattributedef`

=== "List all"
    ```
    show grid attribute
    ```
=== "Output"
    ```
    name=Owner type=STRING
    name=Env type=ENUM list_values=production,staging,dev
    name=Site type=STRING comment=Physical location
    ```

=== "Specific attribute"
    ```
    show grid attribute Owner
    ```

## configure grid attribute add

**Syntax:**

```
configure grid attribute add <name> type {string|integer|email|enum|url|date}
    [comment <text>]
    [list_value=<value> ...]
```

**WAPI:** `POST extensibleattributedef`

Supported types:

| Type | WAPI value | Notes |
|---|---|---|
| `string` | `STRING` | Free-form text |
| `integer` | `INTEGER` | Integer value |
| `email` | `EMAIL` | Validated email format |
| `enum` | `ENUM` | Must supply `list_value` options |
| `url` | `URL` | Validated URL format |
| `date` | `DATE` | Date value |

=== "String attribute"
    ```
    configure grid attribute add Owner type string
    ```
=== "WAPI body"
    ```json
    {"name": "Owner", "type": "STRING"}
    ```

Enum attribute with allowed values:

=== "Command"
    ```
    configure grid attribute add Env type enum \
        list_value=production list_value=staging list_value=dev
    ```
=== "WAPI body"
    ```json
    {
      "name": "Env",
      "type": "ENUM",
      "list_values": [
        {"value": "production"},
        {"value": "staging"},
        {"value": "dev"}
      ]
    }
    ```

With a comment:

```
configure grid attribute add Site type string comment "Physical location of device"
```

!!! note
    The `comment` keyword here is a positional argument, not the `comment=` k=v form. Type `comment ` then the text (or a quoted string).

## configure grid attribute \<name\> delete

**Syntax:**

```
configure grid attribute <name> delete
```

**WAPI:** `GET extensibleattributedef?name=<name>` then `DELETE <ref>`

```
configure grid attribute Owner delete
```

---

!!! info "Device-type EAs"
    Earlier versions of ibcli exposed a `configure grid device_type`
    verb as a shortcut for creating ENUM-typed EAs. That verb has been
    removed because it duplicated `configure grid attribute add <name>
    type ENUM` with a misleading name. For an ENUM EA used to classify
    devices, create it like any other ENUM EA:

    ```
    configure grid attribute add DeviceType type ENUM \
        list_value=Switch list_value=Router list_value=Server
    ```

## Using EAs on objects

Once an EA is defined, use `set key=value` with any supported `configure ... add` or `configure ... modify` command.
See [Extensible Attributes user guide](../user-guide/extensible-attributes.md) for details and the set-chain depth
limit.

## Related commands

- [User Guide - Extensible Attributes](../user-guide/extensible-attributes.md) - how to use `set` on objects.
