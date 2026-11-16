#!/usr/bin/env python3
"""tools/fabric/guards/commit_kind.py's argv walk: what counts as
`git commit --amend` when the hook reads the argv of the git that runs it
(review of #120: a word match exempted `commit -m --amend`)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric", "guards"))
import commit_kind  # noqa: E402

CASES = [
    (["git", "commit", "--amend", "--no-edit"], True, "the flag"),
    (["/usr/bin/git", "commit", "--amen", "--no-edit"], True, "a unique prefix"),
    (["git", "commit", "--am"], True, "the shortest unique prefix"),
    (["git", "-C", "/r", "-c", "k=v", "commit", "--amend"], True, "global options with values before the subcommand"),
    (["git", "commit", "-m", "--amend"], False, "--amend as -m's value"),
    (["git", "commit", "-m", "x", "-m", "--amend"], False, "as a second -m's value"),
    (["git", "commit", "-am", "--amend"], False, "as the value ending a short cluster"),
    (["git", "commit", "--message", "--amend"], False, "as --message's value"),
    (["git", "commit", "--message=--amend"], False, "attached to --message"),
    (["git", "commit", "-m--amend"], False, "attached to -m"),
    (["git", "commit", "--", "--amend"], False, "a pathspec after --"),
    (["git", "commit", "-q", "-C", "HEAD"], False, "-C HEAD reuses a message, it does not amend"),
    (["git", "commit", "-C", "--amend"], False, "-C's value"),
    (["git", "-C", "commit", "status", "--amend"], False, "another subcommand"),
    (["git", "commit", "--a"], False, "an ambiguous prefix"),
    (["git"], False, "no subcommand"),
    (["git", "commit", "--mess", "--amend"], False, "--amend as the value of an abbreviated --message (review of #125)"),
    (["git", "commit", "--fil", "--amend"], False, "...of an abbreviated --file"),
    (["git", "commit", "--no-edit", "--amend"], True, "a boolean option before --amend"),
    (["git", "--attr-source", "x", "commit", "--amend"], True, "a global option with a separate value"),
    # The last of --amend and --no-amend wins, as git applies it: on a merge
    # HEAD `--amend --no-am` makes a new one-parent commit on top (measured on
    # git 2.56), which must declare its kind (review of #125, Codex thread).
    (["git", "commit", "--amend", "--no-amend", "-m", "x"], False, "a later --no-amend negates"),
    (["git", "commit", "--amend", "--no-am", "-m", "x"], False, "...as a unique prefix of it"),
    (["git", "commit", "--no-amend", "--amend"], True, "a later --amend wins over --no-amend"),
    (["git", "commit", "--no-verify", "--amend"], True, "--no-verify is its own option, not a negation"),
    (["git", "commit", "--amend", "--", "--no-amend"], True, "a --no-amend pathspec after --"),
    # Mutation: commit_kind.py:79 `len(found) == 1` -> `>= 1` (an ambiguous --a resolves to --author=, which eats --amend)
    (["git", "commit", "--a", "--amend"], True, "an ambiguous prefix names no option, so it swallows no next word"),
]

MSG_REVERT = 'Revert "x"\n\nThis reverts commit {sha}.\n'
MSG_NONE = "subject\n\nbody only\n"
MSG_FIX_NO_ANSWERS = "subject\n\nKind: review-fix\n"
MSG_FIX = "subject\n\nKind: review-fix\nAnswers: F1\n"


def git(repo: str, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "AGENT_FABRIC_"))}
    subprocess.run(["git", "-C", repo, "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                    "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True, env=env)


def repo_with(parents: int, merge_head: bool, tmp: str) -> str:
    """A repo whose HEAD has `parents` (1 or 2) parents' worth of history; with `merge_head`, a MERGE_HEAD file as
    a mid-merge git leaves it."""
    repo = tempfile.mkdtemp(prefix="ck.", dir=tmp)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "commit", "-q", "--allow-empty", "-m", "root")
    git(repo, "commit", "-q", "--allow-empty", "-m", "one")
    if parents == 2:
        git(repo, "switch", "-q", "-c", "side", "HEAD~1")
        git(repo, "commit", "-q", "--allow-empty", "-m", "side")
        git(repo, "switch", "-q", "main")
        git(repo, "merge", "-q", "--no-ff", "-m", "merge", "side")
    if merge_head:
        head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        with open(os.path.join(repo, ".git", "MERGE_HEAD"), "w") as f:
            f.write(head)
    return repo


def run_check(repo: str, msg: str, parent_argv: list[str] | None) -> tuple[int, str]:
    """commit_kind.check() inside `repo` on a message file, the commit's parent process reading as `parent_argv`;
    returns (rc, the message file afterwards)."""
    path = os.path.join(repo, "MSG")
    with open(path, "w") as f:
        f.write(msg)
    saved_argv, saved_cwd = commit_kind.parent_argv, os.getcwd()
    commit_kind.parent_argv = lambda pid: parent_argv
    os.chdir(repo)
    try:
        rc = commit_kind.check(path, "1")
    finally:
        os.chdir(saved_cwd)
        commit_kind.parent_argv = saved_argv
    with open(path) as f:
        return rc, f.read()


def check_cases() -> list[tuple[str, bool]]:
    amend = ["git", "commit", "--amend", "--no-edit"]
    out: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix="ckt.") as tmp:
        one, merging, merged = repo_with(1, False, tmp), repo_with(1, True, tmp), repo_with(2, False, tmp)
        # Mutation: commit_kind.py:135 `if merge_head:` -> `if False:`, and :148 `if is_merge(pid):` -> `if False:`
        rc, _ = run_check(merging, MSG_NONE, None)
        out.append(("a mid-merge commit (MERGE_HEAD) needs no Kind", rc == 0))
        rc, _ = run_check(one, MSG_NONE, None)
        out.append(("a plain commit without a Kind is refused", rc == 1))
        # Mutation: commit_kind.py:141 `<= 2` -> `<= 1` (a one-parent HEAD under an amend is no merge)
        rc, _ = run_check(one, MSG_NONE, amend)
        out.append(("amending a one-parent commit still needs its Kind", rc == 1))
        rc, _ = run_check(merged, MSG_NONE, amend)
        out.append(("amending a two-parent merge needs no Kind", rc == 0))
        rc, _ = run_check(merged, MSG_NONE, ["git", "commit", "-m", "x"])
        out.append(("a fresh commit on a merge HEAD (no amend) needs its Kind", rc == 1))
        # Mutation: commit_kind.py:160 `elif REVERT_RE.search(body):` -> `elif False:`
        rc, text = run_check(one, MSG_REVERT.format(sha="a" * 40), None)
        out.append(("a revert subject is stamped Kind: work", rc == 0 and "Kind: work" in text))
        # Mutation: commit_kind.py:50 `{7,40}` -> `{8,40}` (git's abbreviated 7-hex sha)
        rc, text = run_check(one, MSG_REVERT.format(sha="abc1234"), None)
        out.append(("a revert naming a 7-hex sha is stamped Kind: work", rc == 0 and "Kind: work" in text))
        rc, _ = run_check(one, MSG_REVERT.format(sha="abc123"), None)
        out.append(("a revert naming a 6-hex sha is no revert", rc == 1))
        # Mutation: commit_kind.py:167 `if answers:` -> `if not answers:`
        rc, _ = run_check(one, MSG_FIX_NO_ANSWERS, None)
        out.append(("Kind: review-fix without Answers is refused", rc == 1))
        rc, _ = run_check(one, MSG_FIX, None)
        out.append(("Kind: review-fix with Answers passes", rc == 0))
    return out


def main() -> int:
    fails = 0
    extra = check_cases()
    for label, ok in extra:
        fails += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} check(): {label}")
    for argv, want, label in CASES:
        got = commit_kind.is_amend(argv)
        ok = got is want
        fails += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {label}: {' '.join(argv[1:])} -> {got}")
    total = len(CASES) + len(extra)
    print(f"{total - fails}/{total} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
