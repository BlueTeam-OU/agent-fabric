#!/usr/bin/env python3
"""tools/fabric/review_cli.py — the whole dispatch of bin/fabric-review,
which is a forwarder to this module (ADR-040 §5 rule 1, Wave 9 batch 2).
Standard library only; it renders and judges nothing, it execs the module
that does.

CONTRACT, frozen from the bash (tests/test_fabric_review_cli.py is the oracle):
  argv      brief REQUEST... | check REQUEST | lenses | save PR ROUND...
            | next REQUEST... | --engine codex PR REQUEST... | -h | --help.
  env       AGENT_FABRIC_PYTHON (default /usr/local/bin/fabric-python), the
            interpreter the target runs on; AGENT_FABRIC_ROOT, exported to
            this repository's root when unset or empty.
  dispatch  brief      -> review_brief.py render <rest>
            check, lenses -> review_brief.py <verb> <rest>
            save, next -> review_rounds.py <verb> <rest>
            --engine   -> review_codex.py <rest>
  stdout    USAGE for -h and --help; nothing else of its own.
  stderr    USAGE for no argument (or an empty one); the pin's install
            line; the unknown-command line.
  exit      the pin is checked first, before the verb: absent, 127. -h and
            --help: 0. No argument and an unknown verb: 2. Else the
            target's own, which it is exec'd as.
"""
from __future__ import annotations

import os
import sys

USAGE = """\
bin/fabric-review — brief a blind review: render the facts of one change
into the prompt a code-review dispatch carries.

  fabric-review brief  REQUEST[.yaml|.json|-] [--allow-rationale]   the brief, to stdout; a pinned range
                                      also checks its head out, detached (ADR-020)
  fabric-review check  REQUEST                                        validate only, say what it is
  fabric-review lenses                                                 the lens vocabulary
  fabric-review save PR ROUND [--repo NAME] < report                  keep a round's report; remove its head worktree
  fabric-review next REQUEST (--report F | --pr PR) [--head REV] [--keep-lenses]
                                      the re-review's request, derived and rendered
                                      (tools/fabric/review_rounds.py)
  fabric-review --engine codex PR REQUEST [--gateway chatgpt] [--model M] [--timeout MIN] [--no-post]
                                      the second engine: Codex reviews the PR's head
                                      one-shot and posts, through a gateway of its own
                                      (tools/fabric/review_codex.py, agent-fabric ADR-053)

Then dispatch, exactly as the guard requires (it never reads the prompt):

  Agent(subagent_type: "code-review", model: "fable",
        description: "Review <what>" (or "Re-review <what>"),
        prompt: <the rendered brief, verbatim>)      — and NO isolation

A request names WHAT must be true (mode, repository, range, objective,
requirements, invariants, compatibility, threat model, scope, out of
scope, lenses; previous_findings on a re-review) and never how the
change makes it true: a verdict-shaped sentence refuses the render,
named. tools/fabric/review_brief.py; runtime/claude-code/review/README.md.
"""
PINNED = "/usr/local/bin/fabric-python"
# verb -> (module, the words put before the rest of the argv). check, lenses, save
# and next are the target's own verbs; brief and --engine are this command's names
# for it (render; none) and are not passed on.
ROUTES = {
    "brief": ("review_brief.py", ["render"]),
    "check": ("review_brief.py", ["check"]),
    "lenses": ("review_brief.py", ["lenses"]),
    "save": ("review_rounds.py", ["save"]),
    "next": ("review_rounds.py", ["next"]),
    "--engine": ("review_codex.py", []),
}


def say(stream, text: str) -> None:
    stream.flush()
    stream.buffer.write(text.encode("utf-8"))
    stream.buffer.flush()


def main(argv: list[str]) -> int:
    here = os.path.dirname(os.path.realpath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    if not os.environ.get("AGENT_FABRIC_ROOT"):
        os.environ["AGENT_FABRIC_ROOT"] = root
    py = os.environ.get("AGENT_FABRIC_PYTHON") or PINNED
    # Before the verb, so a host without the pin says so whatever it was asked.
    if not os.access(py, os.X_OK):
        say(sys.stderr, "fabric-review: the fleet's pinned Python is not installed at %s; as root: "
            "/usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install\n" % py)
        return 127
    cmd = argv[0] if argv else ""
    if cmd in ROUTES:
        module, lead = ROUTES[cmd]
        target = os.path.join(root, "tools", "fabric", module)
        try:
            os.execv(py, [py, target, *lead, *argv[1:]])
        except OSError as e:
            say(sys.stderr, "fabric-review: cannot run %s: %s\n" % (py, e.strerror))
            return 126
    if cmd in ("-h", "--help"):
        say(sys.stdout, USAGE)
        return 0
    if cmd == "":
        say(sys.stderr, USAGE)
        return 2
    say(sys.stderr, "fabric-review: unknown command %s (brief | check | lenses | save | next | --engine)\n" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
