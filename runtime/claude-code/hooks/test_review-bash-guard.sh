#!/usr/bin/env bash
# Behavioural tests for runtime/claude-code/hooks/review-bash-guard.sh (the shim) and
# review-bash-guard.py, the fence around
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
echo "…and the routine spellings two blind reviews of #96 found past the first version"
for c in "python3 -c \"import os; print(os.environ['GH_TOKEN'])\"" 'node -e "console.log(process.env.GH_TOKEN)"' 'n=GH_TOKEN; echo ${!n}' 'node -p "process.env"' 'node -p process.env' 'jq -n env' "jq -n '\$ENV'" 'ps eww -p 1' 'xargs env < /dev/null' 'command env' '\env' 'nice env' 'time env' 'env -0' 'env -0 | tr x y' 'env -C /tmp' "perl -e 'print join(\"\\n\", %ENV)'" "perl -e 'print %ENV'" "awk 'BEGIN{for(k in ENVIRON) print k}'" 'cd ~/.config/agent-fabric && cat secrets.env' 'cat ~/.config/agent-fabric/secret*.env' 'cat ~/.config/agent-fabric/*.env' 'python3 -c "import os; print(os.environ.copy())"' 'python3 -c "import os; [print(k,v) for k,v in os.environ.items()]"' 'python3 -c "import os,sys; sys.stdout.write(repr(os.environ))"' 'grep x ~/.config/agent-fabric/secrets.env' 'rg token $HOME/.password-store' 'grep -a TOKEN /proc/1/environ' 'grep -n "$GH_TOKEN" tests'; do
  expect "denied: $c" deny "$c"
done
# A search naming a /proc/*/environ path reads it as surely as cat does:
# the guard cannot tell a pattern from a file argument there, so it is
# refused (search for "environ" instead). The other secret words stay
# searchable as patterns.
expect "denied: a search naming a /proc environ path (indistinguishable from reading it)" deny 'grep -rn "/proc/self/environ" tests'
echo "a search exempts only itself: what is chained to it, and what makes it run a program, is judged in full (#96 round 2)"
for c in 'grep -c x README.md; env' 'git log -1; printenv' 'rg x tools && python3 -c "import os; print(os.environ)"' 'grep x f | xargs env' 'grep -c x README.md; ps eww' 'grep -h export ../../.config/agent-fabric/secrets.env' 'git show HEAD:README.md; cat ../../.config/agent-fabric/secrets.env' 'grep -r TOKEN ~/.config' 'grep -rh = ~/.local/share' 'grep -r TOKEN ~' 'grep -r TOKEN /home/user' 'grep -rn x /home' 'grep -rn x /' 'grep -r x /proc/self' 'grep $(env) f' 'grep `printenv` f' 'git -c diff.external=printenv diff' 'git --config-env=core.pager=X log' 'GIT_EXTERNAL_DIFF=env git diff' 'PAGER=env git log' 'rg --pre env x .' 'find . -maxdepth 0 -exec env \;' 'git config diff.external env' 'git config --add core.pager env' 'git config --global core.pager env' 'git config set core.pager env'; do
  expect "denied: $c" deny "$c"
done
echo "the cut respects quotes, a home through . or .. is a home, and no cd leaves the clone (#96 round 3)"
for c in 'python3 -c "import os;grep =os.environ;print(grep)"' 'node -e "x=1;grep =process.env;console.log(grep)"' "python3 -c 'import os;grep =os.environ;print(grep)'" 'python3 -c "a=1;grep =x+\"/.config/agent-fabric/secrets.env\";print(open(grep).read())"' 'grep "a;b" f; env' 'grep "unclosed f; env' 'grep -rh TOKEN /home/user/.' 'grep -rh TOKEN ~/.' 'grep -rh TOKEN ~/projects/..' 'grep -rh TOKEN /home/user/projects/..' 'grep -r x ../../' 'grep -r x ../..' 'cd' 'cd ~' 'cd -' 'cd ..' 'cd ../..' 'cd /home/user' 'cd ~/.config' 'cd / && ls' 'pushd ~'; do
  expect "denied: $c" deny "$c"
done
for c in 'cd tools && grep -rn x .' 'cd /home/user/projects/agent-fabric && git log -1' 'grep -rn "a|b" tools' "grep -rn 'a;b' tools" 'grep -rn x ../sibling/file' 'grep -E "foo|bar" tools | head -3'; do
  expect "allowed: $c" allow "$c"
done
echo "the cut is trusted only where it cannot disagree with bash: comments, multi-line quotes, \$'...' (#96 round 4)"
nl=$'\n'
for c in "grep -r x . #'${nl}env${nl}#'" "grep -r x . #\"${nl}printenv${nl}#\"" "grep -r x . #'${nl}true; env${nl}#'" "grep x \$'\\'' ; env #'" 'grep "$(echo '"'"')" ; env ; '"'"'x' 'env # x' 'set #x' 'export # x'; do
  expect "denied: $c" deny "$c"
