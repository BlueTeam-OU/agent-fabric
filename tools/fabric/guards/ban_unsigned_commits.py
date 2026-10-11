#!/usr/bin/env python3
"""tools/fabric/guards/ban_unsigned_commits.py -- every commit a push or a
branch adds carries a signature git can read.

WHY. The GitHub ruleset blocks an unsigned commit from merging, but only
after the push. A history rewrite made with git plumbing (commit-tree,
filter-branch) ignores commit.gpgsign: on 2026-10-11 one pushed 36 unsigned
commits that the ruleset then refused to merge. The guard is three things
(policies/AUTHORITY.md): the pre-push hook (githooks_prepush.py calls
`unsigned` for the refs pushed), this entry point for CI (the commits the
branch adds, the range found as ban_generated_by_attribution finds it), and
tests/test_ban_unsigned_commits.py.

"READABLE" IS `%G?` NOT `N`. Whether the signer's key is known is not asked:
CI has no keyring, so a good signature reads `E` there. The ruleset is the
verifier; this only keeps what plainly has no signature off the remote.

Contract: no arguments; cwd is the repository; env as in
ban_generated_by_attribution (GITHUB_EVENT_PATH, GITHUB_BASE_REF), with
AGENT_FABRIC_SIGNATURES_BASE naming the base ref of a hand run. Exit 0 every
commit is signed (or no range could be shown: said as NOT ENFORCED, never as
OK), 1 an unsigned commit, with one line naming them."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import git  # noqa: E402

SHOWN = 8


def unsigned(repo: str, *rev_args: str) -> list[tuple[str, str]]:
    """(short sha, subject) of every commit `git log <rev_args>` lists that
    has no signature. Merges are listed too. Raises git.GitError."""
    out = git.run(repo, "log", "--format=%H%x09%G?%x09%s", *rev_args, errors="replace").stdout
    found = []
    for line in out.splitlines():
        sha, _, rest = line.partition("\t")
        status, _, subject = rest.partition("\t")
        if status == "N":
            found.append((sha[:10], subject))
    return found


def refusal(found: list[tuple[str, str]]) -> str:
    names = ", ".join(f"{sha} {subject[:50]}" for sha, subject in found[:SHOWN])
    more = f" and {len(found) - SHOWN} more" if len(found) > SHOWN else ""
    return (f"{len(found)} unsigned commit(s): {names}{more} -- re-sign with "
            "`git rebase --exec 'git commit --amend --no-edit -S' <base>` "
            "(history rewritten by git plumbing ignores commit.gpgsign)")


def main(env: dict[str, str]) -> int:
    import ban_generated_by_attribution as attribution
    env = dict(env)
    env["AGENT_FABRIC_ATTRIBUTION_BASE"] = env.get("AGENT_FABRIC_SIGNATURES_BASE", "")
    try:
        rng = attribution.resolve_range(env)
        if rng is None:
            print("signatures: NOT ENFORCED -- no usable range (a shallow checkout with no event payload)")
            return 0
        found = unsigned(".", f"{rng[0]}..{rng[1]}")
    except git.GitError as e:
        print(f"signatures: NOT ENFORCED -- {e}")
        return 0
    if found:
        print(f"ban_unsigned_commits: FAIL {refusal(found)}", file=sys.stderr)
        return 1
    print("signatures: OK -- every commit the branch adds is signed")
    return 0


if __name__ == "__main__":
    sys.exit(main(dict(os.environ)))
