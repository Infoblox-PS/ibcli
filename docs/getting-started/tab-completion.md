# Tab Completion

Tab completion is the defining UX feature of ibcli. Every literal word in the command grammar can be abbreviated to any unambiguous prefix, and `<Tab>` fills in or lists options.

## Basic tab demo

Starting from an empty prompt, press `<Tab>` to see all top-level commands:

```
ibcli >  <Tab>
  configure   download    generate    help        history
  quit        restart     show        upload
```

Type `co` and press `<Tab>`:

```
ibcli > co<Tab>
ibcli > configure
```

`co` is an unambiguous prefix of `configure`, so ibcli expands it in place and appends a space.

Type `z` and `<Tab>`:

```
ibcli > configure z<Tab>
ibcli > configure zone
```

Type a space and `<Tab>` again to see the next level:

```
ibcli > configure zone <Tab>
  <zone>   add
```

`<zone>` is a special token - it matches any hostname string. The completion menu shows it to tell you that a zone
name is expected here but can't be auto-completed (ibcli has no way to enumerate all zone names without querying
the grid at completion time).

## Abbreviation rules

Any **unambiguous prefix** of a literal word is accepted. The algorithm is identical to Perl's `Text::Abbrev`:

- Full words always win over prefixes (so `show` is never ambiguous even if another word starts with `show`).
- A prefix that matches two or more words is **ambiguous** and shows all matches instead of expanding.

Examples:

| Typed | Expands to | Reason |
|---|---|---|
| `co` | `configure` | unique prefix |
| `s` | (ambiguous) | matches `show`, `set` in some contexts |
| `sh` | `show` | unique prefix |
| `sho` | `show` | unique prefix |
| `show` | `show` | exact match |
| `q` | `quit` | unique prefix |
| `z` | `zone` | unique after `configure` |

## The `<Tab>` display

`prompt_toolkit` renders completions in a native popup menu below the cursor. Pressing `<Tab>` repeatedly cycles through choices. `<Shift-Tab>` moves backwards. `<Escape>` closes the menu.

Ambiguous prefixes show all matching words. `<zone>`, `<ip>`, and other SPECOPS tokens are listed when the next argument must be a value ibcli cannot enumerate.

## Special tokens

When the next argument is a value (not a keyword), the completion menu shows the token type:

| Token | Meaning |
|---|---|
| `<zone>` | Any DNS zone name (`\S+`) |
| `<ip>` | An IPv4 address (partial match allowed) |
| `<n.n.n.n/mm>` | CIDR notation, IPv4 or IPv6 |
| `<name>` | Any non-whitespace string |
| `<mac>` | MAC address (colon-separated or raw hex) |
| `<num>` | Integer |
| `<comment>` | Quoted or unquoted string |
| `<cr>` | Pressing Enter here is valid (command is complete) |

## Completing key=value options

Options like `comment=`, `view=`, `primary=` appear in the completion menu as keywords. When you type `comment=` and
press `<Tab>`, the tokenizer splits on `=` and the next token becomes `<comment>`, signalling that a value is
expected.

```
configure zone add example.com view=<Tab>
  <name>
```

Type the view name and press `<Tab>` again to see what else is allowed.

## The `?` key

Pressing `?` at any point prints a brief reminder:

```
  press <tab> for options; '\' or Ctrl-U to clear; Ctrl-D to exit
```

`?` does not consume the current input - the buffer is preserved.

## Unknown words

If you type an unknown word and press Enter, ibcli prints an error showing exactly which token failed:

```
ibcli > show badword
      ^--- Unknown argument at marker
```

The caret points to the start of the bad token. Completions are suppressed while the earlier part of the line is invalid.
