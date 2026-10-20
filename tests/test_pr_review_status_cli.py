#!/usr/bin/env python3
"""fabric-pr review-status, driven through the real script with
a mocked `gh`. Ported from runtime/github/test_pr-review-status.sh
(ADR-040 Wave 6).

This suite covers what only a process has: the exit status, which stream a
line goes to, the output mode (text, --json), a usage refusal, a gh failure
surfaced to the caller, a wait that really sleeps. One case per outcome. WHY a
run ends in 0, 1, 5 or 2 (what counts as a review, the head's birth, a decline
against a request, the wait loop) is verdict logic, and it is asserted
in-process at 0.1 s a suite in tests/test_pr_review_status.py: a reason that
ends in the same exit status on the same stream is not an outcome.

The script exists because two GitHub behaviours make the obvious reading
wrong — a self-reply registers as a REVIEW, and a comment's commit_id is
re-anchored to the current head. Both produce the SAME dangerous answer:
"this was reviewed" when it was not. A reviewed-then-pushed PR with nothing
requested is the permanent "no review is coming" state, and must exit 5
without sleeping out a --wait.

The mock serves one scripted poll per `gh pr view` call, so a case can
say "unreviewed, unreviewed, reviewed" and assert where the loop stopped.
It is fixture, not code under test, and serves only what the cases here
reach: the PR, its reviews, no comments, no threads, one passing check.
  state/polls    one line per `gh pr view`: <state>:<headRefOid>:<requests>
  state/reviews  served on every call: <login>,<commit_id>,<submitted_at>
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import tempfile
from git_env import scrub_process_env  # noqa: E402 — tests/, the script's own directory
scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNDER_TEST = [os.path.join(ROOT, "bin", "fabric-pr"), "review-status"]
MODULE = os.path.join(ROOT, "tools", "fabric", "github", "pr_review_status.py")

GH_MOCK = r'''
#!/usr/bin/env bash
S="$GH_MOCK_STATE"

# The Python port (tools/fabric/gh.py) sends GraphQL as a JSON request on
# stdin (`--input -`) and asks REST unfiltered, with `--paginate --slurp`
# answering a LIST OF PAGES. Each is answered in the shape the real gh gives.
case "$1 ${2:-}" in
  "pr view")
    n=$(cat "$S/n" 2>/dev/null || echo 0)
    line=$(sed -n "$((n+1))p" "$S/polls")
    [[ -z "$line" ]] && line=$(tail -1 "$S/polls")
    echo $((n+1)) > "$S/n"
    IFS=: read -r st head req <<<"$line"
    [[ "$st" == "FAIL" ]] && exit 1
    printf '{"state":"%s","mergeStateStatus":"CLEAN","headRefOid":"%s","headRefName":"mine/branch","author":{"login":"me"},"isDraft":false,"reviewRequests":%s}\n' \
      "$st" "$head" "$(jq -nc --argjson n "$req" '[range($n) | {__typename:"User", login:"reviewer[bot]"}]')"
    exit 0 ;;
  "pr checks")
    echo "some / Check	pass	1s"; exit 0 ;;
  "api graphql")
    cat > /dev/null
    echo '{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[]}}}}}'; exit 0 ;;
esac

# Matched across ALL arguments, not positionally: --paginate shifts the URL
# out of $2 and made a positional match fall through to the catch-all
# `exit 0` — an empty body that reads as zero reviews, i.e. the suite would
# have gone green on a script that fetched nothing at all.
# A list the poll reads conditionally (`api -i <path>?per_page=100`) is answered as gh prints it with -i:
# the status line and headers, a blank line, then the page itself (one list, not a list of pages).
if [[ "$1" == "api" && "$2" == "-i" ]]; then
  printf 'HTTP/2.0 200 OK\r\nEtag: W/"mock"\r\n\r\n'
  OPEN='['; CLOSE=']'
else
  OPEN='[['; CLOSE=']]'
fi
if [[ "$1" == "api" && "$*" == *"/reviews"* ]]; then
  printf '%s' "$OPEN"
  first=1
  # The author is OWNER; any other account a MEMBER, a trusted reviewer.
  while IFS=, read -r login commit at; do
    [[ -z "$login" ]] && continue
    (( first )) || printf ','
    first=0
    [[ "$login" == me ]] && assoc=OWNER || assoc=MEMBER
    printf '{"user":{"login":"%s"},"author_association":"%s","state":"COMMENTED","commit_id":"%s","submitted_at":"%s","body":""}' \
      "$login" "$assoc" "$commit" "$at"
  done < "$S/reviews"
  printf '%s\n' "$CLOSE"
  exit 0
fi

if [[ "$1" == "api" && "$*" == *"/comments"* ]]; then
  echo "$OPEN$CLOSE"; exit 0
fi
exit 0
'''


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as sandbox:
        state = f"{sandbox}/state"
        os.makedirs(state)
        os.makedirs(f"{sandbox}/bin")
        with open(f"{sandbox}/bin/gh", "w", encoding="utf-8") as fh:
            fh.write(GH_MOCK.lstrip("\n"))
        os.chmod(f"{sandbox}/bin/gh", 0o755)
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
        base.update(PATH=f"{sandbox}/bin:{base.get('PATH', '')}", GH_MOCK_STATE=state,
                    AGENT_FABRIC_STATE_DIR=f"{sandbox}/agent-state")   # the ledger and the ETag cache stay here

        def put(name: str, text: str) -> None:
            with open(f"{state}/{name}", "w", encoding="utf-8") as fh:
                fh.write(text)

        def run(polls: str, reviews: str, *args: str) -> tuple[int, str, str]:
            """One run against scripted polls and reviews, every fixture
            written afresh so nothing leaks into the next case. The script
            ships with no automated reviewer configured (the review class is
            the review). stdout and stderr are kept apart: under -q stderr
            is a contract."""
            put("n", "")
            # A trailing newline on every write: `read` drops a final line
            # without one, which once turned three reviews into two.
            put("polls", polls + "\n")
            put("reviews", reviews + "\n")
            r = subprocess.run(["timeout", "20", *UNDER_TEST, "77", "o/r", *args], env=base,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
            out = r.stdout + r.stderr
            if r.returncode == 124:
                out = "TIMED OUT — the run did not return\n" + out
            return r.returncode, out, r.stderr

        def bare(*args: str) -> int:
            return subprocess.run([*UNDER_TEST, *args], env=base, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, timeout=60).returncode

        def one_json(text: str):
            """stdout as exactly one JSON value, or None."""
            try:
                return json.loads(text)
            except ValueError:
                return None

        reviewed = "bot,abc123,2026-08-07T10:00:00Z"
        stale = "bot,oldhead,2026-08-07T10:00:00Z"

        print("fabric-pr review-status — the report, on stdout")
        rc, out, _ = run("OPEN:abc123:0", reviewed)
        check("independent review AT the head exits 0", rc == 0, out)
        check("  and says so, naming the review",
              "yes — an independent review (bot, abc123, 2026-08-07T10:00:00Z)" in out, out)
        rc, out, _ = run("OPEN:abc123:0", "")
        check("no reviews at all exits 1", rc == 1, out)
        rc, out, _ = run("OPEN:newhead:0", stale)
        check("reviewed then pushed, nothing requested, exits 5", rc == 5, out)
        check("  names the cause", "NO REVIEW COMING" in out, out)
        # A background watcher runs for half an hour, so anything
        # unconditional on stderr is emitted on every poll.
        rc, out, err = run("OPEN:newhead:0", stale, "-q")
        check("-q writes NOTHING to stderr", rc == 5 and err == "", err)

        print("fabric-pr review-status — --json: one object on stdout, the same exit")
        rc, out, _ = run("OPEN:abc123:0", reviewed, "--json")
        d = one_json(out)
        check("--json keeps the exit code, stdout is one object",
              rc == 0 and isinstance(d, dict) and d.get("head_reviewed") == "yes", out)
        rc, out, _ = run("OPEN:newhead:0", stale, "--json", "-q")
        d = one_json(out)
        check("--json keeps exit 5, stdout is one object with the cause in no_review_coming",
              rc == 5 and isinstance(d, dict) and (d.get("no_review_coming") or {}).get("cause") == "head-moved", out)

        print("fabric-pr review-status — waiting")
        rc, out, _ = run("OPEN:abc123:1\nOPEN:abc123:1", "", "--wait", "2", "--interval", "1", "-q")
        check("wait expires with nothing and exits 1", rc == 1, out)

        print("fabric-pr review-status — invocation")
        check("unknown option exits 2", bare("77", "o/r", "--nope") == 2)
        r = subprocess.run([*UNDER_TEST, "--help"], env=base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=60)
        check("--help exits 0", r.returncode == 0, r.stdout)
        # Three consecutive unreadable polls is unreadable; fewer is a blip.
        rc, out, _ = run("FAIL\nFAIL\nFAIL", "")
        check("three failed lookups exit 2", rc == 2, out)

        print("fabric-pr review-status — no gh api call invents a flag gh does not have")
        # The mock cannot catch this, by construction: it was the mock that
        # was wrong once (`--argjson`, a jq option gh api lacks, failed every
        # real invocation while the suite stayed green). The implementation
        # is Python and calls no jq: every argument list goes to gh, so a
        # jq-only flag ANYWHERE in the module is one handed to gh.
        # The module and every part it is split into (tools/fabric/github/
        # review_status/): a scan of the facade alone would pass for code
        # that has moved out of it.
        sources = [MODULE, *sorted(glob.glob(os.path.join(os.path.dirname(MODULE), "review_status", "*.py")))]
        offenders = []
        for source in sources:
            with open(source, encoding="utf-8") as fh:
                offenders += re.findall(r"--(argjson|null-input|raw-input)", fh.read())
        offenders = sorted(set(offenders))
        check("gh api is never handed a jq-only flag", not offenders, f"gh api does not accept: {offenders}")

    print(f"\ntest_pr_review_status_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
