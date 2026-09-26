#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

# sweep-show.sh - run every no-arg `show` command against a live NIOS grid and
# classify the errors.
#
# Usage:
#   scripts/sweep-show.sh -s <host> -u <user> -p <password> [-o <outdir>] [--deep]
#
# Or via env vars (handy for CI / not-in-history):
#   IBCLI_HOST=... IBCLI_USER=... IBCLI_PASS=... scripts/sweep-show.sh
#
# --deep also re-runs every show command with fields=<every SDK field> to
# catch version-specific "Unknown argument/field" / "Field is not readable"
# errors that the bare form doesn't surface. Takes a separate pass; the
# deep-sweep results get their own section in the report. Large models are
# split into sequential 40-field chunks (one command invocation per chunk)
# so every field is exercised deterministically.
#
# --require-smoke runs scripts/smoke/verify.py first and aborts if the grid
# isn't populated with smoke-build objects. Use this to ensure the sweep is
# looking at real data before committing to a full run.
#
# Exit codes:
#   0 - no suspected CLI bugs (only friendly-usage hints and/or grid-config errors)
#   1 - one or more errors look like CLI bugs; see the "BUGS" section in output
#   2 - bad invocation

set -euo pipefail

HOST="${IBCLI_HOST:-}"
USER="${IBCLI_USER:-}"
PASS="${IBCLI_PASS:-}"
OUTDIR=""
QUIET=0
DEEP=0
REQUIRE_SMOKE=0
SMOKE_SCALE="${IBCLI_SMOKE_SCALE:-small}"
SMOKE_TAG="${IBCLI_SMOKE_TAG:-v1}"

usage() {
    sed -n '2,22p' "$0" >&2
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -s) HOST="$2"; shift 2 ;;
        -u) USER="$2"; shift 2 ;;
        -p) PASS="$2"; shift 2 ;;
        -o) OUTDIR="$2"; shift 2 ;;
        -q|--quiet) QUIET=1; shift ;;
        --deep) DEEP=1; shift ;;
        --require-smoke) REQUIRE_SMOKE=1; shift ;;
        --smoke-scale) SMOKE_SCALE="$2"; shift 2 ;;
        --smoke-tag)   SMOKE_TAG="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "unknown arg: $1" >&2; usage ;;
    esac
done

if [[ -z "$HOST" || -z "$USER" || -z "$PASS" ]]; then
    echo "error: host/user/password required (flags or env)" >&2
    usage
fi

if [[ -z "$OUTDIR" ]]; then
    OUTDIR="$(mktemp -d -t ibcli-sweep-XXXXXX)"
fi
mkdir -p "$OUTDIR"

# Run from repo root so relative script paths resolve.
cd "$(dirname "$0")/.."

# Runners: prefer an explicit $IBCLI, then the repo venv, then poetry - so
# the sweep works on a machine without poetry installed.
if [[ -n "${IBCLI:-}" ]]; then
    read -r -a IBCLI_CMD <<< "$IBCLI"
elif [[ -x "$PWD/.venv/bin/ibcli" ]]; then
    IBCLI_CMD=("$PWD/.venv/bin/ibcli")
elif [[ -x "$PWD/.venv/bin/python" ]]; then
    IBCLI_CMD=("$PWD/.venv/bin/python" -m ibcli)
else
    IBCLI_CMD=(poetry run ibcli)
fi
if [[ -x "$PWD/.venv/bin/python" ]]; then
    PY_CMD=("$PWD/.venv/bin/python")
else
    PY_CMD=(poetry run python)
fi

# Pre-run smoke-build verification - opt-in. Runs the smoke verify.py,
# which counts objects by name prefix / EA and compares against the
# selected scale's expected totals. Abort the sweep if verify fails so
# we don't chase field errors that are actually empty-data artefacts.
if [[ "$REQUIRE_SMOKE" -eq 1 ]]; then
    echo "[precheck] verifying smoke-build state on $HOST (scale=$SMOKE_SCALE tag=$SMOKE_TAG)..." >&2
    if ! "${PY_CMD[@]}" scripts/smoke/verify.py \
            --host "$HOST" --user "$USER" --password "$PASS" \
            --scale "$SMOKE_SCALE" --tag "$SMOKE_TAG"
    then
        echo "error: smoke-build verification failed. Build with scripts/smoke/build.py" >&2
        echo "       or re-run without --require-smoke to sweep anyway." >&2
        exit 1
    fi
