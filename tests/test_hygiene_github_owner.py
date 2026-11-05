#!/usr/bin/env python3
"""policies/hygiene.json: a GitHub URL, an <owner>/<repo>#N reference, a repos/ path or --repo/-R argument, and a repo or repository
label before an <owner>/<repo>, never reach a slice, skill or prompt section under an owner that is no listed organization
(a bare heading such as ## microsoft/apm is not caught: tests/run.sh and commit/push read the same): a personal handle in a distilled slice travels into every project's repository, a privacy matter as a name
is (j533). The organizations the corpus already names are the list; the placeholders (owner, o, testorg) stand for no one.
Plain script: prints ok/FAIL, exit 1 on any failure.
Kills: dropping any of the four patterns; one without the owner list, or with a list not anchored by the slash (github/
letting githubber/ through); an owner list that differs between the four; a lost case-insensitivity."""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

LEAKS = [
    "Source: https://github.com/someperson/overgraph and its ROADMAP", "git@github.com:someperson/tool.git",
    "https://raw.githubusercontent.com/someperson/x/main/a.md", "https://api.github.com/repos/someperson/x/pulls",
    "see github.com/Someone-Else/tool/issues", "https://github.com/githubber/x", "https://github.com/BlueTeam/x",
    "fixed in someperson/overgraph#12", "the review on someperson/tool#7.", "(a.b-c/x_y#3)",
    "gh api repos/someperson/x/pulls", "gh pr list --repo someperson/x", "gh pr list --repo=someperson/x", "gh issue -R someperson/x list",
    "the repo someperson/overgraph", "repository: `Someone-Else/tool`", "Repo: someperson/tool.",
]
FINE = [
    "https://github.com/BlueTeam-OU/herdr", "https://github.com/gzapi-org/x/pull/3", "https://github.com/BLUETEAM-OU/herdr",
    "git@github.com:apache/arrow.git", "https://github.com/github/codeql", "https://raw.githubusercontent.com/oxc-project/x/main/a",
    "https://api.github.com/repos/z-galaxy/zbus/pulls", "https://github.com/testorg/testrepo",
    "BlueTeam-OU/herdr#12 and gzapi-org/x#3", "owner/repo#4", "gh issue -R owner/repo delete 5", "gh pr list --repo o/n",
    "the repo apache/arrow", "repository: BlueTeam-OU/herdr",
    # A path, a placeholder, a variable and a bare number are no owner.
    "src/a/b#9", "repos/{owner}/{repo}", "--repo $GH_REPO", "github.com and github.io", "https://github.com/",
    "the OR/equality case", "## tests/run.sh", "the repo\n\ntools/fabric", "a heading microsoft/apm in prose", "x/y#", "~/projects/x#3",
    # Only a reference with a number, a flag, a URL or a repo label is read as one: someperson/overgraph in prose is not (a known gap).
    "text then someperson/overgraph in prose",
]


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    with open(os.path.join(ROOT, "policies", "hygiene.json"), encoding="utf-8") as fh:
        entries = json.load(fh)["patterns"]
    owner = [e for e in entries if "owner that is no listed organization" in e["label"]]
    check("four patterns, each with a refer_as and the case-insensitive flag",
          len(owner) == 4 and all(e.get("refer_as") and e.get("flags") == "i" for e in owner))
    lists = {m.group(1) for e in owner if (m := re.search(r"\(\?!\(\?:([^)]*)\)/\)", e["pattern"]))}
    check("one owner list, in all four", len(lists) == 1 and all("(?!(?:" in e["pattern"] for e in owner))
    listed = set(next(iter(lists)).split("|")) if lists else set()
    for org in ("BlueTeam-OU", "gzapi-org"):
        check(f"{org} is listed", org in listed)
    compiled = [re.compile(e["pattern"], re.I) for e in owner]
    for text in LEAKS:
        check(f"matched: {text!r}", any(p.search(text) for p in compiled))
    for text in FINE:
        check(f"not matched: {text!r}", not any(p.search(text) for p in compiled))
    for pat, text in zip(compiled, ("github.com/someperson/x", "someperson/x#1", "--repo someperson/x", "repo someperson/x")):
        check(f"{text!r} is caught by its own pattern", bool(pat.search(text)))
    print("test_hygiene_github_owner:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
