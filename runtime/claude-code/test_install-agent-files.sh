#!/usr/bin/env bash
# runtime/claude-code/test_install-agent-files.sh
#
# The locale worker's installation: ~/.claude/agents/locale-worker.md
# exists exactly on a language-culture login whose locale the fabric
# authored a worker for, and is removed from any other (a rebind, a locale
# with no worker), by the marker in its description. The class files ride
# unchanged. Sandboxed like tests/test_launch_cli.py: a fixture
# fabric root, a state dir with this login's binding, HOME in scratch.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REAL_ROOT="$(cd "$HERE/../.." && pwd)"
LOGIN="$(id -un)"; SUFFIX="${LOGIN##*-}"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ✓ %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  ✗ %s\n' "$1"; [[ -n "${2:-}" ]] && printf '%s\n' "$2" | sed 's/^/      /' | head -6; }
SANDBOX="$(mktemp -d)"; trap 'rm -rf "$SANDBOX"' EXIT
export HOME="$SANDBOX/home"; mkdir -p "$HOME"; unset CLAUDE_CONFIG_DIR   # never the caller's real config
# The fixture fabric is the whole tree it reads: an exported operator would
# outrank it (ADR-045 §5 rule 3) and send the reads to data this suite did not build.
unset AGENT_FABRIC_OPERATOR
FABRIC="$SANDBOX/fabric"; STATE="$SANDBOX/state"
mkdir -p "$FABRIC/runtime/claude-code" "$FABRIC/tools/fabric" "$FABRIC/runtime" "$STATE/agents/$LOGIN"
cp -r "$REAL_ROOT/routing" "$FABRIC/routing"
# The committed roles/agents layers may name the login running this suite;
# the cases assert what the defaults and the layers they write resolve to.
python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); d["roles"], d["agents"] = {}, {}; json.dump(d, open(sys.argv[1], "w"), indent=2)' "$FABRIC/routing/profiles.json"
cp "$REAL_ROOT/runtime/claude-code/aliases.json" "$REAL_ROOT/runtime/claude-code/install-agent-files.sh" "$FABRIC/runtime/claude-code/"
cp -r "$REAL_ROOT/runtime/claude-code/agents" "$FABRIC/runtime/claude-code/agents"
cp "$REAL_ROOT/runtime/identity.py" "$FABRIC/runtime/"
cp "$REAL_ROOT/tools/fabric/routing.py" "$REAL_ROOT/tools/fabric/workingcopy.py" "$REAL_ROOT/tools/fabric/layout.py" "$REAL_ROOT/tools/fabric/install_agent_files.py" "$REAL_ROOT/tools/fabric/fabric_writes.py" "$REAL_ROOT/tools/fabric/roots.py" "$FABRIC/tools/fabric/"
bind() { printf '{"agent":"%s","host":"%s","role":"%s","updated_at":"x"}\n' "$LOGIN" "$(hostname -s)" "$1" > "$STATE/agents/$LOGIN/binding.json"; }
WORKER="$FABRIC/identities/roles/language-culture/locale/$SUFFIX/worker.md"
mkdir -p "$(dirname "$WORKER")"
printf -- '---\nname: locale-worker\ndescription: The locale worker (agent-fabric) — fixture\nmodel: opus\ntools:\n---\n\nფიქსტურა.\n' > "$WORKER"
run_install() { AGENT_FABRIC_ROOT="$FABRIC" AGENT_FABRIC_STATE_DIR="$STATE" bash "$FABRIC/runtime/claude-code/install-agent-files.sh" "$@" 2>&1; }
DEST="$HOME/.claude/agents/locale-worker.md"

echo "a language-culture login with an authored worker for its locale gets the file"
bind language-culture
out="$(run_install --dry-run)"
grep -q "locale-worker.md (would write)" <<<"$out" && [[ ! -e "$DEST" ]] && ok "dry run names it and writes nothing" || bad "dry run" "$out"
out="$(run_install)"
[[ -f "$DEST" ]] && cmp -s "$DEST" "$WORKER" && ok "installed, byte-equal to the source" || bad "install" "$out"
[[ -f "$HOME/.claude/agents/code-low.md" && -f "$HOME/.claude/agents/code-review.md" ]] && ok "the class files ride as before" || bad "class files"
out="$(run_install)"; grep -q "locale-worker.md" <<<"$out" && grep -q "=  $DEST" <<<"$out" && ok "a second run changes nothing" || bad "idempotence" "$out"

