# Contributing

## Getting set up

```bash
git clone https://github.com/Infoblox-PS/ibcli.git
cd ibcli
poetry install --with dev,lint
```

`dev`, `lint` and `docs` are PEP 735 dependency groups, not extras. With uv: `uv sync --group dev --group lint`.

## Before you open a pull request

Run what CI runs:

```bash
poetry run pytest                                                              # 3,284 tests, no grid needed
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

Maintainers only, and it is one command from a clean `main`:

```bash
scripts/release.sh 1.1.0             # or --dry-run to see the diff and change nothing
```

That bumps `version` in `pyproject.toml`, `__version__` in `src/ibcli/__init__.py` and the changelog heading
together, relocks, runs everything CI runs, then commits, tags `v1.1.0` and pushes. Pushing the tag is what starts
`.github/workflows/release.yml`, which re-checks that the tag matches the packaged version, builds, rejects
metadata PyPI would refuse, publishes the GitHub release and uploads to PyPI.

The tag is pushed from your machine on purpose. A tag pushed by `GITHUB_TOKEN` inside Actions does not start
another workflow, so a "prepare release" job would create the tag and then silently never release.

Two things the script will refuse: an `[Unreleased]` section with nothing in it, and a `main` that is dirty or out
of sync with the remote. Release notes come from the CHANGELOG section for that version, so the `## [X.Y.Z]`
heading has to exist - `tests/test_packaging.py` pins that, along with the version agreeing across all three files.

PyPI uploading is gated on the repository variable `PUBLISH_TO_PYPI` being `true`, so tagging works before
publishing is configured. The upload authenticates with the `PYPI_API_TOKEN` secret when it is set, and otherwise
falls through to Trusted Publishing.

Neither one decides ownership. PyPI gives a project to whoever creates it, and uploading a name that does not yet
exist creates it under the uploading account - so a project meant to belong to the InfobloxPS organisation has to
be created from that organisation's Projects page before its first upload, or transferred afterwards.