done
for c in 'grep -rn "#!" tools' "grep -rn '#' tools | head" 'grep -rn x tools # a note' 'env -i PATH=/usr/bin ls # note'; do
  expect "allowed: $c" allow "$c"
done
echo "a search is exempt on one line only: a continuation hid a comment (#96 round 5)"
for c in "grep x . \\${nl}#\\${nl}env" "grep x . #\\${nl}env" "grep x . \\${nl}#\\${nl}printenv" "git log -1 \\${nl}#\\${nl}ps eww" "grep x . \\${nl}#\\${nl}cat ~/.config/agent-fabric/secrets.env" "grep x . \\${nl}#\\${nl}cat secrets.env" "grep -rn x tools${nl}env" 'grep "${x:-'"'"'}"'"'"'}" ; env #'"'"; do
  expect "denied: $c" deny "$c"
done
for c in "grep -rn x tools${nl}git log -1" "grep -rn secrets.env tools" 'grep -rn "secrets.env" tools # where it is read'; do
  expect "allowed: $c" allow "$c"
done
echo "a search may not run a pager or reach a home through a glob (#96 round 6)"
for c in "git grep -O'less;true' -e x" 'git grep --open-files-in-pager=less x' 'grep -rn x /h*/*/.config/agent-fabric/' 'grep -r . /h??e/*/.config/agent-fabric/secrets.env' 'grep -r TOKEN /home/user/.c*' 'grep -r TOKEN ~/.[a-z]*'; do
  expect "denied: $c" deny "$c"
done
for c in 'grep -rn x tools/*.py' 'git log -1 --format=%H'; do
  expect "allowed: $c" allow "$c"
done
echo "Python backtracks where grep did not: a crafted command is judged in time, and a late verdict is a deny (CodeQL on #96)"
tabs=$'\t'
long_git="git"; long_env="env${tabs}"; for _ in $(seq 3000); do long_git+="${tabs}--"; long_env+="-C${tabs}--${tabs}"; done
expect "allowed in time: git followed by 3000 options" allow "${long_git}!"
expect "allowed in time: env -C -- repeated 3000 times, then text" allow "${long_env}!"
long_search="git${tabs}-A"; for _ in $(seq 3000); do long_search+="${tabs}-A"; done
expect "allowed in time: git -A repeated 3000 times, then text" allow "${long_search}!"
long_words=""; for _ in $(seq 20000); do long_words+="git "; done
expect "allowed in time: the word git 20000 times" allow "${long_words}x"
long_cc="git"; long_attr="git"; for _ in $(seq 3000); do long_cc+=" -C -C"; long_attr+=" --attr-source"; done
expect "allowed in time: git -C -C repeated 3000 times, then text" allow "${long_cc}!"
expect "allowed in time: git --attr-source repeated 3000 times, then text" allow "${long_attr}!"
out="$(jq -nc '{tool_input:{command:"ls"}}' | AGENT_FABRIC_REVIEW_GUARD_BUDGET=0 bash "$UNDER_TEST" 2>/dev/null)"
if printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then
  pass "a verdict later than the budget is a deny, even for ls"
else
  fail "a verdict later than the budget is a deny, even for ls" "out=[$out]"
fi
echo "an option's argument is the next word whatever it is, as getopt reads it; pagers and expansions (#96 round 7)"
for c in 'env -u -.' 'env -u -/' 'env -u -.x' 'env -u -. | sort' 'env -C -.' 'env -C =x' 'env -C/tmp' 'env --chdir=/tmp' 'env --unset=X' 'git -C -. push origin HEAD' 'git -C -/ -c core.pager=less log' 'git --git-dir=.git push' 'git --work-tree=. commit -m x' 'git --git-dir .git push' "git grep -iO'less' -e x" 'git grep "-Oless" -e x' "git grep --open='less' -e x" 'grep -r TOKEN /h*' 'grep -r TOKEN /hom?' 'grep -r TOKEN /[h]ome' 'grep -r TOKEN /*' 'grep -r TOKEN /{home,x}/user/.config/agent-fabric/' 'grep -r TOKEN ~{,}/.config/agent-fabric' 'grep -r TOKEN ~user/.config/agent-fabric' 'grep -r TOKEN .?/.?/.config' 'grep -n x /home/user/projects/agent-fabric/tools/*.py'; do
  expect "denied: $c" deny "$c"
done
# Refused on purpose, with the spelling that works: a search over an absolute
# glob (use a relative path from the clone).
for c in 'gcc -O2 x.c' 'python3 -O tests/x.py' 'git log --cc -1' 'grep -n x tools/*.py' 'git -C tools log -1'; do
  expect "allowed: $c" allow "$c"
