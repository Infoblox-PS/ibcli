# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

from collections.abc import Iterable

from ibcli.registry import COMMANDS, SPECOPS, CommandEntry


def abbrev(words: Iterable[str]) -> dict[str, str]:
    """Return a map of every unambiguous prefix to its full word.

    Mirrors Perl's Text::Abbrev: full words always map to themselves (a full
    word that happens to be a prefix of another longer word is NOT ambiguous).
    Prefixes that match two or more distinct longer words are excluded.
    """
    unique_words = list(dict.fromkeys(words))
    full = set(unique_words)
    table: dict[str, str] = {w: w for w in unique_words}
    ambiguous: set[str] = set()
    for word in unique_words:
        for i in range(1, len(word)):
            prefix = word[:i]
            if prefix in full:
                continue  # full word wins - not ambiguous
            if prefix in table:
                if table[prefix] != word:
                    ambiguous.add(prefix)
            else:
                table[prefix] = word
    return {k: v for k, v in table.items() if k not in ambiguous}


def expand_word(
    inword: str,
    words: list[str],
) -> tuple[bool, str, str, list[str]]:
    """Match `inword` against `words`. Returns (done, sptype, expword, matches).

    Priority:
      1. Unique abbrev of a literal word  -> (True, "", "<word> ", [])
      2. Ambiguous literal prefix         -> (False, "", inword, sorted_matches)
      3. Matches a <special> regex        -> (False, "<special>", inword, [])
      4. No match                         -> (False, "", "", sorted(words))
    """
    # Separate literal words (no leading '<') from <specials>.
    literals = [w for w in words if not w.startswith("<")]
    specials = sorted(w for w in words if w.startswith("<"))

    # Build abbrev table from literals only.
    abbr = abbrev(literals)
    inword_lc = inword.lower()

    # 1. Unique abbrev
    if inword_lc in abbr:
        return (True, "", f"{abbr[inword_lc]} ", [])

    # 2. Ambiguous literal prefix
    if inword:
        literal_matches = sorted(w for w in literals if w.startswith(inword_lc))
        if literal_matches:
            # Perl behavior: when there's an inword and literal matches,
            # prepend the available specials to the matches list.
            return (False, "", inword, specials + literal_matches)

    # 3. Try SPECOPS regexes for each <special> in words
    for spec in specials:
        pattern = SPECOPS.get(spec)
        if pattern and inword and pattern.search(inword):
            return (False, spec, inword, [])

    # 4. No match - return sorted word list as suggestions
    return (False, "", "", sorted(words))


def add_context(match_line: str, words: str, add_func: bool, copyfrom: str) -> None:
    """Insert a derived context if one doesn't already exist.

    Mirrors Perl's add_context(): used by get_context() when expanding
    alternates and key=value pairs. If `add_func` and `copyfrom` has a handler,
    the new entry inherits that handler.
    """
    if match_line in COMMANDS:
        return
    entry = CommandEntry(words=words)
    if add_func and copyfrom in COMMANDS:
        entry.func = COMMANDS[copyfrom].func
    COMMANDS[match_line] = entry


def get_context(match_line: str) -> list[str]:
    """Return the list of valid next-tokens for a given match-line.

    Expands `a|b|c` alternates and `key=<special>` pairs by side-effect -
    new derived entries get inserted into COMMANDS on first use, so future
    lookups at deeper contexts find them.
    """
    match_line = match_line.strip()
    if not match_line:
        match_line = "NULL"
    entry = COMMANDS.get(match_line)
    if entry is None or entry.words is None:
        return []

    words: list[str] = []
    wordlist = entry.words
    for cw in wordlist.split():
        if "|" in cw:
            for alt in cw.split("|"):
                _append_alt(match_line, wordlist, alt, words)
        else:
            _append_alt(match_line, wordlist, cw, words)
    return words


def _append_alt(match_line: str, wordlist: str, alt: str, words: list[str]) -> None:
    import re as _re

    m = _re.match(r"^(\S+)=(<\S+>)$", alt)
    if m:
        key, spec = m.group(1), m.group(2)
        words.append(key)
        add_context(f"{match_line} {key}", spec, add_func=False, copyfrom="")
        add_context(f"{match_line} {key} {spec}", wordlist, add_func=True, copyfrom=match_line)
    else:
        words.append(alt)
        if not alt.startswith("<"):
            add_context(f"{match_line} {alt}", wordlist, add_func=True, copyfrom=match_line)


def lastarg(line: str) -> tuple[str, str]:
    """Return (prearg, lastarg). See Perl sub lastarg() lines 893-922.

    - ""              -> ("NULL", "")
    - "show"          -> ("NULL", "show")
    - "show zone "    -> ("zone", "")
    - "show zone fo"  -> ("zone", "fo")
    """
    if line == "":
        return ("NULL", "")
    if line.endswith(" ") or line.endswith("\t"):
        # trailing whitespace - last complete word is the "pre", current is empty
        tokens = line.split()
        if len(tokens) == 0:
            return ("NULL", "")
        return (tokens[-1], "")
    tokens = line.split()
    if len(tokens) == 1:
        return ("NULL", tokens[0])
    return (tokens[-2], tokens[-1])


def _tokenize(line: str) -> list[str]:
    """Split on whitespace while preserving double-quoted substrings as one
    token (with the quotes kept). Matches Perl's URL-encoding-based quote
    protection but without the encoding step - simpler and equivalent.

    Additionally, bare ``key=value`` tokens (no quotes, no leading ``<``) are
    split on the first ``=`` so that ``a_record=web.foo.com`` becomes the two
    tokens ``["a_record", "web.foo.com"]``, mirroring the Perl parser behaviour
    where ``key=value`` is syntactic sugar for ``key value``.
    """
    tokens: list[str] = []
    current: list[str] = []
    in_quotes = False
    for ch in line:
        if ch == '"':
            current.append(ch)
            in_quotes = not in_quotes
        elif ch.isspace() and not in_quotes:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(ch)
    if current:
        tokens.append("".join(current))

    # Split bare key=value tokens (not quoted, not <special>) on the first '='.
    result: list[str] = []
    for tok in tokens:
        if "=" in tok and not tok.startswith("<") and not tok.startswith('"'):
            key, _, val = tok.partition("=")
            if key and val:
                result.append(key)
                result.append(val)
                continue
        result.append(tok)
    return result


def expand_line(line: str) -> tuple[str, str, str]:
    """Walk tokens left-to-right, returning (expanded, error, match_line).

    `match_line` uses `<special>` tokens in place of concrete values so the
    COMMANDS dict can be looked up; `expanded` contains the concrete values.
    """
    line = line.strip()
    expline = ""
    matchline = ""
    for arg in _tokenize(line):
        context_key = matchline.strip() if matchline.strip() else "NULL"
        words = get_context(context_key)
        done, sptype, expword, matches = expand_word(arg, words)

        if expword and matches:
            # Ambiguous - stop and report.
            error = f"  Ambiguous : {expline}({' '.join(matches)})"
            return (expline, error, matchline)
        if sptype:
            expline += f"{expword} "
            matchline += f"{sptype} "
        elif not expword:
            # Unknown word - marker-based error, matching Perl.
            expline += arg
            matchline += arg
            bad_at = len(expline) - len(arg)
            spc = " " * bad_at + "^"
            error = f"{spc}--- Unknown argument at marker"
            return (expline, error, matchline)
        else:
            expline += expword  # expword has trailing space from expand_word
            matchline += expword

    return (expline.strip(), "", matchline.strip())
