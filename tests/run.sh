#!/usr/bin/env bash
# tests/run.sh — every suite agent-fabric has, in one run.
#
#   tests/run.sh            # all
#   tests/run.sh python     # only the python suites
#   tests/run.sh bash       # only the bash suites (launcher, guards, hooks)
#   tests/run.sh static     # only the static checks (bash -n, shellcheck, ruff)
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
what="${1:-all}"
# CI runs one section a leg: a misspelt one ran nothing and said "all
# suites passed" (review of #68). An unknown section is an invocation error.
case "$what" in all|static|python|bash) ;; *) echo "tests/run.sh: no section '$what' (all, static, python, bash)" >&2; exit 2 ;; esac
fail=0
run() { echo; echo "== $1"; shift; "$@" || fail=$((fail+1)); }

# The python suites, up to AGENT_FABRIC_TEST_JOBS at a time (default: the
# cores; 1 is the old serial run). Each suite is independent: it makes its
# own scratch under this run's TMPDIR, binds port 0 for any socket and gives
# itself a HOME (the one fixed path, /var/tmp/agent-fabric-<login> in
# test_launch_cli, is created idempotently).
# The slowest start first, so the last one started is a short one and not the
# 3-minute launcher alone at the end. A suite's output is buffered and printed
# whole when it ends, under the same "== <suite>" header the serial run
# printed, so the log reads the same but in completion order.
SLOW_PYTHON_SUITES=(
    test_launch_cli test_new_agent_cli test_gzcoord_port test_bootstrap_cli
    test_secret_store test_control_agentd test_gzcoord_protocol test_jobs
    test_roots_readers test_control_ctl test_pr_review_status_cli test_arm_cli
    test_session_start test_lint test_assemble
)
run_python_suites() {
    local slots="${AGENT_FABRIC_TEST_JOBS:-$(nproc 2>/dev/null || echo 1)}"
    [[ "$slots" =~ ^[1-9][0-9]*$ ]] || { echo "tests/run.sh: AGENT_FABRIC_TEST_JOBS='$slots' is not a positive number" >&2; exit 2; }
    local -a ordered=() started=()
    local t n running=0
    for n in "${SLOW_PYTHON_SUITES[@]}"; do
        [[ -f "tests/$n.py" ]] && ordered+=("tests/$n.py")
    done
    for t in tests/test_*.py; do
        for n in "${ordered[@]}"; do [[ "$n" == "$t" ]] && continue 2; done
        ordered+=("$t")
    done
    # Own process group per suite, so cleanup can end a suite's children too.
    set -m
    for t in "${ordered[@]}"; do
        if (( running >= slots )); then wait -n; running=$((running-1)); flush_python_suites; fi
        n="$OUT_DIR/$(basename "$t")"
        started+=("$t")
        # The status file appears whole (mv) and after the output is complete.
        ( python3 "$t" >"$n.out" 2>&1; echo $? >"$n.rc.tmp"; mv "$n.rc.tmp" "$n.rc" ) &
        running=$((running+1))
    done
    while (( running > 0 )); do wait -n; running=$((running-1)); flush_python_suites; done
    set +m
}
# Print and account every finished suite not yet printed.
flush_python_suites() {
    local t n
    for t in "${started[@]}"; do
        n="$OUT_DIR/$(basename "$t")"
        [[ -f "$n.rc" && ! -f "$n.done" ]] || continue
        echo; echo "== $t"; cat "$n.out"
        [[ "$(cat "$n.rc")" == 0 ]] || fail=$((fail+1))
        : >"$n.done"
    done
}

# A test run leaves behind nothing it did not find (the owner,
# 2026-09-19). The run owns its temporary directory: a fresh one under
# the account's, exported as TMPDIR so every suite — mktemp, Node's
# os.tmpdir(), Python's tempfile — writes there and nowhere else. At the
# end, every entry in it is a failure named by path: seventy such
# directories per run had accumulated to 120 MB before anyone looked
# (ADR-021). The directory itself goes when the run ends,
# however it ends; and because it is this run's alone, a second run, a
# pip install or an editor writing into the account's directory at the
# same time is never mistaken for a leak. tests/leak-check.sh is the
# check; test_leak-check.sh is where a planted entry proves it fires.
# shellcheck source=leak-check.sh
. "$ROOT/tests/leak-check.sh"
# The run's directories are made SHORT: a unix socket path is limited to 107
# bytes, and the account's own TMPDIR (/var/tmp/agent-fabric-<login>/…) plus a
# suite's nesting overflowed it for gpg's agent and the relay, and truncated
# paths in assertions (found by the 2026-10-11 parallel trial). The runtime
# directory is private to the account and short; /tmp is the fallback.
short_dir() {
    if [[ -n "${XDG_RUNTIME_DIR:-}" && -d "$XDG_RUNTIME_DIR" && -w "$XDG_RUNTIME_DIR" ]]; then
        printf '%s\n' "$XDG_RUNTIME_DIR"
    else
        printf '/tmp\n'
    fi
}
SCRATCH_DIR="$(mktemp -d "$(short_dir)/af-t.XXXXXX")" || exit 1
# The parallel python suites' buffered output lives beside SCRATCH_DIR, not in
# it: it is the harness's, and the leak check would name it as a suite's.
OUT_DIR="$(mktemp -d "$(short_dir)/af-o.XXXXXX")" || exit 1
export TMPDIR="$SCRATCH_DIR"
# A suite that block-buffers its stdout shows nothing in a CI log until it
# ends (the 2026-10-11 audit could not time a case from one).
export PYTHONUNBUFFERED=1
# The GZCoord tools speak the READER's language, so a suite that asserts
# their lines depends on which login runs it: green on a login with no
# locale directory (CI's) and red on every holder's. The run pins the
# default locale; the cases that exercise a locale build their own
# dictionary and pass it explicitly (tools/fabric/gzcoord/i18n.py).
export GZCOORD_DEFAULT_LOCALE_ONLY=1
# Likewise the account's commit signing: a gpg key with a timestamp that
# needs the network made five suites' fixture commits fail offline, green
# in CI and red on the account that signs. Git's environment config
# outranks every file, so the run's sandboxes never sign.
export GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=commit.gpgsign GIT_CONFIG_VALUE_0=false \
       GIT_CONFIG_KEY_1=tag.gpgsign GIT_CONFIG_VALUE_1=false
