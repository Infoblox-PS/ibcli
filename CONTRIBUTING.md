# Contributing

## Getting set up

`ibx-nios-sdk` 0.2.0 or newer is a prerequisite and is published from a private repository, so install it first:

```bash
git clone https://github.com/Infoblox-PS/ibcli.git
cd ibcli
poetry install --with dev,lint
poetry run pip install 'ibx-nios-sdk @ git+https://github.com/Infoblox-PS/ibx-nios-sdk@v0.2.0'
```

`dev`, `lint` and `docs` are PEP 735 dependency groups, not extras. With uv: `uv sync --group dev --group lint`.

## Before you open a pull request

Run what CI runs:

```bash
poetry run pytest                                                              # 3,278 tests, no grid needed
poetry run ruff check src/ tests/ scripts/ .github/scripts/
poetry run ruff format --check src/ tests/ scripts/ .github/scripts/
poetry run pymarkdown --config pyproject.toml scan -r README.md CHANGELOG.md CONTRIBUTING.md SECURITY.md docs/
```

The mocked suite needs no NIOS grid. The `real_grid` tests are skipped unless `IBCLI_TEST_GRID`, `IBCLI_TEST_USER`
and `IBCLI_TEST_PASS` are set; they change state on whatever grid they point at, so never aim them at production.

## House rules

- **ASCII hyphens only.** No em or en dashes, in code, docs or commit messages - `tests/test_docs_structure.py`
  fails on them.
- **Document the why.** A comment that restates the code is noise; one that records the constraint behind it is
  what keeps the next change from undoing it.
- **Add a CHANGELOG entry** under `## [Unreleased]` for anything a user would notice.
- **Never commit grid data.** No real hostnames, addresses, credentials, backups or support bundles. Examples use
  `example.com` and RFC 1918 or documentation address space.

## Licence and copyright

ibcli is GPL-3.0-or-later and the copyright is held by Infoblox Inc. By contributing you agree your contribution is
licensed on those terms. Contributors are credited in the git history; source files carry the Infoblox copyright
line and an `SPDX-License-Identifier` header, which new files should copy.

## Releases

Maintainers only. Date the `[Unreleased]` changelog section, bump `version` in `pyproject.toml` and
`__version__` in `src/ibcli/__init__.py` together, merge, then push a `vX.Y.Z` tag. The tag triggers
`.github/workflows/release.yml`, which verifies the tag matches the packaged version, builds, checks the metadata,
publishes the GitHub release and uploads to PyPI. The release notes are the CHANGELOG section for that version, so
a missing or misnamed `## [X.Y.Z]` heading downgrades them to a bare commit list.
