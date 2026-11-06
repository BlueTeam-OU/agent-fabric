#!/usr/bin/env python3
"""policies/hygiene.json: a GitHub URL, an <owner>/<repo>#N reference, and a gh api repos/ path or --repo argument never
carry a personal handle into a slice, skill or prompt section: an owner that is no listed organization is refused by lint and
becomes <owner> in a drain (j533). A personal handle in a distilled slice travels into every project's repository, a privacy
matter as a name is. Each pattern matches the owner alone, so the drain's substitution leaves the URL or reference readable
(#497 round 1 F3). Not read, because a path looks the same: a bare owner/repo in prose or a heading, a repo label, gh's -R
(#497 round 1 F1). The organizations the corpus already names are the list; owner, o and testorg are placeholders.
Plain script: prints ok/FAIL, exit 1 on any failure.
Kills: dropping any of the three patterns; one without the owner list, or with a list that lets an owner beginning with a
listed name through; an owner list that differs between the three; a lost case-insensitivity; a match wider than the owner;
GitHub's own routes read as owners."""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

LEAKS = [
    "Source: https://github.com/someperson/overgraph and its ROADMAP", "git@github.com:someperson/tool.git",
    "https://raw.githubusercontent.com/someperson/x/main/a.md", "https://api.github.com/repos/someperson/x/pulls",
    "see github.com/Someone-Else/tool/issues", "https://github.com/githubber/x", "https://github.com/BlueTeam/x",
    "https://github.com/BlueTeam-OU-evil/x", "the profile github.com/someperson.", "https://gist.github.com/someperson/abc",
    "fixed in someperson/overgraph#12", "the review on someperson/tool#7.", "(some-person/x_y#3)", "<someperson/tool#7>",
    "BlueTeam-OU-evil/x#1", "githubber/x#1",
    "gh api repos/someperson/x/pulls", "gh pr list --repo someperson/x", "gh pr list --repo=someperson/x", "--repo githubber/x",
]
FINE = [
    "https://github.com/BlueTeam-OU/herdr", "https://github.com/gzapi-org/x/pull/3", "https://github.com/BLUETEAM-OU/herdr",
    "git@github.com:apache/arrow.git", "https://github.com/github/codeql", "https://raw.githubusercontent.com/oxc-project/x/main/a",
    "https://api.github.com/repos/z-galaxy/zbus/pulls", "https://github.com/testorg/testrepo",
    "BlueTeam-OU/herdr#12 and gzapi-org/x#3", "owner/repo#4", "gh pr list --repo owner/repo", "gh pr list [--repo o/n]", "the proxy at github.com:443.", "<owner>/<repo>#4",
    # GitHub's own routes are no owner (#497 round 1 F2).
    "https://github.com/settings/tokens", "https://github.com/orgs/BlueTeam-OU/projects/1", "github.com/apps/claude",
    "https://github.com/user-attachments/assets/x.png", "github.com/marketplace/actions/x", "https://github.com/features/actions",
    # A path, a placeholder, a variable and a bare number are no owner (#497 round 1 F1).
    "src/a/b#9", "gh api repos/{owner}/{repo}", "--repo $GH_REPO", "github.com and github.io", "https://github.com/",
    "the OR/equality case", "## tests/run.sh", "x/y#", "~/projects/x#3", "a.b-c/x_y#3",
    "cp -R templates/base dest", "ls -R docs/adr", "~/repos/agent-fabric/tools", "/srv/git/repos/herdr/hooks",
    "the repo tools/fabric/lint.py", "the repository docs/adr records", "gh issue -R someperson/x list",
    "text then someperson/overgraph in prose", "## someperson/overgraph",
]
# The drain substitutes refer_as for the match: the text around the owner survives (#497 round 1 F3).
SUBSTITUTED = {
    "Source: https://github.com/someperson/overgraph and its ROADMAP.md": "Source: https://github.com/<owner>/overgraph and its ROADMAP.md",
    "Run gh pr list --repo someperson/tool to see them.": "Run gh pr list --repo <owner>/tool to see them.",
    "fixed in someperson/overgraph#12, then": "fixed in <owner>/overgraph#12, then",
    "gh api repos/someperson/x/pulls": "gh api repos/<owner>/x/pulls",
    "git@github.com:someperson/tool.git": "git@github.com:<owner>/tool.git",
    "https://api.github.com/repos/someperson/x": "https://api.github.com/repos/<owner>/x",
}


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    from fabric.assembler.core import hygiene_substitute

    with open(os.path.join(ROOT, "policies", "hygiene.json"), encoding="utf-8") as fh:
        entries = json.load(fh)["patterns"]
    owner = [e for e in entries if "owner that is no listed organization" in e["label"]]
    check("three patterns, each with refer_as <owner> and the case-insensitive flag",
          len(owner) == 3 and all(e.get("refer_as") == "<owner>" and e.get("flags") == "i" for e in owner))
    # The URL pattern's routes lookahead has the same shape: the owner list is the one naming the fabric's organization.
    found = [[x for x in re.findall(r"\(\?!\(\?:([^)]*)\)\(\?!\[\\w-\]\)\)", e["pattern"]) if "BlueTeam-OU" in x.split("|")]
             for e in owner]
    check("each pattern carries the owner list, closed by a name boundary", len(found) == 3 and all(len(f) == 1 for f in found))
    lists = {f[0] for f in found if f}
    check("one owner list, in all three", len(lists) == 1)
    listed = set(next(iter(lists)).split("|")) if lists else set()
    for org in ("BlueTeam-OU", "gzapi-org"):
        check(f"{org} is listed", org in listed)
    compiled = [re.compile(e["pattern"], re.I) for e in owner]
    for text in LEAKS:
        check(f"matched: {text!r}", any(p.search(text) for p in compiled))
    for text in FINE:
        check(f"not matched: {text!r}", not any(p.search(text) for p in compiled))
    for pat, texts in zip(compiled, (("github.com/someperson/x", "github.com/githubber/x", "github.com/BlueTeam-OU-x/y"),
                                     ("someperson/x#1", "githubber/x#1", "BlueTeam-OU-x/y#1"),
                                     ("--repo someperson/x", "--repo githubber/x", "--repo BlueTeam-OU-x/y"))):
        for text in texts:
            m = pat.search(text)
            check(f"{text!r} is caught by its own pattern, the owner alone", bool(m) and "/" not in m.group(0))
    triples = [(re.compile(e["pattern"], re.I), e["label"], e["refer_as"]) for e in owner]
    for text, want in SUBSTITUTED.items():
        got, _ = hygiene_substitute(text, "test", triples)
        check(f"{text!r} reads {want!r}", got == want)
    print("test_hygiene_github_owner:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
