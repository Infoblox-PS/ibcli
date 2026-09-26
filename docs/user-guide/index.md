# User Guide

This guide covers how to run ibcli and get the most out of the interactive REPL.

## In this section

- **[Invocation](invocation.md)** - all command-line flags, `.ibcli.cf` auto-load, and environment.
- **[REPL](repl.md)** - key bindings, history, and the `?` help key.
- **[Aliases](aliases.md)** - `pwd`, `cd`, `ls`, `prop`, `info` shortcuts.
- **[Batch mode](batch-mode.md)** - scripting with batch files and `-e`.
- **[Extensible Attributes](extensible-attributes.md)** - the `set key=value` pattern for attaching metadata to objects.

## The two modes

ibcli runs in two modes:

**Interactive (REPL):** started when no `-e` flag or batch file is given. Displays a prompt, accepts tab completion, maintains history.

**Non-interactive:** triggered by `-e <command>`, a positional batch file, or `.ibcli.cf` on startup. All three modes funnel through the same `process_line` function - output is identical to interactive mode.
