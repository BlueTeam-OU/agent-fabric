#!/usr/bin/env python3
"""runtime/claude-code/managed/hook_entry.py — the one program every managed hook runs (agent-fabric ADR-043 rule 2).

CONTRACT:
  argv    one guard name from GUARDS; the managed file runs it in exec form as
          /usr/local/bin/fabric-python -I -S <prefix>/managed/current/runtime/claude-code/managed/hook_entry.py <name>
  stdin   the hook payload, handed to the guard untouched (this program never reads it)
  stdout  the guard's answer; an ask when the name is unknown, or the guard is missing or cannot run (plan-hold:
          nothing, it never refuses)
  exit    0

Claude Code 2.1.316 spawns a managed hook with the session's own environment
(docs/live-checks/2026-10-31-managed-settings-2-1-316.md), so PATH, BASH_ENV, PYTHONPATH, AGENT_FABRIC_ROOT and
AGENT_FABRIC_PYTHON are the login's to choose. Nothing here trusts them. The interpreter is named by its absolute
path and runs -I -S (no PYTHON* variable, no user site, no script directory on sys.path, no site); no shell runs
anywhere; and the guard runs on that same interpreter with a cleared environment: the variables in KEEP, the
snapshot as AGENT_FABRIC_ROOT, the pin as AGENT_FABRIC_PYTHON and PATH the root-owned directories, so whatever a
guard itself runs by name is the host's.

The snapshot is resolved ONCE, from this file's real path: an install that swaps `current` mid-call cannot hand the
guard half of one snapshot and half of the next.

Each guard's Python module runs directly; the .sh forwarders the workspace settings run are skipped, and what they
did beyond forwarding is carried here. Those forwarders did not exec: a guard that crashes exits non-zero with
nothing on stdout, and the harness reads that as no objection, so a gate's failed run becomes its ask (their
cannot_run line). Their stderr went to /dev/null, and so does it here. plan-hold.sh exec'd plan_hold.py, which
only marks the inbox held and exits 0 whatever happens, so it is exec'd here too, keeping the harness its parent
(plan_hold.py reads the harness pid as its parent when CLAUDE_PID is unset).

The names are a fixed table, never a path: a name not in it asks, so a managed file and a snapshot that disagree
show it on the next call instead of passing it. A gate whose module is missing asks, the pipe-status and self-kill
guards included, which passed in silence when their script was missing from the workspace.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

INSTALLED = "/usr/local/lib/agent-fabric/"
PY = "/usr/local/bin/fabric-python"
# A test runs a scratch snapshot on a host it cannot install into, so it may name another interpreter for the
# guards; only a copy outside the installed prefix honours it, so the installed one has no override.
TEST_PY = "AGENT_FABRIC_HOOK_ENTRY_TEST_PYTHON"
PATH = "/usr/local/bin:/usr/bin:/bin"
KEEP = ("HOME", "USER", "LOGNAME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "AGENT_FABRIC_STATE_DIR",
        "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "CLAUDE_ENV_FILE", "CLAUDE_PROJECT_DIR",
        "AGENT_FABRIC_LAUNCH_PROVIDER", "AGENT_FABRIC_LAUNCH_PROFILE", "TMPDIR", "TERM", "LANG")
SUFFIX = "/runtime/claude-code/managed"
SKILL = "See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md)."

# name: (module under the snapshot, event, the approval the ask asks for; None: never refuses, exec'd)
GUARDS = {
    "agent-dispatch-guard": ("tools/fabric/guards/dispatch_guard.py", "PreToolUse",
                             "Approve only if you have checked model and isolation yourself. " + SKILL),
    "subagent-clone-guard": ("runtime/claude-code/hooks/subagent-clone-guard.py", "PreToolUse",
                             "Approve only if this tool call is not a subagent writing in the session clone. "
                             "See CLAUDE.md - Subagents."),
    "pipe-status-guard": ("runtime/claude-code/hooks/pipe-status-guard.py", "PreToolUse",
                          "Approve only if this command does not pipe a check into a filter and chain it with && "
                          "into a commit, push or merge."),
    "self-kill-guard": ("runtime/claude-code/hooks/self-kill-guard.py", "PreToolUse",
                        "Approve only if this command kills nothing of this session's own: its claude, its shell "
                        "or its inbox watch."),
    "job-copy-guard": ("runtime/claude-code/hooks/job-copy-guard.py", "PreToolUse",
                       "Approve only if this command does not commit or publish outside the working copy of this "
                       "session's job. See agent-fabric ADR-037 rule 3."),
    "plan-hold": ("tools/fabric/plan_hold.py", None, None),
    "model-switch-guard": ("runtime/claude-code/hooks/model-switch-guard.py", "PreModelSwitch",
                           "In a broker session a bare model id runs without its family shim; approve only if the "
                           "target is a composite or a family that needs none."),
    "review-fence": ("runtime/claude-code/hooks/review-fence.py", "PreToolUse",
                     "Approve only if this is not the code-review agent (agent-fabric ADR-065 rule 1)."),
}
LABEL = {"agent-dispatch-guard": "The dispatch guard", "subagent-clone-guard": "The subagent clone guard",
         "pipe-status-guard": "The pipe-status guard", "self-kill-guard": "The self-kill guard",
         "job-copy-guard": "The job copy guard", "model-switch-guard": "The model-switch guard",
         "review-fence": "The review-class fence"}


def ask(event: str, reason: str) -> int:
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": event, "permissionDecision": "ask",
                                                        "permissionDecisionReason": reason}},
                                ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


def snapshot_of(path: str) -> str | None:
    here = os.path.dirname(os.path.realpath(path))
    return here[:-len(SUFFIX)] if here.endswith(SUFFIX) and len(here) > len(SUFFIX) else None


def interpreter(snap: str, environ) -> str:
    """The pin, or a test's interpreter for a snapshot outside the installed prefix."""
    if not (snap + "/").startswith(INSTALLED) and environ.get(TEST_PY):
        return environ[TEST_PY]
    return PY


