# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from ibcli.commands import server, system, zone  # noqa: F401 - register all
from ibcli.completer import IbcliCompleter


def _completions(text: str) -> list[str]:
    comp = IbcliCompleter()
    doc = Document(text, cursor_position=len(text))
    return [c.text for c in comp.get_completions(doc, CompleteEvent())]


def test_empty_input_yields_top_level():
    cs = _completions("")
    assert "show" in cs
    assert "configure" in cs


def test_unique_prefix_completes():
    cs = _completions("co")
    assert cs == ["configure"]


def test_ambiguous_prefix_lists_candidates():
    # "s" is ambiguous between show + (anything starting with s at top level).
    cs = _completions("s")
    assert "show" in cs


def test_after_complete_word_yields_next_context():
    cs = _completions("show ")
    # some known next-words
    assert "zone" in cs or "grid" in cs


def test_special_value_yields_no_completions():
    # "show zone foo.com " - next is <cr>|view=...|... ; <zone> itself is not
    # auto-completable, but the following context is.
    cs = _completions("show zone 1.2.3.4 ")
    # any completions offered here must not be <special> tokens
    for c in cs:
        assert not c.startswith("<")


def test_unknown_command_suppresses_completions():
    cs = _completions("totallybogusverb ")
    assert cs == []


def test_dynamic_completions_from_ctx():
    """A registered dynamic callback surfaces its values."""
    from ibcli.context import Context
    from ibcli.registry import COMMANDS, register

    register("show", words="probe3")
    register(
        "show probe3", words="<name>", dynamic=lambda ctx: [("alpha", "meta-a"), ("beta", "meta-b")]
    )
    assert COMMANDS["show probe3"].dynamic is not None

    ctx = Context()
    comp = IbcliCompleter(ctx=ctx)
    doc = Document("show probe3 ", cursor_position=len("show probe3 "))
    out = [c.text for c in comp.get_completions(doc, CompleteEvent())]
    assert "alpha" in out and "beta" in out

    # Prefix filtering on dynamics works:
    doc2 = Document("show probe3 a", cursor_position=len("show probe3 a"))
    out2 = [c.text for c in comp.get_completions(doc2, CompleteEvent())]
    assert "alpha" in out2 and "beta" not in out2


def test_dynamic_callback_exception_is_swallowed():
    from ibcli.context import Context
    from ibcli.registry import register

    def boom(ctx):
        raise RuntimeError("nope")

    register("show", words="probe4")
    register("show probe4", words="<name>", dynamic=boom)

    ctx = Context()
    comp = IbcliCompleter(ctx=ctx)
    doc = Document("show probe4 ", cursor_position=len("show probe4 "))
    # Must not raise - dynamic errors are swallowed.
    list(comp.get_completions(doc, CompleteEvent()))


def test_cr_special_renders_as_hint():
    # After `show grid` the next context contains <cr>; it should be yielded
    # as a hint-only completion (empty text).
    from ibcli.context import Context

    comp = IbcliCompleter(ctx=Context())
    doc = Document("show grid ", cursor_position=len("show grid "))
    completions = list(comp.get_completions(doc, CompleteEvent()))
    # Hint completions have empty text.
    assert any(c.text == "" for c in completions)
