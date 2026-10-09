#!/usr/bin/env python3
"""tools/fabric/github/repo_settings.py — reapply this repository's
GitHub-side settings (docs/adr/ADR-019-work-arrives-as-pull-requests.md §6)
to a repository, through tools/fabric/gh.py. It covers the repository,
its topics, Actions and workflow permissions, and the ruleset on main;
code scanning and secret scanning are set on GitHub by hand.
`fabric-repo-settings` runs it (ADR-040 Wave 1).

  fabric-repo-settings [owner/repo]     # default: BlueTeam-OU/agent-fabric
  fabric-repo-settings --show [owner/repo]

Idempotent: every call sets the documented value. The ruleset on main
is tools/fabric/github-ruleset-main.json, created or updated by name;
its one required check is ci.yml's ci-ok job, which stands for every
other job, so a job renamed in .github/workflows/ci.yml needs no change
here, and ci-ok renamed is renamed there too, or no PR can merge. It
never touches secrets (there are none) or collaborators.
"""
# The contract the port keeps, from the bash:
#   - argv: `--show` only as the first word; then the repository, by
#     default BlueTeam-OU/agent-fabric; a word after it is not read.
#   - --show: five lines on stdout, each compact JSON with sorted keys, as
#     gh's --jq printed them: the repository's settings, Actions, workflow
#     permissions, the topics, the rule types on main.
#   - apply: the repository, the topics, Actions, workflow permissions,
#     then the ruleset (PUT to the one named in the file, else POST), each
#     the same request the bash made; one line on stdout at the end.
#   - a refused call stops the run, exit 1, the call and GitHub's reason on
#     stderr; what was applied before it stays, and a rerun is safe.
# Changed, and said in j31's delivery: -h/--help prints this usage (the
# bash took it for a repository's name); the ruleset file is read before
# the first write, so a missing or broken one changes nothing; the
# rulesets are listed across every page (the bash read the first thirty,
# and a ruleset past them would have been created twice), and the
# organisation's are not among them (review of j31).
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402

DEFAULT_REPO = "BlueTeam-OU/agent-fabric"
RULESET = os.path.join(os.path.dirname(HERE), "github-ruleset-main.json")

REPOSITORY = {
    "description": "Control plane for the agents working on sibling repositories: identities, roles, memory, "
                   "model routing, messaging.",
    "default_branch": "main",
    "has_issues": True, "has_projects": True, "has_wiki": True, "has_discussions": False,
    "allow_merge_commit": True, "allow_squash_merge": True, "allow_rebase_merge": True,
    "allow_auto_merge": True, "delete_branch_on_merge": False, "allow_update_branch": False,
    "merge_commit_title": "MERGE_MESSAGE", "merge_commit_message": "PR_TITLE",
    "squash_merge_commit_title": "COMMIT_OR_PR_TITLE", "squash_merge_commit_message": "COMMIT_MESSAGES",
    "web_commit_signoff_required": False,
}
# Topics replace the whole list on every call, so this is the list.
TOPICS = ["agent-memory", "agent-orchestration", "ai-agents", "claude-code", "control-plane", "developer-tools",
          "llm-ops", "multi-agent-systems"]
ACTIONS = {"enabled": True, "allowed_actions": "all"}
WORKFLOW = {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": False}


def say(text: str) -> None:
    print(f"github-repo-settings: {text}", file=sys.stderr)


def _line(value) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def show(repo: str) -> None:
    r = gh.api(f"repos/{repo}") or {}
    print(_line({k: r.get(k) for k in ("visibility", *REPOSITORY)}))
    a = gh.api(f"repos/{repo}/actions/permissions") or {}
    print(_line({"actions_enabled": a.get("enabled"), "allowed_actions": a.get("allowed_actions")}))
    w = gh.api(f"repos/{repo}/actions/permissions/workflow") or {}
    print(_line({k: w.get(k) for k in WORKFLOW}))
    print(_line((gh.api(f"repos/{repo}/topics") or {}).get("names")))
    print(_line([rule.get("type") for rule in gh.api(f"repos/{repo}/rules/branches/main") or []]))


def ruleset() -> dict:
    """The ruleset file, read before anything is written."""
    try:
        with open(RULESET, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as e:
        raise gh.GhError("the ruleset", f"{RULESET} cannot be read: {e}") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("name"), str) or not doc["name"]:
        raise gh.GhError("the ruleset", f"{RULESET} names no ruleset")
    return doc


def apply(repo: str) -> None:
    rules = ruleset()
    gh.api(f"repos/{repo}", method="PATCH", body=REPOSITORY)
    gh.api(f"repos/{repo}/topics", method="PUT", body={"names": TOPICS})
    gh.api(f"repos/{repo}/actions/permissions", method="PUT", body=ACTIONS)
    gh.api(f"repos/{repo}/actions/permissions/workflow", method="PUT", body=WORKFLOW)
    # The ruleset: required checks and a pull request on main (ADR-019
    # rule 6), so auto-merge waits for green and nothing reaches main
    # another way. The repository's own rulesets only: the list includes
    # the organisation's by default, and one of the same name would be
    # matched and its id PUT to the repository, which GitHub refuses.
    ids = [r.get("id") for r in gh.api(f"repos/{repo}/rulesets?includes_parents=false", paginate=True)
           if isinstance(r, dict) and r.get("name") == rules["name"]]
    if ids:
        gh.api(f"repos/{repo}/rulesets/{ids[0]}", method="PUT", body=rules)
    else:
        gh.api(f"repos/{repo}/rulesets", method="POST", body=rules)


def run(argv: list[str]) -> int:
    if argv[:1] in (["-h"], ["--help"]):
        sys.stdout.write(__doc__.split("\n\n", 2)[1] + "\n")
        return 0
    showing = argv[:1] == ["--show"]
    rest = argv[1:] if showing else argv
    repo = rest[0] if rest and rest[0] else DEFAULT_REPO
    try:
        if showing:
            show(repo)
            return 0
        apply(repo)
    except gh.GhError as e:
        say(str(e) if showing else f"{e}; what was applied before it stays, and a rerun is safe")
        return 1
    print(f"github-repo-settings: applied to {repo} (docs/adr/ADR-019-work-arrives-as-pull-requests.md)")
    return 0


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
