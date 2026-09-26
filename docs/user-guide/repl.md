# REPL

When started without `-e` or batch files, ibcli enters an interactive Read-Eval-Print Loop (REPL) powered by `prompt_toolkit`.

## Banner

```
#####################################################################
#
# the Infoblox CLI (Python port, beta)
#
#####################################################################

( press <tab> for help )
```

## Prompt

The prompt starts as `ibcli > ` and changes to `user@host > ` after a successful `configure server` connection:

```
ibcli > configure server gm.example user admin password s3cr3t
admin@gm.example >
```

## Line continuation

Use `\` at the end of a line to continue the command on the next line, just like bash:

```
ibcli > configure grid Infoblox member add dns1.example.com \
      >     ipaddress 10.0.0.5/24 \
      >     platform VNIOS hwtype IB-V4126 \
      >     license enterprise license dns
```

Type `\` at the very end of the line and press `Enter`; the REPL will show a continuation prompt and keep collecting
input.  Pressing `Enter` on a line that does **not** end with `\` submits the whole accumulated command.

Pasting multi-line text (with literal `\`+newline in the paste buffer) also works - ibcli strips the continuation markers before tokenising.

## Key bindings

| Key | Action |
|---|---|
| `<Tab>` | Show completions / expand unambiguous prefix |
| `<Shift-Tab>` | Cycle backward through completion menu |
| `<Enter>` | Execute the current line (or continue if line ends with `\`) |
| `?` | Print quick help reminder (does not clear the buffer) |
| `\` (mid-line) | Clear the current line |
| `\` (end of line) | Insert `\` as a line-continuation marker |
| `Ctrl-U` | Clear the current line (readline standard) |
| `Ctrl-D` | Exit (on an empty line) |
| `Ctrl-C` | Clear the line (does **not** exit - matches Perl's `SIG{INT} = 'IGNORE'`) |
| `↑` / `↓` | Navigate history |
| `Ctrl-R` | Reverse-search history |

!!! note "Ctrl-D behaviour"
    `Ctrl-D` on a non-empty line is treated as "end of input for this buffer" by `prompt_toolkit`, which clears the line. Press it on an **empty** prompt to exit ibcli.

## History

Command history is stored persistently in `~/.ibcli_history` (Windows: `%USERPROFILE%\.ibcli_history`). This is an upgrade over the Perl version, which kept history only in memory.

- Up/down arrows navigate history in the order commands were entered.
- `Ctrl-R` opens reverse incremental search - type a substring to jump to matching entries.
- History is shared across sessions.

The `history` command in the REPL prints a short reminder that history is managed by `prompt_toolkit`; there is no inline `!N` syntax.

## `?` for help

Pressing `?` at any point prints:

```
  press <tab> for options; '\' at end of line to continue; Ctrl-D to exit
```

The buffer is not modified. This is implemented as a custom `prompt_toolkit` key binding.

## `help` command

The `help` command (or `h<Tab>`) prints the same message. `help all` points to the full documentation.

## Incomplete commands

If you press `<Enter>` on a valid but incomplete command (one that has no handler at that parse depth), ibcli prints:

```
  Incomplete : configure zone  (add <zone>)
```

The message shows the expanded line and the expected next tokens. This matches Perl's behaviour at line 730.

## Quit

Any of `quit`, `exit`, or `bye` exits the REPL. `Ctrl-D` on an empty line also exits.
