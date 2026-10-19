#!/usr/bin/env python3
"""runtime/claude-code/hooks/model-switch-guard.py — the model-switch guard (ADR-040 Wave 9 batch 5;
model-switch-guard.sh beside it is its forwarder, run by the PreModelSwitch hook of
runtime/claude-code/workspace/settings.json and .claude/settings.json).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      none read
  stdin     the PreModelSwitch payload, JSON: to_model (the id the session would run after the switch) and
            requested_model (what was typed), each read as jq's `.field // ""`
  env       AGENT_FABRIC_LAUNCH_PROFILE (set and non-empty: a broker session; anything else: nothing to guard),
            AGENT_FABRIC_ROOT (empty or unset: the checkout three directories above this file), PATH (jq's
            presence, below)
  stdout    nothing (allow), or one compact hookSpecificOutput line, hookEventName PreModelSwitch, whose
            permissionDecision is deny or ask
  stderr    nothing
  exit      0, always

DECISIONS, in order, with their exact words:
  1. AGENT_FABRIC_LAUNCH_PROFILE empty or unset                      -> nothing (vanilla claude)
  2. no `jq` on PATH -> ask, the bash's literal line:
     "The model-switch guard could not run (jq is not installed). In a broker session a bare model id runs
     without its family shim; approve only if the target is a composite or a family that needs none."
     This module needs no jq; the check is kept because the bash's contract (and its oracle) holds it, and it
     fails closed (an ask). Dropping it is the coordinator's call, not a port's.
  3. stdin not JSON, or to_model read with an error (the payload a string or an array) -> nothing
  4. to_model empty (absent, null, false, "")                         -> nothing
  5. target = requested_model when it contains "@preset/", else to_model; target contains "@preset/" ->
     nothing (it names its shim already; a tier alias resolves to the launcher's composite export)
  6. $AGENT_FABRIC_ROOT/tools/fabric/routing.py not a file -> ask:
     "The model-switch guard cannot consult routing (<routing.py> not found). In a broker session a bare model
     id runs without its family shim; approve only if '<target>' needs none."
  7. `routing.py --fabric <root> shim <target>` run as a program exits non-zero -> ask:
     "The model-switch guard could not run routing.py shim for '<target>'. Approve only if the target needs no
     family shim."
  8. it prints nothing (trailing newlines dropped)                   -> nothing (the family rides bare)
  9. else deny:
     "This session was launched through the broker (profile <profile>); '<target>' belongs to a family that
     needs the <shim> compatibility preset, and a bare /model would run it with none — the failures that
     follow look like model defects and are not. Switch to '<target up to its first @><shim>' instead, or
     relaunch with the model in the profile (routing/profiles.json, or the local override)."

NOT BYTE-IDENTICAL to the bash, each by the jq the bash read through (hook_jq.py beside this file):
  - routing.py runs on this interpreter (the pin, under the forwarder), where the bash ran the first
    `python3` on PATH; its argv, environment and the stdout it reads are the bash's.
  - a to_model or requested_model that is not a string is rendered as Python's JSON, not jq's (jq 1.8 keeps
    a number's literal); the harness sends strings.
  - a stream of several JSON values, a NaN, a lone surrogate: read as jq 1.8 reads them; jq 1.6 and 1.7
    exited differently on a stream, so the bash's own answer there was the host's jq version.

WHY THE GUARD EXISTS, the bash's header kept:

In a broker session, a bare /model to a family that needs a shim is refused. The broker launcher
(runtime/openrouter/launch) exports every class, and the session model, as a COMPOSITE — <model>@<shim> — so a
model family that cannot speak Claude Code's wire protocol on its own gets its compatibility preset attached
(routing/shims.json). That binding is made once, at launch, in the child's environment. A hand `/model <bare id>`
inside the session bypasses it: the harness would run the bare model with no shim, and every symptom of that —
invented turns, native tool markup in the output — looks like a model defect rather than a routing one. This was
the one idea of the retired per-account wrapper worth keeping; it is written against routing/ so that "which
families need a shim" has one implementation (tools/fabric/routing.py shim) and no vendor name lives in a hook.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Under `python -I` the script's directory is not on sys.path; the jq reading is a sibling.
sys.path.insert(0, HERE)
import hook_jq  # noqa: E402

EVENT = "PreModelSwitch"
NO_JQ = ('{"hookSpecificOutput":{"hookEventName":"PreModelSwitch","permissionDecision":"ask","permissionDecisionReason":'
         '"The model-switch guard could not run (jq is not installed). In a broker session a bare model id runs without '
         'its family shim; approve only if the target is a composite or a family that needs none."}}')


def field(name: str):
    return lambda value: [hook_jq.alt(hook_jq.index(value, name), "")]


def say(kind: str, reason: str) -> None:
    hook_jq.write(hook_jq.decision(EVENT, kind, reason) + "\n")


def main() -> int:
    profile = hook_jq.env_text(os.environ.get("AGENT_FABRIC_LAUNCH_PROFILE", ""))
    if not profile:
        return 0
    # A path stays the bytes the environment gave; only the words printed are made UTF-8.
    root = os.environ.get("AGENT_FABRIC_ROOT", "") or os.path.normpath(os.path.join(HERE, "..", "..", ".."))
    routing = f"{root}/tools/fabric/routing.py"
    if shutil.which("jq") is None:
        hook_jq.write(NO_JQ + "\n")
        return 0
    # `input="$(cat)"`: a shell variable holds no NUL and no trailing newline.
    text = sys.stdin.buffer.read().replace(b"\0", b"").rstrip(b"\n").decode("utf-8", "replace")
    values, ok = hook_jq.run(text, field("to_model"))
    if not ok:
        return 0
    to = hook_jq.captured(values)
    if not to:
        return 0
    values, ok = hook_jq.run(text, field("requested_model"))
    requested = hook_jq.captured(values) if ok else ""

    # Judge the RESOLVED id; a request spelled as a composite counts as one too.
    target = requested if "@preset/" in requested else to
    if "@preset/" in target:
        return 0
    if not os.path.isfile(routing):
        say("ask", f"The model-switch guard cannot consult routing ({hook_jq.env_text(routing)} not found). In a broker "
                   f"session a bare model id runs without its family shim; approve only if '{target}' needs none.")
        return 0
    try:
        r = subprocess.run([sys.executable, routing, "--fabric", root, "shim", target], stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
        failed = r.returncode != 0
    except OSError:
        failed = True
    if failed:
        say("ask", f"The model-switch guard could not run routing.py shim for '{target}'. Approve only if the target needs "
                   "no family shim.")
        return 0
    shim = r.stdout.decode("utf-8", "replace").rstrip("\n").replace("\0", "")
    if not shim:
        return 0                                   # a family with no shim rides bare
    say("deny", f"This session was launched through the broker (profile {profile}); '{target}' belongs to a family that "
                f"needs the {shim} compatibility preset, and a bare /model would run it with none — the failures that "
                f"follow look like model defects and are not. Switch to '{target.split('@', 1)[0]}{shim}' instead, or "
                "relaunch with the model in the profile (routing/profiles.json, or the local override).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
