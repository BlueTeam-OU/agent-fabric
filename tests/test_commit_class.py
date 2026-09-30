#!/usr/bin/env python3
"""Tests for tools/fabric/github/commit_class.py's internals; the rule
itself is runtime/github/test_commit-class.sh's, run unchanged against the
shim (ADR-040 §5 rule 5)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from github import commit_class as cc  # noqa: E402


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        reg = os.path.join(tmp, "registry.json")
        json.dump({"projects": {"gzapp": {"remotes": ["git@github.com:gzapi-org/gzapp.git"]},
                                "interweave": {"remotes": ["https://github.com/gzapi-org/InterWeave.git"]}}}, open(reg, "w"))
        check("known_repos: each project id and each remote's name, lower-cased",
              cc.known_repos(reg) == {"gzapp", "interweave"}, cc.known_repos(reg))
        check("known_repos: an unreadable registry names none", cc.known_repos(os.path.join(tmp, "none.json")) == set())
    check("_ref: owner/repo#N of this repository is N", cc._ref("gzapi-org/agent-fabric#53", "gzapi-org/agent-fabric") == "53")
    check("_ref: owner/repo#N of another is x", cc._ref("gzapi-org/gzapp#53", "gzapi-org/agent-fabric") == "x")
    check("_ref: 'PR #918' is this repository's", cc._ref("PR #918", "gzapi-org/agent-fabric") == "918")
    check("_ref: without a repository only the number counts", cc._ref("gzapp#9", "") == "9")
    check("revert_targets: git's own line, nothing else",
          cc.revert_targets("Revert x\n\nThis reverts commit abcdef1234.\nreverts commit 999") == ["abcdef1234"])
    tool = os.path.join(HERE, "tools", "fabric", "github", "commit_class.py")
    r = subprocess.run([sys.executable, tool, "class"], capture_output=True, text=True)
    check("the CLI refuses too few arguments as usage (exit 2)", r.returncode == 2 and "usage" in r.stderr, r.stderr)
    r = subprocess.run([sys.executable, tool, "class", "a b", "anything"], capture_output=True, text=True)
    check("the CLI prints one word", r.stdout == "merge\n", r.stdout)
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
