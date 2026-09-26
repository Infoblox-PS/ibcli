# Extensible Attributes

NIOS Extensible Attributes (EAs) are user-defined key-value metadata that can be attached to almost any WAPI object.
ibcli uses the `set key=value` pattern to pass EA values when creating or modifying objects.

## Syntax

Append `set <key> <value>` to any `configure ... add` or `configure ... modify` command that supports extensible attributes:

```
configure zone add corp.example set Owner alice set Env production
configure network add 10.1.0.0/24 set Site NYC set Owner bob
```

The tokenizer splits `set key=value` into `set key value`, so both forms are equivalent:

```
configure zone add corp.example set Owner alice
configure zone add corp.example set Owner=alice
```

## How it maps to WAPI

Each `set key value` pair is translated into a WAPI `extattrs` dict:

```json
{
  "fqdn": "corp.example",
  "extattrs": {
    "Owner": {"value": "alice"},
    "Env":   {"value": "production"}
  }
}
```

The EA key must already be defined on the grid (see [configure grid attribute](../commands/extensible-attributes.md)) before it can be attached to an object.

## Set-chain depth limit

!!! note "Set-chain depth cap"
    The parser registers a static set-chain up to **16 pairs deep** per command. A command with more than 16 `set
    key value` pairs will hit an "Unknown argument" error - bump the `range(16)` / `range(1, 17)` constants in
    `src/ibcli/commands/*.py` if you need more (each additional depth adds ~3 entries per endpoint to the flat
    `COMMANDS` dict).

Affected commands: `configure zone add`, `configure zone modify`, `configure network add`, `configure network modify`,
`configure network container add/modify`, `configure template network add`, `configure zone <zone> add host`.

## Viewing EA values

Extensible attribute values are not returned by default `show` commands - WAPI requires explicit `_return_fields+` to
include `extattrs`. The current `show` handlers do not request EA values in their output. Use the WAPI GUI or a direct
WAPI query to inspect EAs on existing objects.

## Defining EA types

See [Extensible Attributes commands](../commands/extensible-attributes.md) for how to add, list, and delete EA definitions on the grid.
