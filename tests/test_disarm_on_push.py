#!/usr/bin/env python3
""".github/workflows/disarm-on-push.yml: its run script, taken out of the
workflow as it is and run under bash against a fake gh on PATH, so the
case and the workflow cannot drift apart. A push takes auto-merge off
only an arming older than the push; an unarmed PR and an arming of the
new head are left alone. Also the trigger and the one write permission.
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
    if [[ "$q" == *"autoMergeRequest{enabledAt}"* && -n "${FAKE_ENABLED_AT:-}" ]]; then
      doc='{"data":{"repository":{"pullRequest":{"id":"PR_NODE","autoMergeRequest":{"enabledAt":"'"$FAKE_ENABLED_AT"'"}}}}}'
    else
      doc='{"data":{"repository":{"pullRequest":{"id":"PR_NODE","autoMergeRequest":null}}}}'
    fi
    if [[ -n "$jqx" ]]; then printf '%s' "$doc" | jq -r "$jqx"; else printf '%s\n' "$doc"; fi ;;
  *) : ;;
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


def run(enabled_at: str | None, pushed_at: str = "2026-10-09T06:10:00Z") -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as d:
        gh = os.path.join(d, "gh")
        with open(gh, "w") as f:
            f.write(FAKE_GH)
        os.chmod(gh, 0o755)
        log = os.path.join(d, "gh.log")
        open(log, "w").close()
        env = dict(os.environ, PATH=f"{d}:{os.environ['PATH']}", GH_LOG=log, GH_TOKEN="t", GH_REPO="o/r",
                   PR="7", BEFORE="aaaaaaaa11", AFTER="bbbbbbbb22", PUSHED_AT=pushed_at)
        if enabled_at is not None:
            env["FAKE_ENABLED_AT"] = enabled_at
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

    print("disarm-on-push: armed at or after the push, an arming of the new head, kept")
    for when in ("2026-10-09T06:10:00Z", "2026-10-09T06:20:00Z"):
        rc, out, calls = run(when)
        check(f"armed {when}: exit 0, no mutation, no comment", rc == 0 and "disablePullRequestAutoMerge" not in calls
              and "comments" not in calls, out + calls)

    print("disarm-on-push: what it runs on and may do")
    text = open(WORKFLOW).read()
    check("on a pull request's synchronize only", re.search(r"pull_request:\n\s+types: \[synchronize\]", text) is not None)
    perms = re.search(r"\npermissions:\n((?:  .*\n)+)", text)
    check("pull-requests: write and contents: read, nothing else",
          perms is not None and sorted(perms.group(1).split()) == sorted(["contents:", "read", "pull-requests:", "write"]),
          perms.group(1) if perms else "no permissions block")
    want_if = ("github.event.pull_request.head.repo.full_name == github.repository && github.actor != 'dependabot[bot]'"
               " && github.event.pull_request.user.login != 'dependabot[bot]'")
    check("skipped for a fork, a push by Dependabot and a Dependabot pull request (the whole if:)",
          f"    if: {want_if}\n" in text, re.search(r"\n    if: .*", text).group(0) if re.search(r"\n    if: .*", text) else "no if:")

    print("all passed" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
