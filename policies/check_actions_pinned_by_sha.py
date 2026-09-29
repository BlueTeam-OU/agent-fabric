#!/usr/bin/env python3
"""policies/check_actions_pinned_by_sha.py

Every third-party action a workflow `uses:` is pinned to a full commit SHA,
with the release it is in as a trailing comment:

    uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

WHY. A tag is a movable pointer in someone else's repository. Whoever can
push to that repository (its maintainers, or anyone who steals one of their
tokens) can point `@v7` at new code, and every workflow here runs it on its
next trigger, with this repository's GITHUB_TOKEN and whatever secrets the
job holds. It has happened: in March 2025 a widely used third-party action
had every one of its tags rewritten to a commit that dumped runner secrets
into the logs. A commit SHA cannot be moved; the code it names is the code
that was reviewed when the pin changed.

The comment is not decoration. Dependabot's github-actions ecosystem updates
a SHA pin only when it can read the version beside it, and rewrites both
together; without the comment the pin freezes silently and the repository
stops receiving the actions' security fixes. A reader also needs it: a bare
SHA says nothing about which release is running.

Exempt: a local action or reusable workflow (`./…`), which is this
repository at the commit being run, and a `docker://` image pinned by
`@sha256:` digest. A docker image by tag is rejected for the same reason a
tag is.

What this does NOT prove: that the SHA belongs to the named repository's own
history rather than a fork's (GitHub serves a fork's commit under the
parent's path), or that the comment names the release the SHA is in. Both
need the network; the diff that changes a pin is where they are read.

Exit codes: 0 every action is pinned by SHA with its version comment;
1 at least one is not; 2 invocation problem (no workflow found).

Ported from devex-tooling's shell guard of the same name (itself ported from
gzapp's); the owner asked for new fabric tooling in Python.
"""
from __future__ import annotations

import os
import re
import sys

ME = "check_actions_pinned_by_sha"
# `uses:` as a step key or as a list item's first key; a commented-out line
# starts with `#` and does not match.
USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S.*)$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^v?[0-9]+(?:\.[0-9]+)*(?:[-+][0-9A-Za-z.-]+)?$")


def workflow_files(root: str) -> list[str]:
    out = []
    wf = os.path.join(root, ".github", "workflows")
    if os.path.isdir(wf):
        out += [os.path.join(wf, f) for f in sorted(os.listdir(wf)) if re.search(r"\.ya?ml$", f)]
    actions = os.path.join(root, ".github", "actions")
    for dirpath, _, names in sorted(os.walk(actions)):
        out += [os.path.join(dirpath, n) for n in sorted(names) if n in ("action.yml", "action.yaml")]
    return out


def judge(ref: str, comment: str) -> str | None:
    """The reason a use fails, or None when it is pinned (or exempt)."""
    if ref.startswith("docker://"):
        if "@sha256:" in ref:
            return None if DIGEST_RE.match(ref.rsplit("@sha256:", 1)[1]) else "a sha256 digest is 64 hex characters"
        return "a docker action is pinned by @sha256: digest, not by tag"
    if "@" not in ref:
        return "names no ref at all — it runs the default branch"
    at = ref.rsplit("@", 1)[1]
    if not SHA_RE.match(at):
        return f"is pinned to '{at}', which its owner can move — pin the 40-character commit SHA"
    if not VERSION_RE.match(comment):
        return "carries no '# vX.Y.Z' comment — Dependabot cannot update a pin it cannot read the version of"
    return None


def check(root: str) -> tuple[list[str], int]:
    """Findings, one line each, and the number of pinned uses."""
    findings, pinned = [], 0
    for path in workflow_files(root):
        rel = os.path.relpath(path, root)
        with open(path, encoding="utf-8") as fh:
            for num, line in enumerate(fh, 1):
                m = USES_RE.match(line.rstrip("\n"))
                if not m:
                    continue
                rest = m.group(1)
                ref, _, comment = rest.partition("#")
                ref = ref.strip().strip("'\"")
                if ref.startswith("./"):
                    continue
                why = judge(ref, comment.strip())
                if why:
                    # A reason that is a sentence of its own ("a docker action is…")
                    # follows a dash; one that continues the ref ("is pinned to…") does not.
                    sep = " — " if why.startswith("a ") else " "
                    findings.append(f"FAIL: {rel}:{num} '{ref}'{sep}{why}")
                else:
                    pinned += 1
    return findings, pinned


def main() -> int:
    root = os.environ.get("REPO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not workflow_files(root):
        print(f"{ME}: no workflow under {root}/.github/workflows", file=sys.stderr)
        return 2
    findings, pinned = check(root)
    if findings:
        print("\n".join(findings))
        print("\nA tag or branch is a pointer the action's owner — or whoever holds\n"
              "their token — can move to new code, which then runs here with this\n"
              "repository's token and secrets. Resolve the release to its commit:\n\n"
              "    git ls-remote --tags https://github.com/<owner>/<repo> 'v1.2.3*'\n\n"
              "(an annotated tag lists its commit on the '^{}' line) and write\n"
              "    uses: <owner>/<repo>@<40-hex sha> # v1.2.3")
        return 1
    print(f"{ME}: OK — {pinned} third-party action use(s), every one pinned by SHA with its version.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
