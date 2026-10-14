#!/usr/bin/env bash
# Behavioural tests for runtime/claude-code/hooks/subagent-ledger.py: the
# SubagentStop hook that appends one counts-only row v1 per subagent stop
# to <state>/agents/<login>/ledger.jsonl.
#
# What this holds still: the row read from the fixture transcript
# (testdata/subagent-ledger/), field by field, and that every row holds
# exactly the v1 keys — a message split over several records counts once
# at its final usage, a <synthetic> message and a torn last line count for
# nothing, the model is that of most turns; without a dispatch header the
# row is "inferred", purpose other-subagent, the description kept and
# never parsed (its #251 is not a pr), repository and head_sha from the
# transcript's cwd; with an `agent-fabric-dispatch v1` header as the
# brief's first fenced block its fields are copied, a field of the wrong
# type is not, and a header that is not the first block, or not a JSON
# object, is not one; status and status_source for every ending the
# transcript can show, none of the unfinished ones "completed"; provider
# from the model id, effort from the hook input else the transcript; no
# text of the transcript reaches the ledger; a second stop appends a
# second line; a credential in a remote URL never reaches the row; a
# run that never got an API answer still writes its row (turns 0, failed
# or cancelled); a dispatch row's missing or malformed field stays null,
# never filled from the cwd; a transcript with no conversation, and every
# input it cannot read, writes nothing, prints nothing and exits 0.
set -uo pipefail
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/subagent-ledger.py"
FIXTURE="$SCRIPT_DIR/testdata/subagent-ledger"
[[ -f "$UNDER_TEST" ]] || { echo "test: not found: $UNDER_TEST" >&2; exit 1; }
command -v jq >/dev/null || { echo "test: jq required" >&2; exit 1; }

