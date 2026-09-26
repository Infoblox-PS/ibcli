# RADIUS

## `radius:user` and `radius:nas` were removed

ibcli no longer registers `configure radius user`, `configure radius device`,
`show radius user` or `show radius device`.

Those commands mapped to the WAPI object types `radius:user` and `radius:nas`, which do not exist
on NIOS 9.1. The grid answers any call against them with:

```
Error: Unknown object type (radius:user)
Error: Unknown object type (radius:nas)
```

`ibx-nios-sdk` dropped both resources in 0.1.6 after confirming this against a live grid, so the
commands had nothing to call. They were removed rather than left in place to fail at runtime.

If you are on an older NIOS that still exposes these object types, drive them through the WAPI
endpoints directly - the SDK no longer models them, so there is no client-side path.

## What is still here: `radius:authservice`

RADIUS *authentication services* are a different object and are fully supported. This is what you
configure to let NIOS authenticate admins against a RADIUS server.

### `show auth radius`

List configured RADIUS authentication services.

```
show auth radius
show auth radius <name>
```

Abbreviated: `s au r`

=== "Command"
    ```
    show auth radius
    ```
=== "WAPI"
    ```
    GET radius:authservice
    ```

### `configure auth radius add`

```
configure auth radius add <name>
```

Abbreviated: `c au r a <name>`

### `configure auth radius <name> set`

Set fields on an existing service. Press ++tab++ after `set` to see the writable field list, which
is derived from the SDK model and tracks whichever WAPI version the SDK is pinned to.

```
configure auth radius <name> set <key>=<value>
```

### `configure auth radius <name> delete`

```
configure auth radius <name> delete
```

## Related

- `download radius_conf <file> member <name>` - fetch a member's RADIUS configuration file. See
  [File operations](files.md).
- [Admin users and groups](admin.md) - local admin accounts and the groups that map to
  authentication services.
