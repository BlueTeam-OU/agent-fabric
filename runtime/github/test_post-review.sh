#!/usr/bin/env bash
# runtime/github/test_post-review.sh (lifted from the first managed project's tools/gh/ on 2026-09-19 — the commit names it; general to every managed project, whose own tools/gh/ copy is a forwarder through projects/<id>/integration/gh/)
#
# Behavioural tests for post-review.sh.
#
# What this exists to hold still: the MARKER. The review class's review
# is authored by the same GitHub account as every other session's work,
# so nothing but an exact marker distinguishes it from a thread reply —
# and pr-review-status.sh greps for that exact string. A marker that
# drifts on one side turns real review coverage back into "0 reviews",
# silently, which is the failure this whole mechanism was built to end.
#
# Driven through the real script with a mocked `gh` on PATH.
#
# Exit codes:
#   0  all assertions passed
#   1  one or more assertions failed

set -uo pipefail

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/post-review.sh"
# Both ends of the marker contract are Python modules now; the scripts
# above are their shims, run as the paths every caller uses.
EMITTER="$SCRIPT_DIR/../../tools/fabric/github/post_review.py"
READER="$SCRIPT_DIR/../../tools/fabric/github/pr_review_status.py"
marker_of() { grep -m1 "^REVIEW_MARKER = " "$1" | cut -d= -f2- | sed 's/^ //' | tr -d "'\""; }

[[ -f "$UNDER_TEST" ]] || { echo "test: not found: $UNDER_TEST" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "test: jq required" >&2; exit 1; }

failures=0
SANDBOX=""
cleanup() { [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"; }
trap cleanup EXIT

pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1" >&2; printf '%s\n' "${2:-}" | sed 's/^/      /' >&2; failures=$((failures+1)); }

# Same marker-file guard as the sibling suites: bash runs
# command_not_found_handle in a SUBSHELL, so a counter incremented there
# is discarded and the suite reports success with the case vacuous.
GUARD_MARKER="$(mktemp)"
command_not_found_handle() {
    printf '%s\n' "$1" >> "$GUARD_MARKER"
    echo "  ✗ self-test bug: called '$1', which is not defined here" >&2
    return 127
}

assert_rc()       { [[ "$RUN_RC" -eq "$2" ]] && pass "$1" || fail "$1 — wanted $2, got $RUN_RC" "$RUN_OUT"; }
assert_contains() { [[ "$RUN_OUT" == *"$2"* ]] && pass "$1" || fail "$1 — lacked '$2'" "$RUN_OUT"; }
assert_lacks()    { [[ "$RUN_OUT" != *"$2"* ]] && pass "$1" || fail "$1 — unexpectedly had '$2'" "$RUN_OUT"; }

CLONE_NAME="gzapp-testclone"
HOST="$(hostname -s)"
# The session is the agent (login), not the clone directory; the clone's
# name is still accepted as this session for older branches.
ME="$HOST/$(id -un)"
ME_LEGACY="$HOST/$CLONE_NAME"
OTHER="$HOST/gzapp-otherclone"

setup_sandbox() {
    SANDBOX="$(mktemp -d)"
    mkdir -p "$SANDBOX/$CLONE_NAME" "$SANDBOX/bin" "$SANDBOX/state"
    git -C "$SANDBOX/$CLONE_NAME" init -q 2>/dev/null
    cat > "$SANDBOX/bin/gh" <<'MOCK'
#!/usr/bin/env bash
S="$GH_STATE"
case "$1" in
  repo) echo "gzapi-org/gzapp"; exit 0 ;;
  pr)   cat "$S/pr.json"; exit 0 ;;
  api)
    # The PR's files, as REST pages (--paginate --slurp): each a filename
    # and, for a rename, its previous_filename.
    if [ "$2" = "--paginate" ]; then
      [ -f "$S/files.json" ] && { cat "$S/files.json"; exit 0; }
      # As real gh does under --slurp: the error BODY on stdout, wrapped,
      # and a failing status (review of #70: stderr alone hid the case).
      echo '[{"message":"Not Found","documentation_url":"https://docs.github.com","status":"404"}]'
      echo "gh: Not Found (HTTP 404)" >&2; exit 1
    fi
    # Record the request body so a case can assert on what was SENT,
    # not on what the script said it would send.
    for a in "$@"; do
      [ "$prev" = "--input" ] && cp "$a" "$S/payload.json"
      prev="$a"
    done
    echo "POST $2" >> "$S/calls"
    [ -f "$S/api_fail" ] && { echo "gh: Validation Failed (HTTP 422)" >&2; exit 1; }
    [ -f "$S/api_empty" ] && { echo ""; exit 0; }
    echo "https://github.com/gzapi-org/gzapp/pull/1#pullrequestreview-1"
    exit 0 ;;
