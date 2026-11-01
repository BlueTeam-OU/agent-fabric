#!/usr/bin/env python3
""".github/workflows/disarm-on-push.yml: its run script, taken out of the
workflow as it is and run under bash against a fake gh on PATH, so the
case and the workflow cannot drift apart. A push takes auto-merge off
every arming that is not tied to the new head by fabric-pr arm's
`fabric/armed` status on it; an unarmed PR and an arming of the new head
are left alone, and a status that cannot be read is no tie. Also the
trigger and the permissions.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "disarm-on-push.yml")

# The fake answers the query as GitHub's GraphQL API does — a document of
# the fields asked for, null for a field the API does not have — and
# applies the script's own --jq to it with jq, so a query or jq that names
# the wrong field reads "not armed" here as it would live (review of #140,
# P2 8). It logs every call, so a case reads what was mutated and posted.
FAKE_GH = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$GH_LOG"
q=""; jqx=""; prev=""
for a in "$@"; do
  case "$prev" in -f) case "$a" in query=*) q="${a#query=}" ;; esac ;; --jq) jqx="$a" ;; esac
  prev="$a"
done
case "$q" in
  *"query("*)
    # Each field only when the query asks for it, as GitHub answers.
    id='null'; [[ "$q" == *"pullRequest(number:\$n){id "* ]] && id='"PR_NODE"'
    # The PR's head now: FAKE_HEAD, the event's AFTER unless a case moved it on.
    head='null'; [[ "$q" == *" headRefOid "* ]] && head='"'"${FAKE_HEAD:-$AFTER}"'"'
    if [[ "$q" == *"autoMergeRequest{enabledAt}"* && -n "${FAKE_ENABLED_AT:-}" ]]; then
      doc='{"data":{"repository":{"pullRequest":{"id":'"$id"',"headRefOid":'"$head"',"autoMergeRequest":{"enabledAt":"'"$FAKE_ENABLED_AT"'"}}}}}'
    else
      doc='{"data":{"repository":{"pullRequest":{"id":'"$id"',"headRefOid":'"$head"',"autoMergeRequest":null}}}}'
    fi
    if [[ -n "$jqx" ]]; then printf '%s' "$doc" | jq -r "$jqx"; else printf '%s\n' "$doc"; fi ;;
  *)
    # The combined status of a commit, as REST answers it: the latest status of each context on the ref
    # asked, an empty list when it has none. FAKE_STATUS_SHA is the commit fabric/armed is on, with
    # FAKE_STATUS_STATE (success when unset); FAKE_STATUS_FAIL makes the read fail as a refusal does.
    path=""; for a in "$@"; do case "$a" in repos/*) path="$a" ;; esac; done
    if [[ "$path" =~ ^repos/[^/]+/[^/]+/commits/([^/?]+)/status(\?.*)?$ ]]; then
      [[ -n "${FAKE_STATUS_FAIL:-}" ]] && { echo "gh: Resource not accessible by integration (HTTP 403)" >&2; exit 1; }
      ref="${BASH_REMATCH[1]}"; statuses='[]'
      if [[ -n "${FAKE_STATUS_SHA:-}" && "$ref" == "$FAKE_STATUS_SHA" ]]; then
        statuses='[{"context":"ci-ok","state":"success"},{"context":"fabric/armed","state":"'"${FAKE_STATUS_STATE:-success}"'","description":"armed through the gate"}]'
      fi
      doc='{"sha":"'"$ref"'","state":"success","total_count":1,"statuses":'"$statuses"'}'
      if [[ -n "$jqx" ]]; then printf '%s' "$doc" | jq -r "$jqx"; else printf '%s\n' "$doc"; fi
    fi ;;
esac
"""

failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f": {detail}"))
    failures += 0 if ok else 1


def run_script() -> str:
    text = open(WORKFLOW).read()
    m = re.search(r"\n        run: \|\n((?:          .*\n|\n)+)", text)
    assert m, "no run block in the workflow"
    return "\n".join(line[10:] for line in m.group(1).splitlines())


