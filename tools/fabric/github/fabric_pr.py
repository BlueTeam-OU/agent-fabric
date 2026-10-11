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
              "usage: fabric-pr <verb> [args…]" then "verbs: gate, …, counts",
              exit 0. `fabric-pr <verb> --help` is that verb's module's help.
  unknown     any other verb, the empty one included: nothing on stdout, stderr
              "fabric-pr: unknown verb '<verb>'; verbs: gate, …, counts", exit 2
  a verb      its module under this directory runs with the verb's remaining
              argv; its stdout, stderr and exit status are untouched, because
              this process is replaced by it (os.execv), not wrapped
  environment nothing is read or set here: a module reads what it always read.
              The interpreter that runs the module is this one (sys.executable),
              the pin the forwarder chose.
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
HERE = os.path.dirname(os.path.abspath(__file__))


def _out(stream, text: str) -> None:
    # Bytes, so the "…" of the usage line does not depend on the stream's locale.
    stream.buffer.write(text.encode("utf-8"))
    stream.buffer.flush()


def main(argv: list[str]) -> int:
    listing = ", ".join(VERBS)
    # argv[1:2] and not `or "help"`: an empty verb is an unknown one, not no verb.
    verb = argv[1] if len(argv) > 1 else "help"
    if verb in ("help", "-h", "--help"):
        _out(sys.stdout, f"usage: fabric-pr <verb> [args…]\nverbs: {listing}\n")
        return 0
    if verb not in VERBS:
        _out(sys.stderr, f"fabric-pr: unknown verb '{verb}'; verbs: {listing}\n")
        return 2
    module = os.path.join(HERE, VERBS[verb] + ".py")
    os.execv(sys.executable, [sys.executable, module, *argv[2:]])
    return 127  # unreachable: execv returns only by raising


if __name__ == "__main__":
    sys.exit(main(sys.argv))
