# Parser Reference

The ibcli parser is responsible for tab completion, abbreviation expansion, and routing each typed command to its handler function. This page explains the internals.

## Overview

Every command is registered in the `COMMANDS` dict with a **match-line key** - a string where literal words and `<special>` tokens are space-separated. For example:

```
"configure zone add <zone>"
```

The parser walks a typed line left-to-right, expanding each word against the word list at the current context depth.

## Abbreviation (`abbrev`)

The `abbrev(words)` function builds a map of every unambiguous prefix to its full word, mirroring Perl's `Text::Abbrev`.

Rules:

- A full word always maps to itself (e.g., `show → show`).
- A prefix that is itself a full word in the list is not considered ambiguous with longer words (the full word wins).
- A prefix matching two or more distinct longer words is **ambiguous** and excluded from the map.

```python
abbrev(["configure", "show", "set"])
→ {"c": "configure", "co": "configure", ..., "configure": "configure",
   "sh": "show", "sho": "show", "show": "show",
   "se": "set", "set": "set"}
```

Prefix `s` is ambiguous (`show` vs `set`) and therefore excluded.

## `expand_word`

`expand_word(inword, words)` matches a single token against the word list at the current context. Returns a 4-tuple `(done, sptype, expword, matches)`.

**Priority order:**

1. **Unique abbreviation** of a literal word → `done=True`, `expword=<full_word>+space`
2. **Ambiguous literal prefix** → `done=False`, `matches=[list of matching literals + any specials]`
3. **Matches a `<special>` regex** (only if no literal matches) → `done=False`, `sptype=<special>`, `expword=inword`
4. **No match** → `done=False`, `expword=""`, `matches=sorted(words)`

This priority order is load-bearing: a literal next-word (e.g., `add`) always wins over a `<zone>` special that would also syntactically match.

## `expand_line`

`expand_line(line)` walks all tokens left-to-right and returns `(expanded, error, match_line)`.

- `expanded` - the concrete command with full words and user-supplied values, space-separated.
- `error` - an empty string on success, or an error message (ambiguous/unknown).
- `match_line` - like `expanded` but with user-supplied values replaced by `<special>` tokens, used as the key into `COMMANDS`.

On an unknown word, the error format is:

```
<spaces>^--- Unknown argument at marker
```

where the caret is positioned at the column where the unknown token starts.

## `get_context`

`get_context(match_line)` looks up `COMMANDS[match_line].words`, splits on whitespace, and expands `a|b|c` alternates
and `key=<special>` pairs by side-effect - inserting derived entries into `COMMANDS` on first access. This mirrors the
Perl `add_context` trick.

For `key=<special>` pairs (e.g., `comment=<comment>`):

- `comment` is added as a literal word to the context.
- A new `COMMANDS` entry is created for `<matchline> comment` with `words=<comment>`.
- A new `COMMANDS` entry is created for `<matchline> comment <comment>` that inherits the parent's word list and handler.

This allows the parser to consume `comment "my comment"` as two tokens after the handler-level node.

## SPECOPS tokens

Special tokens are matched by regex. Each `<token>` in a word list corresponds to an entry in `SPECOPS`:

| Token | Pattern | Matches |
|---|---|---|
| `<zone>` | `^\S+$` | Any non-whitespace string |
| `<ip>` | Partial IP pattern | `1.2.3` or `1.2.3.4` |
| `<n.n.n.n/mm>` | Full IP/CIDR or IPv6/prefix | `10.0.0.0/8` or `2001:db8::/32` |
| `<mac>` | `[\w:]+` | `aa:bb:cc:dd:ee:ff` or `aabbccddeeff` |
| `<name>` | `^\S+$` | Any non-whitespace string |
| `<value>` | `^("([^"]+)"\|\S+)$` | Any token or quoted string |
| `<comment>` | `^("([^"]+)"\|\S+)$` | Any token or quoted string |
| `<num>` | `^\d+$` | Integers only |
| `<cr>` | `^$` | Empty string (signals valid stop) |
| `<name=value>` | `^\S+=\S+$` | Bare `key=value` token |
| `</cidr>` | `^/\d{1,2}$` | Prefix suffix like `/24` |

## Tokenizer: `key=value` splitting

The tokenizer (`_tokenize`) splits bare `key=value` tokens on the first `=`, treating them as two separate tokens:

```
comment=hello  →  ["comment", "hello"]
view=external  →  ["view", "external"]
```

This happens for tokens that:

- Contain `=`
- Do not start with `<`
- Are not quoted

!!! warning "Key=value split affects parsing"
    Because `key=value` is split before matching, the `<name=value>` SPECOPS token never matches in practice for
    user input - the tokenizer splits it first. The `<name=value>` token exists in SPECOPS for completeness but is
    effectively unused in normal command parsing. See [Known Quirks](../development/known-quirks.md).

## Quoted string handling

Double-quoted strings are treated as a single token by the tokenizer:

```
comment "hello world"  →  ["comment", '"hello world"']
```

The quotes are preserved through tokenization. Handlers strip quotes from values when constructing WAPI payloads.

## Alias substitution

Before `expand_line` runs, `process_line` applies prefix substitution for two built-in aliases:

| Alias | Replacement |
|---|---|
| `pwd` | `show debug pwd` |
| `info` | `show debug session` |

See [user-guide/aliases.md](../user-guide/aliases.md) for the full list and removal history.

## Completer integration

The `IbcliCompleter` in `completer.py` uses `expand_line` and `get_context` to compute completions for `prompt_toolkit`:

1. Call `expand_line(line_before_cursor)`.
2. If error contains "Unknown", return no completions.
3. Get `lastarg` from the line.
4. Strip the last arg from the match_line to get the current context.
5. Call `get_context(context)` to get the word list.
6. Call `expand_word(lastarg, words)` to get completions.
7. Yield `Completion` objects.

Complete-while-typing is disabled (`complete_while_typing=False`), matching the Perl tab-only behaviour.