echo "the locale search tool: an MCP entry in the user configuration, on the same login"
mkdir -p "$(dirname "$WORKER")"; printf '{"timezone": "Asia/Tbilisi", "serpapi": {"gl": "ge", "hl": "ka", "tool_description": "ვებ-ძიება"}}' > "$(dirname "$WORKER")/locale.json"
mkdir -p "$FABRIC/runtime/mcp/websearch-locale"; cp "$REAL_ROOT/runtime/mcp/websearch-locale/install.py" "$FABRIC/runtime/mcp/websearch-locale/"; mkdir -p "$FABRIC/bin"; : > "$FABRIC/bin/fabric-websearch-locale"
printf '{"theme": "dark", "mcpServers": {"mine": {"command": "x"}}}' > "$HOME/.claude.json"
out="$(run_install)"; grep -q "mcpServers.websearch-locale" <<<"$out" && python3 -c "import json,sys; d=json.load(open('$HOME/.claude.json')); e=d['mcpServers']['websearch-locale']; assert e['command'].endswith('/bin/fabric-websearch-locale') and e['args']==[] and e['env']['WEBSEARCH_LOCALE_FILE'].endswith('/locale.json') and d['theme']=='dark' and 'mine' in d['mcpServers'], d" && ok "the entry is written beside what was there" || bad "mcp entry" "$out"
out="$(run_install)"; grep -q "=  $HOME/.claude.json mcpServers.websearch-locale" <<<"$out" && ok "a second run leaves it" || bad "mcp idempotence" "$out"
python3 -c "import json; d=json.load(open('$HOME/.claude/settings.json')); assert d['permissions']['deny']==['WebSearch','WebSearch(agent-fabric)'], d" && ok "the harness's WebSearch is denied in the user settings, marked as the fabric's" || bad "websearch deny" "$(cat "$HOME/.claude/settings.json" 2>&1)"

echo "another role: the worker is removed by its marker"
bind backend-dev
out="$(run_install --dry-run)"; grep -q "would remove: role is backend-dev" <<<"$out" && [[ -f "$DEST" ]] && ok "dry run names the removal and touches nothing" || bad "dry-run removal" "$out"
out="$(run_install)"; [[ ! -e "$DEST" ]] && grep -q "removed: role is backend-dev" <<<"$out" && ok "removed" || bad "removal" "$out"
out="$(run_install)"; ! grep -q "locale-worker" <<<"$out" && ok "nothing to remove the second time, nothing said" || bad "second removal" "$out"
python3 -c "import json; d=json.load(open('$HOME/.claude.json')); assert 'websearch-locale' not in d['mcpServers'] and 'mine' in d['mcpServers'], d" && ok "the MCP entry went with the role; the login's own stayed" || bad "mcp removal" "$(cat "$HOME/.claude.json")"
python3 -c "import json; d=json.load(open('$HOME/.claude/settings.json')); assert d['permissions']['deny']==[], d" && ok "the WebSearch deny went with it" || bad "websearch allow" "$(cat "$HOME/.claude/settings.json")"
printf '{"permissions": {"deny": ["WebSearch"]}, "theme": "dark"}' > "$HOME/.claude/settings.json"
out="$(run_install)"; python3 -c "import json; d=json.load(open('$HOME/.claude/settings.json')); assert d['permissions']['deny']==['WebSearch'] and d['theme']=='dark', d" && ok "a WebSearch the login denied itself is left alone" || bad "own deny touched" "$(cat "$HOME/.claude/settings.json")"

echo "a language-culture login whose locale has no authored worker: removed, never another locale's"
bind language-culture
run_install >/dev/null; [[ -f "$DEST" ]] || bad "precondition: installed"
rm -rf "$FABRIC/identities/roles/language-culture/locale/$SUFFIX"; mkdir -p "$FABRIC/identities/roles/language-culture/locale/xx"; cp "$WORKER" "$FABRIC/identities/roles/language-culture/locale/xx/worker.md" 2>/dev/null || printf -- '---\nname: locale-worker\ndescription: (agent-fabric)\nmodel: opus\ntools:\n---\nx\n' > "$FABRIC/identities/roles/language-culture/locale/xx/worker.md"
out="$(run_install)"; [[ ! -e "$DEST" ]] && grep -q "no worker authored for locale $SUFFIX" <<<"$out" && ok "removed and the reason names the locale" || bad "wrong-locale removal" "$out"

