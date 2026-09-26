#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

# smoke.sh - orchestrate a smoke-test against a live NIOS grid.
#
# Usage:
#   scripts/smoke/smoke.sh -s <host> -u <user> -p <pw> \
#       [--scale tiny|small|full|production]   # default: small
#       [--tag <tag>]                 # default: v1
#       [--grid <name>]               # grid name; must match `show grid`
#       [--members <n>]               # override the scale's member count
#       [--phases 1,2,3]              # default: 1,2,3,4,5,6,7,8,9
#       [--build]                     # run build phase
#       [--verify]                    # run verify phase
#       [--teardown]                  # run teardown phase
#       [--all]                       # --build --verify --teardown
#       [-o <outdir>]                 # keep generated .ibcli + logs here
#
# You must pass at least one of --build / --verify / --teardown (or --all).
# Default is conservative: no operation runs unless you ask for it.
#
# Exit codes:
#   0 - every requested phase succeeded
#   1 - at least one phase failed (see the log file for detail)
#   2 - bad invocation

set -euo pipefail

HOST="${IBCLI_HOST:-}"
USER="${IBCLI_USER:-}"
PASS="${IBCLI_PASS:-}"
SCALE="small"
TAG="v1"
GRID="${IBCLI_SMOKE_GRID:-}"
MEMBERS=""
PHASES="0,1,2,10,3,4,5,6,7,8,9"
OUTDIR=""
DO_BUILD=0
DO_VERIFY=0
DO_TEARDOWN=0

usage() {
    sed -n '2,19p' "$0" >&2
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -s) HOST="$2"; shift 2 ;;
        -u) USER="$2"; shift 2 ;;
        -p) PASS="$2"; shift 2 ;;
        --scale) SCALE="$2"; shift 2 ;;
        --tag) TAG="$2"; shift 2 ;;
        --grid) GRID="$2"; shift 2 ;;
        --members) MEMBERS="$2"; shift 2 ;;
        --phases) PHASES="$2"; shift 2 ;;
        -o) OUTDIR="$2"; shift 2 ;;
        --build) DO_BUILD=1; shift ;;
        --verify) DO_VERIFY=1; shift ;;
        --teardown) DO_TEARDOWN=1; shift ;;
        --all) DO_BUILD=1; DO_VERIFY=1; DO_TEARDOWN=1; shift ;;
        -h|--help) usage ;;
        *) echo "unknown arg: $1" >&2; usage ;;
    esac
done

if [[ -z "$HOST" || -z "$USER" || -z "$PASS" ]]; then
    echo "error: host/user/password required (flags or env)" >&2
    usage
fi

if [[ "$DO_BUILD" -eq 0 && "$DO_VERIFY" -eq 0 && "$DO_TEARDOWN" -eq 0 ]]; then
    echo "error: pass at least one of --build / --verify / --teardown / --all" >&2
    usage
fi

# Repo root (script is at scripts/smoke/smoke.sh).
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"

# Output dir: per-run tmpdir by default.
if [[ -z "$OUTDIR" ]]; then
    OUTDIR="$(mktemp -d -t ibcli-smoke-XXXXXX)"
fi
mkdir -p "$OUTDIR"

BUILD_SCRIPT="$OUTDIR/build.ibcli"
BUILD_LOG="$OUTDIR/build.log"
VERIFY_LOG="$OUTDIR/verify.log"
TEARDOWN_SCRIPT="$OUTDIR/teardown.ibcli"
TEARDOWN_LOG="$OUTDIR/teardown.log"

# Flags shared by build.py / teardown.py / verify.py so the three agree on
# how many members exist and which grid they belong to. A mismatch leaves
# pre-provisioned members behind at teardown.
EXTRA=()
[[ -n "$GRID" ]] && EXTRA+=(--grid "$GRID")
[[ -n "$MEMBERS" ]] && EXTRA+=(--members "$MEMBERS")
# verify.py counts objects over WAPI and never names the grid, so it takes
# --members only.
VERIFY_EXTRA=()
[[ -n "$MEMBERS" ]] && VERIFY_EXTRA+=(--members "$MEMBERS")

# ibcli runner: prefer an explicit $IBCLI, then the repo venv, then
# poetry. Lets the harness run on a machine without poetry installed.
if [[ -n "${IBCLI:-}" ]]; then
    read -r -a IBCLI_CMD <<< "$IBCLI"
