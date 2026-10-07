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

The comment is for the reader: a bare SHA says nothing about which release
is running. On the same line it cannot go stale, because Dependabot rewrites
it together with the pin (.github/dependabot.yml). Dependabot does not need
it to update the pin: it reads the release from the upstream tag at the
pinned commit.

Exempt: a local action or reusable workflow (`./…`), which is this
repository at the commit being run, and a `docker://` image pinned by
`@sha256:` digest. A docker image by tag is rejected for the same reason a
tag is.

What this does NOT prove: that the SHA belongs to the named repository's own
history rather than a fork's (GitHub serves a fork's commit under the
parent's path), or that the comment names the release the SHA is in. Both
need the network; the diff that changes a pin is where they are read.

Two third-party uses on one line (a flow mapping, `- {uses: a@<sha>, …}`)
are refused: they would share one version comment, which can name only one
release.

    check_actions_pinned_by_sha.py [--root <dir>] [-h|--help]

The root is --root, else REPO_ROOT, else this repository. A managed
project's forwarder passes its own toplevel: the default is the fabric's
tree, never the project's.

Exit codes: 0 every action is pinned by SHA with its version comment;
1 at least one is not; 2 not checked (no workflow found, a bad argument,
a workflow that cannot be read).

Ported from devex-tooling's shell guard of the same name (itself ported from
gzapp's); the owner asked for new fabric tooling in Python.
"""
from __future__ import annotations

import os
import re
import sys

ME = "check_actions_pinned_by_sha"
# `uses` as a key wherever YAML lets GitHub read one: a block key, a list
# item's first key, quoted ("uses":), with a space before the colon, or
# inside a flow mapping (- {name: a, uses: x@v1}). Anchored only to what may
# precede a key, never to the line's start: that anchoring once let every
# one of those shapes pass unread.
USES_RE = re.compile(r"""(?:^|[\s{,\-])(?:"uses"|'uses'|uses)\s*:\s*("[^"]*"|'[^']*'|[^\s,}]+)""")
# A block key with nothing after it: its value is the next, more indented
# line, a plain scalar GitHub reads the same (review of #68: `- uses:` over
# `actions/checkout@v7` passed unread).
EMPTY_USES_RE = re.compile(r"""(?:^|[\s\-])(?:"uses"|'uses'|uses)\s*:\s*$""")
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


def split_comment(line: str) -> tuple[str, str]:
    """The line's YAML before its comment, and the comment: a `#` that
    starts the line or follows a space, outside quotes."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i], line[i + 1:]
    return line, ""


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
        return "carries no '# vX.Y.Z' comment on its line — the release a reader needs, rewritten with the pin"
    return None


class Unreadable(Exception):
    """A workflow that could not be read: the run checked nothing, exit 2."""


def needs_version_comment(ref: str) -> bool:
    """A third-party use that names its release in a comment: not a local
    action, and not a docker image by digest, which carries no comment —
    so two digests on one line share nothing (devex-tooling, seq 17579)."""
    ref = ref.strip().strip("'\"")
    return not (ref.startswith("./") or (ref.startswith("docker://") and "@sha256:" in ref))


def check(root: str) -> tuple[list[str], int]:
    """Findings, one line each, and the number of pinned uses."""
    findings, pinned = [], 0
    for path in workflow_files(root):
        rel = os.path.relpath(path, root)
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().split("\n")
        except (OSError, UnicodeDecodeError) as e:
            raise Unreadable(f"{rel} ({e.__class__.__name__})") from None
        for num, line in enumerate(lines, 1):
            code, comment = split_comment(line)
            refs = [(m.group(1), comment) for m in USES_RE.finditer(code)]
            third = [r for r, _ in refs if needs_version_comment(r)]
            if len(third) > 1:
                findings.append(f"FAIL: {rel}:{num} {len(third)} third-party uses on one line share one version "
                                "comment — put each on its own line")
                continue
            if EMPTY_USES_RE.search(code):
                # The value is a plain scalar on a following line indented
                # deeper than the key, comment-only lines skipped; its
                # version comment is read from that line, where the pin is.
                # A next line at the key's indent or less (the next key, a
                # new list item) means the key has no value (review of #68).
                # The KEY's column: a list item's `- uses:` indents its
                # siblings to the key, past the dash (review of #70).
                indent = len(line) - len(re.sub(r"^\s*-\s+", "", line) if re.match(r"^\s*-\s", line) else line.lstrip())
                nxt = next((ln for ln in lines[num:] if ln.strip() and not ln.lstrip().startswith("#")), "")
                deeper = nxt and (len(nxt) - len(nxt.lstrip())) > indent and not nxt.lstrip().startswith("- ")
                ncode, ncomment = split_comment(nxt) if deeper else ("", "")
                refs.append((ncode.strip() or "(nothing)", ncomment))
            for ref, comment in refs:
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


def main(argv: list[str]) -> int:
    root = None
    args = list(argv)
    while args:
        a = args.pop(0)
        if a in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        if a == "--root" or a.startswith("--root="):
            root = a.split("=", 1)[1] if "=" in a else (args.pop(0) if args else "")
            if not root:
                print(f"{ME}: --root needs a value", file=sys.stderr)
                return 2
            continue
        print(f"{ME}: unexpected argument: {a}", file=sys.stderr)
        return 2
    root = root or os.environ.get("REPO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not workflow_files(root):
        print(f"{ME}: no workflow under {root}/.github/workflows", file=sys.stderr)
        return 2
    try:
        findings, pinned = check(root)
    except Unreadable as e:
        # Exit 1 is a finding; a workflow that cannot be read was not checked.
        print(f"{ME}: a workflow could not be read: {e}", file=sys.stderr)
        return 2
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
    sys.exit(main(sys.argv[1:]))
