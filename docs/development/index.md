# Development

Information for contributors and developers extending ibcli.

## In this section

- **[Architecture](architecture.md)** - module layout, design decisions, key data flow.
- **[Adding Commands](adding-commands.md)** - step-by-step guide to adding a new command family.
- **[Testing](testing.md)** - pytest setup, `httpx.MockTransport` patterns, test organisation.
- **[Known Quirks](known-quirks.md)** - parser edge cases, set-chain limits, tokenizer behaviour.

## Quick orientation

The Python port lives entirely under `python/src/ibcli/`. The entry point is `cli.py:main()`. Every command is
registered via `@command(...)` decorators in files under `commands/`. The command tree is built at import time and
never changes at runtime.

The most important modules:

| Module | Role |
|---|---|
| `registry.py` | `COMMANDS` dict, `@command` decorator, `SPECOPS`, `ALIASES` |
| `parser.py` | `expand_line`, `expand_word`, `abbrev`, `get_context` |
| `completer.py` | `prompt_toolkit` adapter |
| `context.py` | `Context` - holds the `NiosClient` and session state |
| `fileop.py` | `http_direct_file_io` transfers (the non-WAPI half of fileop) |
| `debug.py` | `-d` tracing; enables the httpx / SDK loggers |
| `cli.py` | `argparse`, startup, REPL loop |
| `commands/*.py` | Per-domain handlers |
