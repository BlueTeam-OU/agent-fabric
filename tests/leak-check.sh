#!/usr/bin/env bash
# tests/leak-check.sh — sourced by tests/run.sh: did the run leave anything
# under its temporary directory? (run.sh makes one per run and exports it
# as TMPDIR, so the snapshot is empty and everything left is the run's.)
#
#   leak_snapshot <dir>              → the directory's entries, one per line
#   leak_report <dir> <snapshot>     → prints every entry not in the snapshot,
#                                      indented; returns 1 if there was one
#
# A test run leaves behind nothing it did not find (the owner, 2026-09-19).
# leak_dir is where a suite's scratch lands when the run does not export
# TMPDIR — resolved as Node's os.tmpdir() does (TMPDIR, then TMP, then TEMP,
# then /tmp; Python reads TEMP before TMP, which stops mattering once run.sh
# exports TMPDIR for the run). run.sh makes its own directories (af-t.*,
# af-o.*) under $XDG_RUNTIME_DIR or /tmp, not under leak_dir.
# Names are handled as whole lines: an entry with a space or a glob
# character is printed as itself, never split or expanded.
leak_dir() { printf '%s\n' "${TMPDIR:-${TMP:-${TEMP:-/tmp}}}"; }
leak_snapshot() { ls -A -- "$1" 2>/dev/null | LC_ALL=C sort; }
leak_report() {
    local dir="$1" before="$2" left
    left="$(LC_ALL=C comm -13 <(printf '%s\n' "$before") <(ls -A -- "$dir" 2>/dev/null | LC_ALL=C sort) | grep -v '^$' || true)"
    [[ -n "$left" ]] || return 0
    echo "== scratch left behind under $dir (a suite did not clean up):"
    printf '%s\n' "$left" | sed 's/^/   /'
    return 1
}
