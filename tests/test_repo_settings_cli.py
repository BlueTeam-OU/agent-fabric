#!/usr/bin/env python3
"""tools/fabric/github-repo-settings.sh, through the shim with a fake `gh`
that records every request (method, path, JSON body) and answers it.

What the settings script promises, and the bash had no test for: every
call sets the documented value; the ruleset is updated by name when it
exists (on any page) and created when it does not; a refused call stops
the run; a ruleset file it cannot read writes nothing; --show prints
five compact lines and writes nothing. Plain script: prints ok/FAIL,
exit 1 on any failure."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "fabric", "github-repo-settings.sh")

# The fake speaks gh.py's transport: --method, the body as JSON on
# `--input -`, `--paginate --slurp` wrapping the pages in a list.
GH = r'''#!{python}
import json, os, sys
a = sys.argv[1:]
path, method, body, slurp = a[1], "GET", None, False
if "--method" in a:
    method = a[a.index("--method") + 1]
if "--input" in a:
    body = json.load(sys.stdin)
slurp = "--slurp" in a
with open(os.environ["GH_LOG"], "a") as fh:
    fh.write(json.dumps({"method": method, "path": path, "body": body}) + "\n")
if os.environ.get("GH_FAIL") == f"{method} {path}":
    print("gh: Validation Failed (HTTP 422)", file=sys.stderr)
    sys.exit(1)
answers = json.loads(os.environ.get("GH_ANSWERS", "{}"))
answer = answers.get(path, {})
if path.endswith("/rulesets") and method == "GET":
    pages = json.loads(os.environ.get("GH_RULESET_PAGES", "[[]]"))
    answer = pages if slurp else pages[0]
print(json.dumps(answer))
'''


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with open(os.path.join(ROOT, "tools", "fabric", "github-ruleset-main.json"), encoding="utf-8") as fh:
        ruleset = json.load(fh)

    with tempfile.TemporaryDirectory() as t:
        bin_, log = os.path.join(t, "bin"), os.path.join(t, "log")
        os.makedirs(bin_)
        with open(os.path.join(bin_, "gh"), "w", encoding="utf-8") as fh:
            fh.write(GH.replace("{python}", sys.executable))
        os.chmod(os.path.join(bin_, "gh"), 0o755)
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_", "GH_")) and k != "GIT_DIR"}
        base.update(PATH=bin_ + os.pathsep + os.environ.get("PATH", ""), GH_LOG=log)

        def settings(*args: str, tool: str = TOOL, **env: str) -> tuple[int, str, str, list[dict]]:
            if os.path.exists(log):
                os.remove(log)
            r = subprocess.run([tool, *args], env={**base, **env}, capture_output=True, text=True, timeout=120)
            calls = []
            if os.path.exists(log):
                with open(log, encoding="utf-8") as fh:
                    calls = [json.loads(line) for line in fh]
            return r.returncode, r.stdout, r.stderr, calls

        print("github-repo-settings: apply")
        named = json.dumps([[{"id": 3, "name": "other"}], [{"id": 7, "name": ruleset["name"]}]])
        rc, out, err, calls = settings("o/r", GH_RULESET_PAGES=named)
        writes = [(c["method"], c["path"]) for c in calls if c["method"] != "GET"]
        check("every setting, in order, then the ruleset found on the second page updated by its id",
              rc == 0 and writes == [("PATCH", "repos/o/r"), ("PUT", "repos/o/r/topics"),
                                     ("PUT", "repos/o/r/actions/permissions"),
                                     ("PUT", "repos/o/r/actions/permissions/workflow"),
                                     ("PUT", "repos/o/r/rulesets/7")], f"rc={rc}\n{err}{json.dumps(calls)[:600]}")
        body = {c["path"]: c["body"] for c in calls}
        check("…the documented values: merge settings, the topic list whole, read-only workflows",
              body.get("repos/o/r", {}).get("allow_auto_merge") is True
              and body["repos/o/r"].get("delete_branch_on_merge") is False
              and body["repos/o/r"].get("merge_commit_title") == "MERGE_MESSAGE"
              and body.get("repos/o/r/topics", {}).get("names", [None])[0] == "agent-memory"
              and len(body["repos/o/r/topics"]["names"]) == 8
              and body.get("repos/o/r/actions/permissions/workflow")
              == {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": False},
              json.dumps(body)[:600])
        check("…the ruleset sent is the file, whole", body.get("repos/o/r/rulesets/7") == ruleset)
        check("…and one line on stdout", out == "github-repo-settings: applied to o/r "
              "(docs/adr/ADR-019-work-arrives-as-pull-requests.md)\n", out)

        rc, out, err, calls = settings(GH_RULESET_PAGES=json.dumps([[{"id": 3, "name": "other"}]]))
        last = calls[-1] if calls else {}
        check("no ruleset of that name: created; no repository named: the default one",
              rc == 0 and last.get("method") == "POST" and last.get("path") == "repos/gzapi-org/agent-fabric/rulesets"
              and last.get("body") == ruleset, f"rc={rc}\n{err}{json.dumps(calls)[-400:]}")

        rc, out, err, calls = settings("o/r", GH_FAIL="PUT repos/o/r/topics")
        check("a refused call stops the run: exit 1, the call and GitHub's reason, nothing after it",
              rc == 1 and out == "" and "repos/o/r/topics" in err and "HTTP 422" in err
              and [c["path"] for c in calls] == ["repos/o/r", "repos/o/r/topics"], f"rc={rc}\n{err}")

        # A copy of the tool with a ruleset file that is not JSON.
        copy = os.path.join(t, "copy", "tools", "fabric")
        os.makedirs(os.path.join(copy, "github"))
        for rel in ("github-repo-settings.sh", "gh.py", os.path.join("github", "repo_settings.py"),
                    os.path.join("github", "__init__.py")):
            shutil.copy2(os.path.join(ROOT, "tools", "fabric", rel), os.path.join(copy, rel))
        with open(os.path.join(copy, "github-ruleset-main.json"), "w", encoding="utf-8") as fh:
            fh.write("{")
        rc, out, err, calls = settings("o/r", tool=os.path.join(copy, "github-repo-settings.sh"))
        check("a ruleset file it cannot read: exit 1 before any call", rc == 1 and calls == []
              and "github-ruleset-main.json" in err, f"rc={rc}\n{err}{calls}")

        print("github-repo-settings: --show and --help")
        answers = {"repos/o/r": {"visibility": "public", "allow_auto_merge": True, "name": "r", "zz": 1},
                   "repos/o/r/actions/permissions": {"enabled": True, "allowed_actions": "all"},
                   "repos/o/r/actions/permissions/workflow": {"default_workflow_permissions": "read",
                                                              "can_approve_pull_request_reviews": False},
                   "repos/o/r/topics": {"names": ["b", "a"]},
                   "repos/o/r/rules/branches/main": [{"type": "deletion", "x": 1}, {"type": "pull_request"}]}
        rc, out, err, calls = settings("--show", "o/r", GH_ANSWERS=json.dumps(answers))
        lines = out.splitlines()
        check("five compact lines, keys sorted, nothing written",
              rc == 0 and len(lines) == 5 and all(c["method"] == "GET" for c in calls)
              and lines[1:] == ['{"actions_enabled":true,"allowed_actions":"all"}',
                                '{"can_approve_pull_request_reviews":false,"default_workflow_permissions":"read"}',
                                '["b","a"]', '["deletion","pull_request"]'], f"rc={rc}\n{out}{err}")
        try:
            first = json.loads(lines[0]) if lines else {}
        except ValueError:
            first = {}
        check("…the settings line: the documented keys only, an absent one null",
              list(first) == sorted(first) and first.get("visibility") == "public" and "name" not in first
              and "zz" not in first and first.get("has_wiki", 0) is None and len(first) == 18, lines[0] if lines else "")

        rc, out, err, calls = settings("--help")
        check("--help: the usage, exit 0, no call", rc == 0 and "--show [owner/repo]" in out and calls == [],
              f"rc={rc}\n{out}{err}")

    print(f"\ntest_repo_settings_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
