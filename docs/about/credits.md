# Credits

## Original Perl ibcli

The Python port is a ground-up rewrite of the original **ibcli** Perl tool, written by **Geoff Horne**. The Perl tool
established the command syntax, WAPI mapping conventions, tab-completion UX, and the `key=value` tokenizer behaviour
that the Python port faithfully reproduces.

Key design decisions inherited from the Perl tool:

- The two-token `key value` convention (rather than `key=value` at the command level).
- The `set key value` extensible attribute pattern and the four-depth chain limit.
- The `configure server <host> <user> <password>` connect command with `ibapauth` cookie reuse.
- Arpa form conversion for reverse-zone CIDRs.
- The `<cr>` token as a completion signal for valid-but-not-required end-of-input positions.
- The ALIASES mechanism (short prefix substitutions applied before parsing). The original Perl aliases (`pwd`, `cd`,
  `ls`, `prop`, `info`) targeted a `show file` / `configure file` subtree that was never implemented in the Python
  port; the surviving aliases (`pwd`, `info`) retarget the same mechanism at the real `show debug` subcommands.

## ibx-nios-sdk

All WAPI interaction goes through the Infoblox-published
**[`ibx-nios-sdk`](https://github.com/Infoblox-PS/ibx-nios-sdk)** async Python SDK. The SDK provides version
negotiation, cookie-based session handling, typed resource classes under `NiosClient.<domain>.<object>`, pagination,
and the three-step fileop upload/download protocol. ibcli is a thin CLI layered on top.

## prompt_toolkit

The REPL, tab-completion menu, key bindings, and `FileHistory` are built on
**[prompt_toolkit](https://python-prompt-toolkit.readthedocs.io/)** by Jonathan Slenders. prompt_toolkit provides the
`Completer` base class, `Document`, `PromptSession`, and the `CompleteStyle.READLINE_LIKE` completion display used by
ibcli. Its asyncio integration is what lets the REPL and the async WAPI handlers share a single event loop.

## httpx

Under the SDK, every WAPI request rides on **[httpx](https://www.python-httpx.org/)** by Tom Christie.
`httpx.AsyncClient` provides the connection pooling and cookie jar used for `ibapauth` persistence;
`httpx.MockTransport` is what the mocked test suite plugs in to intercept requests without hitting a grid.

## pytest

The test suite is built on **[pytest](https://docs.pytest.org/)**, `pytest-asyncio` (async test support), and
`pytest-cov` (coverage). All 3,278 tests run without a live NIOS grid - requests are intercepted via
`httpx.MockTransport` handlers that return pre-configured JSON responses, enabling full offline CI in ~3 seconds.
