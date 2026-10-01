#!/usr/bin/env bash
# Behavioural tests for .claude/agent-dispatch-guard.sh.
#
# What this holds still: the DECISION TABLE of the Agent dispatch hook.
# The program used to live as a jq string inside settings.json and its
# two properties were "pipe-tested at the time it was written" -- in a
# terminal, once, by hand. Both halves of the review carve-out were
# later found to be load-bearing TOGETHER (a type-only key let fable
# through), which is the kind of regression a table of cases catches
# and a comment does not.
#
# Every case pipes a tool-call payload through the REAL script and
# checks the decision: "allow" (no output), "deny", or "ask".
#
# Exit codes:
#   0  all assertions passed
#   1  one or more assertions failed
set -uo pipefail

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/agent-dispatch-guard.sh"
[[ -f "$UNDER_TEST" ]] || { echo "test: not found: $UNDER_TEST" >&2; exit 1; }

failures=0
pass() { echo "  ok   $1"; }
fail() { echo "  FAIL $1" >&2; [[ $# -gt 1 ]] && printf '       %s\n' "$2" >&2; failures=$((failures + 1)); }

# decision <json-tool_input>  -> prints allow | deny | ask
# These cases are an UNLAUNCHED session: the runner may itself be a
# fabric-launched one, so the launch variable is removed, never inherited.
decision() {
  local out
  out="$(printf '{"tool_name":"Agent","tool_input":%s}' "$1" | env -u AGENT_FABRIC_LAUNCH_PROVIDER bash "$UNDER_TEST" 2>/dev/null)"
  if [[ -z "$out" ]]; then echo allow
  else printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision // "malformed"'; fi
}
reason() {
  printf '{"tool_name":"Agent","tool_input":%s}' "$1" | env -u AGENT_FABRIC_LAUNCH_PROVIDER bash "$UNDER_TEST" 2>/dev/null | jq -r '.hookSpecificOutput.permissionDecisionReason // ""'
}
expect() {
  local label="$1" want="$2" input="$3" got
  got="$(decision "$input")"
  if [[ "$got" == "$want" ]]; then pass "$label"; else fail "$label" "want $want, got $got"; fi
}

echo "forks"
expect "a fork is allowed with nothing set" allow '{"subagent_type":"fork","description":"continue"}'

echo "the review class: all four conditions, or denied -- never asked"
R='{"subagent_type":"code-review","model":"fable","description":"Review PR 626 diff","prompt":"..."}'
expect "code-review + review + fable + no isolation is allowed without a prompt" allow "$R"
expect "re-review is a review" allow '{"subagent_type":"code-review","model":"fable","description":"Re-review PR 626 after fixes"}'
expect "case-insensitive prefix" allow '{"subagent_type":"code-review","model":"fable","description":"REVIEW of the delta"}'
expect "any word form beginning review (Reviewing) is a review" allow '{"subagent_type":"code-review","model":"fable","description":"Reviewing PR 626"}'
expect "review type with a full model id is denied (the Agent tool only accepts aliases; fable is the review alias)" deny '{"subagent_type":"code-review","model":"claude-opus-5[1m]","description":"Review PR 626"}'
expect "review type with a writing description is denied" deny '{"subagent_type":"code-review","model":"fable","description":"Address review feedback on PR 626"}'
expect "review anywhere but not at the start is denied" deny '{"subagent_type":"code-review","model":"fable","description":"Fix and review the mapper"}'
expect "review type on sonnet is denied, not asked" deny '{"subagent_type":"code-review","model":"sonnet","description":"Review PR 626"}'
expect "review type on haiku is denied" deny '{"subagent_type":"code-review","model":"haiku","description":"Review PR 626"}'
expect "review type with model unset is denied" deny '{"subagent_type":"code-review","description":"Review PR 626"}'
expect "review type with opus is denied (opus is code-high's alias on the broker path)" deny '{"subagent_type":"code-review","model":"opus","description":"Review PR 626"}'
expect "review type WITH isolation is denied" deny '{"subagent_type":"code-review","model":"fable","isolation":"worktree","description":"Review PR 626"}'
expect "the review prefix on a general agent is denied" deny '{"subagent_type":"general-purpose","model":"sonnet","isolation":"worktree","description":"Review the diff"}'

echo "read-only types: model required, no worktree, premium asks"
expect "Explore on sonnet without isolation is allowed" allow '{"subagent_type":"Explore","model":"sonnet","description":"Explore the provisioning scripts"}'
expect "Plan on haiku without isolation is allowed" allow '{"subagent_type":"Plan","model":"haiku","description":"Plan the split"}'
expect "claude-code-guide on haiku is allowed" allow '{"subagent_type":"claude-code-guide","model":"haiku","description":"How do hooks work"}'
expect "Explore with model unset is denied (the tier is still a choice)" deny '{"subagent_type":"Explore","description":"Explore the provisioning scripts"}'
expect "Explore WITH worktree isolation is denied (it would hide uncommitted work)" deny '{"subagent_type":"Explore","model":"sonnet","isolation":"worktree","description":"Explore the provisioning scripts"}'
expect "Explore on fable asks" ask '{"subagent_type":"Explore","model":"fable","description":"Explore the provisioning scripts"}'
expect "a read-only type whose description begins with review is still denied (reviews use the class)" deny '{"subagent_type":"Explore","model":"sonnet","description":"Review the diff"}'

echo "everything else: model and worktree required, premium asks"
expect "sonnet + worktree is allowed" allow '{"subagent_type":"general-purpose","model":"sonnet","isolation":"worktree","description":"Extract the table"}'
expect "haiku + worktree is allowed" allow '{"model":"haiku","isolation":"worktree","description":"Rename the field"}'
expect "missing model is denied" deny '{"subagent_type":"general-purpose","isolation":"worktree","description":"Extract the table"}'
expect "missing isolation is denied" deny '{"subagent_type":"general-purpose","model":"sonnet","description":"Extract the table"}'
expect "isolation other than worktree is denied" deny '{"model":"sonnet","isolation":"remote","description":"Extract"}'
expect "opus on a general agent asks" ask '{"subagent_type":"general-purpose","model":"opus","isolation":"worktree","description":"Extract the table"}'
expect "fable on a general agent asks" ask '{"model":"fable","isolation":"worktree","description":"Extract the table"}'
expect "Opus in caps still asks" ask '{"model":"Opus","isolation":"worktree","description":"Extract"}'

echo "the denial says why"
r="$(reason '{"subagent_type":"code-review","model":"sonnet","description":"Review PR 626"}')"
if grep -q "green PR that merges" <<<"$r"; then pass "the tier denial names the failure mode"; else fail "the tier denial names the failure mode" "$r"; fi
# The pointer is the fabric's own skill, installed on every account; a
# heading in one project's CLAUDE.md is missing from the others.
if grep -q "subagent-dispatch skill" <<<"$r" && ! grep -q "CLAUDE.md - Subagent" <<<"$r"; then pass "the denial points at the fabric's skill, not one project's heading"; else fail "the denial points at a project heading" "$r"; fi
r="$(reason '{"subagent_type":"code-review","model":"fable","isolation":"worktree","description":"Review PR 626"}')"
if grep -q "baseRef" <<<"$r"; then pass "the isolation denial names baseRef"; else fail "the isolation denial names baseRef" "$r"; fi

echo "a coding class decides its tier: model must be the class's alias (aliases.json)"
expect "code-low on haiku is allowed" allow '{"subagent_type":"code-low","model":"haiku","isolation":"worktree","description":"Extract the table"}'
expect "code-medium on sonnet is allowed" allow '{"subagent_type":"code-medium","model":"sonnet","isolation":"worktree","description":"Rework the mapper"}'
expect "code-high on opus asks (premium), never silently" ask '{"subagent_type":"code-high","model":"opus","isolation":"worktree","description":"Design the protocol"}'
expect "code-low on sonnet is denied: the class decides, not the call" deny '{"subagent_type":"code-low","model":"sonnet","isolation":"worktree","description":"Extract the table"}'
expect "code-high on haiku is denied: high work on the cheap tier with nothing saying so" deny '{"subagent_type":"code-high","model":"haiku","isolation":"worktree","description":"Design the protocol"}'
expect "code-high on sonnet is denied, not downgraded" deny '{"subagent_type":"code-high","model":"sonnet","isolation":"worktree","description":"Design the protocol"}'
expect "a class with model unset is denied (nothing is inferred)" deny '{"subagent_type":"code-medium","isolation":"worktree","description":"Rework the mapper"}'
expect "a class with a full model id is denied" deny '{"subagent_type":"code-low","model":"claude-haiku-4-5","isolation":"worktree","description":"Extract the table"}'
expect "a class without worktree isolation is denied" deny '{"subagent_type":"code-low","model":"haiku","description":"Extract the table"}'
r="$(reason '{"subagent_type":"code-low","model":"sonnet","isolation":"worktree","description":"Extract the table"}')"
if grep -q "rides the haiku alias" <<<"$r"; then pass "the mismatch denial names the class's alias"; else fail "the mismatch denial names the class's alias" "$r"; fi
# aliases.json unreadable: the class branch denies and says why, never loosens.
# A copy of the guard placed where no aliases.json exists around it. The
# guard is the module now (ADR-040 §5 rule 5): the copy is of the module,
# which finds the aliases from where it stands, as the bash script did.
ORPHAN="$(mktemp -d)"; mkdir -p "$ORPHAN/hooks"; cp "$SCRIPT_DIR/../../../tools/fabric/guards/dispatch_guard.py" "$ORPHAN/hooks/guard.py"
out="$(printf '{"tool_input":{"subagent_type":"code-low","model":"haiku","isolation":"worktree","description":"x"}}' | python3 "$ORPHAN/hooks/guard.py" 2>/dev/null)"; rm -rf "$ORPHAN"
if grep -q '"deny"' <<<"$out" && grep -q "binds no alias" <<<"$out"; then pass "an unreadable aliases.json denies a class dispatch rather than allowing it"; else fail "an unreadable aliases.json denies a class dispatch rather than allowing it" "$out"; fi

echo "the locale worker: model required, isolation refused, any alias allowed without an ask"
expect "locale-worker on opus is allowed, no ask" allow '{"subagent_type":"locale-worker","model":"opus","description":"Translate the finding into Georgian"}'
expect "locale-worker on fable is allowed, no ask" allow '{"subagent_type":"locale-worker","model":"fable","description":"x"}'
expect "locale-worker on sonnet is allowed" allow '{"subagent_type":"locale-worker","model":"sonnet","description":"x"}'
expect "locale-worker with model unset is denied" deny '{"subagent_type":"locale-worker","description":"x"}'
expect "locale-worker with isolation is denied" deny '{"subagent_type":"locale-worker","model":"opus","isolation":"worktree","description":"x"}'
expect "locale-worker whose description begins with review is allowed: reviewing text is its job" allow '{"subagent_type":"locale-worker","model":"opus","description":"Review the Georgian rendering of the finding"}'
r="$(reason '{"subagent_type":"locale-worker","model":"opus","isolation":"worktree","description":"x"}')"
if grep -q "writes nothing" <<<"$r"; then pass "the isolation denial says why"; else fail "the isolation denial says why" "$r"; fi

echo "a guard that cannot run asks; it never silently allows"
# Nothing to run on: no PATH, and no pinned Python (the hook reaches that by
# its path, so an empty PATH alone no longer stops it).
out="$(printf '{"tool_input":{"model":"sonnet","isolation":"worktree","description":"x"}}' | env PATH=/nonexistent AGENT_FABRIC_PYTHON=/nonexistent/fabric-python /bin/bash "$UNDER_TEST" 2>/dev/null)"
if printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "ask"' >/dev/null 2>&1; then
  pass "with jq unavailable the guard asks rather than allowing"
else
  fail "with jq unavailable the guard asks rather than allowing" "out=[$out]"
fi

echo "malformed input never breaks the tool call with a bad shape"
for payload in '{}' 'not json' ''; do
  out="$(printf '%s' "$payload" | bash "$UNDER_TEST" 2>/dev/null)"; rc=$?
  # Exit 2 is the ONE code Claude Code treats as a blocking hook error:
  # a guard that exits 2 on a parse failure hard-blocks every dispatch.
  if [[ "$rc" -ne 2 ]] && { [[ -z "$out" ]] || printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision' >/dev/null 2>&1; }; then
    pass "payload (${payload:-empty}) yields allow or a well-formed decision, never exit 2 (rc=$rc)"
  else
    fail "payload (${payload:-empty}) yields allow or a well-formed decision, never exit 2" "rc=$rc out=[$out]"
  fi
done

echo "the file pin: under a fabric launch a review dispatch keeps its rules, then hands the model to the agent file"
# The pin is merged for the login (`pins --me`): an empty state dir keeps
# the runner's own binding and local layer out of these assertions, and a
# scratch CLAUDE_CONFIG_DIR carries the reviewer file the guard checks.
EMPTY_STATE="$(mktemp -d)"; SCRATCH_HOME="$(mktemp -d)"; FIXTURE_ROOT="$(mktemp -d)"; trap 'rm -rf "$EMPTY_STATE" "$SCRATCH_HOME" "$FIXTURE_ROOT"' EXIT
FABRIC_ROOT="$(cd "$(dirname "$UNDER_TEST")/../../.." && pwd)"
# The guard resolves through routing.py, which reads AGENT_FABRIC_ROOT: a
# root on the frozen column of 2026-09-24, where the five classes differ
# in model and level, so a guard that compared the wrong class's value
# would be caught. The committed column is two models at one level.
cp -r "$FABRIC_ROOT/routing" "$FIXTURE_ROOT/routing"
cp "$FABRIC_ROOT/tests/fixtures/routing-distinct/capabilities.json" "$FABRIC_ROOT/tests/fixtures/routing-distinct/effort.json" "$FIXTURE_ROOT/routing/"
mkdir -p "$FIXTURE_ROOT/runtime/claude-code"; cp "$FABRIC_ROOT/runtime/claude-code/aliases.json" "$FIXTURE_ROOT/runtime/claude-code/"
cp "$FABRIC_ROOT/runtime/identity.py" "$FIXTURE_ROOT/runtime/"   # `pins --me` asks it who is running
reviewer_file() { mkdir -p "$SCRATCH_HOME/agents"; printf -- '---\nname: code-review\nmodel: %s\n---\n' "$1" > "$SCRATCH_HOME/agents/code-review.md"; }
launched() { local provider="$1"; shift; printf '{"tool_name":"Agent","tool_input":%s}' "$1" | AGENT_FABRIC_ROOT="$FIXTURE_ROOT" AGENT_FABRIC_STATE_DIR="$EMPTY_STATE" CLAUDE_CONFIG_DIR="$SCRATCH_HOME" AGENT_FABRIC_LAUNCH_PROVIDER="$provider" bash "$UNDER_TEST" 2>/dev/null; }
vanilla() { launched anthropic "$1"; }
reviewer_file "claude-opus-5[1m]"
out="$(vanilla "$R")"
[[ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out")" == allow ]] && pass "review + fable + no isolation: an explicit allow" || fail "vanilla review not allowed" "$out"
[[ "$(jq -r '.hookSpecificOutput.updatedInput | has("model")' <<<"$out")" == false ]] && pass "…with the dispatch's model removed, so the reviewer file's claude-opus-5[1m] decides" || fail "model still on the dispatch" "$out"
[[ "$(jq -r '.hookSpecificOutput.updatedInput.subagent_type' <<<"$out")" == code-review && "$(jq -r '.hookSpecificOutput.updatedInput.prompt' <<<"$out")" == "..." ]] && pass "…and everything else on the dispatch intact" || fail "dispatch fields lost" "$out"
grep -q "claude-opus-5\[1m\]" <<<"$out" && pass "the reason names the pinned model" || fail "reason silent on the pin" "$out"
out="$(vanilla '{"subagent_type":"code-review","model":"opus","description":"Review PR 626 diff"}')"
[[ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out")" == deny ]] && pass "the fable rule still holds first: a review on opus is denied even here" || fail "opus review admitted on vanilla" "$out"
out="$(vanilla '{"subagent_type":"code-review","description":"Review PR 626 diff"}')"
[[ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out")" == deny ]] && pass "…and an unset model is still denied (the dispatcher writes fable; the guard drops it)" || fail "unset model admitted on vanilla" "$out"
out="$(vanilla '{"subagent_type":"code-high","model":"opus","isolation":"worktree","description":"Fix the parser"}')"
[[ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out")" == ask ]] && pass "a coding class is untouched: code-high still asks and keeps its alias (its pin is the export)" || fail "code-high changed on vanilla" "$out"
out="$(vanilla '{"subagent_type":"code-plan","model":"fable","isolation":"worktree","description":"Plan the migration"}')"
[[ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out")" == ask ]] && pass "code-plan: a premium class on fable, asks like code-high" || fail "code-plan not handled" "$out"
out="$(vanilla '{"subagent_type":"code-plan","model":"opus","isolation":"worktree","description":"Plan the migration"}')"
[[ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out")" == deny ]] && pass "code-plan on opus is denied: the class rides fable" || fail "code-plan alias not checked" "$out"
out="$(vanilla '{"subagent_type":"blind-reviewer","model":"fable","description":"Review PR 626 diff"}')"
[[ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out")" == deny ]] && grep -q "code-review" <<<"$out" && pass "the retired type name is denied and the message names code-review" || fail "blind-reviewer not redirected" "$out"
# The broker path is the same route: the file carries the composite.
reviewer_file "deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim"
out="$(launched openrouter "$R")"
[[ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out")" == allow && "$(jq -r '.hookSpecificOutput.updatedInput | has("model")' <<<"$out")" == false ]] && grep -q "deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" <<<"$out" && pass "on the broker path the review dispatch hands the model to the file too, the composite" || fail "broker review not on the file route" "$out"
# A stale file: another launch of this account rewrote it.
reviewer_file "claude-opus-5[1m]"
out="$(launched openrouter "$R")"
[[ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out")" == deny ]] && grep -q "rewritten" <<<"$out" && pass "a reviewer file that disagrees with this launch's resolution is denied, not run" || fail "stale reviewer file admitted" "$out"
# THE SAME STALENESS, FOR EFFORT. A level is written into every class's
# file, not just the reviewer's model, so the cross-provider rewrite
# strands any class. Compared only when the file carries a line: a missing
# one is an install older than effort, and denying on it would block every
# dispatch on every account until it relaunched.
class_file() {  # class_file <name> <model> [level]  — [level] omitted writes no effort: line
    mkdir -p "$SCRATCH_HOME/agents"
    { printf -- '---\nname: %s\nmodel: %s\n' "$1" "$2"
      [[ -n "${3:-}" ]] && printf 'effort: %s\n' "$3"
      printf -- '---\n'; } > "$SCRATCH_HOME/agents/$1.md"
}
HIGH='{"subagent_type":"code-high","model":"opus","isolation":"worktree","description":"do the thing"}'
class_file code-high opus
out="$(vanilla "$HIGH")"
! grep -q "think at a level nothing chose" <<<"$out" && pass "no effort: line in the class file — an older install is not treated as another launch's value" || fail "denied on a missing effort line" "$out"
class_file code-high opus high
out="$(vanilla "$HIGH")"
! grep -q "think at a level nothing chose" <<<"$out" && pass "the file's level agrees with this launch: not denied for it" || fail "denied on an agreeing level" "$out"
class_file code-high opus low
out="$(vanilla "$HIGH")"
[[ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out")" == deny ]] && grep -q "think at a level nothing chose" <<<"$out" && pass "a class file another launch rewrote to a different level is denied, not run" || fail "stranded effort admitted" "$out"
rm -f "$SCRATCH_HOME/agents/code-high.md"
reviewer_file "claude-opus-5[1m]"
printf -- '---\nname: code-review\nmodel: claude-opus-5[1m]\neffort: low\n---\n' > "$SCRATCH_HOME/agents/code-review.md"
out="$(vanilla "$R")"
[[ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out")" == deny ]] && grep -q "effort" <<<"$out" && pass "…and the review class is checked the same way" || fail "reviewer effort not checked" "$out"
reviewer_file "claude-opus-5[1m]"

# The runner may itself be a fabric-launched session; "unlaunched" is the variable absent, not inherited.
[[ -z "$(printf '{"tool_name":"Agent","tool_input":%s}' "$R" | env -u AGENT_FABRIC_LAUNCH_PROVIDER bash "$UNDER_TEST" 2>/dev/null)" ]] && pass "unlaunched vanilla: plain allow, fable is the harness's" || fail "rewrite leaked to an unlaunched session"

echo
if [[ "$failures" -eq 0 ]]; then echo "all assertions passed"; exit 0; fi
echo "$failures assertion(s) failed" >&2; exit 1