fi

SCRIPT="$OUTDIR/sweep.ibcli"
OUT="$OUTDIR/sweep.out"
REPORT="$OUTDIR/report.txt"

# 1) Generate the sweep script - every registered no-arg show command.
"${IBCLI_CMD[@]}" -l \
    | grep -E "^\s*show " \
    | grep -v "<" \
    | sort -u \
    | sed 's/^[[:space:]]*//' > "$SCRIPT"

CMD_COUNT=$(wc -l < "$SCRIPT" | tr -d ' ')

# 2) Run against the grid. ibcli returns 0 per-line - individual errors are
#    captured in stdout, not the process exit code.
"${IBCLI_CMD[@]}" -s "$HOST" -u "$USER" -p "$PASS" -k "$SCRIPT" > "$OUT" 2>&1 || true

# 3) Pair each error with the command that produced it.
#    ibcli prints "read line N: <cmd>" before each line, and errors follow on
#    the next line indented with "  Error: …". Tie them together.
paste -d"|" \
    <(grep -n "^read line" "$OUT" | sed 's/:read line [0-9]*: /|/') \
    <(grep -A1 "^read line" "$OUT" | grep "^  Error:" || true) \
    > "$OUTDIR/pairs.txt" 2>/dev/null || true

# Walk the raw output and bucket each command's output.
python3 - "$OUT" "$OUTDIR" <<'PY'
import re, sys, os
path, outdir = sys.argv[1], sys.argv[2]

# List of (lineno, cmd, [output_lines]) - preserves order & duplicates.
runs = []
cur = None
with open(path) as f:
    for raw in f:
        line = raw.rstrip("\n")
        m = re.match(r"^read line (\d+): (.*)$", line)
        if m:
            cur = {"lineno": int(m.group(1)), "cmd": m.group(2), "out": []}
            runs.append(cur)
            continue
        if cur is not None:
            cur["out"].append(line)

# Write per-command summary: lineno, cmd, status, n_lines, preview.
with open(os.path.join(outdir, "summary.tsv"), "w") as fh:
    fh.write("lineno\tstatus\tn_lines\tcmd\tpreview\n")
    for r in runs:
        nonempty = [ln for ln in r["out"] if ln.strip()]
        err_line = next((ln for ln in nonempty if ln.startswith("  Error:")), None)
        if err_line:
            status = "ERROR"
            preview = err_line.strip()
        elif not nonempty:
            status = "SILENT"
            preview = ""
        elif len(nonempty) == 1 and nonempty[0].lstrip().startswith("Incomplete :"):
            # Dispatcher echo for an intermediate waypoint - useful for
            # discoverability but isn't real command output.
            status = "WAYPOINT"
            preview = nonempty[0].strip()
        else:
            status = "OK"
            preview = " | ".join(ln.strip() for ln in nonempty[:2])
            if len(preview) > 160:
                preview = preview[:160] + "…"
        fh.write(f"{r['lineno']}\t{status}\t{len(nonempty)}\t{r['cmd']}\t{preview}\n")

# Also write errors.txt for the classifier downstream (cmd<TAB>error_line).
with open(os.path.join(outdir, "errors.txt"), "w") as fh:
    for r in runs:
        err = next((ln for ln in r["out"] if ln.startswith("  Error:")), None)
        if err:
            fh.write(f"{r['cmd']}\t{err.strip()}\n")
PY

ERRORS_TOTAL=$(wc -l < "$OUTDIR/errors.txt" | tr -d ' ')
SILENT_COUNT=$(awk -F'\t' 'NR>1 && $2=="SILENT"' "$OUTDIR/summary.tsv" | wc -l | tr -d ' ')
OK_COUNT=$(awk -F'\t' 'NR>1 && $2=="OK"' "$OUTDIR/summary.tsv" | wc -l | tr -d ' ')
WP_COUNT=$(awk -F'\t' 'NR>1 && $2=="WAYPOINT"' "$OUTDIR/summary.tsv" | wc -l | tr -d ' ')

