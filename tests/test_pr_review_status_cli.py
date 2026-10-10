#!/usr/bin/env python3
"""fabric-pr review-status, driven through the real script with
a mocked `gh`. Ported from runtime/github/test_pr-review-status.sh
(ADR-040 Wave 6), case for case.

The script exists because two GitHub behaviours make the obvious reading
wrong — a self-reply registers as a REVIEW, and a comment's commit_id is
re-anchored to the current head. Both produce the SAME dangerous answer:
"this was reviewed" when it was not. So the cases that matter most assert
a NON-zero exit on input that superficially looks reviewed. The waiting
half adds a second dangerous silence: a PR reviewed and then pushed to
will never be reviewed again unless asked, and a tool that waits out its
timeout there reports "not yet" for a state that is permanent. That must
exit 5, immediately, without sleeping.

The mock serves one scripted poll per `gh pr view` call, so a case can
say "unreviewed, unreviewed, reviewed" and assert where the loop stopped.
It is the bash suite's own, carried over: it answers both transports, and
it is fixture, not code under test.
  state/polls    one line per `gh pr view`: <state>:<headRefOid>:<requests>
  state/reviews  served on every call: <login>,<commit_id>,<submitted_at>
                 [,MARKED|BUILTIN|LEGACY|STRANGER|QUOTES[,<association>]]
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNDER_TEST = [os.path.join(ROOT, "bin", "fabric-pr"), "review-status"]
MODULE = os.path.join(ROOT, "tools", "fabric", "github", "pr_review_status.py")
UNSET = object()

GH_MOCK = r'''
#!/usr/bin/env bash
S="$GH_MOCK_STATE"

# TWO TRANSPORTS, because the script under test has two generations. The
# bash asked GraphQL with `-f query=...` and REST with `--jq`; the Python
# port (tools/fabric/gh.py) sends a JSON request on stdin (`--input -`) and
# reads GitHub's full response, and asks REST unfiltered, with `--paginate
# --slurp` answering a LIST OF PAGES. Both are answered here, each in the
# shape the real gh gives, so one oracle judges both implementations.
GQL=""
if [[ "$1 ${2:-}" == "api graphql" && "$*" == *"--input -"* ]]; then
  GQL="$(jq -r '.query' < /dev/stdin)"
fi
SLURP=0
[[ "$*" == *--slurp* ]] && SLURP=1

case "$1 ${2:-}" in
  "pr view")
    if [[ "$*" == *"nameWithOwner"* ]]; then
      echo '{"nameWithOwner":"o/r"}'; exit 0
    fi
    n=$(cat "$S/n" 2>/dev/null || echo 0)
    line=$(sed -n "$((n+1))p" "$S/polls")
    [[ -z "$line" ]] && line=$(tail -1 "$S/polls")
    echo $((n+1)) > "$S/n"
    IFS=: read -r st head req <<<"$line"
    [[ "$st" == "FAIL" ]] && exit 1
    # reviewRequests carry a login, because a decline answers only the
    # reviewer who made it. A bare count still works: `<state>:<head>:<n>`
    # fills n slots with the fixture's configured reviewer, `:<n>@login`
    # fills them with that account instead, and `:<n>@a+b` lists a and b
    # — one request each, n ignored — for the cases where WHO is still
    # pending is the whole question.
    who="${req##*@}"; n="${req%%@*}"
    [[ "$who" == "$req" ]] && who="reviewer[bot]"
    if [[ "$who" == *+* ]]; then
      printf '{"state":"%s","mergeStateStatus":"CLEAN","headRefOid":"%s","headRefName":%s,"author":{"login":"me"},"isDraft":false,"reviewRequests":%s}\n' \
        "$st" "$head" \
        "$(jq -n --arg b "$(cat "$S/headref" 2>/dev/null || echo mine/branch)" '$b')" \
        "$(jq -Rn --arg w "$who" '$w | split("+") | map({__typename:"User", login:.})')"
      exit 0
    fi
    # The ref is JSON-ESCAPED, not spliced bare: git permits a `"` in a
    # branch name, and a mock that emits invalid JSON for one would fail
    # the case for its own reason rather than the script's.
    printf '{"state":"%s","mergeStateStatus":"CLEAN","headRefOid":"%s","headRefName":%s,"author":{"login":"me"},"isDraft":false,"reviewRequests":%s}\n' \
      "$st" "$head" "$(jq -n --arg b "$(cat "$S/headref" 2>/dev/null || echo mine/branch)" '$b')" "$(python3 -c "
import json,sys
print(json.dumps([{'__typename':'User','login':sys.argv[1]}]*int(sys.argv[2])))" "$who" "$n")"
    exit 0 ;;
  "repo view")
    # `--jq .nameWithOwner` (the bash) answers the bare name; without it
    # (the port) the object. The real gh does both.
    if [[ "$*" == *--jq* ]]; then echo 'o/r'; else echo '{"nameWithOwner":"o/r"}'; fi
    exit 0 ;;
  "pr checks")
    # state/checks names gh's other answers, as measured on gh 2.87.3:
    # `none` is its "no checks reported" (exit 1, nothing on stdout),
    # `502` an HTTP error with no table.
    case "$(cat "$S/checks" 2>/dev/null)" in
      none) echo "no checks reported on the '$(cat "$S/headref")' branch" >&2; exit 1 ;;
      502) echo "HTTP 502: Bad Gateway (https://api.github.com/graphql)" >&2; exit 1 ;;
    esac
    echo "some / Check	pass	1s"; exit 0 ;;
  "api graphql")
    # REVIEW_REQUESTED_EVENT timestamps, so the refusal override has the
    # ordering the request COUNT cannot supply. state/formaldate empty
    # means the lookup found nothing.
    if [[ "$*$GQL" == *REVIEW_REQUESTED_EVENT* ]]; then
      # RAW JSON ONLY. This mock previously accepted `--argjson` and ran
      # the caller's filter itself — a flag `gh api` does not have. The
      # real command failed with "unknown flag" on every invocation while
      # the suite stayed green, because the mock implemented an interface
      # that does not exist. A mock may only serve what the real thing
      # serves; the caller's jq is the caller's business.
      #
      # state/formaldate holds "<date>" or "<date>,<login>" per line
      # (login defaults to the fixture's configured reviewer).
      raw="$(cat "$S/formaldate" 2>/dev/null || true)"
      printf '{"data":{"repository":{"pullRequest":{"timelineItems":{"nodes":['
      first=1
      while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        d="${line%%,*}"; who="${line#*,}"
        [[ "$who" == "$line" ]] && who="reviewer[bot]"
        (( first )) || printf ','
        first=0
        printf '{"createdAt":"%s","requestedReviewer":{"login":"%s"}}' "$d" "$who"
      done <<< "$raw"
      # Five objects opened above, five closed here.
      printf ']}}}}}\n'
      exit 0
    fi
    # The unresolved-threads lookup (already filtered: the script passes
    # --jq). state/threads_fail makes it FAIL, which must read as unknown.
    if [[ "$*$GQL" == *reviewThreads* ]]; then
      [[ -f "$S/threads_fail" ]] && exit 1
      if [[ -n "$GQL" ]]; then
        # Full response shape. The fixture holds the nodes; a blank one
        # (the default) is a lookup that found no pull request, which the
        # script must read as unknown, exactly as the filtered form's
        # blank line was read.
        if [[ -n "$(tr -d '[:space:]' < "$S/threads")" ]]; then
          printf '{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":%s}}}}}\n' "$(cat "$S/threads")"
        else
          echo '{"data":{"repository":{"pullRequest":null}}}'
        fi
        exit 0
      fi
      [[ -s "$S/threads" ]] && { cat "$S/threads"; exit 0; }
    fi
    echo '[]'; exit 0 ;;
esac

# gh api [--paginate] repos/o/r/pulls/N/reviews
#
# Matched across ALL arguments, not positionally: the script passes
# --paginate, which shifts the URL out of $2 and made a positional match
# fall through to the catch-all `exit 0` — an empty body that reads as
# zero reviews, i.e. the suite would have gone green on a script that
# fetched nothing at all.
if [[ "$1" == "api" && "$*" == *"/reviews"* ]]; then
  # A lookup that FAILS, for the fail-closed case. Distinct from a lookup
  # that succeeds with no reviews, which is an empty state/reviews file.
  [[ -f "$S/reviews_fail" ]] && exit 1
  # ...and one that fails only AFTER a given poll, so a case can script
  # "probe 1 read everything, probe 2 died halfway". The pr view call of
  # this same probe has already advanced state/n, so n IS the poll number.
  if [[ -f "$S/reviews_fail_after" ]]; then
    (( $(cat "$S/n" 2>/dev/null || echo 0) > $(cat "$S/reviews_fail_after") )) && exit 1
  fi
  {
    (( SLURP )) && printf '['
    printf '['
    first=1
    # A fifth field is the reviewer's author_association; an account
    # other than the author defaults to MEMBER (a trusted reviewer), the
    # author to OWNER.
    while IFS=, read -r login commit at kind assoc; do
      [[ -n "$assoc" ]] || { [[ "$login" == me ]] && assoc=OWNER || assoc=MEMBER; }
      [[ -z "$login" ]] && continue
      (( first )) || printf ','
      first=0
      # A 4th CSV field of MARKED gives the review the review class's
      # marker as its body. A SENTINEL rather than a literal body,
      # because the body is the thing under test and embedding it in a
      # comma-separated fixture would let a stray comma silently change
      # what the case asserts.
      body=""
      case "$kind" in
        MARKED) body='<!-- agent-fabric-review v1 -->\nfindings…' ;;
        # The fabric's own earlier marker, from when the review class was
        # called a substitute: built in, counts with nothing configured.
        BUILTIN) body='<!-- agent-fabric-substitute-review v1 -->\nfindings…' ;;
        # A project's earlier marker, named by its forwarder through
        # AGENT_FABRIC_LEGACY_REVIEW_MARKERS: counts. One nobody named: not.
        LEGACY) body='<!-- legacy-project-review v1 -->\nfindings…' ;;
        STRANGER) body='<!-- somebody-else-review v1 -->\nfindings…' ;;
        # The marker QUOTED mid-body, not leading it. A review discussing
        # the marker — reviewing this very mechanism does it — must not
        # be counted as a blind review.
        QUOTES) body='I think the marker <!-- agent-fabric-review v1 --> should move.' ;;
      esac
      printf '{"user":{"login":"%s"},"author_association":"%s","state":"COMMENTED","commit_id":"%s","submitted_at":"%s","body":"%s"}' \
        "$login" "$assoc" "$commit" "$at" "$body"
    done < "$S/reviews"
    printf ']\n'
    (( SLURP )) && printf ']\n'
  }
  exit 0
fi

# gh api repos/o/r/commits/<sha>  — when the head commit was pushed.
# gh api repos/o/r/commits/<sha>/check-suites — created BY the push, so
# its timestamp tracks the ref update rather than the commit metadata.
# state/suitedate empty means "no suite ran", which exercises the
# committer-date fallback.
if [[ "$1" == "api" && "$*" == *"/check-suites"* ]]; then
  # Serves the RAW envelope and lets the caller's --jq do the work, so
  # the PR-scoping filter is actually exercised. A mock that pre-answers
  # the question cannot test the query that asks it.
  #
  # Every suite carries a head_branch, because the real ones do and the
  # filter reads it. state/headref is this PR's ref.
  #
  # state/suitedate  — this PR's own suite: this ref, this PR.
  # state/foreignsuitedate — an OLDER suite for the same sha on another
  #   ref, belonging to another PR. Neither term matches.
  # state/claimsuitedate — a LATER suite for the same sha on another
  #   ref that nonetheless CLAIMS this PR number. How GitHub populates
  #   `pull_requests` is undocumented, so a sha-only match rule would
  #   produce exactly this; the ref term is what has to reject it.
  # state/unownedsuitedate — a LATER suite on THIS ref that belongs to
  #   no PR: something other than a push to the head raised it. The ref
  #   term cannot reject that one; the PR term is what has to.
  # state/latersuitedate — a LATER suite on THIS ref, owned by THIS pr,
  #   raised by something that never moved the ref: a manual
  #   workflow_dispatch, a schedule, a re-run, or a close/reopen. Both
  #   the ref and the PR term admit it, and its event name cannot tell
  #   it from a push (`reopened` reports as `pull_request`), so ORDER is
  #   what rejects it.
  ref="$(jq -n --arg b "$(cat "$S/headref" 2>/dev/null || echo mine/branch)" '$b')"
  sd="$(cat "$S/suitedate" 2>/dev/null || true)"
  fd="$(cat "$S/foreignsuitedate" 2>/dev/null || true)"
  cd_="$(cat "$S/claimsuitedate" 2>/dev/null || true)"
  ud="$(cat "$S/unownedsuitedate" 2>/dev/null || true)"
  ld="$(cat "$S/latersuitedate" 2>/dev/null || true)"
  {
    printf '{"check_suites":['
    first=1
    if [[ -n "$fd" ]]; then
      printf '{"id":1,"created_at":"%s","head_branch":"someone/else","pull_requests":[{"number":999}]}' "$fd"; first=0
    fi
    if [[ -n "$cd_" ]]; then
      (( first )) || printf ','
      printf '{"id":2,"created_at":"%s","head_branch":"someone/else","pull_requests":[{"number":77}]}' "$cd_"; first=0
    fi
    if [[ -n "$ud" ]]; then
      (( first )) || printf ','
      printf '{"id":3,"created_at":"%s","head_branch":%s,"pull_requests":[]}' "$ud" "$ref"; first=0
    fi
    if [[ -n "$sd" ]]; then
      (( first )) || printf ','
      printf '{"id":4,"created_at":"%s","head_branch":%s,"pull_requests":[{"number":77}]}' "$sd" "$ref"; first=0
    fi
    if [[ -n "$ld" ]]; then
      (( first )) || printf ','
      printf '{"id":5,"created_at":"%s","head_branch":%s,"pull_requests":[{"number":77}]}' "$ld" "$ref"; first=0
    fi
    # An EARLIER suite for this same pr on this same ref: the sha was
    # this pr's head before, was replaced, and came back.
    ed="$(cat "$S/earliersuitedate" 2>/dev/null || true)"
    if [[ -n "$ed" ]]; then
      (( first )) || printf ','
      printf '{"id":6,"created_at":"%s","head_branch":%s,"pull_requests":[{"number":77}]}' "$ed" "$ref"
    fi
    printf ']}\n'
  } > "$S/.suites.json"
  # `--paginate --slurp`: a list of PAGES, each the raw envelope. Page two
  # carries one suite of this ref and this pr, dated EARLIER than page
  # one's, so that reducing page one alone picks the wrong date.
  if (( SLURP )); then
    p2="$(cat "$S/page2suitedate" 2>/dev/null || true)"
    if [[ -n "$p2" ]]; then
      printf '[%s,{"check_suites":[{"id":7,"created_at":"%s","head_branch":%s,"pull_requests":[{"number":77}]}]}]\n' \
        "$(cat "$S/.suites.json")" "$p2" "$ref"
    else
      printf '[%s]\n' "$(cat "$S/.suites.json")"
    fi
    exit 0
  fi
  jqf=""
  prev=""
  for a in "$@"; do [[ "$prev" == "--jq" ]] && jqf="$a"; prev="$a"; done
  if [[ -n "$jqf" ]]; then jq -r "$jqf" "$S/.suites.json"; else cat "$S/.suites.json"; fi
  # A SECOND PAGE. `gh api --paginate` applies --jq to each page and
  # prints one result per page, so a paginated response reaches the
  # caller as several lines — this emits page two's candidate as its own
  # line, and dates it EARLIER than page one's so that taking page one
  # (or taking the last line) picks the wrong one.
  p2="$(cat "$S/page2suitedate" 2>/dev/null || true)"
  if [[ -n "$p2" && "$*" == *--paginate* ]]; then printf '%s\n' "$p2"; fi
  exit 0
fi

if [[ "$1" == "api" && "$*" == *"/commits/"* ]]; then
  # Honours --jq, because the caller passes one and reads the EXTRACTED
  # value. A mock that dumps the envelope regardless hands back a JSON
  # blob where a date was expected, and the comparison silently goes the
  # wrong way rather than failing.
  d="$(cat "$S/headdate" 2>/dev/null || echo 2026-08-10T00:00:00Z)"
  if [[ "$*" == *"--jq"* ]]; then printf '%s\n' "$d"
  else printf '{"commit":{"committer":{"date":"%s"}}}\n' "$d"; fi
  exit 0
fi

# gh api [--paginate] repos/o/r/issues/N/comments
#
# The verdict comments a project's CONFIGURED automated reviewer leaves
# instead of a review object when it finds nothing. state/verdicts holds
# <login>,<sha> per line; empty by default, so every case written before
# verdict comments existed keeps its exact meaning. The wording is the
# fixture's, matched by the regexes run() configures below — nothing in
# the script under test knows these phrases.
if [[ "$1" == "api" && "$*" == *"/comments"* ]]; then
  [[ -f "$S/verdicts_fail" ]] && exit 1
  {
    (( SLURP )) && printf '['
    printf '['
    first=1
    # <login>,<sha>[,<created_at>]. A sha of REFUSED serves the
    # reviewer's decline wording instead of a verdict.
    while IFS=, read -r login sha at; do
      [[ -z "$login" ]] && continue
      (( first )) || printf ','
      first=0
      [[ -z "$at" ]] && at="2026-08-25T10:00:00Z"
      if [[ "$sha" == "REQUEST" ]]; then
        printf '{"user":{"login":"%s"},"created_at":"%s","body":"@reviewer review\\n\\nplease look again"}' \
          "$login" "$at"
      elif [[ "$sha" == "REFUSED" ]]; then
        printf '{"user":{"login":"%s"},"created_at":"%s","body":"Usage limit reached for reviews; none will run."}' \
          "$login" "$at"
      elif [[ "$sha" == "REFUSED_DASH" ]]; then
        printf '{"user":{"login":"%s"},"created_at":"%s","body":"\\r\\nCannot review this PR — usage limit reached for reviews.\\r\\nTry later."}' \
          "$login" "$at"
      elif [[ "$sha" == "NOENV" ]]; then
        printf '{"user":{"login":"%s"},"created_at":"%s","body":"No environment for this repo; none will run."}' \
          "$login" "$at"
      else
        printf '{"user":{"login":"%s"},"created_at":"%s","body":"### Review\\n\\n**Reviewed commit:** `%s`\\n"}' \
          "$login" "$at" "$sha"
      fi
    done < "$S/verdicts" 2>/dev/null
    printf ']\n'
    (( SLURP )) && printf ']\n'
  }
  exit 0
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
        base.update(PATH=f"{sandbox}/bin:{base.get('PATH', '')}", GH_MOCK_STATE=state)

        def put(name: str, text: str) -> None:
            with open(f"{state}/{name}", "w", encoding="utf-8") as fh:
                fh.write(text)

        def polls_made() -> int:
            try:
                with open(f"{state}/n", encoding="utf-8") as fh:
                    return int(fh.read().strip() or 0)
            except (OSError, ValueError):
                return 0

        def run(polls: str, reviews: str, *args: str, verdicts: str = "", threads: str = "",
                threads_fail: bool = False, reviews_fail: bool = False, verdicts_fail: bool = False,
                reviews_fail_after: str = "", head_date: str = "", suite_date=UNSET, formal_date: str = "",
                head_ref: str = "", foreign: str = "", claiming: str = "", unowned: str = "", earlier: str = "",
                later: str = "", page2: str = "", checks: str = "", verdict_authors=UNSET, refusal_re=UNSET, request_re=UNSET,
                posters=UNSET, env: dict | None = None) -> tuple[int, str, str]:
            """One run against scripted polls and reviews, every fixture
            written afresh so nothing leaks into the next case. The fixture
            configures an automated reviewer; the script ships with none (the
            review class is the review), and an override set to "" reaches
            the script as empty, exercising its own default. stdout and
            stderr are kept apart: under -q stderr is a contract."""
            put("n", "")
            for f in ("reviews_fail", "reviews_fail_after", "verdicts_fail", "threads_fail"):
                if os.path.exists(f"{state}/{f}"):
                    os.remove(f"{state}/{f}")
            if threads_fail:
                put("threads_fail", "")
            # A trailing newline on every write: `read` drops a final line
            # without one, which once turned three reviews into two.
            put("threads", threads + "\n")
            put("checks", checks + "\n")
            if reviews_fail:
                put("reviews_fail", "")
            if verdicts_fail:
                put("verdicts_fail", "")
            if reviews_fail_after:
                put("reviews_fail_after", reviews_fail_after + "\n")
            put("polls", polls + "\n")
            put("reviews", reviews + "\n")
            put("verdicts", verdicts + "\n")
            hd = head_date or "2026-08-10T00:00:00Z"
            put("headdate", hd + "\n")
            put("suitedate", (hd if suite_date is UNSET else suite_date) + "\n")
            put("formaldate", formal_date + "\n")
            put("headref", (head_ref or "mine/branch") + "\n")
            for name, value in (("foreignsuitedate", foreign), ("claimsuitedate", claiming),
                                ("unownedsuitedate", unowned), ("earliersuitedate", earlier),
                                ("latersuitedate", later), ("page2suitedate", page2)):
                put(name, value + "\n")
            e = {**base, **(env or {}),
                 "AGENT_FABRIC_VERDICT_AUTHORS": '["reviewer[bot]"]' if verdict_authors is UNSET else verdict_authors,
                 "AGENT_FABRIC_REVIEWER_REFUSAL_RE": ("usage limit reached|no environment for this repo"
                                                      if refusal_re is UNSET else refusal_re),
                 "AGENT_FABRIC_REVIEW_REQUEST_RE": "@reviewer[[:space:]]+review" if request_re is UNSET else request_re,
                 "AGENT_FABRIC_REVIEW_POSTERS": "[]" if posters is UNSET else posters}
            r = subprocess.run(["timeout", "20", *UNDER_TEST, "77", "o/r", *args], env=e,
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

        print("fabric-pr review-status — the head-reviewed verdict")
        rc, out, _ = run("OPEN:abc123:0", "bot,abc123,2026-08-07T10:00:00Z")
        check("independent review AT the head exits 0", rc == 0, out)
        check("  and says so", "head reviewed?      : yes" in out, out)
        check("  naming the review", "yes — an independent review (bot, abc123, 2026-08-07T10:00:00Z)" in out, out)
        rc, out, _ = run("OPEN:abc123:0", "")
        check("no reviews at all exits 1", rc == 1, out)
        # The PR #363 case: three self-replies are REVIEW objects authored by
        # the PR author. They must not read as coverage.
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z\nme,abc123,2026-08-07T10:01:00Z\n"
                         "me,abc123,2026-08-07T10:02:00Z")
        check("self-authored reviews are NOT coverage", rc == 1, out)
        check("  counted as self", "self reviews        : 3" in out, out)
        check("  and not as independent", "independent reviews : 0" in out, out)
        # The review class's BLIND review is coverage, and authorship cannot
        # see it: every session pushes as the same account. The marker, an
        # exact string, is what separates it from a thread reply.
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,MARKED")
        check("a blind review at the head IS coverage", rc == 0, out)
        check("a marked review counts as a blind review", "blind reviews       : 1" in out, out)
        check("  and NOT as a self review", "self reviews        : 0" in out, out)
        check("  and says what it is", "the review class — coverage" in out, out)
        # The verdict line names its evidence: agents trim this report with
        # `tail`, and evidence above it was once cut off before a permission
        # check read the trimmed report as no review.
        check("  and the head line names it, trimmed or not",
              "head reviewed?      : yes — the review class's blind review of abc123, 2026-08-07T10:00:00Z" in out, out)
        # The marker the review class posted under before it was THE review
        # is built in.
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,BUILTIN")
        check("the fabric's earlier marker still counts, unconfigured", rc == 0, out)
        check("  as a blind review", "blind reviews       : 1" in out, out)
        # THE INVERSE RISK, and the worse one: a body merely QUOTING the
        # marker is not coverage.
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,QUOTES")
        check("a review that only QUOTES the marker is not coverage", rc == 1, out)
        check("  not counted as a blind review", "blind reviews       : 0" in out, out)
        check("  still counted as a self review", "self reviews        : 1" in out, out)
        # A LEGACY marker counts only when that project's forwarder names it.
        legacy = {"AGENT_FABRIC_LEGACY_REVIEW_MARKERS": "<!-- legacy-project-review v1 -->"}
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,LEGACY", env=legacy)
        check("a legacy marker the forwarder names IS coverage", rc == 0, out)
        check("  counted as a blind review", "blind reviews       : 1" in out, out)
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,LEGACY")
        check("the same marker, not named by the environment: not coverage", rc == 1, out)
        check("  counted as a self review", "self reviews        : 1" in out, out)
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,STRANGER", env=legacy)
        check("a marker nobody named is not coverage even with a legacy one set", rc == 1, out)
        # A marked review from ANOTHER account is neither blind nor
        # independent: any account on a public repository could otherwise
        # cover a head by pasting the published marker.
        rc, out, _ = run("OPEN:abc123:0", "somebodyelse,abc123,2026-08-07T10:00:00Z,MARKED")
        check("a marked review from another account is NOT coverage", rc == 1, out)
        check("  not a blind review", "blind reviews       : 0" in out, out)
        check("  and NOT an independent review", "independent reviews : 0" in out, out)
        check("  reported under its own line", "marked, other login : 1" in out, out)
        check("  with its login", "- somebodyelse  commit=abc123" in out, out)
        rc, out, _ = run("OPEN:abc123:0", "somebodyelse,abc123,2026-08-07T10:00:00Z,MARKED", posters='["somebodyelse"]')
        check("a poster named in AGENT_FABRIC_REVIEW_POSTERS IS coverage", rc == 0, out)
        check("  as a blind review, login shown", "- somebodyelse  commit=abc123" in out, out)
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,MARKED")
        check("the author's own marked review is blind, login shown", "- me  commit=abc123" in out, out)
        # AN INDEPENDENT REVIEWER IS ONE THE REPOSITORY TRUSTS (the review of
        # #41).
        rc, out, _ = run("OPEN:abc123:0", "stranger,abc123,2026-08-07T10:00:00Z,,NONE")
        check("a stranger's review is NOT coverage", rc == 1, out)
        check("  not an independent review", "independent reviews : 0" in out, out)
        check("  listed as not trusted, with its association", "- stranger  NONE  commit=abc123" in out, out)
        rc, out, _ = run("OPEN:abc123:0", "helper,abc123,2026-08-07T10:00:00Z,,COLLABORATOR")
        check("a collaborator's review IS coverage", rc == 0, out)
        # A configured reviewer (an App, which GitHub lists as NONE) is
        # trusted by name.
        rc, out, _ = run("OPEN:abc123:0", "reviewer[bot],abc123,2026-08-07T10:00:00Z,,NONE")
        check("a configured reviewer's review IS coverage whatever its association", rc == 0, out)
        # A FAILED THREADS LOOKUP IS "unknown", never 0.
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,MARKED", threads_fail=True)
        check("a failed threads lookup reads unknown", "unresolved threads  : unknown" in out, out)
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,MARKED",
                         threads='[{"isResolved":false,"isOutdated":false,"path":"a.sh"}]')
        check("a real unresolved thread is counted", "unresolved threads  : 1" in out, out)
        # A FAILED CHECKS LOOKUP IS "unknown" too; gh's "no checks reported" is 0.
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,MARKED", checks="502")
        check("a failed checks lookup reads unknown", rc == 0 and "  checks              : unknown\n" in out, out)
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,MARKED", checks="none")
        check("gh's 'no checks reported' reads 0", "  checks              : 0 pass, 0 other\n" in out, out)
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,MARKED")
        check("a check table is counted", "  checks              : 1 pass, 0 other\n" in out, out)
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,MARKED", "--json", "-q", checks="502")
        d = one_json(out)
        check("--json: a failed checks lookup is null, not 0",
              isinstance(d, dict) and d.get("checks") == {"pass": None, "other": None}, out)
        # THE --json CONTRACT: the same answer as fields, the same exit code.
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,MARKED\n"
                         "somebodyelse,abc123,2026-08-07T10:01:00Z,MARKED", "--json", threads_fail=True)
        check("--json keeps the exit code", rc == 0, out)
        m = re.search(r"^\{.*?^\}", out, re.M | re.S)
        d = one_json(m.group(0)) if m else None
        try:
            good = (d["head_reviewed"] == "yes" and d["blind"]["count"] == 1 and d["blind"]["rows"][0]["login"] == "me"
                    and d["blind"]["rows"][0]["commit_sha8"] == "abc123" and d["marked_by_others"]["count"] == 1
                    and d["unresolved_threads"] is None and d["independent"]["count"] == 0
                    and isinstance(d["checks"]["pass"], (int, float)) and not isinstance(d["checks"]["pass"], bool))
        except (TypeError, KeyError, IndexError):
            good = False
        check("--json carries the buckets, the login, and null for an unknown thread count", good, out)
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,MARKED", "--json", "-q", threads="[]")
        d = one_json(out)
        check("--json: a successful lookup with none is 0, not null",
              isinstance(d, dict) and d.get("unresolved_threads") == 0 and d.get("unresolved_threads") is not False, out)
        # Marked and unmarked must not blur.
        rc, out, _ = run("OPEN:abc123:0", "me,abc123,2026-08-07T10:00:00Z,MARKED\nme,abc123,2026-08-07T10:01:00Z\n"
                         "me,abc123,2026-08-07T10:02:00Z")
        check("marked and unmarked are separated (blind)", "blind reviews       : 1" in out, out)
        check("marked and unmarked are separated (self)", "self reviews        : 2" in out, out)
        # Reviewed at an EARLIER commit, a review still requested: "not yet"
        # (1), not "never coming" (5).
        rc, out, _ = run("OPEN:newhead:1", "bot,oldhead,2026-08-07T10:00:00Z")
        check("stale review WITH a request pending is 'not yet'", rc == 1, out)
        check("  flags the earlier commit", "an EARLIER commit" in out, out)

        print("fabric-pr review-status — no review is coming (exit 5)")
        rc, out, _ = run("OPEN:newhead:0", "bot,oldhead,2026-08-07T10:00:00Z")
        check("reviewed then pushed, nothing requested, exits 5", rc == 5, out)
        check("  names the cause", "NO REVIEW COMING" in out, out)
        # Under --json stdout stays ONE object on this path too, the cause a
        # field rather than a prose line after it.
        rc, out, _ = run("OPEN:newhead:0", "bot,oldhead,2026-08-07T10:00:00Z", "--json", "-q")
        check("--json keeps exit 5", rc == 5, out)
        d = one_json(out)
        check("  stdout is one object, the cause in no_review_coming",
              isinstance(d, dict) and (d.get("no_review_coming") or {}).get("cause") == "head-moved", out)
        # A FRESH PR has had no review, and its owner has yet to dispatch
        # one — so it must NOT be 5.
        rc, out, _ = run("OPEN:abc123:0", "")
        check("a never-reviewed PR is 1, not 5", rc == 1, out)
        check("  and claims nothing about the cause", "NO REVIEW COMING" not in out, out)

        print("fabric-pr review-status — waiting")
        rc, out, _ = run("OPEN:abc123:1\nOPEN:abc123:1", "", "--wait", "2", "--interval", "1", "-q")
        check("wait expires with nothing and exits 1", rc == 1, out)
        rc, out, _ = run("OPEN:abc123:1", "bot,abc123,2026-08-07T10:00:00Z", "--wait", "60", "--interval", "1", "-q")
        check("wait returns immediately once the head is reviewed", rc == 0, out)
        # Exit 5 must not sleep: --wait 3600 with a permanent state comes back
        # at once.
        t0 = time.monotonic()
        rc, out, _ = run("OPEN:newhead:0", "bot,oldhead,2026-08-07T10:00:00Z", "--wait", "3600", "--interval", "1", "-q")
        took = time.monotonic() - t0
        check("a permanent no-review state exits 5 under a long --wait", rc == 5, out)
        check(f"  and does not sleep first ({took:.0f}s)", took < 5, f"took {took:.1f}s")
        rc, out, _ = run("CLOSED:abc123:1", "", "--wait", "3600", "--interval", "1", "-q")
        check("a CLOSED PR stops the wait and exits 1", rc == 1, out)
        # --wait SHORTER than --interval once answered at once while reporting
        # a 4-second wait: the nap is clamped to what is left.
        t0 = time.monotonic()
        rc, out, _ = run("OPEN:abc123:1", "", "--wait", "4", "--interval", "60", "-q")
        took = time.monotonic() - t0
        check("a --wait shorter than --interval still exits 1", rc == 1, out)
        check(f"  and waits the requested time ({took:.0f}s)", took >= 3, f"returned after {took:.1f}s")
        check("  polling again at the deadline", polls_made() >= 2, f"only {polls_made()} poll(s)")

        print("fabric-pr review-status — invocation")
        check("no PR number exits 2", bare() == 2)
        check("zero --interval exits 2", bare("77", "o/r", "--interval", "0") == 2)
        # The duration table: this suite is what stops as_seconds accepting
        # something a caller did not mean.
        for bad in ("", "10sm", "m", "-1", "1x", "10 m"):
            check(f"rejects --wait '{bad}'", bare("77", "o/r", "--wait", bad) == 2)
        # A bare number is seconds; a unit converts. A reviewed head returns 0
        # at once either way, which makes this assertable without sleeping.
        for wait, interval in (("5m", "1s"), ("2h", "30s")):
            rc, out, _ = run("OPEN:abc123:0", "bot,abc123,2026-08-07T10:00:00Z", "--wait", wait, "--interval", interval, "-q")
            check(f"accepts --wait {wait} --interval {interval}", rc == 0, out)
        rc, out, _ = run("OPEN:abc123:0", "bot,abc123,2026-08-07T10:00:00Z", "--wait", "300", "--interval", "1", "-q")
        check("  and bare seconds still work", rc == 0, out)
        check("unknown option exits 2", bare("77", "o/r", "--nope") == 2)
        r = subprocess.run([*UNDER_TEST, "--help"], env=base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=60)
        check("--help exits 0", r.returncode == 0, r.stdout)
        check("  and documents exit 5", "no review is COMING" in r.stdout, r.stdout)
        # Three consecutive unreadable polls is unreadable; fewer is a blip.
        rc, out, _ = run("FAIL\nFAIL\nFAIL", "")
        check("three failed lookups exit 2", rc == 2, out)

        print("fabric-pr review-status — an unreadable reviews lookup is not 'no reviews'")
        rc, out, _ = run("OPEN:abc123:0", "", "--wait", "10", "--interval", "1", "-q", reviews_fail=True)
        check("a failing reviews lookup exits 2, not 1", rc == 2, out)
        check("  and renders no verdict from data it never had", "head reviewed?" not in out, out)

        print("fabric-pr review-status — coverage is ANY review at the head")
        # A review submitted LAST against an older commit must not mask the
        # coverage that is there.
        rc, out, _ = run("OPEN:head1:0", "reviewer-a,head1,2026-08-12T10:00:00Z\nreviewer-b,oldsha,2026-08-12T11:00:00Z")
        check("a stale review submitted LAST cannot mask head coverage", rc == 0, out)
        check("  head reads reviewed", "head reviewed?      : yes" in out, out)
        # A partial probe is not readable data. The numbers are load-bearing:
        # wait < 3 x interval reaches the fall-out path (two failures, not
        # three), with room for two probes on a loaded runner.
        rc, out, _ = run("OPEN:sha-one:0\nOPEN:sha-two:0", "", "--wait", "4", "--interval", "3", "-q",
                         reviews_fail_after="1")
        check("a probe that dies halfway does not render stale data", rc == 2, out)

        print("fabric-pr review-status — a merged pr is never told that no review is coming")
        rc, out, _ = run("MERGED:newsha:0", "reviewer-a,oldsha1,2026-08-12T10:00:00Z")
        check("a merged pr with a stale review does not claim exit 5", rc != 5, out)
        rc, out, _ = run("OPEN:newsha:0", "reviewer-a,oldsha1,2026-08-12T10:00:00Z")
        check("an open pr past its newest review still exits 5", rc == 5, out)

        print("fabric-pr review-status — a configured reviewer's clean verdict is a review")
        # An automated reviewer that finds nothing posts an issue comment
        # naming the commit, not a review object.
        rc, out, _ = run("OPEN:e7eb89d90cabc:0", "", verdicts="reviewer[bot],e7eb89d90c")
        check("a verdict comment at the head exits 0, with zero reviews", rc == 0, out)
        check("  and says the head is reviewed", "head reviewed?      : yes" in out, out)
        check("  and shows where the coverage came from", "verdict comments    : 1" in out, out)
        check("  and names it as a clean review", "a clean review leaves no review object" in out, out)

        print("fabric-pr review-status — the verdict's sha is READ, never assumed")
        rc, out, _ = run("OPEN:bbbbbbbbbb:0", "", verdicts="reviewer[bot],aaaaaaaaaa")
        check("a verdict naming an older commit is not coverage", rc == 5, out)
        check("  the verdict was READ, not ignored", "verdict comments    : 1" in out, out)
        check("  head stays unreviewed", "head reviewed?      : no" in out, out)
        check("  and names the cause, as a stale review object would", "NO REVIEW COMING" in out, out)

        print("fabric-pr review-status — abbreviated shas match by prefix, both ways")
        rc, out, _ = run("OPEN:2756062690aaaabbbbccccddddeeeeffff00001111:0", "", verdicts="reviewer[bot],2756062690")
        check("a short verdict sha covers a full head", rc == 0, out)

        print("fabric-pr review-status — only a RECOGNISED reviewer's verdict counts")
        rc, out, _ = run("OPEN:cccccccccc:0", "", verdicts="some-stranger,cccccccccc")
        check("a stranger's forged verdict is NOT coverage", rc == 1, out)
        check("  head stays unreviewed", "head reviewed?      : no" in out, out)
        check("  and none is counted", "verdict comments    : 0" in out, out)

        print("fabric-pr review-status — a self-authored verdict is not coverage")
        rc, out, _ = run("OPEN:dddddddddd:0", "", verdicts="me,dddddddddd")
        check("the pr author cannot certify their own head", rc == 1, out)

        print("fabric-pr review-status — the allow-list is the project's, and empty by default")
        rc, out, _ = run("OPEN:eeeeeeeeee:0", "", verdicts="some-other-bot,eeeeeeeeee", verdict_authors='["some-other-bot"]')
        check("AGENT_FABRIC_VERDICT_AUTHORS names the reviewer", rc == 0, out)
        rc, out, _ = run("OPEN:eeeeeeeeee:0", "", verdicts="some-other-bot,eeeeeeeeee")
        check("  an account the list does not name is not recognised", rc == 1, out)
        rc, out, _ = run("OPEN:eeeeeeeeee:0", "", verdicts="reviewer[bot],eeeeeeeeee", verdict_authors="")
        check("unconfigured, no comment is a verdict", rc == 1, out)
        check("  and none is counted", "verdict comments    : 0" in out, out)

        print("fabric-pr review-status — an unreadable comments lookup is not 'no verdicts'")
        rc, out, _ = run("OPEN:newsha:0", "reviewer-a,newsha,2026-08-12T10:00:00Z", verdicts_fail=True)
        check("a failing comments lookup exits 2, not 0", rc == 2, out)
        check("  and renders no verdict from data it never had", "head reviewed?" not in out, out)

        print("fabric-pr review-status — a configured reviewer that DECLINED ends the wait")
        # A spent usage limit or a repository it cannot open is not slowness:
        # the wording that counts is the project's, and the reason reported is
        # the reviewer's own first line.
        rc, out, _ = run("OPEN:ffffffffff:0", "", "--wait", "10m", "--interval", "1s", verdicts="reviewer[bot],REFUSED")
        check("a decline exits 5 immediately, not after 10m", rc == 5, out)
        check("  names the cause", "the reviewer declined" in out, out)
        check("  and reports the decline", "reviewer declined   :" in out, out)
        check("  and says WHICH decline it is, in the reviewer's words",
              "decline reason      : Usage limit reached for reviews" in out, out)
        check("  in the verdict line too",
              "the reviewer declined: Usage limit reached for reviews; none will run. (exit 5)" in out, out)

        print("fabric-pr review-status — every configured phrase is the same verdict")
        rc, out, _ = run("OPEN:ffffffffff:0", "", verdicts="reviewer[bot],NOENV")
        check("the second phrase exits 5 too", rc == 5, out)
        check("  and names its reason", "decline reason      : No environment for this repo" in out, out)

        print("fabric-pr review-status — with no refusal wording configured, nothing is a decline")
        rc, out, _ = run("OPEN:ffffffffff:0", "", verdicts="reviewer[bot],REFUSED", refusal_re="")
        check("unconfigured, the comment is just a comment", rc == 1, out)
        check("  and nothing is reported as declined", "reviewer declined   :" not in out, out)

        print("fabric-pr review-status — a refusal a later review superseded is stale")
        rc, out, _ = run("OPEN:ffffffffff:0", "", verdicts="reviewer[bot],REFUSED,2026-08-01T10:00:00Z\n"
                         "reviewer[bot],ffffffffff,2026-08-20T10:00:00Z")
        check("the later verdict wins", rc == 0, out)
        check("  and the decline is marked superseded", "superseded by later coverage" in out, out)

        print("fabric-pr review-status — a stranger cannot fake a refusal either")
        rc, out, _ = run("OPEN:ffffffffff:0", "", verdicts="some-stranger,REFUSED")
        check("a forged refusal is ignored", rc == 1, out)
        check("  and nothing is reported as declined", "reviewer declined   :" not in out, out)

        stale = "reviewer-a,aaaaaaaaaa,2026-08-01T10:00:00Z"
        print("fabric-pr review-status — a configured review ask in flight is not 'nothing coming'")
        # A phrase ask is no GitHub review request, so `requested` stays 0:
        # "nothing is coming" fired seconds after the ask, hit live.
        rc, out, _ = run("OPEN:ffffffffff:0", stale, verdicts="someone,REQUEST,2026-08-20T10:00:00Z")
        check("reports 'not yet', not 'nothing is coming'", rc == 1, out)
        check("  and claims nothing about the cause", "NO REVIEW COMING" not in out, out)
        check("  and says the ask is in flight", "in flight" in out, out)

        print("fabric-pr review-status — with no ask phrase configured, nothing is an ask")
        rc, out, _ = run("OPEN:ffffffffff:0", stale, verdicts="someone,REQUEST,2026-08-20T10:00:00Z", request_re="")
        check("unconfigured, the stale review is 'nothing is coming'", rc == 5, out)
        check("  and no ask is reported", "review asked        :" not in out, out)

        print("fabric-pr review-status — the review it asked for answers the ask")
        rc, out, _ = run("OPEN:ffffffffff:0", "reviewer[bot],ffffffffff,2026-08-20T10:00:00Z",
                         verdicts="someone,REQUEST,2026-08-15T10:00:00Z", head_date="2026-08-10T00:00:00Z")
        check("the head is covered", rc == 0, out)
        check("  and the ask reads answered", "already answered" in out, out)
        check("  not in flight", "in flight" not in out, out)

        def ask_case(head_date: str, review_at: str, ask_at: str, **kw) -> tuple[int, str]:
            rc, out, _ = run("OPEN:ffffffffff:0", f"reviewer-a,aaaaaaaaaa,{review_at}",
                             verdicts=f"someone,REQUEST,{ask_at}", head_date=head_date, **kw)
            return rc, out

        print("fabric-pr review-status — head birth comes from the PUSH, not the commit date")
        # Committed 11:48:37, pushed 12:06: an ask inside that gap is for the
        # PREVIOUS head.
        rc, out = ask_case("2026-08-25T11:48:37Z", "2026-08-25T11:50:00Z", "2026-08-25T11:55:00Z",
                           suite_date="2026-08-25T12:06:07Z")
        check("an ask between commit and push is for the older head", rc == 5, out)
        check("  names the cause", "NO REVIEW COMING" in out, out)

        print("fabric-pr review-status — ...and an ask after the push is current")
        rc, out = ask_case("2026-08-25T11:48:37Z", "2026-08-25T11:50:00Z", "2026-08-25T12:10:00Z",
                           suite_date="2026-08-25T12:06:07Z")
        check("an ask after the ref moved is in flight", rc == 1, out)

        print("fabric-pr review-status — a REBASED head still expires an older ask")
        rc, out = ask_case("2026-01-01T00:00:00Z", "2026-08-25T11:50:00Z", "2026-08-25T11:55:00Z",
                           suite_date="2026-08-25T12:06:07Z")
        check("an ancient commit date does not make the ask current", rc == 5, out)

        print("fabric-pr review-status — a RESTORED sha keeps the ask in flight rather than expiring it")
        # Dating from the latest suite bought exit 5 here and paid for it with
        # a false exit 5 on every dispatch, schedule, re-run and reopen; a
        # longer wait is the safe direction.
        rc, out = ask_case("2026-08-25T08:00:00Z", "2026-08-25T11:50:00Z", "2026-08-25T11:00:00Z",
                           suite_date="2026-08-25T12:06:07Z", earlier="2026-08-25T09:00:00Z")
        check("the restored sha costs a wait, not a verdict", rc == 1, out)
        check("  and nothing declares the review dead", "NO REVIEW COMING" not in out, out)

        for heading, label, kw in (
                ("a suite from ANOTHER pr does not date this head", "the other pr's suite is ignored",
                 {"foreign": "2026-01-01T00:00:00Z"}),
                ("an EARLIER suite on ANOTHER ref cannot date this head", "the other ref's suite is ignored",
                 {"claiming": "2026-01-01T00:00:00Z"}),
                ("an EARLIER suite this pr does not own cannot date its head", "a suite belonging to no pr is ignored",
                 {"unowned": "2026-01-01T00:00:00Z"})):
            print(f"fabric-pr review-status — {heading}")
            rc, out = ask_case("2026-08-25T11:48:37Z", "2026-08-25T11:50:00Z", "2026-08-25T11:55:00Z",
                               suite_date="2026-08-25T12:06:07Z", **kw)
            check(label, rc == 5, out)
            check("  names the cause", "NO REVIEW COMING" in out, out)

        print("fabric-pr review-status — a LATER suite on this ref cannot date this head")
        # Dispatch, schedule, re-run and reopen raise a suite for the
        # unchanged sha with this ref AND this pr: ordering rejects the class.
        rc, out = ask_case("2026-08-25T11:48:37Z", "2026-08-25T11:50:00Z", "2026-08-25T12:10:00Z",
                           suite_date="2026-08-25T12:06:07Z", later="2026-08-25T13:00:00Z")
        check("a later suite does not move the head's birthday", rc == 1, out)
        check("  and nothing declares the review dead", "NO REVIEW COMING" not in out, out)

        print("fabric-pr review-status — the earliest suite is found ACROSS pages, not on page one")
        # HEAD_DATE is LATER than the ask, so the committer-date fallback
        # yields exit 5: without that, every way of getting this wrong still
        # reached exit 1 and the case passed vacuously.
        rc, out = ask_case("2026-08-25T12:30:00Z", "2026-08-25T11:50:00Z", "2026-08-25T11:55:00Z",
                           suite_date="2026-08-25T12:06:07Z", page2="2026-08-25T11:00:00Z")
        check("a later page's earlier suite wins", rc == 1, out)
        check("  and nothing declares the review dead", "NO REVIEW COMING" not in out, out)

        print("fabric-pr review-status — a quote in the branch name does not break the lookup")
        rc, out = ask_case("2026-01-01T00:00:00Z", "2026-08-25T11:50:00Z", "2026-08-25T11:55:00Z",
                           suite_date="2026-08-25T12:06:07Z", head_ref='mine/we"ird')
        check("the suite date is still found", rc == 5, out)
        check("  names the cause", "NO REVIEW COMING" in out, out)

        print("fabric-pr review-status — no check suite falls back to the commit date")
        # The ask falls BEFORE the commit date, so the fallback CHANGES the
        # answer: written the other way round, it passed with the fallback
        # deleted.
        rc, out = ask_case("2026-08-20T00:00:00Z", "2026-08-25T10:00:00Z", "2026-08-15T10:00:00Z", suite_date="")
        check("the commit date still decides when nothing else can", rc == 5, out)
        check("  names the cause", "NO REVIEW COMING" in out, out)

        print("fabric-pr review-status — a STALE review does not answer a later ask")
        rc, out = ask_case("2026-08-10T00:00:00Z", "2026-08-20T10:00:00Z", "2026-08-15T10:00:00Z")
        check("the ask still counts as in flight", rc == 1, out)
        check("  and nothing claims the review is not coming", "NO REVIEW COMING" not in out, out)

        print("fabric-pr review-status — ...but an ask made BEFORE this head still expires")
        rc, out = ask_case("2026-08-10T00:00:00Z", "2026-08-07T10:00:00Z", "2026-08-05T10:00:00Z")
        check("an ask for an older head does not suppress the verdict", rc == 5, out)
        check("  names the cause", "NO REVIEW COMING" in out, out)

        print("fabric-pr review-status — an ask ALREADY ANSWERED does not suppress the verdict")
        rc, out, _ = run("OPEN:ffffffffff:0", "reviewer-a,aaaaaaaaaa,2026-08-20T10:00:00Z",
                         verdicts="someone,REQUEST,2026-08-01T10:00:00Z")
        check("the answer that followed it wins", rc == 5, out)
        check("  and the ask is marked answered", "already answered" in out, out)

        print("fabric-pr review-status — a re-ask after a refusal supersedes it")
        rc, out, _ = run("OPEN:ffffffffff:0", "", verdicts="reviewer[bot],REFUSED,2026-08-01T10:00:00Z\n"
                         "someone,REQUEST,2026-08-20T10:00:00Z")
        check("the re-ask reopens the wait", rc == 1, out)
        check("  and the decline no longer ends it", "the reviewer declined" not in out, out)

        print("fabric-pr review-status — a refusal AFTER the ask still ends the wait")
        rc, out, _ = run("OPEN:ffffffffff:0", "", verdicts="someone,REQUEST,2026-08-01T10:00:00Z\n"
                         "reviewer[bot],REFUSED,2026-08-20T10:00:00Z")
        check("the decline wins", rc == 5, out)
        check("  and names itself", "the reviewer declined" in out, out)

        print("fabric-pr review-status — a pending request from ANYONE suppresses the verdict")
        rc, out, _ = run("OPEN:ffffffffff:1@a-human", "reviewer-a,aaaaaaaaaa,2026-08-01T10:00:00Z")
        check("a pending request means a review may be coming", rc == 1, out)

        refused = "reviewer[bot],REFUSED,2026-08-20T10:00:00Z"
        print("fabric-pr review-status — a formal request PREDATING the refusal does not supersede it")
        rc, out, _ = run("OPEN:ffffffffff:1", "", verdicts=refused, formal_date="2026-08-01T10:00:00Z")
        check("the refusal answered that request, and still stands", rc == 5, out)
        check("  names the decline", "the reviewer declined" in out, out)

        print("fabric-pr review-status — ...and one made AFTER it does supersede it")
        rc, out, _ = run("OPEN:ffffffffff:1", "", verdicts=refused, formal_date="2026-08-25T10:00:00Z")
        check("a genuine re-request reopens the wait", rc == 1, out)
        check("  and the decline no longer ends it", "the reviewer declined" not in out, out)

        print("fabric-pr review-status — a request since WITHDRAWN cannot supersede the refusal")
        # The timeline keeps a REVIEW_REQUESTED_EVENT after the request is
        # withdrawn: the event has to name a reviewer who is STILL pending.
        rc, out, _ = run("OPEN:ffffffffff:1", "", verdicts=refused, formal_date="2026-08-25T10:00:00Z,a-human")
        check("a withdrawn request does not reopen the wait", rc == 5, out)
        check("  the decline still stands", "the reviewer declined" in out, out)

        print("fabric-pr review-status — a decline does not answer a PENDING HUMAN request")
        rc, out, _ = run("OPEN:ffffffffff:2@a-human+reviewer[bot]", "", verdicts="someone,REQUEST,2026-08-01T10:00:00Z\n"
                         "reviewer[bot],REFUSED,2026-08-20T10:00:00Z")
        check("the human request outlives the reviewer's decline", rc == 1, out)
        check("  and nothing declares the review dead", "the reviewer declined" not in out, out)

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

        print("fabric-pr review-status — a request event for someone NOT pending does not clear the refusal")
        rc, out, _ = run("OPEN:ffffffffff:1", "", verdicts=refused,
                         formal_date="2026-08-19T10:00:00Z,reviewer[bot]\n2026-08-25T10:00:00Z,a-human")
        check("the reviewer's decline still stands", rc == 5, out)
        check("  names the decline", "the reviewer declined" in out, out)

        print("fabric-pr review-status — ...and a request of the reviewer itself after it clears it")
        rc, out, _ = run("OPEN:ffffffffff:1", "", verdicts=refused, formal_date="2026-08-25T10:00:00Z,reviewer[bot]")
        check("a re-request of the configured reviewer reopens the wait", rc == 1, out)

        print("fabric-pr review-status — unreadable timeline leaves the refusal standing")
        rc, out, _ = run("OPEN:ffffffffff:1", "", verdicts=refused, formal_date="")
        check("no ordering evidence means the refusal is not superseded", rc == 5, out)

        print("fabric-pr review-status — a CURRENT refusal outranks the stale-review message")
        rc, out, _ = run("OPEN:ffffffffff:0", stale, verdicts=refused)
        check("still exits 5", rc == 5, out)
        check("names the DECLINE, not the stale review", "the reviewer declined" in out, out)
        check("  and does not send the caller to re-review", "dispatch a re-review (exit 5)" not in out, out)

        print("fabric-pr review-status — a configuration that cannot be applied is refused, never read as 'none'")
        rc, out, _ = run("OPEN:ffffffffff:0", stale, verdicts="someone,REQUEST,2026-08-20T10:00:00Z",
                         request_re="@reviewer review(")
        check("an invalid ask regex exits 2", rc == 2, out)
        check("  and names the variable", "AGENT_FABRIC_REVIEW_REQUEST_RE" in out, out)
        rc, out, _ = run("OPEN:ffffffffff:0", "", verdicts="reviewer[bot],REFUSED", refusal_re="[unclosed")
        check("an invalid refusal regex exits 2", rc == 2, out)
        check("  and names the variable", "AGENT_FABRIC_REVIEWER_REFUSAL_RE" in out, out)
        rc, out, _ = run("OPEN:ffffffffff:0", "", verdicts="reviewer[bot],ffffffffff", verdict_authors="reviewer[bot]")
        check("a verdict-author list that is not a JSON array exits 2", rc == 2, out)
        check("  and names the variable", "AGENT_FABRIC_VERDICT_AUTHORS" in out, out)

        print("fabric-pr review-status — the decline reason is the reviewer's first line, whole")
        rc, out, _ = run("OPEN:ffffffffff:0", "", verdicts="reviewer[bot],REFUSED_DASH")
        check("still a decline", rc == 5, out)
        check("  the reason is the first non-empty line, CR stripped",
              "decline reason      : Cannot review this PR — usage limit reached for reviews." in out, out)
        check("  and the verdict line carries it whole",
              "the reviewer declined: Cannot review this PR — usage limit reached for reviews. (exit 5)" in out, out)

        print("fabric-pr review-status — a MERGED pr is not ended by a refusal")
        rc, out, _ = run("MERGED:ffffffffff:0", "", verdicts="reviewer[bot],REFUSED")
        check("a merged pr keeps waiting despite a decline", rc == 1, out)

        print("fabric-pr review-status — -q writes NOTHING to stderr")
        # A background watcher runs for half an hour, so anything
        # unconditional on stderr is emitted on every poll; a diagnostic
        # printf once shipped because no case asked what stderr held. The
        # head-birth path is exercised: that is where the leak was.
        rc, out, err = run("OPEN:ffffffffff:0", "reviewer-a,aaaaaaaaaa,2026-08-25T11:50:00Z", "-q",
                           verdicts="someone,REQUEST,2026-08-25T12:10:00Z", head_date="2026-08-25T11:48:37Z",
                           suite_date="2026-08-25T12:06:07Z")
        check("no diagnostic output escapes under -q", err == "", err)

    print(f"\ntest_pr_review_status_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