done
echo "an option no list knows may take a word too; getopt_long's long, abbreviated and clustered forms (#96 round 8)"
for c in 'git --attr-source HEAD push origin HEAD' 'git --attr-source HEAD commit -m x' 'git --attr-source HEAD -C . reset --hard' 'git --a-future-option value push' 'env --unset X' 'env --uns X' 'env -0u X' 'env -0uX' 'env --unset -.' 'env --chdir /tmp' 'git -c core.pager=less log' 'git -C . -c core.pager=less log' 'git --no-pager -c core.pager=less log'; do
  expect "denied: $c" deny "$c"
done
for c in 'git grep -c TODO' 'git log -SOracle -1' 'git log -c -1' 'git --attr-source HEAD log -1' 'git log --grep push -1'; do
  expect "allowed: $c" allow "$c"
done
echo "running in a clean environment, and searching code for the word, stay allowed"
for c in 'env -i HOME=/tmp/x PATH=/usr/bin python3 tools/fabric/lint.py' 'env -u AGENT_FABRIC_ROOT python3 tests/test_lint.py' 'env LC_ALL=C sort file' 'grep -rn "secrets.env" tools/fabric' 'grep -rn FABRIC_CONTROL_SIGNING_KEY runtime/control' 'set -euo pipefail' 'export FOO=bar && make' 'echo $HOME' 'echo ${PATH}' 'python3 -c "import os; print(os.environ.get(\"HOME\"))"' 'fabric-secrets status' 'git log -p -- tools/fabric/secret_store.py' 'grep -rn ".gnupg" tools' 'grep -rn ".password-store" tools' 'rg -n secret_store tools' 'git grep -n process.env runtime' 'git show HEAD:tools/fabric/secrets_sync.py' 'ps aux' 'ps -ef' 'cat .env.example' 'ls tests' 'python3 -c "import os; print(os.environ[\\"HOME\\"])"' 'node -e "console.log(process.env.HOME)"' 'grep -rn "secrets.env" tools | head' 'git grep -n process.env runtime | wc -l' 'grep -E "foo|bar" tools' 'git config --get user.name' 'git config --list' 'grep -c x README.md' 'git -C /home/user/projects/agent-fabric log -1' 'grep -rn x /home/user/projects/agent-fabric/tools' 'rg -n TOKEN /home/user/projects/agent-fabric/runtime'; do
  expect "allowed: $c" allow "$c"
done
echo "read-only git and no-install builds are allowed"
for c in 'git log --oneline -5' 'git show HEAD:CLAUDE.md' 'git diff origin/main..HEAD' 'git blame -L 1,5 file' 'git status --short' 'git rev-parse HEAD' 'git branch --show-current' 'git remote -v' 'git worktree list' 'git tag --list' 'dotnet build Gzapp.sln -c Release --no-restore' 'dotnet test Gzapp.sln --no-restore' 'pnpm --filter admin_web test' 'flutter analyze' 'flutter test' 'node tools/validate_contracts/validate.js' 'bash tools/checks/scan_semantic_collisions.sh' 'grep -rn gitadd .' 'echo "git push is banned"' 'cat docs/git-pushing.md' 'dotnet test 2>/dev/null' 'ls >/dev/null 2>&1' 'cmd 2>&1 | head' 'git diff origin/main..HEAD > /dev/null'; do
  expect "allowed: $c" allow "$c"
done
echo "a guard that cannot run denies; it never silently allows"
out="$(printf '{"tool_input":{"command":"ls"}}' | env AGENT_FABRIC_PYTHON=/nonexistent /bin/bash "$UNDER_TEST" 2>/dev/null)"
if printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then
  pass "with the fleet's Python unavailable the guard denies, even a harmless command"
else
  fail "with the fleet's Python unavailable the guard denies, even a harmless command" "out=[$out]"
fi

out="$(printf '{"tool_input":{"command":"ls"}}' | env AGENT_FABRIC_PYTHON=/bin/false /bin/bash "$UNDER_TEST" 2>/dev/null)"
if printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then
  pass "a module that fails (any exit but 0) is a deny, even for ls"
else
  fail "a module that fails (any exit but 0) is a deny, even for ls" "out=[$out]"
fi

echo "malformed input allows and never exits 2"
for payload in '{}' 'not json' ''; do
  out="$(printf '%s' "$payload" | bash "$UNDER_TEST" 2>/dev/null)"; rc=$?
  if [[ "$rc" -ne 2 && -z "$out" ]]; then pass "payload (${payload:-empty}) allows (rc=$rc)"; else fail "payload (${payload:-empty}) allows" "rc=$rc out=[$out]"; fi
done
echo
if [[ "$failures" -eq 0 ]]; then echo "all assertions passed"; exit 0; fi
echo "$failures assertion(s) failed" >&2; exit 1
