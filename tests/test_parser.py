# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from ibcli.parser import abbrev, expand_line, expand_word, get_context, lastarg
from ibcli.registry import COMMANDS, CommandEntry


def test_abbrev_single_word():
    assert abbrev(["configure"]) == {
        "c": "configure",
        "co": "configure",
        "con": "configure",
        "conf": "configure",
        "confi": "configure",
        "config": "configure",
        "configu": "configure",
        "configur": "configure",
        "configure": "configure",
    }


def test_abbrev_two_disjoint_words():
    result = abbrev(["show", "set"])
    assert result["sh"] == "show"
    assert result["sho"] == "show"
    assert result["show"] == "show"
    assert result["se"] == "set"
    assert result["set"] == "set"
    assert "s" not in result  # ambiguous


def test_abbrev_word_that_is_prefix_of_another():
    result = abbrev(["show", "shown"])
    assert result["show"] == "show"  # full word wins
    assert result["shown"] == "shown"
    assert "sho" not in result  # ambiguous between show/shown
    assert "sh" not in result  # ambiguous


def test_expand_word_unique_abbrev():
    done, sptype, expword, matches = expand_word("co", ["configure", "show", "set"])
    assert done is True
    assert sptype == ""
    assert expword == "configure "  # trailing space signals completion
    assert matches == []


def test_expand_word_full_match():
    done, sptype, expword, matches = expand_word("show", ["show", "set"])
    assert done is True
    assert expword == "show "


def test_expand_word_ambiguous():
    done, sptype, expword, matches = expand_word("s", ["show", "set"])
    assert done is False
    assert sptype == ""
    assert expword == "s"
    assert matches == ["set", "show"]


def test_expand_word_matches_special():
    done, sptype, expword, matches = expand_word("1.2.3.4", ["<ip>", "view"])
    assert done is False
    assert sptype == "<ip>"
    assert expword == "1.2.3.4"
    assert matches == []


def test_expand_word_no_match():
    done, sptype, expword, matches = expand_word("xyz", ["show", "set"])
    assert done is False
    assert sptype == ""
    assert expword == ""
    assert matches == ["set", "show"]


def test_expand_word_literal_wins_over_special():
    # The word "add" also syntactically matches <zone> (^\S+$), but literal
    # next-words take priority over SPECOPS regexes.
    done, sptype, expword, matches = expand_word("add", ["add", "<zone>"])
    assert done is True
    assert sptype == ""
    assert expword == "add "


def test_expand_word_blank_input_returns_sorted_words():
    done, sptype, expword, matches = expand_word("", ["show", "configure", "help"])
    assert done is False
    assert expword == ""
    assert matches == ["configure", "help", "show"]


def test_get_context_null_top_level():
    COMMANDS["NULL"] = CommandEntry(words="help configure show")
    assert set(get_context("NULL")) == {"help", "configure", "show"}


def test_get_context_splits_alternates():
    COMMANDS["show admin role"] = CommandEntry(words="<cr>|<name>")
    words = get_context("show admin role")
    assert set(words) == {"<cr>", "<name>"}


def test_get_context_expands_key_equals_value_pair():
    # configure zone add <zone> with 'comment=<comment>' creates two sub-contexts:
    # "configure zone add <zone> comment" -> words "<comment>"
    # "configure zone add <zone> comment <comment>" -> words (original wordlist)
    COMMANDS["configure zone add <zone>"] = CommandEntry(
        words="<cr> comment=<comment>|view=<name>",
    )
    words = get_context("configure zone add <zone>")
    assert "comment" in words
    assert "view" in words
    # And the side-effects must have created the follow-on contexts.
    assert COMMANDS["configure zone add <zone> comment"].words == "<comment>"
    assert COMMANDS["configure zone add <zone> comment <comment>"].words == (
        "<cr> comment=<comment>|view=<name>"
    )


def test_get_context_returns_empty_for_unknown():
    assert get_context("no such line") == []


def test_lastarg_empty_line():
    prearg, last = lastarg("")
    assert prearg == "NULL"
    assert last == ""


def test_lastarg_single_word_no_trailing_space():
    prearg, last = lastarg("sh")
    assert prearg == "NULL"
    assert last == "sh"


def test_lastarg_trailing_space():
    prearg, last = lastarg("show zone ")
    assert prearg == "zone"
    assert last == ""


def test_lastarg_partial_last_word():
    prearg, last = lastarg("show zo")
    assert prearg == "show"
    assert last == "zo"


def test_expand_line_walks_tokens(monkeypatch):
    from ibcli.registry import COMMANDS, CommandEntry

    COMMANDS.clear()
    COMMANDS["NULL"] = CommandEntry(words="configure show")
    COMMANDS["configure"] = CommandEntry(words="zone server")
    COMMANDS["configure zone"] = CommandEntry(words="add <zone>")
    COMMANDS["configure zone add"] = CommandEntry(words="<zone>")
    COMMANDS["configure zone add <zone>"] = CommandEntry(words="<cr>")

    expanded, error, match_line = expand_line("co z a foo.com")
    assert error == ""
    assert expanded == "configure zone add foo.com"
    assert match_line == "configure zone add <zone>"


def test_expand_line_preserves_quoted_multi_word_token():
    from ibcli.parser import _tokenize  # private helper

    assert _tokenize('configure zone add foo comment "hello world"') == [
        "configure",
        "zone",
        "add",
        "foo",
        "comment",
        '"hello world"',
    ]


def test_expand_line_unknown_word_reports_error():
    from ibcli.registry import COMMANDS, CommandEntry

    COMMANDS.clear()
    COMMANDS["NULL"] = CommandEntry(words="configure show")
    expanded, error, match_line = expand_line("bogus")
    assert "Unknown" in error