# ---------------------------------------------------------------------------
# Deep sweep - re-run each show command with fields=<every SDK field>.
# ---------------------------------------------------------------------------
DEEP_CMD_COUNT=0
DEEP_BAD_FIELDS=""
if [[ "$DEEP" -eq 1 ]]; then
    DEEP_MAP="$OUTDIR/deep-map.tsv"
    DEEP_SCRIPT="$OUTDIR/deep.ibcli"
    DEEP_OUT="$OUTDIR/deep.out"

    # 1) Discover the <command> → <all fields> mapping via SDK introspection.
    "${PY_CMD[@]}" scripts/smoke/show_fields_map.py > "$DEEP_MAP" || true

    # 2) Emit `<cmd> fields=f1,f2,…` for each mapping. Partitions each
    #    command's field list into sequential 40-field chunks so every
    #    field gets exercised exactly once, deterministically. 40 fields
    #    per URL stays well under NIOS's _return_fields+ length limits.
    python3 - "$DEEP_MAP" "$DEEP_SCRIPT" <<'PY'
import sys

CHUNK = 40
m, out = sys.argv[1], sys.argv[2]
with open(m) as fin, open(out, "w") as fout:
    for raw in fin:
        cmd, _, flds = raw.rstrip("\n").partition("\t")
        if not cmd or not flds:
            continue
        names = flds.split(",")
        for i in range(0, len(names), CHUNK):
            chunk = names[i:i + CHUNK]
            fout.write(f"{cmd} fields={','.join(chunk)}\n")
PY

    DEEP_CMD_COUNT=$(wc -l < "$DEEP_SCRIPT" | tr -d ' ')

    # 3) Run it against the grid.
    "${IBCLI_CMD[@]}" -s "$HOST" -u "$USER" -p "$PASS" -k "$DEEP_SCRIPT" \
        > "$DEEP_OUT" 2>&1 || true

    # 4) Per-command bucketing + per-field rejection list.
    python3 - "$DEEP_OUT" "$OUTDIR" <<'PY'
import re, sys, os
path, outdir = sys.argv[1], sys.argv[2]

_FIELD_RE = re.compile(
    r"Unknown argument/field:\s*'([^']+)'"
    r"|Field is not readable:\s*'?([A-Za-z_][A-Za-z0-9_]*)'?"
    r"|Field is not searchable:\s*'?([A-Za-z_][A-Za-z0-9_]*)'?"
)

runs = []
cur = None
with open(path) as f:
    for raw in f:
        line = raw.rstrip("\n")
        m = re.match(r"^read line (\d+): (.*)$", line)
        if m:
            cur = {"cmd": m.group(2), "out": []}
            runs.append(cur)
            continue
        if cur is not None:
            cur["out"].append(line)

bad_rows = []
for r in runs:
    err = next((ln for ln in r["out"] if ln.startswith("  Error:")), None)
    if not err:
        continue
    # strip fields=... from the cmd to print just the base show verb
    base = re.sub(r"\s+fields=\S+$", "", r["cmd"])
    m = _FIELD_RE.search(err)
    bad = m.group(1) or m.group(2) or m.group(3) if m else None
    bad_rows.append((base, bad, err.strip()))

with open(os.path.join(outdir, "deep-bad-fields.tsv"), "w") as fh:
    fh.write("command\tbad_field\terror\n")
    for base, bad, err in bad_rows:
        fh.write(f"{base}\t{bad or ''}\t{err}\n")
PY

    DEEP_BAD_FIELDS="$OUTDIR/deep-bad-fields.tsv"
fi

# 4) Classify each error.
#    - "Error: <x> required (usage: …)"  → our own friendly hint (not a bug)
#    - grid-config markers                → not a bug
#    - anything else                      → suspected CLI bug
FRIENDLY_RE='Error: [^(]*\(usage:'
# "does not support <op>" is ibx-nios-sdk >= 0.2.0 refusing an operation
# NIOS restricts for that object type - the same condition the grid reports
# as "Operation read not allowed", just caught before the request is sent.
GRID_RE='Operation read not allowed|does not support (read|create|update|delete)|is not enabled|Connection refused|Site not found/configured|Unknown object type|Network view is required'