# EXIT removes; a signal EXITS. Naming INT/TERM/HUP on the removal trap
# itself made bash run the removal and then CONTINUE the script — every
# remaining suite ran against a deleted TMPDIR and was reported failed,
# and a harness that follows TERM with KILL got no cleanup at all. Bash
# runs the EXIT trap when it dies of an untrapped signal, so the three
# traps below only make the status conventional (128+signal).
# The parallel suites run as background process groups (set -m in
# run_python_suites): a run that dies takes them with it, or they would go on
# writing into a deleted TMPDIR.
cleanup() {
    local pid
    for pid in $(jobs -p); do kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null; done
    rm -rf "$SCRATCH_DIR" "$OUT_DIR"
}
trap cleanup EXIT
trap 'exit 130' INT; trap 'exit 143' TERM; trap 'exit 129' HUP
scratch_before="$(leak_snapshot "$SCRATCH_DIR")"

if [[ "$what" == all || "$what" == static ]]; then
    run "static (bash -n, shellcheck, ruff)" bash tests/static.sh
fi
if [[ "$what" == all || "$what" == python ]]; then
    run_python_suites
    run "corpus lint" python3 tools/fabric/lint.py
    run "routing check" python3 tools/fabric/routing.py check
fi
if [[ "$what" == all || "$what" == bash ]]; then
    # The branch's authority, from the branch's own copy of the guards: the
    # local check. CI's verdict is main's copy, run isolated in a step before
    # this script (ci.yml), since a contributor's tests and modules run here
    # first (docs/live-checks/2026-10-01-guard-shadowing.md).
    run ".agent-fabric/ authority (this branch)" env AGENT_FABRIC_CHARTER_BASE=origin/main python3 tools/fabric/guards/agent_fabric_dir_authority.py
    run "charter authority (this branch)" env AGENT_FABRIC_CHARTER_BASE=origin/main python3 tools/fabric/guards/charter_authority.py "$PWD"
    run ".agent-fabric/ authority guard" python3 tools/fabric/github/run_suite.py policies/test_check_agent_fabric_dir_authority.sh
    run "no-model-pins guard" python3 tools/fabric/github/run_suite.py policies/test_check_repo_settings_carry_no_model_pins.sh
    run "actions pinned by SHA (this tree)" python3 policies/check_actions_pinned_by_sha.py
    run "attribution (this branch)" env AGENT_FABRIC_ATTRIBUTION_BASE=origin/main python3 tools/fabric/guards/ban_generated_by_attribution.py
    run "decision-record amendments (this branch)" env AGENT_FABRIC_ADR_BASE=origin/main python3 tools/fabric/adr.py range-check
    run "leak check (what a run left behind)" bash tests/test_leak-check.sh
    run "status line" bash runtime/claude-code/hooks/test_statusline.sh
    run "language identification (the detector venv)" bash runtime/langid/test_install.sh
    run "subagent clone guard" bash runtime/claude-code/hooks/test_subagent-clone-guard.sh
    run "pipe status guard" bash runtime/claude-code/hooks/test_pipe-status-guard.sh
    run "model-switch guard" bash runtime/claude-code/hooks/test_model-switch-guard.sh
    run "plan hold" bash runtime/claude-code/hooks/test_plan-hold.sh
    run "model fallback note" bash runtime/claude-code/hooks/test_model-fallback-note.sh
    run "install-agent-files (the locale worker)" bash runtime/claude-code/test_install-agent-files.sh
    run "the fabric's user settings (attribution off, thinking summaries, verbose)" bash runtime/claude-code/test_user-settings.sh
fi

echo
leak_report "$SCRATCH_DIR" "$scratch_before" || fail=$((fail+1))
if (( fail )); then echo "tests/run.sh: $fail suite(s) FAILED"; exit 1; fi
echo "tests/run.sh: all suites passed"