esac
echo "mock gh: unhandled $1" >&2; exit 1
MOCK
    chmod +x "$SANDBOX/bin/gh"
}

set_pr() {  # $1 = branch, $2.. = the files it changes, "old=>new" for a rename (none: the list cannot be read)
    local b="$1"; shift
    jq -n --arg b "$b" '{number:552,state:"OPEN",headRefName:$b,headRefOid:"abcdef1234567890"}' \
      > "$SANDBOX/state/pr.json"
    rm -f "$SANDBOX/state/files.json"
    if [[ $# -gt 0 ]]; then
      jq -n '[$ARGS.positional | map(if test("=>") then (split("=>") | {previous_filename: .[0], filename: .[1]})
                                     else {filename: .} end)]' --args "$@" > "$SANDBOX/state/files.json"
    fi
    : > "$SANDBOX/state/calls"; rm -f "$SANDBOX/state/payload.json"
}
invoke() {
    local body="$1"; shift
    RUN_OUT="$(cd "$SANDBOX/$CLONE_NAME" && printf '%s' "$body" | \
        env -u AGENT_FABRIC_LAUNCH_ROLE ${AGENT_FABRIC_LAUNCH_ROLE_CASE:+AGENT_FABRIC_LAUNCH_ROLE=$AGENT_FABRIC_LAUNCH_ROLE_CASE} PATH="$SANDBOX/bin:$PATH" GH_STATE="$SANDBOX/state" AGENT_FABRIC_ROOT="${FAKE_FABRIC:-$SANDBOX/no-fabric}" \
        timeout 20 bash "$UNDER_TEST" "$@" 2>&1)"
    RUN_RC=$?
}
posted()  { grep -q POST "$SANDBOX/state/calls" 2>/dev/null; }
body_of() { jq -r '.body' "$SANDBOX/state/payload.json" 2>/dev/null; }

setup_sandbox

echo "post-review: the marker is the first line of what is SENT"
# Asserted against the request payload, not the script's own output: the
# reader greps the stored body, so that is the only thing that matters.
set_pr "$ME/feat/thing"
invoke "A P1 in the ownership guard." 552
assert_rc "exits 0" 0
if posted; then pass "a review was posted"; else fail "nothing posted" "$(cat "$SANDBOX/state/calls")"; fi
if [[ "$(body_of | head -1)" == '<!-- agent-fabric-review v1 -->' ]]; then
    pass "the marker is line 1 of the body"
else
    fail "marker missing or not first" "got: $(body_of | head -1)"
fi
if [[ "$(body_of)" == *"A P1 in the ownership guard."* ]]; then
    pass "the caller's body survives verbatim"
else fail "body was mangled" "$(body_of)"; fi

# THE HEADLINE PROMISE, with a body that would actually catch a
# regression to `-f body="…"`. The plain-ASCII fixture above cannot: a
# review body quotes code by definition, and the shell would expand
# backticks and $vars before gh ever saw them — which has already posted
# a mangled comment in this repo.
NASTY='backtick `id` dollar $HOME quote " apostrophe '"'"' unicode ünïcode $(echo pwned)'
set_pr "$ME/feat/thing"
invoke "$NASTY" 552
if [[ "$(body_of)" == *"$NASTY"* ]]; then
    pass "a body full of shell metacharacters survives byte-for-byte"
else
    fail "the body was expanded or mangled" "sent: $(body_of)"
