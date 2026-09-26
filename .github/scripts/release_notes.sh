#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.
#
# Print the CHANGELOG section for a tag, falling back to the commit log.
#
# `git log` between tags is a poor substitute here: the history was squashed for
# the public release, so the first tag would produce a single line, and the
# CHANGELOG already carries a written, categorised account of every release.
set -euo pipefail

tag="${1:?usage: release_notes.sh vX.Y.Z [changelog]}"
changelog="${2:-CHANGELOG.md}"
version="${tag#v}"

# Everything between this version's heading and the next `## [` heading.
section="$(
  awk -v want="## [${version}]" '
    index($0, want) == 1 { collecting = 1; next }
    collecting && /^## \[/  { exit }
    collecting              { print }
  ' "$changelog"
)"

# Strip leading and trailing blank lines.
section="$(printf '%s\n' "$section" | sed -e '/./,$!d' | sed -e :a -e '/^\n*$/{$d;N;};/\n$/ba')"

if [ -n "$section" ]; then
  printf '%s\n' "$section"
  exit 0
fi

echo "::warning title=No changelog section::${changelog} has no '## [${version}]' heading; falling back to the commit log." >&2
# Fall back to HEAD when the tag is not resolvable, so a notes problem never
# fails the release job on its own.
ref="$tag"
git rev-parse --verify --quiet "$tag" >/dev/null || ref="HEAD"
prev="$(git describe --tags --abbrev=0 "${ref}^" 2>/dev/null || true)"
if [ -n "$prev" ]; then
  git log --pretty='* %s' "${prev}..${ref}"
else
  git log --pretty='* %s' "$ref"
fi
