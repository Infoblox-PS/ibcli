# Installation

## Requirements

- **Python 3.11 or newer** (declared in `pyproject.toml`).
- No external services beyond the NIOS grid you intend to manage.

## From PyPI

```bash
pip install ibcli
```

`ibx-nios-sdk` is a prerequisite rather than a declared dependency - it is published from a private repository, so
install it first. See [the README](https://github.com/Infoblox-PS/ibcli#prerequisite-ibx-nios-sdk).

## From the repository (editable install)

Editable install is recommended for day-to-day use - `git pull` picks up changes without reinstalling.

```bash
git clone https://github.com/Infoblox-PS/ibcli.git
cd ibcli

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Editable install
pip install -e .
```

After installation, `ibcli` is on your `PATH`:

```bash
ibcli --version
ibcli 1.0.0
```

## With Poetry

If you use [Poetry](https://python-poetry.org/) (2.0 or newer - it reads the PEP 621 `[project]` metadata directly, no migration needed):

```bash
git clone https://github.com/Infoblox-PS/ibcli.git
cd ibcli
poetry install              # creates .venv, installs runtime deps, writes poetry.lock
poetry run ibcli --help # invoke without activating the venv
poetry shell                # or activate the venv (Poetry 1.x);
                            # Poetry 2.x uses `poetry env activate`
```

The committed `poetry.lock` gives reproducible installs across machines.

## Runtime dependencies

Declared in `pyproject.toml`:

| Package | Purpose |
|---|---|
| `ibx-nios-sdk` | Infoblox-published async Python SDK for WAPI - provides the `NiosClient` HTTP layer |
| `httpx` | Async HTTP client used by the SDK and by mocked tests |
| `prompt_toolkit` | Cross-platform tab completion, REPL history, line editing |

`httpx` and `prompt_toolkit` are installed automatically. `ibx-nios-sdk` is **not** - it lives in a private
repository, so declaring it as a dependency would make every install fail for anyone without access to that repo.
Install it first; ibcli checks for it at startup and explains what to do if it is missing.

## Development dependencies

```bash
pip install --group dev -e .     # pip 25.1 or newer
# or with poetry:
poetry install --with dev
```

`dev` and `lint` are PEP 735 dependency groups, not extras, so `pip install -e '.[dev]'` and
`poetry install --extras dev` do not install them. The `dev` group holds `pytest`, `pytest-asyncio`,
`pytest-cov`, `httpx` and `ruff`; `lint` holds `pymarkdownlnt`; `docs` holds `zensical`. No separate `requests-mock` library - the mocked test suite uses `httpx.MockTransport` directly.

Run the mocked suite:

```bash
pytest          # 3,278 tests, no grid required, ~9 seconds
pytest --cov    # with coverage (~93%)
```

## Windows notes

`prompt_toolkit` is cross-platform. The history file is written to `%USERPROFILE%\.ibcli_history`. TLS certificate verification behaves identically to other platforms.

## Verifying the install

```bash
ibcli -l    # list every registered command and exit
ibcli -V    # print version and exit
```

If `ibcli` is not found after install, confirm your virtual environment is active (`which ibcli` should land
inside `.venv/bin/`). With Poetry, prefix commands with `poetry run` to invoke without activating the venv.
