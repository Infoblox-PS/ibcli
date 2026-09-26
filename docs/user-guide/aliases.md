# Aliases

ibcli supports a small set of short aliases for common introspection commands. They are applied as **prefix
substitutions** before parsing - a line beginning with the alias keyword is rewritten as if the full command had been
typed.

## Alias table

| Alias  | Expands to          | Purpose                                  |
|--------|---------------------|------------------------------------------|
| `pwd`  | `show debug pwd`    | Print ibcli's current working directory. |
| `info` | `show debug session`| Dump the current REPL session state (host, WAPI version, online flag). |

## How aliases work

Aliases are applied by `process_line` as the very first step, before the command is passed to the parser. The alias must be the **first word** of the line. Arguments following the alias are preserved verbatim.

For example, `pwd` is substituted to `show debug pwd`, then parsed normally through the command registry.

## Alias vs. abbreviation

Aliases are distinct from abbreviations. An abbreviation (e.g., `co` for `configure`) works at every word position and
is resolved by the parser's `abbrev()` engine. Aliases are a fixed prefix-level substitution applied once before
parsing begins.

You can abbreviate the commands that aliases expand to as well, but the aliases themselves must be typed in full (`pwd`, not `pw`).

## Example usage

```
admin@grid > pwd
/home/admin/grid-config

admin@grid > info
host=192.0.2.39 version=2.14 online=True
```

## Removed aliases

Earlier versions advertised `cd`, `ls`, and `prop` as aliases for `configure file path` / `show file nodes` / `show
file properties`. Those target commands were inherited from the Perl port but never implemented in the Python rewrite,
so the aliases always errored. They were removed; use `show debug commands` if you want to inspect the command tree
and `show debug session` for runtime state.