fi

echo "post-review: it is posted as a REVIEW, at the head commit"
if [[ "$(jq -r '.event' "$SANDBOX/state/payload.json")" == "COMMENT" ]]; then
    pass "event=COMMENT (a review object, not an issue comment)"
else fail "wrong event" "$(cat "$SANDBOX/state/payload.json")"; fi
if [[ "$(jq -r '.commit_id' "$SANDBOX/state/payload.json")" == "abcdef1234567890" ]]; then
    pass "pinned to the head commit"
else fail "wrong commit_id" "$(cat "$SANDBOX/state/payload.json")"; fi
if grep -q 'POST repos/gzapi-org/gzapp/pulls/552/reviews' "$SANDBOX/state/calls"; then
    pass "posted to the reviews endpoint"
else fail "wrong endpoint" "$(cat "$SANDBOX/state/calls")"; fi

echo "post-review: it says what it is — the review class's blind review, nothing less"
assert_contains "output says the reader counts it as THE review" "counts it as the review of this head"
# The needle must not span the body's line wrap.
if [[ "$(body_of)" == *"**Blind review**"* ]]; then
    pass "the body names the method"
else fail "the body does not say what it is" "$(body_of)"; fi
for word in substitute fallback "not a real review" "not an equivalent"; do
    if [[ "$(body_of)" == *"$word"* ]]; then
        fail "the body still calls the review '$word'" "$(body_of)"
    else pass "the body never says '$word'"; fi
done

echo "post-review: --model is recorded when given, absent when not"
set_pr "$ME/feat/thing"; invoke "findings" 552 --model opus
[[ "$(body_of)" == *"<!-- model: opus -->"* ]] && pass "records the model" \
    || fail "model not recorded" "$(body_of)"
set_pr "$ME/feat/thing"; invoke "findings" 552
[[ "$(body_of)" != *"<!-- model:"* ]] && pass "no model line when unset" \
    || fail "invented a model line" "$(body_of)"

echo "post-review: an older branch named for this clone is still this session's"
set_pr "$ME_LEGACY/feat/thing"; invoke "findings" 552
assert_rc "exits 0" 0
posted && pass "posted on the legacy-prefixed branch" || fail "did not post on the legacy prefix"

echo "post-review: another session's PR is refused"
set_pr "$OTHER/fix/theirs"
invoke "I should not be able to post this." 552
assert_rc       "exits 2" 2
assert_contains "names the owning session" "$OTHER"
if ! posted; then pass "nothing was sent"; else fail "posted to another session's PR" "$(cat "$SANDBOX/state/calls")"; fi

echo "post-review: the locale carve-out's merger may post on another session's locale-only PR"
# A fabric whose identity.py answers the role the case plants: the merger
# of a locale PR is fabric-coordinator (agent-fabric CLAUDE.md, carve-out).
FAKE_FABRIC="$SANDBOX/fake-fabric"; mkdir -p "$FAKE_FABRIC/runtime"
printf '%s\n' 'import os, sys' 'print(os.environ.get("FAKE_ROLE", "") if "--role" in sys.argv else "someone")' \
  > "$FAKE_FABRIC/runtime/identity.py"
