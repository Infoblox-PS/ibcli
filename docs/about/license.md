# License

ibcli is distributed under the **GNU General Public License v3.0 or later**
(SPDX: `GPL-3.0-or-later`).

The full license text ships with the source as [`LICENSE`](https://github.com/Infoblox-PS/ibcli/blob/main/LICENSE),
and is published at <https://www.gnu.org/licenses/gpl-3.0.html>. Run `ibcli --license` to
print the notice from the CLI itself.

```text
ibcli - a Python port of the Infoblox CLI written by Geoff Horne
Copyright (C) 2026 Infoblox Inc.

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <https://www.gnu.org/licenses/>.
```

## What this means in practice

The GPL is a **copyleft** license, which makes it stricter than the permissive licenses common in
this ecosystem. In short:

| If you… | Then… |
|---|---|
| Run ibcli to manage a grid | No obligation. Using the tool is unrestricted. |
| Modify it for internal use only | No obligation, as long as you do not distribute the result. |
| Distribute it, modified or not | You must pass on the source, under the GPL, with the same rights. |
| Incorporate this code into other software you distribute | That combined work must also be GPL-licensed. |

"Distribute" means conveying the software to someone else - shipping it in a product, publishing a
fork, or handing a modified build to a customer. Internal use inside one organisation is not
distribution.

!!! note "Why v3 and not v2"

    GPLv3 carries an explicit patent grant, a cure period for first-time violations, and - decisive
    here - compatibility with Apache 2.0. `ibx-nios-sdk`, the SDK every grid call goes through, is
    Apache 2.0, which **cannot** be combined with GPLv2. The `-or-later` suffix follows the FSF's own
    recommendation, letting downstreams adopt a future GPL version without tracking down every
    copyright holder.

## Trademarks

INFOBLOX is a trademark of Infoblox Inc. or its affiliated companies, registered in the United States and other
countries. Infoblox Grid is a trademark of Infoblox Inc. NIOS and other product names referenced throughout this
documentation are marks of Infoblox Inc. or its affiliated companies.

This documentation uses those marks descriptively, to identify the products the tool operates against. Per the
[Infoblox Trademark Use Guidelines](https://www.infoblox.com/wp-content/uploads/infoblox-trademark-guidelines.pdf),
the marks remain the property of Infoblox Inc.; nothing here grants any licence to them. The published list of marks
is expressly non-exhaustive, so absence of a name from it does not imply it is unclaimed.

Questions about mark usage go to `brand@infoblox.com`.

## Third-party dependencies

ibcli depends on the following open-source packages, each with its own license.

### Prerequisite

[`ibx-nios-sdk`](https://github.com/Infoblox-PS/ibx-nios-sdk) is a declared dependency and installs with ibcli.
See [Installation](../getting-started/installation.md).

| Package | Version | License | Purpose |
|---|---|---|---|
| `ibx-nios-sdk` | 1.0.0+ | Apache 2.0 | Async NIOS WAPI client; every grid call goes through it |

### Runtime

| Package | License | Purpose |
|---|---|---|
| `httpx` | BSD 3-Clause | Async HTTP client for WAPI calls |
| `prompt_toolkit` | BSD 3-Clause | REPL, completion menu, key bindings |
| `zensical` | MIT | Documentation site generator |

Pulled in transitively by `httpx`:

| Package | License | Purpose |
|---|---|---|
| `httpcore` | BSD 3-Clause | Connection pooling and HTTP/1.1 transport |
| `h11` | MIT | HTTP/1.1 protocol implementation |
| `anyio` | MIT | Async runtime abstraction |
| `certifi` | MPL 2.0 | Default CA bundle for TLS verification |
| `idna` | BSD 3-Clause | Internationalised domain name handling |

### Development (not shipped)

| Package | License | Purpose |
|---|---|---|
| `pytest` | MIT | Test runner |
| `pytest-asyncio` | Apache 2.0 | Async test support |
| `pytest-cov` | MIT | Coverage reporting |
| `ruff` | MIT | Linting and formatting |
| `pymarkdownlnt` | MIT | Markdown linting |

The mocked test suite uses `httpx.MockTransport` directly - there is no separate HTTP-mocking
dependency.

### Compatibility with the GPL

Every dependency above is compatible with GPLv3, in the one-way sense the GPL requires - each may
be combined into a GPL-licensed work, with the combined result distributed under the GPL:

- **BSD 3-Clause** (`httpx`, `httpcore`, `idna`, `prompt_toolkit`) and **MIT** (`h11`, `anyio`,
  `zensical`, and the dev tools) are permissive and impose no conditions the GPL conflicts with.
- **Apache 2.0** (`ibx-nios-sdk`, `pytest-asyncio`) is compatible with GPL **v3**, though not with
  GPLv2 - its patent-termination clause is the reason. Since every grid call goes through the
  Apache-licensed SDK, this is what made v3 the only workable GPL version here.
- **MPL 2.0** (`certifi`) is a file-level copyleft covering modifications to `certifi` itself. Its
  §3.3 secondary-license provision explicitly permits distribution under the GPL, and it is
  redistributed unmodified in any case.

None of these dependencies are *incorporated* into ibcli's own source; they are imported at
runtime and installed separately by the user.
