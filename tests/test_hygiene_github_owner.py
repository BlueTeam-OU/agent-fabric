#!/usr/bin/env python3
"""policies/hygiene.json: a GitHub URL, an <owner>/<repo>#N reference, a --repo, gh repo or uses: argument, and a gh api
repos/ path never carry a personal handle into a slice, skill or prompt section: an owner that is no listed organization is refused by lint and
becomes <owner> in a drain (j533). A personal handle in a distilled slice travels into every project's repository, a privacy
matter as a name is. Each pattern matches the owner alone, so the drain's substitution leaves the URL or reference readable
(#497 round 1 F3). Not read, because a path looks the same: a bare owner/repo in prose or a heading, a repo label, gh's -R,
a variable such as REPO=owner/repo (#497 round 1 F1), a gh api path after a flag that ends in no API resource the
fourth pattern lists (#497 round 3 F6). The organizations the corpus already names are the list; owner, o and testorg are placeholders.
Plain script: prints ok/FAIL, exit 1 on any failure.
Kills: dropping any of the four patterns; one without the owner list, or with a list that lets an owner beginning with a
listed name through; an owner list that differs between the four; a lost case-insensitivity; a match wider than the owner;
GitHub's own routes, its API root or another of its sites read as owners; the handle after sponsors/ or users/ left in."""
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
    # A Sponsors page and the users API name the owner one segment on (#497 round 2 F5).
    "https://github.com/sponsors/someperson", "curl https://api.github.com/users/someperson",
    # gh api with a flag or a quote before repos/, as the corpus writes it (#497 round 2 F6).
    "gh api --paginate repos/someperson/x/pulls", "gh api -X POST repos/someperson/x/issues",
    'gh api -H "Accept: x" repos/someperson/x/code-scanning/alerts', 'gh api "repos/someperson/x/pulls"', "gh api  repos/someperson/x/pulls",
    'gh pr list --repo "someperson/x"', "gh repo clone someperson/x", "uses: someperson/action@v1",
    # A user's Projects board, and the hosts beside github.com that carry the owner first (#497 round 3 F7, F8).
    "https://github.com/users/someperson/projects/1", "https://gist.githubusercontent.com/someperson/abc123/raw/f.sh",
    "https://codeload.github.com/someperson/x/tar.gz/main", "https://uploads.github.com/repos/someperson/x/releases/1/assets",
    "https://media.githubusercontent.com/media/someperson/x/main/f.bin", "https://www.github.com/someperson/x",
    "https://www.github.com/users/someperson/projects/2", "https://www.github.com/sponsors/someperson",
    # gh api with a flag, on an API resource the fourth pattern lists (#497 round 3 F6).
    "gh api --paginate repos/someperson/x/contributors", 'gh api -H "x" repos/someperson/x/pages',
    "gh api --paginate repos/someperson/x/stats/contributors",
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
    "text then someperson/overgraph in prose", "## someperson/overgraph", "REPO=someperson/x",
    # More of GitHub's routes, and its docs host (#497 round 2 F2).
    "https://github.com/advisories/GHSA-abcd-1234", "https://docs.github.com/en/rest/pulls", "https://github.com/copilot",
    "https://github.com/new", "https://github.com/pulls", "https://github.com/codespaces", "https://github.com/explore",
    "https://github.com/sponsors/BlueTeam-OU", "https://api.github.com/users/apache",
    # A relative path with a heading anchor, and repos/ in a path with no API resource after it.
    "adr/ADR-013.md#2-hygiene", "under repos/herdr/hooks dir", "gh api -H \"Accept: x\" repos/<o>/<r>/code-scanning",
    # GitHub's own Actions and Docker's are organizations; an avatar id and a Sponsors route are no owner.
    "uses: actions/checkout@v4", "uses: docker/build-push-action@v5", "https://avatars.githubusercontent.com/u/12345",
    "https://user-images.githubusercontent.com/12345/x.png", "https://github.com/sponsors/accounts",
    "https://support.github.com/contact", "https://skills.github.com/x",
    # GitHub's API root and its other sites, and a host that only ends in github.com (#497 round 4 F9).
    "https://api.github.com/graphql", "https://api.github.com/meta", "https://api.github.com/user/repos",
    "https://api.github.com/rate_limit", "https://cli.github.com/manual/gh_api", "https://desktop.github.com/download",
    "https://pages.github.com/versions", "https://status.github.com/x", "https://mygithub.com/foo",
    "https://objects.githubusercontent.com/github-production-release-asset-2e65be/1", "https://camo.githubusercontent.com/abc123",
    # A stated gap: gh api after a flag on a path that ends in no listed API resource.
    "gh api -X PATCH repos/someperson/x -f a=b",
    # A bare number after a host is a gist id or an asset, never an owner (#497 round 5 F10).
    "https://gist.github.com/1234567", "https://gist.github.com/1234567.js", "https://github.com/sponsors/1234",
]
# The drain substitutes refer_as for the match: the text around the owner survives (#497 round 1 F3).
SUBSTITUTED = {
    "Source: https://github.com/someperson/overgraph and its ROADMAP.md": "Source: https://github.com/<owner>/overgraph and its ROADMAP.md",
    "Run gh pr list --repo someperson/tool to see them.": "Run gh pr list --repo <owner>/tool to see them.",
    "fixed in someperson/overgraph#12, then": "fixed in <owner>/overgraph#12, then",
    "gh api repos/someperson/x/pulls": "gh api repos/<owner>/x/pulls",
    "git@github.com:someperson/tool.git": "git@github.com:<owner>/tool.git",
    "https://api.github.com/repos/someperson/x": "https://api.github.com/repos/<owner>/x",
    "https://github.com/sponsors/someperson": "https://github.com/sponsors/<owner>",
    "https://api.github.com/users/someperson": "https://api.github.com/users/<owner>",
    'gh api -H "Accept: x" repos/someperson/x/pulls': 'gh api -H "Accept: x" repos/<owner>/x/pulls',
    "uses: someperson/action@v1": "uses: <owner>/action@v1",
    "https://github.com/users/someperson/projects/1": "https://github.com/users/<owner>/projects/1",
    "https://gist.githubusercontent.com/someperson/abc/raw/f.sh": "https://gist.githubusercontent.com/<owner>/abc/raw/f.sh",
    "https://uploads.github.com/repos/someperson/x/releases": "https://uploads.github.com/repos/<owner>/x/releases",
    "https://media.githubusercontent.com/media/someperson/x/main/f": "https://media.githubusercontent.com/media/<owner>/x/main/f",
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
    check("four patterns, each with refer_as <owner> and the case-insensitive flag",
          len(owner) == 4 and all(e.get("refer_as") == "<owner>" and e.get("flags") == "i" for e in owner))
    # The URL pattern's routes lookahead has the same shape: the owner list is the one naming the fabric's organization.
    found = [[x for x in re.findall(r"\(\?!\(\?:([^)]*)\)\(\?!\[\\w-\]\)\)", e["pattern"]) if "BlueTeam-OU" in x.split("|")]
             for e in owner]
    check("each pattern carries the owner list, closed by a name boundary", len(found) == 4 and all(len(f) == 1 for f in found))
    lists = {f[0] for f in found if f}
    check("one owner list, in all four", len(lists) == 1)
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
                                     ("--repo someperson/x", "--repo githubber/x", "--repo BlueTeam-OU-x/y"),
                                     (" repos/someperson/x/pulls", " repos/githubber/x/pulls", " repos/BlueTeam-OU-x/y/pulls"))):
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
