#!/usr/bin/env python3
"""tools/fabric/guards/commit_kind.py — the commit-msg hook's Kind: rule
(agent-fabric ADR-019 §5 rule 3), out of the shell hook so that git's argv
can be parsed the way git parses it.

    commit_kind.py <message-file> <pid of the git that runs the hook>

Every commit declares its kind in its trailer block: `Kind: work`, or
`Kind: review-fix` with the `Answers: <labels or thread>` it answers. An
Answers: trailer alone is stamped review-fix, and git's own revert line
work; anything else undeclared is refused (exit 1) with what to add. A merge
is exempt: one being made has MERGE_HEAD; one being amended has none, and is
told by HEAD being a merge and `--amend` among the options of the git that
runs the hook. A matched subject also exempted `commit -C HEAD` on top of a
merge, and a bare word match `commit -m --amend` (reviews of #120), so the
argv is walked as git reads it: an option's value is skipped, `--` ends the
options, and a unique prefix of `--amend` counts. An argv that cannot be
read exempts nothing.

git runs no commit-msg hook for `git revert` or for a rebase's picks, a
conflict's `--continue` included; a reword or a squash runs it (measured,
pinned in tests/test_githooks_cli.py).
"""
from __future__ import annotations

import re
import subprocess
import sys

# git's own options before the subcommand that take their value as the next
# word (`git -C <path> commit`, `git -c k=v commit`).
GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix"}
# git commit's options whose value may be the next word.
COMMIT_LONG_WITH_VALUE = {"--message", "--file", "--reedit-message", "--reuse-message", "--template", "--author",
                          "--date", "--cleanup", "--trailer", "--fixup", "--squash", "--pathspec-from-file"}
COMMIT_SHORT_WITH_VALUE = set("mFcCt")
# Every unique prefix of --amend among git commit's long options: no other
# long option of git commit begins with "--am".
AMEND = {"--am", "--ame", "--amen", "--amend"}
REVERT_RE = re.compile(r"^This reverts commit [0-9a-f]{7,40}", re.M)

REFUSAL = """commit-msg: every commit declares its kind in its trailers (the last paragraph):
  Kind: work                    new work, a bug fix of the project, docs, a record
  Answers: <labels or thread>   a commit answering a review of this PR (Kind: review-fix is added)
pr-gate.sh and the PR's count check read it; nothing guesses from the subject."""


def is_amend(argv: list[str]) -> bool:
    """Whether a git argv is `git … commit … --amend …`, read as git reads it."""
    i = 1
    while i < len(argv) and argv[i].startswith("-"):
        i += 2 if argv[i] in GLOBAL_WITH_VALUE else 1
    if i >= len(argv) or argv[i] != "commit":
        return False
    i += 1
    while i < len(argv):
        word = argv[i]
        if word == "--":
            return False
        if word.startswith("--"):
            if word in AMEND:
                return True
            if word in COMMIT_LONG_WITH_VALUE:
                i += 1
        elif word.startswith("-") and len(word) > 1:
            # A cluster such as -am: a short option that takes a value ends
            # it, with the value attached or as the next word.
            for j, ch in enumerate(word[1:], start=1):
                if ch in COMMIT_SHORT_WITH_VALUE:
                    if j == len(word) - 1:
                        i += 1
                    break
        i += 1
    return False


def parent_argv(pid: str) -> list[str] | None:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read()
    except OSError:
        return None
    return [w.decode("utf-8", "replace") for w in raw.split(b"\0") if w]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def is_merge(pid: str) -> bool:
    merge_head = git("rev-parse", "--git-path", "MERGE_HEAD").stdout.strip()
    if merge_head:
        try:
            with open(merge_head):
                return True
        except OSError:
            pass
    if len(git("rev-list", "--parents", "-n", "1", "HEAD").stdout.split()) <= 2:
        return False
    argv = parent_argv(pid)
    return argv is not None and is_amend(argv)


def check(msg_path: str, pid: str) -> int:
    if is_merge(pid):
        return 0
    trailers = git("interpret-trailers", "--parse", msg_path).stdout.splitlines()
    pairs = [(k.strip().lower(), v.strip()) for k, sep, v in (t.partition(":") for t in trailers) if sep]
    kinds = [v for k, v in pairs if k == "kind"]
    kind = "".join(kinds[-1].split()).lower() if kinds else ""
    answers = sum(1 for k, _ in pairs if k == "answers")
    if not kind:
        with open(msg_path, encoding="utf-8", errors="replace") as f:
            body = "".join(line for line in f if not line.startswith("#"))
        if answers:
            kind = "review-fix"
        elif REVERT_RE.search(body):
            kind = "work"
        if kind:
            git("interpret-trailers", "--in-place", "--trailer", f"Kind: {kind}", msg_path)
    if kind == "work":
        return 0
    if kind == "review-fix":
        if answers:
            return 0
        print("commit-msg: Kind: review-fix needs the review it answers: add 'Answers: <labels or thread>'.",
              file=sys.stderr)
        return 1
    print(REFUSAL, file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: commit_kind.py <message-file> <git-pid>", file=sys.stderr)
        return 2
    try:
        return check(argv[1], argv[2])
    except Exception as e:  # noqa: BLE001 - a hook that cannot judge refuses, and says why
        print(f"commit-msg: the Kind check could not run ({type(e).__name__}: {e})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