echo "the class files carry the effort routing resolves, and only where a model expresses one"
bind backend-dev; rm -rf "$HOME/.claude/agents"; run_install >/dev/null
A="$HOME/.claude/agents"
for klass in code-low code-medium code-high code-plan code-review; do
    want="$(AGENT_FABRIC_ROOT="$FABRIC" AGENT_FABRIC_STATE_DIR="$STATE" python3 "$FABRIC/tools/fabric/routing.py" efforts --me --provider anthropic | awk -v k="$klass" '$1==k {print $2}')"
    got="$(sed -n 's/^effort: //p' "$A/$klass.md")"
    if [[ "$want" == "-" ]]; then
        [[ -z "$got" ]] && ok "$klass: the model expresses no effort, so no effort: line at all" || bad "$klass got effort: $got where none is expressible"
    else
        [[ "$got" == "$want" ]] && ok "$klass: effort: $want, as routing resolves it" || bad "$klass effort: wanted $want, got '${got:-none}'"
    fi
done
grep -q "^effort:" "$FABRIC/runtime/claude-code/agents/code-high.md" && bad "the committed source carries a hand-written effort:" || ok "the committed sources carry none: the installer is the only writer"
out="$(run_install)"; grep -q "0 written, 5 already current" <<<"$out" && ok "a second run rewrites nothing" || bad "not idempotent" "$out"

echo "the pre-fabric backup is taken once, not on every run"
rm -rf "$HOME/.claude/agents"; mkdir -p "$A"
printf -- '---
name: code-high
model: sonnet
---

the user own file.
' > "$A/code-high.md"
run_install >/dev/null
grep -q "the user own file" "$A/code-high.md.before-agent-fabric" && ok "a file the fabric did not write is kept aside" || bad "the original was not kept"
printf -- '---
name: code-high
model: opus
effort: max
---

fabric.
' > "$A/code-high.md"
run_install >/dev/null
grep -q "the user own file" "$A/code-high.md.before-agent-fabric" && ok "…and a later run never overwrites it with the fabric's own previous file" || bad "the backup was clobbered by a second run" "$(cat "$A/code-high.md.before-agent-fabric")"

echo "a routing failure refuses the whole run rather than writing files with no routing"
bind backend-dev; rm -rf "$HOME/.claude/agents"
printf '{"providers":{"anthropic":{"effort":{"code-high":"not-a-level"}}}}\n' > "$STATE/agents/$LOGIN/model-profile.local.json"
out="$(run_install)"; rc=$?
[[ $rc -ne 0 ]] && ok "a local layer routing.py refuses fails the installer" || bad "exit 0 with no routing" "$out"
grep -q "refusing to write agent files with no routing" <<<"$out" && ok "…and says so, naming the subcommand" || bad "failure not named" "$out"
[[ ! -e "$HOME/.claude/agents/code-high.md" ]] && ok "…and wrote nothing" || bad "wrote a file with an empty routing map"
# EACH call is guarded, not just the first. Every data-shaped break fails
# `pins` before `efforts` is reached (resolve() loads effort.json too), so
# the second guard is proved by failing that ONE subcommand: the fixture's
# own copy of routing.py is made to exit non-zero for `efforts` alone.
rm -f "$STATE/agents/$LOGIN/model-profile.local.json"
cp "$FABRIC/tools/fabric/routing.py" "$SANDBOX/routing.py.bak"
# A STUB in front of the real module, not an edit to it: routing.py opens
# with `from __future__`, which must be the first statement, so there is
# nowhere at the top to inject a check.
cp "$SANDBOX/routing.py.bak" "$FABRIC/tools/fabric/routing.real.py"
cat > "$FABRIC/tools/fabric/routing.py" <<'STUB'
import os, runpy, sys
if "efforts" in sys.argv:
    sys.exit(3)
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "routing.real.py"), run_name="__main__")
STUB
out="$(run_install)"; rc=$?
[[ $rc -ne 0 ]] && grep -q "routing.py efforts failed" <<<"$out" && ok "a failure of efforts alone is caught too, and named" || bad "the efforts guard is unreachable" "$out"
cp "$SANDBOX/routing.py.bak" "$FABRIC/tools/fabric/routing.py"; rm -f "$FABRIC/tools/fabric/routing.real.py"

echo "a worker file the fabric did not write is left alone"
bind backend-dev
mkdir -p "$HOME/.claude/agents"; printf -- '---\nname: locale-worker\ndescription: my own\n---\nmine\n' > "$DEST"
run_install >/dev/null; [[ -f "$DEST" ]] && grep -q "my own" "$DEST" && ok "a hand-written file without the marker survives" || bad "hand-written file removed"

echo
if (( FAIL == 0 )); then echo "test_install-agent-files: OK — $PASS assertion(s) passed."; exit 0; fi
echo "test_install-agent-files: $FAIL failure(s)" >&2; exit 1