LOC="identities/roles/language-culture/locale/ge/team.md"
FAKE_ROLE=fabric-coordinator; export FAKE_ROLE FAKE_FABRIC
AGENT_FABRIC_LAUNCH_ROLE_CASE=fabric-coordinator   # launched as the merger, as well as bound
set_pr "$OTHER/i18n/ge-team" "$LOC"; invoke "findings" 552
assert_rc "the merger posts on a locale-only PR" 0
posted && pass "…it was sent" || fail "the merger's review was not sent"
MARKER="$(marker_of "$EMITTER")"
[[ -n "$MARKER" && "$(body_of | head -1)" == "$MARKER" ]] && pass "…the marker is still its first line" || fail "the marker moved" "want '$MARKER'; $(body_of | head -3)"
[[ "$(body_of)" == *"posted by the locale carve-out's merger"* ]] && pass "…and it says it was posted by the carve-out's merger" || fail "no carve-out note" "$(body_of | head -3)"
set_pr "$OTHER/i18n/ge-team" "$LOC" "tools/fabric/lint.py"; invoke "no" 552
[[ "$RUN_RC" -eq 2 ]] && ! posted && pass "one file outside a locale refuses" || fail "posted on a PR touching code" "rc=$RUN_RC"
set_pr "$OTHER/i18n/ge-team" "identities/roles/language-culture/locale/ge/sub/x.md"; invoke "no" 552
[[ "$RUN_RC" -eq 2 ]] && ! posted && pass "a path nested below a locale directory refuses" || fail "posted on a nested path" "rc=$RUN_RC"
set_pr "$OTHER/i18n/ge-team"; invoke "no" 552
[[ "$RUN_RC" -eq 2 ]] && ! posted && pass "an unreadable file list refuses" || fail "posted with no file list" "rc=$RUN_RC"
many=(); for i in $(seq 1 100); do many+=("identities/roles/language-culture/locale/ge/f$i.md"); done
set_pr "$OTHER/i18n/ge-team" "${many[@]}"; invoke "no" 552
[[ "$RUN_RC" -eq 0 ]] && posted && pass "a locale PR of 100 files posts" || fail "refused a large locale PR" "rc=$RUN_RC"
many=(); for i in $(seq 1 3000); do many+=("identities/roles/language-culture/locale/ge/f$i.md"); done
set_pr "$OTHER/i18n/ge-team" "${many[@]}"; invoke "no" 552
[[ "$RUN_RC" -eq 2 ]] && ! posted && pass "3000 files, GitHub's list cap: it may be cut, so it refuses" || fail "posted on a list that may be cut" "rc=$RUN_RC"
set_pr "$OTHER/i18n/ge-team" "$LOC"; echo '[["not an object"]]' > "$SANDBOX/state/files.json"; invoke "no" 552
[[ "$RUN_RC" -eq 2 ]] && ! posted && pass "pages whose items are not files refuse, never read as 0 outside" || fail "posted on a malformed list" "rc=$RUN_RC"
set_pr "$OTHER/i18n/ge-team" "tools/fabric/lint.py=>$LOC"; invoke "no" 552
[[ "$RUN_RC" -eq 2 ]] && ! posted && pass "a code file renamed INTO a locale directory refuses: its old path counts" || fail "posted on a rename into locale/" "rc=$RUN_RC"
AGENT_FABRIC_LAUNCH_ROLE_CASE=devex-tooling
set_pr "$OTHER/i18n/ge-team" "$LOC"; invoke "no" 552
unset AGENT_FABRIC_LAUNCH_ROLE_CASE
[[ "$RUN_RC" -eq 2 ]] && ! posted && pass "bound fabric-coordinator but launched as another role: refused" || fail "posted with a drifted role" "rc=$RUN_RC"
set_pr "$OTHER/i18n/ge-team" "$LOC"; invoke "no" 552
[[ "$RUN_RC" -eq 2 ]] && ! posted && pass "bound fabric-coordinator, not started by the launcher (no stamp): refused" || fail "posted without a launch stamp" "rc=$RUN_RC"
AGENT_FABRIC_LAUNCH_ROLE_CASE=fabric-coordinator
FAKE_ROLE=devex-tooling
set_pr "$OTHER/i18n/ge-team" "$LOC"; invoke "no" 552
[[ "$RUN_RC" -eq 2 ]] && ! posted && pass "another role refuses, even on a locale-only PR" || fail "a non-coordinator posted" "rc=$RUN_RC"
unset FAKE_ROLE FAKE_FABRIC AGENT_FABRIC_LAUNCH_ROLE_CASE

echo "post-review: a branch naming no session is allowed, with a warning"
for b in "agent/global-event-identity" "dependabot/pub/apps/x/y" "add-claude-github-actions-178"; do
    set_pr "$b"
    invoke "findings" 552
    if [[ "$RUN_RC" -eq 0 ]] && posted; then pass "posts on '$b'"
    else fail "refused an unowned branch '$b'" "rc=$RUN_RC"; fi