failures=0
pass() { echo "  ok   $1"; }
fail() { echo "  FAIL $1" >&2; [[ $# -gt 1 ]] && printf '       %s\n' "$2" >&2; failures=$((failures + 1)); }
SANDBOX="$(mktemp -d)"; trap 'rm -rf "$SANDBOX"' EXIT
export AGENT_FABRIC_STATE_DIR="$SANDBOX/state"
LEDGER="$AGENT_FABRIC_STATE_DIR/agents/$(id -un)/ledger.jsonl"

# The subagent's working copy: a repository whose origin names the project.
REPO="$SANDBOX/work"
git init -q "$REPO"
git -C "$REPO" -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q --allow-empty -m fixture
git -C "$REPO" remote add origin git@github.com:BlueTeam-OU/agent-fabric.git
HEAD_SHA="$(git -C "$REPO" rev-parse HEAD)"

TR="$SANDBOX/subagents/agent-afixture.jsonl"
mkdir -p "$SANDBOX/subagents"
sed "s|@CWD@|$REPO|g" "$FIXTURE/agent-afixture.jsonl" > "$TR"
cp "$FIXTURE/agent-afixture.meta.json" "$SANDBOX/subagents/"

fire() {  # fire <transcript> [hook effort JSON] -> stdout, then rc=N
  jq -nc --arg tp "$1" --argjson effort "${2:-null}" '{hook_event_name:"SubagentStop", session_id:"sess-1", transcript_path:"/parent.jsonl", cwd:"/", stop_hook_active:false, agent_id:"afixture", agent_type:"code-review", agent_transcript_path:$tp} + (if $effort == null then {} else {effort:$effort} end)' \
    | python3 "$UNDER_TEST"
  echo "rc=$?"
}
row=""
field() {  # field <name> <expected jq value as JSON> <why>
  local got; got="$(printf '%s' "$row" | jq -c ".$1" 2>/dev/null)"
  if [[ "$got" == "$2" ]]; then pass "$1 = $2 ($3)"; else fail "$1 = $2 ($3)" "got: $got"; fi
}
KEYS='["agent_id","agent_type","attribution","base_sha","cache_read","cache_write","completed_at","description","dispatch_id","effort","engine","evidence","first_turn_context","head_sha","input","job_id","model","output","parent_session_id","pr","project","provider","purpose","reasoning","repository","review_id","review_round","schema_version","session_id","started_at","status","status_source","tool_use_id","turns","wall_time"]'
has_keys() {  # has_keys <why>
  local keys; keys="$(printf '%s' "$row" | jq -c 'keys' 2>/dev/null)"
  if [[ "$keys" == "$KEYS" ]]; then pass "the row holds exactly the v1 keys ($1)"; else fail "the row holds exactly the v1 keys ($1)" "$keys"; fi
}

# variant <name> <python body over `recs`, the fixture's parsed lines> -> path
# The fixture with its records changed, for the cases one line apart.
variant() {
  local out="$SANDBOX/subagents/agent-a$1.jsonl"
  python3 - "$TR" "$out" "$2" <<'PY'
import json, sys
src, out, body = sys.argv[1:]
lines = open(src).read().split("\n")
recs = [json.loads(l) for l in lines if l.startswith("{") and l.endswith("}")]
def last_api():
    return next(r for r in reversed(recs) if r["type"] == "assistant" and r["message"]["model"] != "<synthetic>")
def add(**rec):
    recs.append({"agentId": "afixture", "isSidechain": True, "cwd": recs[0]["cwd"],
                 "timestamp": "2026-10-14T10:00:13.000Z", **rec})
exec(body)
open(out, "w").write("".join(json.dumps(r) + "\n" for r in recs))
PY
  cp "$FIXTURE/agent-afixture.meta.json" "${out%.jsonl}.meta.json"
  printf '%s' "$out"
}

echo "subagent ledger: no dispatch header — inferred, the counts and the status"
out="$(fire "$TR" '{"level":"xhigh"}')"
if [[ "$out" == "rc=0" ]]; then pass "exit 0, nothing printed"; else fail "exit 0, nothing printed" "$out"; fi
if [[ -f "$LEDGER" && "$(wc -l < "$LEDGER")" -eq 1 ]]; then pass "one line in the ledger"; else fail "one line in the ledger" "$(cat "$LEDGER" 2>/dev/null)"; fi
row="$(head -n1 "$LEDGER" 2>/dev/null)"
has_keys "inferred"
field schema_version 1 "every row"
field engine '"claude"' "the hook's own engine"
field attribution '"inferred"' "no header in the brief"
field purpose '"other-subagent"' "no header"
field description '"review #251 range ade76f23 (round 2, see #12)"' "kept, from the .meta.json"
field pr null "the description is never parsed"
field review_round null "the description is never parsed"
field dispatch_id null "no header"
field session_id '"sess-1"' "the hook's session, from the payload"
field parent_session_id '"sess-1"' "no header: the hook's session, the dispatcher's"
field agent_id '"afixture"' "from the payload"
field agent_type '"code-review"' "from the payload"
field tool_use_id '"toolu_fixture"' "from the .meta.json"
field model '"claude-opus-5-5"' "the model of most turns, synthetic not counted"
field provider '"anthropic"' "a plain model id"
field effort '"xhigh"' "the hook input's effort.level"
field turns 3 "distinct API messages; the split message once, the synthetic none"
field input 6 "3+2+1"
field cache_write 150 "100+50+0"
field cache_read 3250 "1000+1100+1150"
field output 56 "40 (the split message's final count)+7+9"
field reasoning 30 "msg_A's thinking_tokens once; the others report none"
field first_turn_context 1103 "input+cache_write+cache_read of msg_A"
field wall_time 12.5 "first to last timestamp"
field started_at '"2026-10-14T10:00:00.000Z"' "no header: the transcript's first timestamp"
field repository '"BlueTeam-OU/agent-fabric"' "origin of the transcript's cwd"
field head_sha "\"$HEAD_SHA\"" "HEAD of the transcript's cwd"
field base_sha null "no header"
field status '"completed"' "the last API message ends its turn"
field status_source '"transcript:end_turn"' "the evidence"
if printf '%s' "$row" | jq -e '.completed_at | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T.*Z$")' >/dev/null 2>&1; then pass "completed_at is an ISO UTC time"; else fail "completed_at is an ISO UTC time" "$row"; fi
if ! grep -q "NEVER-IN-THE-LEDGER" "$LEDGER"; then pass "no text of the transcript reaches the ledger"; else fail "no text of the transcript reaches the ledger"; fi
if [[ "$(stat -c %a "$LEDGER")" == "600" && "$(stat -c %a "$(dirname "$LEDGER")")" == "700" ]]; then pass "ledger 600 in a 700 directory"; else fail "ledger 600 in a 700 directory" "$(stat -c '%a %n' "$LEDGER" "$(dirname "$LEDGER")")"; fi

echo "subagent ledger: a second stop appends; no hook effort reads the transcript's"
fire "$TR" >/dev/null
if [[ "$(wc -l < "$LEDGER")" -eq 2 ]] && head -n1 "$LEDGER" | jq -e . >/dev/null && tail -n1 "$LEDGER" | jq -e . >/dev/null; then pass "two whole lines"; else fail "two whole lines" "$(cat "$LEDGER")"; fi
row="$(tail -n1 "$LEDGER")"
field effort '"high"' "no effort input: the effort of most turns (high, high, medium)"

echo "subagent ledger: the dispatch header is copied"
HDR='{"dispatch_id":"d-1","parent_session_id":"parent-9","job_id":"j7","project":"agent-fabric","repository":"o/n","pr":251,"review_id":"r-3","review_round":2,"purpose":"pr-review","engine":"codex","evidence":"pinned","base_sha":"ade76f23","head_sha":"0123456789abcdef0123456789abcdef01234567","started_at":"2026-10-14T09:59:00Z","extra":"ignored"}'
T="$(variant header "recs[0]['message']['content'] = [{'type': 'text', 'text': 'Intro line.\n\n\`\`\`agent-fabric-dispatch v1\n' + sys.argv[3].split('#HDR#')[-1] + '\n\`\`\`\n\nBRIEF-TEXT-NEVER-IN-THE-LEDGER'}]#HDR#$HDR")"
rm -f "$LEDGER"; fire "$T" >/dev/null; row="$(cat "$LEDGER" 2>/dev/null)"
has_keys "dispatch"
field attribution '"dispatch"' "the brief's first fenced block is the header"
field purpose '"pr-review"' "copied"
field dispatch_id '"d-1"' "copied"
field parent_session_id '"parent-9"' "copied, over the hook's session"
field session_id '"sess-1"' "still the hook's"
field job_id '"j7"' "copied"
field project '"agent-fabric"' "copied"
field pr 251 "copied"
field review_id '"r-3"' "copied"
field repository '"o/n"' "copied, not the cwd's origin"
field review_round 2 "copied"
field evidence '"pinned"' "copied"
field base_sha '"ade76f23"' "copied"
field head_sha '"0123456789abcdef0123456789abcdef01234567"' "copied, over the cwd's HEAD"
field started_at '"2026-10-14T09:59:00Z"' "copied, over the first timestamp"
field engine '"claude"' "the engine that ran, never the header's"
field description '"review #251 range ade76f23 (round 2, see #12)"' "kept beside the header"
if ! grep -q "NEVER-IN-THE-LEDGER" "$LEDGER"; then pass "no text of the brief reaches a dispatch row"; else fail "no text of the brief reaches a dispatch row"; fi
T="$(variant headernohead "recs[0]['message']['content'] = '\`\`\`agent-fabric-dispatch v1\n{\"purpose\":\"pr-review\"}\n\`\`\`'")"
rm -f "$LEDGER"; fire "$T" >/dev/null; row="$(cat "$LEDGER" 2>/dev/null)"
field head_sha null "a header without head_sha: null, never the cwd's HEAD"
field repository null "a header without repository: null, never the cwd's origin"

echo "subagent ledger: a header field of the wrong type is not copied"
BAD='{"purpose":"a sentence of brief text","review_id":"r-3\n","evidence":"trust me","started_at":"2026-10-14T09:59:00","base_sha":"ade76f23\n","pr":"251","review_round":true,"head_sha":"not-a-sha","repository":"https://x:s3cret@github.com/a/b","dispatch_id":"'"$(printf 'x%.0s' {1..201})"'"}'
T="$(variant badtype "recs[0]['message']['content'] = '\`\`\`agent-fabric-dispatch v1\n' + sys.argv[3].split('#HDR#')[-1] + '\n\`\`\`'#HDR#$BAD")"
rm -f "$LEDGER"; fire "$T" >/dev/null; row="$(cat "$LEDGER" 2>/dev/null)"
field attribution '"dispatch"' "still a header"
field pr null "a string is not a pr"
field review_round null "a bool is not a round"
field dispatch_id null "past 200 characters is not an identifier"
field head_sha null "not a sha: null, never the cwd's HEAD"
field repository null "not owner/name: null, never the cwd's origin"
field evidence null "not pinned or working-tree"
field review_id null "an identifier with a trailing newline is not one"
field base_sha null "a sha with a trailing newline is not one"
field purpose '"other-subagent"' "prose is not an identifier"
field started_at '"2026-10-14T10:00:00.000Z"' "a time without its zone: the transcript's first timestamp"
if ! grep -q s3cret "$LEDGER"; then pass "the header's credential-shaped value never reaches the row"; else fail "no credential from the header"; fi

echo "subagent ledger: what is not the header is not read as one"
T="$(variant notfirst "recs[0]['message']['content'] = 'see:\n\`\`\`text\nquoted\n\`\`\`\n\`\`\`agent-fabric-dispatch v1\n{\"purpose\":\"pr-review\",\"pr\":9}\n\`\`\`'")"
rm -f "$LEDGER"; fire "$T" >/dev/null; row="$(cat "$LEDGER" 2>/dev/null)"
if printf '%s' "$row" | jq -e '.attribution == "inferred" and .purpose == "other-subagent" and .pr == null' >/dev/null 2>&1; then pass "a header after another fenced block: inferred"; else fail "a header after another fenced block: inferred" "$row"; fi
T="$(variant v2 "recs[0]['message']['content'] = '\`\`\`agent-fabric-dispatch v2\n{\"purpose\":\"pr-review\"}\n\`\`\`'")"
rm -f "$LEDGER"; fire "$T" >/dev/null; row="$(cat "$LEDGER" 2>/dev/null)"
if printf '%s' "$row" | jq -e '.attribution == "inferred" and .purpose == "other-subagent"' >/dev/null 2>&1; then pass "a v2 header: not v1, inferred"; else fail "a v2 header: inferred" "$row"; fi
for c in "notjson|{purpose: pr-review}" "array|[1]" "unclosed|{\"purpose\":\"pr-review\"}"; do
  name="${c%%|*}"; body="${c#*|}"
  close='\n\`\`\`'; [[ "$name" == unclosed ]] && close=''
  T="$(variant "inv$name" "recs[0]['message']['content'] = '\`\`\`agent-fabric-dispatch v1\n' + sys.argv[3].split('#B#')[-1] + '$close'#B#$body")"
  rm -f "$LEDGER"; fire "$T" >/dev/null; row="$(cat "$LEDGER" 2>/dev/null)"
  if printf '%s' "$row" | jq -e '.attribution == "invalid-header" and .purpose == "other-subagent" and .dispatch_id == null' >/dev/null 2>&1; then pass "$name header: invalid-header, other-subagent"; else fail "$name header: invalid-header" "$row"; fi
done

echo "subagent ledger: status from how the transcript ends"
status_case() {  # status_case <name> <python body> <status> <status_source>
  local T; T="$(variant "st$1" "$2")"
  rm -f "$LEDGER"; fire "$T" >/dev/null; row="$(cat "$LEDGER" 2>/dev/null)"
  local got; got="$(printf '%s' "$row" | jq -r '.status + " " + .status_source' 2>/dev/null)"
  if [[ "$got" == "$3 $4" ]]; then pass "$1: $3 ($4)"; else fail "$1: $3 ($4)" "got: $got"; fi
}
status_case stop-sequence "last_api()['message']['stop_reason'] = 'stop_sequence'" completed transcript:end_turn
status_case handback "last_api()['message']['content'] = [{'type': 'tool_use', 'id': 'toolu_h', 'name': 'SubagentHandback', 'input': {}}]; last_api()['message']['stop_reason'] = 'tool_use'; add(type='user', message={'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'toolu_h', 'content': 'ok'}]})" completed transcript:handback
status_case handback-error "last_api()['message']['content'] = [{'type': 'tool_use', 'id': 'toolu_h', 'name': 'SubagentHandback', 'input': {}}]; add(type='user', message={'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'toolu_h', 'is_error': True, 'content': 'no'}]})" failed transcript:handback-error
status_case max-tokens "last_api()['message']['stop_reason'] = 'max_tokens'" failed transcript:stop-reason:max_tokens
status_case api-error "add(type='assistant', isApiErrorMessage=True, error='rate_limit', message={'id': 'msg_E', 'model': '<synthetic>', 'role': 'assistant', 'content': [{'type': 'text', 'text': 'limit'}], 'usage': {}})" failed transcript:api-error:rate_limit
status_case api-error-free-text "add(type='assistant', isApiErrorMessage=True, error='rate limit: see https://x', message={'id': 'msg_E', 'model': '<synthetic>', 'role': 'assistant', 'content': [{'type': 'text', 'text': 'limit'}], 'usage': {}})" failed transcript:api-error:unknown
status_case api-error-flag-only "add(type='assistant', isApiErrorMessage=True, error='server_error', message={'id': 'msg_E', 'model': 'claude-opus-5-5', 'role': 'assistant', 'content': [{'type': 'text', 'text': 'x'}]})" failed transcript:api-error:server_error
status_case synthetic "add(type='assistant', message={'id': 'msg_E', 'model': '<synthetic>', 'role': 'assistant', 'content': [{'type': 'text', 'text': 'x'}], 'usage': {}})" cancelled transcript:synthetic
status_case tool-use-unanswered "last_api()['message']['content'] = [{'type': 'tool_use', 'id': 'toolu_y', 'name': 'Bash', 'input': {}}]; last_api()['message']['stop_reason'] = 'tool_use'" cancelled transcript:tool-use-unanswered
status_case after-tool-result "add(type='user', message={'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'toolu_z', 'content': 'x'}]})" cancelled transcript:after-tool-result
status_case interrupted "add(type='user', message={'role': 'user', 'content': [{'type': 'text', 'text': '[Request interrupted by user]'}]})" cancelled transcript:interrupted
status_case message-incomplete "last_api()['message']['stop_reason'] = None" cancelled transcript:message-incomplete
T="$(variant broker "[r['message'].update(model='anthropic/claude-opus-5') for r in recs if r['type'] == 'assistant' and r['message']['model'] != '<synthetic>']")"
rm -f "$LEDGER"; fire "$T" >/dev/null; row="$(cat "$LEDGER" 2>/dev/null)"
field provider '"openrouter"' "a broker vendor/model id"
T="$(variant noreason "[r['message']['usage'].pop('output_tokens_details', None) for r in recs if r['type'] == 'assistant']")"
rm -f "$LEDGER"; fire "$T" >/dev/null; row="$(cat "$LEDGER" 2>/dev/null)"
field reasoning null "no message reports thinking tokens"

echo "subagent ledger: a run with no API answer still writes its row"
T="$(variant firstcallfails "del recs[1:]; add(type='assistant', isApiErrorMessage=True, error='rate_limit', message={'id': 'msg_E', 'model': '<synthetic>', 'role': 'assistant', 'content': [{'type': 'text', 'text': 'limit'}], 'usage': {}})")"
rm -f "$LEDGER"; out="$(fire "$T" '{"level":"high"}')"; row="$(cat "$LEDGER" 2>/dev/null)"
if [[ "$out" == "rc=0" ]] && printf '%s' "$row" | jq -e '.status == "failed" and .status_source == "transcript:api-error:rate_limit" and .turns == 0 and .output == 0 and .model == null and .provider == null and .effort == "high"' >/dev/null 2>&1; then pass "first call refused: failed, turns 0"; else fail "first call refused: failed, turns 0" "$out $row"; fi
T="$(variant briefonly "del recs[1:]")"
rm -f "$LEDGER"; fire "$T" >/dev/null; row="$(cat "$LEDGER" 2>/dev/null)"
if printf '%s' "$row" | jq -e '.status == "cancelled" and .status_source == "transcript:message-incomplete" and .turns == 0' >/dev/null 2>&1; then pass "the brief alone: cancelled, turns 0"; else fail "the brief alone: cancelled, turns 0" "$row"; fi

echo "subagent ledger: what it cannot read about, it leaves null"
rm -f "$LEDGER"
T2="$SANDBOX/other/agent-anometa.jsonl"; mkdir -p "$SANDBOX/other"
sed "s|@CWD@|$SANDBOX/not-a-repo|g" "$FIXTURE/agent-afixture.jsonl" > "$T2"
out="$(fire "$T2")"
row="$(cat "$LEDGER" 2>/dev/null)"
if [[ "$out" == "rc=0" ]] && printf '%s' "$row" | jq -e '.description == null and .tool_use_id == null and .pr == null and .repository == null and .head_sha == null and .agent_type == "code-review" and .turns == 3' >/dev/null 2>&1; then
  pass "no .meta.json, no repository: the counts still, the rest null"
else fail "no .meta.json, no repository" "$out $row"; fi

echo "subagent ledger: a credential in the remote URL never reaches the row"
for url in https://user:s3cret@git.example.com/repo.git https://s3cret@host/repo https://x:s3cret@github.com/BlueTeam-OU/agent-fabric.git; do
  rm -f "$LEDGER"
  git -C "$REPO" remote set-url origin "$url"
  fire "$TR" >/dev/null
  got="$(jq -r .repository "$LEDGER" 2>/dev/null)"
  if [[ -n "$got" && "$got" != *s3cret* && "$got" != *@* ]]; then pass "$url -> $got"; else fail "$url: no credential" "$got"; fi
done
git -C "$REPO" remote set-url origin git@github.com:BlueTeam-OU/agent-fabric.git

echo "subagent ledger: no row, no output, exit 0 on what it cannot read"
rm -f "$LEDGER"
grep '"type":"attachment"' "$TR" > "$SANDBOX/subagents/agent-aempty.jsonl"
for case in missing-transcript no-conversation no-path malformed-stdin not-an-object; do
  case "$case" in
    no-conversation) out="$(fire "$SANDBOX/subagents/agent-aempty.jsonl")" ;;
    missing-transcript) out="$(fire "$SANDBOX/nope.jsonl")" ;;
    no-path) out="$(printf '%s' '{"hook_event_name":"SubagentStop","agent_id":"a"}' | python3 "$UNDER_TEST"; echo "rc=$?")" ;;
    malformed-stdin) out="$(printf 'not json' | python3 "$UNDER_TEST"; echo "rc=$?")" ;;
    not-an-object) out="$(printf '[1]' | python3 "$UNDER_TEST"; echo "rc=$?")" ;;
  esac
  if [[ "$out" == "rc=0" && ! -e "$LEDGER" ]]; then pass "$case: nothing written, exit 0"; else fail "$case: nothing written, exit 0" "$out"; fi
done

echo
if (( failures )); then echo "subagent ledger: $failures failure(s)" >&2; exit 1; fi
echo "subagent ledger: all passed"
