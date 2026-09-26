#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.
#
# Cut a release: bump the version everywhere, date the changelog, verify, tag
# and push. Pushing the tag is what starts .github/workflows/release.yml, which
# builds, checks the metadata, publishes the GitHub release and uploads to PyPI.
#
#   scripts/release.sh 1.1.0             # do it
#   scripts/release.sh 1.1.0 --dry-run   # show the diff, change nothing
#
# The tag is pushed with your own credentials on purpose. A tag pushed by
# GITHUB_TOKEN from inside Actions does not trigger another workflow, so a
# "prepare release" job would create the tag and then silently never release.
set -euo pipefail

cd "$(dirname "$0")/.."

die() { echo "error: $*" >&2; exit 1; }

[ $# -ge 1 ] || die "usage: scripts/release.sh <version> [--dry-run]"
VERSION="$1"
DRY_RUN=false
[ "${2:-}" = "--dry-run" ] && DRY_RUN=true
TAG="v${VERSION}"

# --- preconditions -----------------------------------------------------------
branch="$(git rev-parse --abbrev-ref HEAD)"
[ "$branch" = "main" ] || die "on '$branch'; releases are cut from main"
[ -z "$(git status --porcelain)" ] || die "working tree is dirty; commit or stash first"
git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null && die "tag ${TAG} already exists"
git fetch --quiet origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] \
  || die "main is not in sync with origin/main; pull or push first"

# --- bump --------------------------------------------------------------------
python3 scripts/bump_version.py "$VERSION"
# uv.lock records the project's own version, so it goes stale on every bump and
# CI fails on the mismatch before running a single test.
command -v uv >/dev/null && uv lock --quiet
command -v poetry >/dev/null && poetry lock --quiet >/dev/null 2>&1 || true

# --- verify ------------------------------------------------------------------
echo "--- running the checks CI runs ---"
poetry run pytest -q
poetry run ruff check src/ tests/ scripts/ .github/scripts/
poetry run ruff format --check src/ tests/ scripts/ .github/scripts/
poetry run pymarkdown --config pyproject.toml scan -r README.md CHANGELOG.md CONTRIBUTING.md SECURITY.md docs/
poetry build --quiet
python3 .github/scripts/check_no_direct_urls.py dist
echo "--- release notes preview ---"
.github/scripts/release_notes.sh "$TAG" | head -20
echo "--- (truncated) ---"

if [ "$DRY_RUN" = true ]; then
  echo
  echo "dry run: nothing committed. Changes left in the working tree:"
  git --no-pager diff --stat
  exit 0
fi

# --- commit, tag, push -------------------------------------------------------
git add -A
git commit -m "ibcli ${VERSION}"
git tag -a "$TAG" -m "ibcli ${VERSION}"
git push origin main
git push origin "$TAG"

echo
echo "pushed ${TAG}. Watch the release:"
echo "  gh run watch \$(gh run list --workflow Release --limit 1 --json databaseId -q '.[0].databaseId')"
