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
argv is walked as git reads it: a long option is resolved by its unique
prefix against git's own table, an option's value is skipped (`--mess
--amend` is a message), `--` ends the options, and only --amend or a unique
prefix of it counts (review of #125). An argv that cannot be
read exempts nothing.

git runs no commit-msg hook for `git revert`, for a rebase's picks (a
conflict's `--continue` included) or for its squashes; a reword runs it
(git 2.56, measured and pinned in tests/test_githooks_cli.py). A squash of
undeclared commits therefore lands undeclared and is counted the old way.
"""
from __future__ import annotations

import re
import subprocess
import sys

# git's own options before the subcommand that take their value as the next
# word (`git -C <path> commit`, `git -c k=v commit`).
GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix",
                     "--attr-source"}
# git commit's long options, as `git commit --git-completion-helper` lists
# them on 2.56 (a trailing "=" marks one whose value may be the next word).
# git accepts any unique prefix of a long option (`--mess` is --message), so
# a word is resolved against the table before it is judged: a value-taking
# option's next word is its value, never an option. The installed git's own
# table is read when it can be; this copy is the fallback.
COMMIT_LONG_OPTIONS = (
    "--quiet --verbose --file= --author= --date= --message= --reedit-message= --reuse-message= --fixup= "
    "--squash= --reset-author --trailer= --signoff --template= --edit --cleanup= --status --gpg-sign --all "
    "--include --interactive --patch --unified= --inter-hunk-context= --only --no-verify --dry-run --short "
    "--branch --ahead-behind --porcelain --long --null --amend --no-post-rewrite --untracked-files "
    "--pathspec-from-file= --pathspec-file-nul --verify --post-rewrite").split()
COMMIT_SHORT_WITH_VALUE = set("mFcCt")
REVERT_RE = re.compile(r"^This reverts commit [0-9a-f]{7,40}", re.M)

REFUSAL = """commit-msg: every commit declares its kind in its trailers (the last paragraph):
  Kind: work                    new work, a bug fix of the project, docs, a record
  Answers: <labels or thread>   a commit answering a review of this PR (Kind: review-fix is added)
pr-gate.sh and the PR's count check read it; nothing guesses from the subject."""


def commit_options() -> list[str]:
    """git commit's long options as the installed git lists them, else the
    copy above. Negations (`--no-…`) are left out: none takes a value, and
    none is --amend."""
    try:
        out = subprocess.run(["git", "commit", "--git-completion-helper"], capture_output=True, text=True,
                             timeout=5).stdout.split()
    except (OSError, subprocess.SubprocessError):
        out = []
    found = [w for w in out if w.startswith("--") and w != "--" and not w.startswith("--no-")]
    return found or COMMIT_LONG_OPTIONS


def resolve_long(word: str, options: list[str]) -> str | None:
    """The long option a word names, as git resolves a unique prefix: the
    option with its "=" if it takes a value, or None when the word names no
    option or several."""
    exact = [o for o in options if o.rstrip("=") == word]
    if exact:
        return exact[0]
    found = [o for o in options if o.rstrip("=").startswith(word)]
    return found[0] if len(found) == 1 else None


def is_amend(argv: list[str], options: list[str] | None = None) -> bool:
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
            if "=" not in word:
                option = resolve_long(word, options if options is not None else COMMIT_LONG_OPTIONS)
                if option == "--amend":
                    return True
                if option and option.endswith("="):
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
    return argv is not None and is_amend(argv, commit_options())


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
