#!/usr/bin/env bash
# tests/run.sh — every suite agent-fabric has, in one run.
#
#   tests/run.sh            # all
#   tests/run.sh python     # only the python suites
#   tests/run.sh gzcoord    # only the GZCoord protocol/runtime suite
#   tests/run.sh bash       # only the bash suites (launcher, guards, hooks)
#   tests/run.sh static     # only the static checks (bash -n, shellcheck, ruff)
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
what="${1:-all}"
# CI runs one section a leg: a misspelt one ran nothing and said "all
# suites passed" (review of #68). An unknown section is an invocation error.
case "$what" in all|static|python|gzcoord|bash) ;; *) echo "tests/run.sh: no section '$what' (all, static, python, gzcoord, bash)" >&2; exit 2 ;; esac
fail=0
run() { echo; echo "== $1"; shift; "$@" || fail=$((fail+1)); }

# A test run leaves behind nothing it did not find (the owner,
# 2026-09-19). The run owns its temporary directory: a fresh one under
# the account's, exported as TMPDIR so every suite — mktemp, Node's
# os.tmpdir(), Python's tempfile — writes there and nowhere else. At the
# end, every entry in it is a failure named by path: seventy such
# directories per run had accumulated to 120 MB before anyone looked
# (tests/scratch.mjs). The directory itself goes when the run ends,
# however it ends; and because it is this run's alone, a second run, a
# pip install or an editor writing into the account's directory at the
# same time is never mistaken for a leak. tests/leak-check.sh is the
# check; test_leak-check.sh is where a planted entry proves it fires.
# shellcheck source=leak-check.sh
. "$ROOT/tests/leak-check.sh"
SCRATCH_DIR="$(mktemp -d "$(leak_dir)/agent-fabric-tests.XXXXXX")" || exit 1
export TMPDIR="$SCRATCH_DIR"
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
trap 'rm -rf "$SCRATCH_DIR"' EXIT
trap 'exit 130' INT; trap 'exit 143' TERM; trap 'exit 129' HUP
scratch_before="$(leak_snapshot "$SCRATCH_DIR")"

if [[ "$what" == all || "$what" == static ]]; then
    run "static (bash -n, shellcheck, ruff)" bash tests/static.sh
fi
if [[ "$what" == all || "$what" == python ]]; then
    for t in tests/test_*.py; do run "$t" python3 "$t"; done
    run "corpus lint" python3 tools/fabric/lint.py
    run "routing check" python3 tools/fabric/routing.py check
fi
if [[ "$what" == all || "$what" == gzcoord ]]; then
    run "gzcoord" bash -c 'cd communication/gzcoord && node --test tests/*.test.mjs 2>&1 | grep -E -A14 "^not ok|^# (tests|pass|fail)"; [[ ${PIPESTATUS[0]} -eq 0 ]]'
    run "locale search MCP server" bash -c 'node --test runtime/mcp/websearch-locale/tests/*.test.mjs 2>&1 | grep -E -A14 "^not ok|^# (tests|pass|fail)"; [[ ${PIPESTATUS[0]} -eq 0 ]]'
    run "control plane (ops, agentd, ctl, accounts, unit)" bash -c 'node --test runtime/control/tests/*.test.mjs 2>&1 | grep -E -A14 "^not ok|^# (tests|pass|fail)"; [[ ${PIPESTATUS[0]} -eq 0 ]]'
fi
if [[ "$what" == all || "$what" == bash ]]; then
    # The branch's authority, from the branch's own copy of the guards: the
    # local check. CI's verdict is main's copy, run isolated in a step before
    # this script (ci.yml), since a contributor's tests and modules run here
    # first (docs/live-checks/2026-10-01-guard-shadowing.md).
    run ".agent-fabric/ authority (this branch)" env AGENT_FABRIC_CHARTER_BASE=origin/main bash policies/check_agent_fabric_dir_authority.sh
    run "charter authority (this branch)" env AGENT_FABRIC_CHARTER_BASE=origin/main bash policies/check_charter_authority.sh
    run ".agent-fabric/ authority guard" bash policies/run_suite.sh policies/test_check_agent_fabric_dir_authority.sh
    run "no-model-pins guard" bash policies/run_suite.sh policies/test_check_repo_settings_carry_no_model_pins.sh
    run "actions pinned by SHA (this tree)" python3 policies/check_actions_pinned_by_sha.py
    run "attribution (this branch)" env AGENT_FABRIC_ATTRIBUTION_BASE=origin/main bash policies/ban_generated_by_attribution.sh
    run "decision-record amendments (this branch)" env AGENT_FABRIC_ADR_BASE=origin/main bash policies/check_adr_amendment.sh
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
