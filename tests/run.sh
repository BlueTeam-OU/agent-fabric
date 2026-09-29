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
# dictionary and pass it explicitly (communication/gzcoord/scripts/i18n.mjs).
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
    run "launcher" bash policies/run_suite.sh runtime/openrouter/test_launch.sh
    run "charter authority guard" bash policies/run_suite.sh policies/test_check_charter_authority.sh
    run "git hooks (attribution ban, .agent-fabric/ fence)" bash policies/run_suite.sh policies/githooks/test_hooks.sh
    run ".agent-fabric/ authority guard" bash policies/run_suite.sh policies/test_check_agent_fabric_dir_authority.sh
    run ".agent-fabric/ authority (this branch)" env AGENT_FABRIC_CHARTER_BASE=origin/main bash policies/check_agent_fabric_dir_authority.sh
    run "charter authority (this branch)" env AGENT_FABRIC_CHARTER_BASE=origin/main bash policies/check_charter_authority.sh
    run "no-model-pins guard" bash policies/run_suite.sh policies/test_check_repo_settings_carry_no_model_pins.sh
    run "actions pinned by SHA (this tree)" python3 policies/check_actions_pinned_by_sha.py
    run "attribution guard" bash policies/run_suite.sh policies/test_ban_generated_by_attribution.sh
    run "attribution (this branch)" env AGENT_FABRIC_ATTRIBUTION_BASE=origin/main bash policies/ban_generated_by_attribution.sh
    run "decision-record amendments (this branch)" env AGENT_FABRIC_ADR_BASE=origin/main bash policies/check_adr_amendment.sh
    run "fabric-status" bash policies/run_suite.sh tests/test_fabric-status.sh
    run "fabric-usage" bash policies/run_suite.sh tests/test_fabric-usage.sh
    run "fabric-lease (one holder per host resource)" bash tests/test_fabric-lease.sh
    run "fabric-fresh (an agent ends its own session)" bash tests/test_fabric-fresh.sh
    run "fabric-branches (local branch hygiene)" bash tests/test_fabric-branches.sh
    run "leak check (what a run left behind)" bash tests/test_leak-check.sh
    run "status line" bash runtime/claude-code/hooks/test_statusline.sh
    run "new-agent (the sequence, its refusals, a failure at each step)" bash runtime/provisioning/test_new-agent.sh
    run "account persistence (the Qubes boot script, the snapshot writer)" bash runtime/provisioning/platform/test_qubes-accounts.sh
    run "language identification (the detector venv)" bash runtime/langid/test_install.sh
    run "rename-working-copy (the shell half)" bash runtime/provisioning/test_rename-working-copy.sh
    run "dispatch guard" bash runtime/claude-code/hooks/test_agent-dispatch-guard.sh
    run "review bash guard" bash runtime/claude-code/hooks/test_review-bash-guard.sh
    run "subagent clone guard" bash runtime/claude-code/hooks/test_subagent-clone-guard.sh
    run "pipe status guard" bash runtime/claude-code/hooks/test_pipe-status-guard.sh
    run "model-switch guard" bash runtime/claude-code/hooks/test_model-switch-guard.sh
    run "plan hold" bash runtime/claude-code/hooks/test_plan-hold.sh
    run "model fallback note" bash runtime/claude-code/hooks/test_model-fallback-note.sh
    run "tab title hook" bash runtime/claude-code/hooks/test_tab-title.sh
    run "install-agent-files (the locale worker)" bash runtime/claude-code/test_install-agent-files.sh
    run "the fabric's user settings (attribution off, thinking summaries, verbose)" bash runtime/claude-code/test_user-settings.sh
    run "moveto" bash runtime/provisioning/moveto/test_moveto.sh
    run "hostexec (local and ssh backends)" bash runtime/hostexec/test_hostexec.sh
    run "fabric-secrets" bash policies/run_suite.sh runtime/provisioning/secrets/test_fabric-secrets.sh
    run "enroll (fault injection)" bash runtime/provisioning/secrets/test_enroll.sh
    run "store-enroll (a parent keys an account on another host)" bash runtime/provisioning/secrets/test_store-enroll.sh
    run "github pr-reply" bash runtime/github/test_pr-reply.sh
    run "github pr-sessions" bash runtime/github/test_pr-sessions.sh
    run "github commit-class (work, review fix, merge)" bash runtime/github/test_commit-class.sh
    run "github pr-review-status" bash runtime/github/test_pr-review-status.sh
    run "github post-review" bash runtime/github/test_post-review.sh
    run "github pr-gate (the count rule, the verdict)" bash runtime/github/test_pr-gate.sh
    run "github trial-merge (combine, conflict, the check, nothing left)" bash runtime/github/test_trial-merge.sh
fi

echo
leak_report "$SCRATCH_DIR" "$scratch_before" || fail=$((fail+1))
if (( fail )); then echo "tests/run.sh: $fail suite(s) FAILED"; exit 1; fi
echo "tests/run.sh: all suites passed"
