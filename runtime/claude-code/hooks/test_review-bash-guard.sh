#!/usr/bin/env bash
# Behavioural tests for runtime/claude-code/hooks/review-bash-guard.sh -- the fence around
# the review class, which runs unisolated in the session clone.
#
# Two things held still: state-changing git and installs are DENIED
# however they are spelled (leading whitespace, chained after another
# command, sudo, global git flags), and read-only git, validators,
# guards and no-install builds are ALLOWED -- a fence that blocks the
# review's own tools is a fence the next session removes.
#
# Exit codes: 0 all assertions passed; 1 one or more failed.
set -uo pipefail
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/review-bash-guard.sh"
[[ -f "$UNDER_TEST" ]] || { echo "test: not found: $UNDER_TEST" >&2; exit 1; }
failures=0
pass() { echo "  ok   $1"; }
fail() { echo "  FAIL $1" >&2; [[ $# -gt 1 ]] && printf '       %s\n' "$2" >&2; failures=$((failures + 1)); }
decision() {
  local out; out="$(jq -nc --arg c "$1" '{tool_name:"Bash",tool_input:{command:$c},agent_type:"code-review"}' | bash "$UNDER_TEST" 2>/dev/null)"
  if [[ -z "$out" ]]; then echo allow; else printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision // "malformed"'; fi
}
expect() { local got; got="$(decision "$3")"; if [[ "$got" == "$2" ]]; then pass "$1"; else fail "$1" "want $2, got $got for: $3"; fi; }

echo "state-changing git is denied"
for c in 'git push' 'git push origin HEAD' '  git commit -m x' 'git add -A' 'git checkout main' 'git switch -c x' 'git reset --hard' 'git stash' 'git rebase -i HEAD~2' 'git merge origin/main' 'git worktree add /tmp/x' 'git fetch' 'git pull' 'git clean -fd' 'git branch -D x' 'git tag v1' 'git -C /repo push' 'git --no-pager -c user.name=x commit -m y' 'cd /repo && git push' 'ls; git reset --hard' 'sudo git push' 'echo $(git stash)' 'git restore .'; do
  expect "denied: $c" deny "$c"
done
echo "installs and restores are denied"
for c in 'pnpm install' 'pnpm -r install' 'npm i' 'yarn add left-pad' 'flutter pub get' 'dart pub upgrade' 'dotnet restore Gzapp.sln' 'dotnet add package X' 'pip install requests' 'cd apps/passenger_flutter && flutter pub get'; do
  expect "denied: $c" deny "$c"
done
echo "shell escapes, path-qualified git and in-place writes are denied"
for c in 'bash -c "git push"' 'sh -c git\ push' 'eval "git push"' 'exec git push' '/usr/bin/git push' 'sed -i s/a/b/ CLAUDE.md' 'sed --in-place -e x f' 'echo x > CLAUDE.md' 'echo x >> notes.md' 'tee out.txt' 'rm -rf apps' 'mv a b' 'cp a b' 'ls > /tmp/out'; do
  expect "denied: $c" deny "$c"
done
echo "the environment and secret material are denied (2026-10-04: a reviewer printed the signing key)"
for c in 'env' 'env | grep -i fabric' 'env -u PATH' '/usr/bin/env' 'printenv' 'printenv GH_TOKEN' 'ls; printenv' 'set' 'set | head' 'export' 'export -p' 'declare -p' 'declare -px' 'typeset -x' 'compgen -v' 'echo $GH_TOKEN' 'printf %s "${FABRIC_CONTROL_SIGNING_KEY}"' 'echo $OPENROUTER_API_KEY | wc -c' 'echo $CLAUDE_BRIDGE_AUTH_TOKEN' 'cat ~/.config/agent-fabric/secrets.env' 'grep -c export $HOME/.config/agent-fabric/secrets.env' 'ls ~/.local/share/agent-fabric/secrets' 'git -C ~/.local/share/agent-fabric/children/x log' 'cat /proc/self/environ' 'tr "\\0" "\\n" < /proc/1234/environ' 'ls ~/.password-store' 'gpg --export-secret-keys' 'ls ~/.gnupg' 'pass show x' 'fabric-secrets store get GH_TOKEN' 'python3 -c "import os; print(os.environ)"' 'node -e "console.log(process.env)"' 'python3 -c "import json,os; print(json.dumps(dict(os.environ)))"'; do
  expect "denied: $c" deny "$c"
done
echo "running in a clean environment, and searching code for the word, stay allowed"
for c in 'env -i HOME=/tmp/x PATH=/usr/bin python3 tools/fabric/lint.py' 'env -u AGENT_FABRIC_ROOT python3 tests/test_lint.py' 'env LC_ALL=C sort file' 'grep -rn "secrets.env" tools/fabric' 'grep -rn FABRIC_CONTROL_SIGNING_KEY runtime/control' 'set -euo pipefail' 'export FOO=bar && make' 'echo $HOME' 'echo ${PATH}' 'python3 -c "import os; print(os.environ.get(\"HOME\"))"' 'fabric-secrets status' 'git log -p -- tools/fabric/secret_store.py'; do
  expect "allowed: $c" allow "$c"
done
echo "read-only git and no-install builds are allowed"
for c in 'git log --oneline -5' 'git show HEAD:CLAUDE.md' 'git diff origin/main..HEAD' 'git blame -L 1,5 file' 'git status --short' 'git rev-parse HEAD' 'git branch --show-current' 'git remote -v' 'git worktree list' 'git tag --list' 'dotnet build Gzapp.sln -c Release --no-restore' 'dotnet test Gzapp.sln --no-restore' 'pnpm --filter admin_web test' 'flutter analyze' 'flutter test' 'node tools/validate_contracts/validate.js' 'bash tools/checks/scan_semantic_collisions.sh' 'grep -rn gitadd .' 'echo "git push is banned"' 'cat docs/git-pushing.md' 'dotnet test 2>/dev/null' 'ls >/dev/null 2>&1' 'cmd 2>&1 | head' 'git diff origin/main..HEAD > /dev/null'; do
  expect "allowed: $c" allow "$c"
done
echo "a guard that cannot run denies; it never silently allows"
out="$(printf '{"tool_input":{"command":"git push"}}' | env PATH=/nonexistent /bin/bash "$UNDER_TEST" 2>/dev/null)"
if printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then
  pass "with jq unavailable the guard denies"
else
  fail "with jq unavailable the guard denies" "out=[$out]"
fi

echo "malformed input allows and never exits 2"
for payload in '{}' 'not json' ''; do
  out="$(printf '%s' "$payload" | bash "$UNDER_TEST" 2>/dev/null)"; rc=$?
  if [[ "$rc" -ne 2 && -z "$out" ]]; then pass "payload (${payload:-empty}) allows (rc=$rc)"; else fail "payload (${payload:-empty}) allows" "rc=$rc out=[$out]"; fi
done
echo
if [[ "$failures" -eq 0 ]]; then echo "all assertions passed"; exit 0; fi
echo "$failures assertion(s) failed" >&2; exit 1
