#!/usr/bin/env python3
"""tools/fabric/github/fabric_pr.py — the GitHub toolkit's one command: the verb
table of bin/fabric-pr (agent-fabric ADR-040 §5 rule 7; Wave 9, batch 1). The
bin/ path is a forwarder that finds this module, checks the pinned Python and
execs it; the table, the help and the refusal are here.

THE CONTRACT (frozen from the bash, ADR-040 §5 rule 3)
  argv        fabric-pr <verb> [args…]
              verbs: gate review-status post-review reply arm sessions
                     trial-merge wait-merged owed-supply compliance counts
  help        no verb, `help`, `-h` or `--help` as the verb: stdout is
              "usage: fabric-pr <verb> [args…]", "verbs: gate, …, counts",
              then the --repo line, exit 0. `fabric-pr <verb> --help` is that verb's module's help.
  unknown     any other verb, the empty one included: nothing on stdout, stderr
              "fabric-pr: unknown verb '<verb>'; verbs: gate, …, counts", exit 2
  a verb      its module under this directory runs with the verb's remaining
              argv; its stdout, stderr and exit status are untouched, because
              this process is replaced by it (os.execv), not wrapped
  environment nothing is set here without --repo: a module reads what it
              always read. The one variable read is AGENT_FABRIC_PYTHON, to
              run the module on the interpreter the forwarder named (a
              wrapper stays in the path); without it, on this one
              (sys.executable).
  --repo      `--repo <owner>/<name>|<project>` or `--repo=…`, anywhere
              before a `--` in the argv of a verb in REPO_VERBS: taken out
              of the argv, and the module runs with GH_REPO set to the
              repository and AGENT_FABRIC_PR_PROJECT to its project ("" for a
              repository no project registers), so the PR, its head and the
              project's rules (arm.json, pr-tools.json, the settings
              repository) are that repository's, never the cwd checkout's.
              Two exceptions are said in the help: an exported
              AGENT_FABRIC_ARM_CONFIG still names the arm rules (an explicit
              override wins), and commits are counted from git, so only in a
              clone of that repository. A verb that runs another verb passes
              --repo on (common.fabric_pr_verb).
              A value that names nothing: stderr "fabric-pr: --repo: …",
              exit 2. Without --repo, AGENT_FABRIC_PR_PROJECT is unset, so
              an inherited one never stands in for the cwd's project.
"""
from __future__ import annotations

import os
import sys

# Verb → module in this directory, in the order the help lists them.
VERBS = {
    "gate": "pr_gate",
    "review-status": "pr_review_status",
    "post-review": "post_review",
    "reply": "pr_reply",
    "arm": "arm",
    "sessions": "pr_sessions",
    "trial-merge": "trial_merge",
    "wait-merged": "wait_merged",
    "owed-supply": "owed_supply",
    "compliance": "pr_compliance",
    "counts": "pr_counts",
}
PR_PROJECT = "AGENT_FABRIC_PR_PROJECT"   # common.PR_PROJECT_SETTING, unimported without --repo
HERE = os.path.dirname(os.path.abspath(__file__))
# The verbs that act on one PR of one repository (j146): the others either
# take a ref per PR (counts) or act on this checkout (trial-merge, reply).
REPO_VERBS = ("gate", "review-status", "post-review", "arm", "wait-merged")


def interpreter() -> str:
    """What the forwarder exec'd (`$py`): the bash ran the verb's module on it, wrapper and all."""
    return os.environ.get("AGENT_FABRIC_PYTHON") or sys.executable


def _out(stream, text: str) -> None:
    # Bytes, so the "…" of the usage line does not depend on the stream's locale; surrogateescape,
    # so a verb that is not UTF-8 is echoed as the bytes it came in (the bash did), not a traceback.
    stream.buffer.write(text.encode("utf-8", "surrogateescape"))
    stream.buffer.flush()


def take_repo(args: list[str]) -> tuple[str | None, list[str]]:
    """(the --repo value or None, the argv without it); a second --repo is
    refused, as is one with no value, by raising ValueError."""
    value, rest, i = None, [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            rest.extend(args[i:])
            break
        if a == "--repo" or a.startswith("--repo="):
            if value is not None:
                raise ValueError("given twice")
            if a == "--repo":
                if i + 1 >= len(args) or not args[i + 1] or args[i + 1].startswith("-"):
                    raise ValueError("needs <owner>/<name> or a project id")
                value, i = args[i + 1], i + 2
            else:
                value, i = a[len("--repo="):], i + 1
                if not value:
                    raise ValueError("needs <owner>/<name> or a project id")
            continue
        rest.append(a)
        i += 1
    return value, rest


def main(argv: list[str]) -> int:
    listing = ", ".join(VERBS)
    # argv[1:2] and not `or "help"`: an empty verb is an unknown one, not no verb.
    verb = argv[1] if len(argv) > 1 else "help"
    if verb in ("help", "-h", "--help"):
        _out(sys.stdout, f"usage: fabric-pr <verb> [args…]\nverbs: {listing}\n"
                         f"--repo <owner>/<name>|<project>: {', '.join(REPO_VERBS)} act on that repository's PR,"
                         " never the cwd checkout's;\n  an exported AGENT_FABRIC_ARM_CONFIG still names the arm rules,"
                         " and commits are counted only in a clone of that repository\n")
        return 0
    if verb not in VERBS:
        _out(sys.stderr, f"fabric-pr: unknown verb '{verb}'; verbs: {listing}\n")
        return 2
    module = os.path.join(HERE, VERBS[verb] + ".py")
    args = argv[2:]
    os.environ.pop(PR_PROJECT, None)
    if verb in REPO_VERBS:
        try:
            value, args = take_repo(args)
        except ValueError as e:
            _out(sys.stderr, f"fabric-pr: --repo: {e}\n")
            return 2
        if value is not None:
            sys.path.insert(0, os.path.dirname(HERE))
            from github import common
            try:
                repo, pid = common.resolve_repository(value)
            except common.NoRepository as e:
                _out(sys.stderr, f"fabric-pr: --repo: {e}\n")
                return 2
            os.environ.update({"GH_REPO": repo, PR_PROJECT: pid})
    py = interpreter()
    os.execv(py, [py, module, *args])
    return 127  # unreachable: execv returns only by raising


if __name__ == "__main__":
    sys.exit(main(sys.argv))