BEFORE, AFTER, LATER = "aaaaaaaa11", "bbbbbbbb22", "cccccccc33"


def run(enabled_at: str | None, status_on: str | None = None,
        status_state: str | None = None, status_fail: bool = False,
        head: str | None = None) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as d:
        gh = os.path.join(d, "gh")
        with open(gh, "w") as f:
            f.write(FAKE_GH)
        os.chmod(gh, 0o755)
        log = os.path.join(d, "gh.log")
        open(log, "w").close()
        env = dict(os.environ, PATH=f"{d}:{os.environ['PATH']}", GH_LOG=log, GH_TOKEN="t", GH_REPO="o/r",
                   PR="7", BEFORE=BEFORE, AFTER=AFTER)
        if enabled_at is not None:
            env["FAKE_ENABLED_AT"] = enabled_at
        if status_on is not None:
            env["FAKE_STATUS_SHA"] = status_on
        if status_state is not None:
            env["FAKE_STATUS_STATE"] = status_state
        if status_fail:
            env["FAKE_STATUS_FAIL"] = "1"
        if head is not None:
            env["FAKE_HEAD"] = head
        p = subprocess.run(["bash", "-c", run_script()], env=env, capture_output=True, text=True, timeout=30)
        return p.returncode, p.stdout + p.stderr, open(log).read()