done
assert_contains "says the branch names no session" "names no session"

echo "post-review: an unusual <type> is still another session's"
# The same P1 that the sibling script had: a shape test on <type> would
# make a real session's branch writable. This predicate must agree.
for t in "Fix" "chore(gh)" "WIP" "2fix"; do
    set_pr "$OTHER/$t/x"
    invoke "no" 552
    if [[ "$RUN_RC" -eq 2 ]] && ! posted; then pass "refuses '$t/'"
    else fail "POSTED to another session's '$t/' branch" "rc=$RUN_RC"; fi
done

echo "post-review: unreadable PR metadata REFUSES, it does not post"
# `jq -r .headRefName` on an empty or field-less payload yields "" or the
# literal "null" — either splits into fewer than four segments, so the
# guard read "names no session" and took the POSTING path. The header
# promises the opposite ("not knowing whose PR this is has to mean stop").
for payload in '{}' ''; do
    printf '%s' "$payload" > "$SANDBOX/state/pr.json"
    : > "$SANDBOX/state/calls"; rm -f "$SANDBOX/state/payload.json"
    invoke "findings" 552
    if [[ "$RUN_RC" -eq 2 ]] && ! posted; then
        pass "refuses a PR payload of '${payload:-<empty>}'"
    else
        fail "POSTED with unknown ownership ('${payload:-<empty>}')" "rc=$RUN_RC"
    fi
done

echo "post-review: --dry-run sends nothing"
set_pr "$ME/feat/thing"
invoke "findings" 552 --dry-run
assert_rc       "exits 0" 0
assert_contains "shows the marker"  "agent-fabric-review v1"
if ! posted; then pass "no request was sent"; else fail "dry run posted" "$(cat "$SANDBOX/state/calls")"; fi

echo "post-review: invocation errors are refused, not guessed at"
set_pr "$ME/feat/thing"
invoke "" 552;            assert_rc "an empty body is refused" 2
invoke "x" ;              assert_rc "a missing PR number is refused" 2
invoke "x" notanumber;    assert_rc "a non-numeric PR is refused" 2
invoke "x" 552 --model;   assert_rc "--model without a value is refused" 2
invoke "x" 552 --bogus;   assert_rc "an unknown option is refused" 2

echo "post-review: a rejected post is reported, never assumed"
set_pr "$ME/feat/thing"; touch "$SANDBOX/state/api_fail"
invoke "findings" 552
assert_rc       "exits 2" 2
assert_contains "says GitHub rejected it" "rejected"
assert_contains "  with GitHub's own reason" "Validation Failed (HTTP 422)"
assert_contains "  and says to look before re-running, never to post by hand" "never post it by hand"
rm -f "$SANDBOX/state/api_fail"

set_pr "$ME/feat/thing"; touch "$SANDBOX/state/api_empty"
invoke "findings" 552
assert_rc       "an empty URL is treated as NOT posted" 2
assert_contains "  and says so"                         "NOT posted"
rm -f "$SANDBOX/state/api_empty"

echo "post-review: the marker matches the READER's, byte for byte"
# THE CROSS-FILE CONTRACT. Two constants in two scripts; a one-sided
# edit turns real coverage back into "0 reviews" with nothing failing.
emit="$(marker_of "$EMITTER")"
read_="$(marker_of "$READER")"
if [[ -n "$emit" && "$emit" == "$read_" ]]; then
    pass "emitter and pr-review-status.sh agree on the marker"
else
    fail "MARKER DRIFT — the review would stop counting" \
         "emitter: $emit
reader : $read_"
fi

echo
if [[ -s "$GUARD_MARKER" ]]; then
    echo "SELF-TEST BUG — undefined helper(s): $(sort -u "$GUARD_MARKER" | tr '\n' ' ')" >&2
    rm -f "$GUARD_MARKER"; exit 1
fi
rm -f "$GUARD_MARKER"
if [[ "$failures" -eq 0 ]]; then
    echo "test_post-review: OK — all assertions passed."
    exit 0
fi
echo "test_post-review: FAILED — $failures assertion(s) failed." >&2
exit 1
