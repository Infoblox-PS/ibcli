# Admin Users, Groups, Roles, and Permissions

## Admin Users

### show admin user

**Syntax:**

```
show admin user [<name>]
```

**WAPI:** `GET adminuser`

=== "List all"
    ```
    show admin user
    ```
=== "Output"
    ```
    name=alice groups=dns-admins
    name=bob groups=readonly-group comment=Ops team
    ```

=== "Specific user"
    ```
    show admin user alice
    ```

### configure admin user add

**Syntax:**

```
configure admin user add <name>
    password=<value>
    [comment=<comment>]
```

**WAPI:** `POST adminuser`

Password is required at creation time.

=== "Command"
    ```
    configure admin user add alice password=S3cr3tPass
    ```
=== "WAPI body"
    ```json
    {"name": "alice", "password": "S3cr3tPass"}
    ```

With comment:

```
configure admin user add bob password=AnotherPass comment="Ops team member"
```

### configure admin user \<name\> delete

**Syntax:**

```
configure admin user <name> delete
```

**WAPI:** `GET adminuser?name=<name>` then `DELETE <ref>`

```
configure admin user bob delete
```

---

## Admin Groups

### show admin admin_group

**Syntax:**

```
show admin admin_group [<name>]
```

**WAPI:** `GET admingroup`

=== "List all"
    ```
    show admin admin_group
    ```
=== "Output"
    ```
    name=dns-admins roles=dns-write-role
    name=readonly-group
    ```

=== "Specific group"
    ```
    show admin admin_group dns-admins
    ```

### configure admin group add

**Syntax:**

```
configure admin group add <name> [comment=<comment>]
```

**WAPI:** `POST admingroup`

```
configure admin group add dns-admins comment "DNS administrators"
configure admin group add readonly-group
```

### configure admin group \<name\> delete

**Syntax:**

```
configure admin group <name> delete
```

**WAPI:** `GET admingroup?name=<name>` then `DELETE <ref>`

```
configure admin group readonly-group delete
```

---

## Admin Roles

### show admin role

**Syntax:**

```
show admin role [<name>]
```

**WAPI:** `GET adminrole`

=== "List all"
    ```
    show admin role
    ```
=== "Output"
    ```
    name=dns-write-role
    name=readonly-role comment=Read-only access
    ```

### configure admin role add

**Syntax:**

```
configure admin role add <name> [comment=<comment>]
```

**WAPI:** `POST adminrole`

```
configure admin role add dns-write-role comment "DNS write access"
```

### configure admin role \<name\> delete

**Syntax:**

```
configure admin role <name> delete
```

**WAPI:** `GET adminrole?name=<name>` then `DELETE <ref>`

```
configure admin role dns-write-role delete
```

---

## Permissions

Permissions bind a group or role to an object type with a specific access level (read, write, or deny).

### configure admin permission add

**Syntax:**

```
configure admin permission add
    {group=<name> | role=<name>}
    [object=<name>]
    {read | write | deny}
```

**WAPI:** `POST permission`

Specify either `group=` or `role=` (not both).

=== "Grant write to a group"
    ```
    configure admin permission add group=dns-admins object=zone_auth write
    ```
=== "WAPI body"
    ```json
    {"group": "dns-admins", "object": "zone_auth", "permission": "WRITE"}
    ```

=== "Grant read to a role"
    ```
    configure admin permission add role=readonly-role object=network read
    ```

### configure admin permission delete

**Syntax:**

```
configure admin permission delete
    [group=<name>]
    [role=<name>]
    [object=<name>]
```

**WAPI:** `GET permission?<params>` then `DELETE <ref>`

```
configure admin permission delete group=dns-admins object=zone_auth
```

### configure admin permission modify

**Syntax:**

```
configure admin permission modify
    [group=<name>]
    [role=<name>]
    [object=<name>]
    permission=<read|write|deny>
```

**WAPI:** `GET permission?<params>` then `PUT <ref>`

```
configure admin permission modify group=dns-admins object=zone_auth permission=read
```

!!! note
    The `modify` command requires the permission to match exactly one existing permission record. If multiple records match the filter, it prints an error and aborts.

## Related commands

- [RADIUS](radius.md) - RADIUS user and NAS device management.