def main(argv: list[str], environ=os.environ) -> int:
    name = argv[1] if len(argv) == 2 else None
    if name not in GUARDS:
        print("hook_entry: no managed guard by that name (agent-fabric ADR-043 rule 2)", file=sys.stderr)
        return ask("PreToolUse", "A managed hook named a guard the installed snapshot does not know; approve only "
                                 "if you have checked this call yourself, and tell the host's operator "
                                 "(fabric-managed check).")
    rel, event, approve = GUARDS[name]
    snap = snapshot_of(argv[0])

    def cannot_run(why: str) -> int:
        return 0 if event is None else ask(event, f"{LABEL[name]} could not run ({why}). {approve}")

    if snap is None:
        return cannot_run("hook_entry.py is not inside a managed snapshot")
    module = os.path.join(snap, rel)
    if not os.path.isfile(module):
        return cannot_run(f"{rel} is not in the managed snapshot")
    py = interpreter(snap, environ)
    if not os.access(py, os.X_OK):
        return cannot_run(f"the fleet's pinned Python is missing ({py})")
    env = {k: environ[k] for k in KEEP if k in environ}
    env.update(AGENT_FABRIC_ROOT=snap, AGENT_FABRIC_PYTHON=py, PATH=PATH)
    args = [py, "-I", "-S", module]
    if event is None:
        sys.stdout.flush()
        try:
            os.execve(py, args, env)
        except OSError:
            return 0
    try:
        r = subprocess.run(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    except OSError:
        return cannot_run("the guard did not start")
    if r.returncode != 0:
        return cannot_run("the guard failed")
    out = r.stdout.rstrip(b"\n")
    if out:
        sys.stdout.buffer.write(out + b"\n")
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