FRIENDLY=$(grep -cE "$FRIENDLY_RE" "$OUTDIR/errors.txt" || true)
GRID=$(grep -cE "$GRID_RE" "$OUTDIR/errors.txt" || true)
BUGS=$(grep -vE "$FRIENDLY_RE|$GRID_RE" "$OUTDIR/errors.txt" || true)
BUG_COUNT=$([[ -z "$BUGS" ]] && echo 0 || echo "$BUGS" | wc -l | tr -d ' ')

# 5) Write a human-readable report.
{
    echo "============================================================"
    echo " ibcli show-command sweep - $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo " grid:     $HOST"
    echo " outdir:   $OUTDIR"
    echo "============================================================"
    echo
    echo "commands run:            $CMD_COUNT"
    echo "  produced output:       $OK_COUNT"
    echo "  waypoint (Incomplete): $WP_COUNT  (intermediate nodes enumerating subcommands)"
    echo "  silent (0 lines):      $SILENT_COUNT  (legitimate empty list, or broken printer)"
    echo "  errored:               $ERRORS_TOTAL"
    echo "    friendly usage:      $FRIENDLY  (expected - required-arg forms)"
    echo "    grid-config:         $GRID  (not CLI bugs - grid feature off)"
    echo "    SUSPECTED CLI BUGS:  $BUG_COUNT"
    echo
    if [[ "$BUG_COUNT" -gt 0 ]]; then
        echo "--- BUGS ---------------------------------------------------"
        echo "$BUGS"
        echo
    fi
    if [[ "$SILENT_COUNT" -gt 0 ]]; then
        echo "--- SILENT (no output - verify these are truly empty data) -"
        awk -F'\t' 'NR>1 && $2=="SILENT" {print "  "$4}' "$OUTDIR/summary.tsv"
        echo
    fi
    echo "--- OK - sample output per command -------------------------"
    awk -F'\t' 'NR>1 && $2=="OK" {printf "  %-40s [%3d ln] %s\n", $4, $3, $5}' \
        "$OUTDIR/summary.tsv"
    echo
    echo "--- GRID-CONFIG (informational) ----------------------------"
    grep -E "$GRID_RE" "$OUTDIR/errors.txt" || echo "  (none)"
    echo
    echo "--- USAGE HINTS (informational) ----------------------------"
    grep -E "$FRIENDLY_RE" "$OUTDIR/errors.txt" || echo "  (none)"
    echo
    if [[ "$DEEP" -eq 1 ]]; then
        echo
        echo "--- DEEP SWEEP (every show · fields=<all SDK fields>) ------"
        echo "commands run:            $DEEP_CMD_COUNT"
        if [[ -s "$DEEP_BAD_FIELDS" ]]; then
            BAD_ROW_COUNT=$(($(wc -l < "$DEEP_BAD_FIELDS") - 1))
            echo "commands that rejected a field: $BAD_ROW_COUNT"
            echo
            echo "per-command field rejections:"
            awk -F'\t' 'NR>1 {printf "  %-40s  bad=%-30s  err=%s\n", $1, $2, $3}' \
                "$DEEP_BAD_FIELDS"
            echo
            echo "unique bad field names:"
            awk -F'\t' 'NR>1 && $2 != "" {print "  "$2}' "$DEEP_BAD_FIELDS" | sort -u
        else
            echo "commands that rejected a field: 0"
        fi
        echo
        echo "Deep-sweep raw output:  $DEEP_OUT"
        echo "Deep-sweep map:         $DEEP_MAP"
    fi
    echo
    echo "Full per-line output:  $OUT"
    echo "Per-command summary:   $OUTDIR/summary.tsv"
} > "$REPORT"

if [[ "$QUIET" -eq 0 ]]; then
    cat "$REPORT"
fi

# 6) Exit code reflects CLI-bug count only.
if [[ "$BUG_COUNT" -gt 0 ]]; then
    echo "FAIL: $BUG_COUNT suspected CLI bug(s). Full output: $OUT" >&2
    exit 1
fi
exit 0