elif [[ -x "$REPO/.venv/bin/ibcli" ]]; then
    IBCLI_CMD=("$REPO/.venv/bin/ibcli")
elif [[ -x "$REPO/.venv/bin/python" ]]; then
    IBCLI_CMD=("$REPO/.venv/bin/python" -m ibcli)
else
    IBCLI_CMD=(poetry run ibcli)
fi

echo "smoke outdir: $OUTDIR"
echo "  scale=$SCALE  tag=$TAG  phases=$PHASES  grid=${GRID:-<default>}  members=${MEMBERS:-<scale>}"
echo "  ibcli: ${IBCLI_CMD[*]}"
echo

FAIL=0

# -----------------------------------------------------------------------------
# Build
# -----------------------------------------------------------------------------
if [[ "$DO_BUILD" -eq 1 ]]; then
    echo "[build] generating script..."
    python3 scripts/smoke/build.py --scale "$SCALE" --tag "$TAG" \
        --phases "$PHASES" "${EXTRA[@]}" > "$BUILD_SCRIPT"
    LINES=$(wc -l < "$BUILD_SCRIPT" | tr -d ' ')
    echo "[build] $LINES commands in $BUILD_SCRIPT"

    echo "[build] running against $HOST..."
    set +e
    "${IBCLI_CMD[@]}" -i -k -s "$HOST" -u "$USER" -p "$PASS" "$BUILD_SCRIPT" \
        > "$BUILD_LOG" 2>&1
    RC=$?
    set -e

    ERRS=$(grep -c "^  Error:" "$BUILD_LOG" || true)
    SKIPS=$(grep -c "^  Skipped:" "$BUILD_LOG" || true)
    OKS=$(grep -c "^  OK:" "$BUILD_LOG" || true)
    echo "[build] exit=$RC  OK=$OKS  Skipped=$SKIPS  Error=$ERRS  log=$BUILD_LOG"
    if [[ "$ERRS" -gt 0 ]]; then
        echo "[build] sample errors:"
        grep "^  Error:" "$BUILD_LOG" | sort | uniq -c | sort -rn | head -10
        FAIL=1
    fi
fi

# -----------------------------------------------------------------------------
# Verify
# -----------------------------------------------------------------------------
if [[ "$DO_VERIFY" -eq 1 ]]; then
    echo
    echo "[verify] counting objects on $HOST..."
    set +e
    python3 scripts/smoke/verify.py \
        --host "$HOST" --user "$USER" --password "$PASS" \
        --scale "$SCALE" --tag "$TAG" "${VERIFY_EXTRA[@]}" \
        | tee "$VERIFY_LOG"
    VRC=${PIPESTATUS[0]}
    set -e
    if [[ "$VRC" -ne 0 ]]; then
        FAIL=1
    fi
fi

# -----------------------------------------------------------------------------
# Teardown
# -----------------------------------------------------------------------------
if [[ "$DO_TEARDOWN" -eq 1 ]]; then
    echo
    echo "[teardown] generating script..."
    python3 scripts/smoke/teardown.py --scale "$SCALE" \
        --phases "$PHASES" "${EXTRA[@]}" > "$TEARDOWN_SCRIPT"
    LINES=$(wc -l < "$TEARDOWN_SCRIPT" | tr -d ' ')
    echo "[teardown] $LINES commands in $TEARDOWN_SCRIPT"

    echo "[teardown] running against $HOST..."
    set +e
    "${IBCLI_CMD[@]}" -i -k -s "$HOST" -u "$USER" -p "$PASS" "$TEARDOWN_SCRIPT" \
        > "$TEARDOWN_LOG" 2>&1
    RC=$?
    set -e

    ERRS=$(grep -c "^  Error:" "$TEARDOWN_LOG" || true)
    OKS=$(grep -c "^  OK:" "$TEARDOWN_LOG" || true)
    echo "[teardown] exit=$RC  OK=$OKS  Error=$ERRS  log=$TEARDOWN_LOG"
    if [[ "$ERRS" -gt 0 ]]; then
        echo "[teardown] sample errors:"
        grep "^  Error:" "$TEARDOWN_LOG" | sort | uniq -c | sort -rn | head -10
        # Teardown errors are warnings - objects may not exist. Don't fail
        # the run on them.
    fi
fi

if [[ "$FAIL" -ne 0 ]]; then
    echo
    echo "SMOKE FAILED - see $OUTDIR for logs"
    exit 1
fi

echo
echo "smoke OK"
exit 0