def main() -> int:
    if not shutil.which("jq"):
        print("  FAIL jq is not on PATH: the fake gh applies the workflow's --jq with it")
        return 1
    print("disarm-on-push: not armed, nothing taken off")
    rc, out, calls = run(None)
    check("exit 0", rc == 0, out)
    check("no mutation and no comment", "disablePullRequestAutoMerge" not in calls and "comments" not in calls, calls)

    print("disarm-on-push: armed before the push, taken off and said")
    rc, out, calls = run("2026-10-09T06:00:00Z")
    check("exit 0", rc == 0, out)
    check("the mutation is sent for the PR's node", "disablePullRequestAutoMerge" in calls and "id=PR_NODE" in calls, calls)
    check("a comment names both heads and the arming", "issues/7/comments" in calls and "aaaaaaaa" in calls
          and "bbbbbbbb" in calls and "2026-10-09T06:00:00Z" in calls, calls)

    def disarmed(rc: int, calls: str) -> bool:
        return rc == 0 and "disablePullRequestAutoMerge" in calls and "issues/7/comments" in calls

    def kept(rc: int, calls: str) -> bool:
        return rc == 0 and "disablePullRequestAutoMerge" not in calls and "comments" not in calls

    # enabledAt and the event's updated_at are both whole seconds, so an arming of the OLD head made in the push's
    # second read "at the push" and was kept, and that head merged unreviewed (audit F02). Mutation: the keep
    # decided by `! armed_on < PUSHED_AT` again fails this.
    print("disarm-on-push: armed in the same second as the push, with no tie to the new head, taken off")
    rc, out, calls = run("2026-10-09T06:10:00Z")
    check("armed at the push's own second: the mutation and the comment", disarmed(rc, calls), out + calls)

    # updated_at moves with any edit of the PR, so "after it" is no proof of the new head either.
    print("disarm-on-push: armed after the event's time, with no tie to the new head, taken off")
    rc, out, calls = run("2026-10-09T06:20:00Z")
    check("armed later, no fabric/armed on the new head: taken off", disarmed(rc, calls), out + calls)

    print("disarm-on-push: an arming tied to the new head by fabric/armed on it, kept")
    for when in ("2026-10-09T06:00:00Z", "2026-10-09T06:10:00Z", "2026-10-09T06:20:00Z"):
        rc, out, calls = run(when, status_on=AFTER)
        check(f"armed {when}, fabric/armed success on {AFTER[:8]}: exit 0, no mutation, no comment", kept(rc, calls), out + calls)
    check("the status is asked of the new head's sha, not of the branch", f"repos/o/r/commits/{AFTER}/status" in calls, calls)

    # A run for the push to AFTER that starts late (queued behind a runner) or is re-run keeps its event, while the
    # PR has moved on to LATER and LATER was armed through the gate: that arming stays (review of #454, F1).
    # Mutation: the tie asked of AFTER, not of the PR's head, fails the first check.
    print("disarm-on-push: a late or re-run job for an earlier push leaves a later head's own arming")
    rc, out, calls = run("2026-10-09T06:30:00Z", status_on=LATER, head=LATER)
    check("head moved on to a head carrying fabric/armed: kept", kept(rc, calls), out + calls)
    check("the status is asked of the PR's head, not of the event's AFTER", f"repos/o/r/commits/{LATER}/status" in calls
          and f"commits/{AFTER}/status" not in calls, calls)
    rc, out, calls = run("2026-10-09T06:30:00Z", status_on=AFTER, head=LATER)
    check("fabric/armed on the event's AFTER but the PR's head moved on without it: taken off", disarmed(rc, calls),
          out + calls)

    # Mutation: the status asked of BEFORE (or any ref but AFTER) keeps this one and fails it.
    print("disarm-on-push: fabric/armed on the old head is the old head's arming, taken off")
    rc, out, calls = run("2026-10-09T06:10:00Z", status_on=BEFORE)
    check("fabric/armed on the old head only: taken off", disarmed(rc, calls), out + calls)

    # Mutation: the state test dropped (any fabric/armed counts) fails this.
    print("disarm-on-push: a fabric/armed that is not success is no arming, taken off")
    for state in ("pending", "failure", "error"):
        rc, out, calls = run("2026-10-09T06:10:00Z", status_on=AFTER, status_state=state)
        check(f"fabric/armed {state} on the new head: taken off", disarmed(rc, calls), out + calls)

    # A read that fails must not leave the arming in place: `set -e` would end the job there, auto-merge still on.
    # Mutation: the status read's fallback removed fails this (the job exits non-zero with nothing taken off).
    print("disarm-on-push: the status cannot be read, no tie, taken off")
    rc, out, calls = run("2026-10-09T06:10:00Z", status_fail=True)
    check("the status read refused: taken off all the same", disarmed(rc, calls), out + calls)

    print("disarm-on-push: what it runs on and may do")
    text = open(WORKFLOW).read()
    # pull_request_target runs main's copy of the workflow, so a PR that breaks this file cannot leave its own arming
    # in place; mutation: the trigger back to `pull_request:` fails the first check.
    check("on a pull request's synchronize only, by main's copy (pull_request_target)",
          re.search(r"\n  pull_request_target:\n\s+types: \[synchronize\]", text) is not None
          and re.search(r"\n  pull_request:\n", text) is None)
    # Under pull_request_target the token can write; running the head's code with it would be a stranger's code with
    # write access. Mutation: an actions/checkout step (or any `uses:`) added fails this.
    check("checks nothing out and uses no action: nothing of the pull request runs",
          re.search(r"^\s*-?\s*uses:", text, re.M) is None and "actions/checkout" not in text)
    perms = re.search(r"\npermissions:\n((?:  .*\n)+)", text)
    # statuses: read is what reads fabric/armed: without it the read is refused, and every arming, the new head's
    # too, is taken off. Mutation: the line removed, or made write, fails this.
    check("pull-requests: write and contents: write (disabling auto-merge needs both), statuses: read, nothing else",
          perms is not None and sorted(perms.group(1).split())
          == sorted(["contents:", "write", "pull-requests:", "write", "statuses:", "read"]),
          perms.group(1) if perms else "no permissions block")
    want_if = ("github.event.pull_request.head.repo.full_name == github.repository && github.actor != 'dependabot[bot]'"
               " && github.event.pull_request.user.login != 'dependabot[bot]'")
    check("skipped for a fork, a push by Dependabot and a Dependabot pull request (the whole if:)",
          f"    if: {want_if}\n" in text, re.search(r"\n    if: .*", text).group(0) if re.search(r"\n    if: .*", text) else "no if:")

    print("all passed" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
