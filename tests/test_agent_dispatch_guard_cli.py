#!/usr/bin/env python3
"""The hook-level oracle for runtime/claude-code/hooks/agent-dispatch-guard.sh:
the DECISION TABLE of the Agent dispatch hook, one real payload piped through
the real script per case, the decision read back: "allow" (no output), "deny"
or "ask".

The program used to live as a jq string inside settings.json and its two
properties were "pipe-tested at the time it was written" -- in a terminal,
once, by hand. Both halves of the review carve-out were later found to be
load-bearing TOGETHER (a type-only key let fable through), which is the kind
of regression a table of cases catches and a comment does not.

The hook under test is $DISPATCH_GUARD, default
runtime/claude-code/hooks/agent-dispatch-guard.sh. tests/test_dispatch_guard.py
holds the module's internals; this file is the parity oracle of the bash test.

Exit codes: 0 all assertions passed, 1 one or more failed."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNDER_TEST = os.path.abspath(os.environ.get("DISPATCH_GUARD") or os.path.join(
    HERE, "runtime", "claude-code", "hooks", "agent-dispatch-guard.sh"))
if not os.path.isfile(UNDER_TEST):
    sys.exit(f"test: not found: {UNDER_TEST}")

T = tempfile.mkdtemp(prefix="test_agent_dispatch_guard_cli.")
EMPTY_STATE = f"{T}/state"
SCRATCH_HOME = f"{T}/home"
FIXTURE_ROOT = f"{T}/fixture"
for d in (EMPTY_STATE, SCRATCH_HOME, FIXTURE_ROOT):
    os.makedirs(d, exist_ok=True)

failures = 0


def check(label: str, good: bool, detail: str = "") -> None:
    global failures
    if good:
        print(f"  ok   {label}")
        return
    failures += 1
    print(f"  FAIL {label}: {detail}" if detail else f"  FAIL {label}")


def base_env() -> dict[str, str]:
    # The runner may itself be a fabric-launched session: every launch
    # variable is removed, never inherited; a case sets its own on purpose.
    # GIT_* (GIT_DIR, GIT_INDEX_FILE from a run inside a hook) and XDG_* (a real
    # git config or binding) would point the fixture at the caller's (review of #83).
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "CLAUDE_", "GZCOORD_", "GIT_", "XDG_")) and k != "CLAUDECODE"}
    env["HOME"] = SCRATCH_HOME
    env["CLAUDE_CONFIG_DIR"] = SCRATCH_HOME
    return env


def run(cmd: list[str], stdin: str, env: dict[str, str]) -> tuple[int, str]:
    p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env)
    return p.returncode, p.stdout.rstrip("\n")


def payload(tool_input: str) -> str:
    return '{"tool_name":"Agent","tool_input":%s}' % tool_input


def field(out: str, *path: str):
    try:
        v = json.loads(out)
        for p in path:
            v = v[p]
        return v
    except (ValueError, KeyError, TypeError):
        return None


def decision(tool_input: str) -> str:
    """An UNLAUNCHED session: no launch variable at all."""
    _, out = run(["bash", UNDER_TEST], payload(tool_input), base_env())
    if not out:
        return "allow"
    d = field(out, "hookSpecificOutput", "permissionDecision")
    return "malformed" if d is None else d


def reason(tool_input: str) -> str:
    _, out = run(["bash", UNDER_TEST], payload(tool_input), base_env())
    return field(out, "hookSpecificOutput", "permissionDecisionReason") or ""


def expect(label: str, want: str, tool_input: str) -> None:
    got = decision(tool_input)
    check(label, got == want, f"want {want}, got {got}")


def main() -> int:
    print("forks")
    expect("a fork is allowed with nothing set", "allow", '{"subagent_type":"fork","description":"continue"}')

    print("the review class: all four conditions, or denied -- never asked")
    R = '{"subagent_type":"code-review","model":"fable","description":"Review PR 626 diff","prompt":"..."}'
    expect("code-review + review + fable + no isolation is allowed without a prompt", "allow", R)
    expect("re-review is a review", "allow", '{"subagent_type":"code-review","model":"fable","description":"Re-review PR 626 after fixes"}')
    expect("case-insensitive prefix", "allow", '{"subagent_type":"code-review","model":"fable","description":"REVIEW of the delta"}')
    expect("any word form beginning review (Reviewing) is a review", "allow", '{"subagent_type":"code-review","model":"fable","description":"Reviewing PR 626"}')
    expect("review type with a full model id is denied (the Agent tool only accepts aliases; fable is the review alias)", "deny", '{"subagent_type":"code-review","model":"claude-opus-5[1m]","description":"Review PR 626"}')
    expect("review type with a writing description is denied", "deny", '{"subagent_type":"code-review","model":"fable","description":"Address review feedback on PR 626"}')
    expect("review anywhere but not at the start is denied", "deny", '{"subagent_type":"code-review","model":"fable","description":"Fix and review the mapper"}')
    expect("review type on sonnet is denied, not asked", "deny", '{"subagent_type":"code-review","model":"sonnet","description":"Review PR 626"}')
    expect("review type on haiku is denied", "deny", '{"subagent_type":"code-review","model":"haiku","description":"Review PR 626"}')
    expect("review type with model unset is denied", "deny", '{"subagent_type":"code-review","description":"Review PR 626"}')
    expect("review type with opus is denied (opus is code-high's alias on the broker path)", "deny", '{"subagent_type":"code-review","model":"opus","description":"Review PR 626"}')
    expect("review type WITH isolation is denied", "deny", '{"subagent_type":"code-review","model":"fable","isolation":"worktree","description":"Review PR 626"}')
    expect("the review prefix on a general agent is denied", "deny", '{"subagent_type":"general-purpose","model":"sonnet","isolation":"worktree","description":"Review the diff"}')

    print("read-only types: model required, no worktree, premium asks")
    expect("Explore on sonnet without isolation is allowed", "allow", '{"subagent_type":"Explore","model":"sonnet","description":"Explore the provisioning scripts"}')
    expect("Plan on haiku without isolation is allowed", "allow", '{"subagent_type":"Plan","model":"haiku","description":"Plan the split"}')
    expect("claude-code-guide on haiku is allowed", "allow", '{"subagent_type":"claude-code-guide","model":"haiku","description":"How do hooks work"}')
    expect("Explore with model unset is denied (the tier is still a choice)", "deny", '{"subagent_type":"Explore","description":"Explore the provisioning scripts"}')
    expect("Explore WITH worktree isolation is denied (it would hide uncommitted work)", "deny", '{"subagent_type":"Explore","model":"sonnet","isolation":"worktree","description":"Explore the provisioning scripts"}')
    expect("Explore on fable asks", "ask", '{"subagent_type":"Explore","model":"fable","description":"Explore the provisioning scripts"}')
    expect("a read-only type whose description begins with review is still denied (reviews use the class)", "deny", '{"subagent_type":"Explore","model":"sonnet","description":"Review the diff"}')

    print("everything else: model and worktree required, premium asks")
    expect("sonnet + worktree is allowed", "allow", '{"subagent_type":"general-purpose","model":"sonnet","isolation":"worktree","description":"Extract the table"}')
    expect("haiku + worktree is allowed", "allow", '{"model":"haiku","isolation":"worktree","description":"Rename the field"}')
    expect("missing model is denied", "deny", '{"subagent_type":"general-purpose","isolation":"worktree","description":"Extract the table"}')
    expect("missing isolation is denied", "deny", '{"subagent_type":"general-purpose","model":"sonnet","description":"Extract the table"}')
    expect("isolation other than worktree is denied", "deny", '{"model":"sonnet","isolation":"remote","description":"Extract"}')
    expect("opus on a general agent asks", "ask", '{"subagent_type":"general-purpose","model":"opus","isolation":"worktree","description":"Extract the table"}')
    expect("fable on a general agent asks", "ask", '{"model":"fable","isolation":"worktree","description":"Extract the table"}')
    expect("Opus in caps still asks", "ask", '{"model":"Opus","isolation":"worktree","description":"Extract"}')

    print("the denial says why")
    r = reason('{"subagent_type":"code-review","model":"sonnet","description":"Review PR 626"}')
    check("the tier denial names the failure mode", "green PR that merges" in r, r)
    # The pointer is the fabric's own skill, installed on every account; a
    # heading in one project's CLAUDE.md is missing from the others.
    check("the denial points at the fabric's skill, not one project's heading",
          "subagent-dispatch skill" in r and "CLAUDE.md - Subagent" not in r, r)
    r = reason('{"subagent_type":"code-review","model":"fable","isolation":"worktree","description":"Review PR 626"}')
    check("the isolation denial names baseRef", "baseRef" in r, r)

    print("a coding class decides its tier: model must be the class's alias (aliases.json)")
    expect("code-low on haiku is allowed", "allow", '{"subagent_type":"code-low","model":"haiku","isolation":"worktree","description":"Extract the table"}')
    expect("code-medium on sonnet is allowed", "allow", '{"subagent_type":"code-medium","model":"sonnet","isolation":"worktree","description":"Rework the mapper"}')
    expect("code-high on opus asks (premium), never silently", "ask", '{"subagent_type":"code-high","model":"opus","isolation":"worktree","description":"Design the protocol"}')
    expect("code-low on sonnet is denied: the class decides, not the call", "deny", '{"subagent_type":"code-low","model":"sonnet","isolation":"worktree","description":"Extract the table"}')
    expect("code-high on haiku is denied: high work on the cheap tier with nothing saying so", "deny", '{"subagent_type":"code-high","model":"haiku","isolation":"worktree","description":"Design the protocol"}')
    expect("code-high on sonnet is denied, not downgraded", "deny", '{"subagent_type":"code-high","model":"sonnet","isolation":"worktree","description":"Design the protocol"}')
    expect("a class with model unset is denied (nothing is inferred)", "deny", '{"subagent_type":"code-medium","isolation":"worktree","description":"Rework the mapper"}')
    expect("a class with a full model id is denied", "deny", '{"subagent_type":"code-low","model":"claude-haiku-4-5","isolation":"worktree","description":"Extract the table"}')
    expect("a class without worktree isolation is denied", "deny", '{"subagent_type":"code-low","model":"haiku","description":"Extract the table"}')
    r = reason('{"subagent_type":"code-low","model":"sonnet","isolation":"worktree","description":"Extract the table"}')
    check("the mismatch denial names the class's alias", "rides the haiku alias" in r, r)
    # aliases.json unreadable: the class branch denies and says why, never loosens.
    # A copy of the guard placed where no aliases.json exists around it. The
    # guard is the module now (ADR-040 §5 rule 5): the copy is of the module,
    # which finds the aliases from where it stands, as the bash script did.
    orphan = f"{T}/orphan"
    os.makedirs(f"{orphan}/hooks")
    shutil.copy(os.path.join(os.path.dirname(UNDER_TEST), "..", "..", "..", "tools", "fabric", "guards", "dispatch_guard.py"),
                f"{orphan}/hooks/guard.py")
    _, out = run(["python3", f"{orphan}/hooks/guard.py"],
                 '{"tool_input":{"subagent_type":"code-low","model":"haiku","isolation":"worktree","description":"x"}}', base_env())
    shutil.rmtree(orphan)
    check("an unreadable aliases.json denies a class dispatch rather than allowing it",
          '"deny"' in out and "binds no alias" in out, out)

    print("the locale worker: model required, isolation refused, any alias allowed without an ask")
    expect("locale-worker on opus is allowed, no ask", "allow", '{"subagent_type":"locale-worker","model":"opus","description":"Translate the finding into Georgian"}')
    expect("locale-worker on fable is allowed, no ask", "allow", '{"subagent_type":"locale-worker","model":"fable","description":"x"}')
    expect("locale-worker on sonnet is allowed", "allow", '{"subagent_type":"locale-worker","model":"sonnet","description":"x"}')
    expect("locale-worker with model unset is denied", "deny", '{"subagent_type":"locale-worker","description":"x"}')
    expect("locale-worker with isolation is denied", "deny", '{"subagent_type":"locale-worker","model":"opus","isolation":"worktree","description":"x"}')
    expect("locale-worker whose description begins with review is allowed: reviewing text is its job", "allow", '{"subagent_type":"locale-worker","model":"opus","description":"Review the Georgian rendering of the finding"}')
    r = reason('{"subagent_type":"locale-worker","model":"opus","isolation":"worktree","description":"x"}')
    check("the isolation denial says why", "writes nothing" in r, r)

    print("a guard that cannot run asks; it never silently allows")
    # Nothing to run on: the hook reaches the pinned Python by its fixed path,
    # so a copy whose path names nothing stands for a host without it.
    with open(UNDER_TEST, encoding="utf-8") as f:
        src = f.read()
    src = src.replace("\npy=/usr/local/bin/fabric-python\n", "\npy=/nonexistent/fabric-python\n")
    nopy = f"{T}/nopy.sh"
    with open(nopy, "w", encoding="utf-8") as f:
        f.write(src)
    _, out = run(["/bin/bash", nopy], '{"tool_input":{"model":"sonnet","isolation":"worktree","description":"x"}}',
                 {"PATH": "/nonexistent"})
    check("with jq unavailable the guard asks rather than allowing",
          field(out, "hookSpecificOutput", "permissionDecision") == "ask", f"out=[{out}]")

    print("malformed input never breaks the tool call with a bad shape")
    for pl in ('{}', 'not json', ''):
        rc, out = run(["bash", UNDER_TEST], pl, base_env())
        # Exit 2 is the ONE code Claude Code treats as a blocking hook error:
        # a guard that exits 2 on a parse failure hard-blocks every dispatch.
        good = rc != 2 and (not out or field(out, "hookSpecificOutput", "permissionDecision") is not None)
        check(f"payload ({pl or 'empty'}) yields allow or a well-formed decision, never exit 2 (rc={rc})", good, f"rc={rc} out=[{out}]")

    print("the file pin: under a fabric launch a review dispatch keeps its rules, then hands the model to the agent file")
    # The pin is merged for the login (`pins --me`): an empty state dir keeps
    # the runner's own binding and local layer out of these assertions, and a
    # scratch CLAUDE_CONFIG_DIR carries the reviewer file the guard checks.
    fabric_root = HERE
    # The guard resolves through routing.py, which reads AGENT_FABRIC_ROOT: a
    # root on the frozen column of 2026-09-24, where the five classes differ
    # in model and level, so a guard that compared the wrong class's value
    # would be caught. The committed column is two models at one level.
    shutil.copytree(f"{fabric_root}/routing", f"{FIXTURE_ROOT}/routing")
    for n in ("capabilities.json", "effort.json"):
        shutil.copy(f"{fabric_root}/tests/fixtures/routing-distinct/{n}", f"{FIXTURE_ROOT}/routing/")
    os.makedirs(f"{FIXTURE_ROOT}/runtime/claude-code")
    shutil.copy(f"{fabric_root}/runtime/claude-code/aliases.json", f"{FIXTURE_ROOT}/runtime/claude-code/")
    shutil.copy(f"{fabric_root}/runtime/identity.py", f"{FIXTURE_ROOT}/runtime/")   # `pins --me` asks it who is running

    def reviewer_file(model: str) -> None:
        os.makedirs(f"{SCRATCH_HOME}/agents", exist_ok=True)
        with open(f"{SCRATCH_HOME}/agents/code-review.md", "w", encoding="utf-8") as f:
            f.write(f"---\nname: code-review\nmodel: {model}\n---\n")

    def launched(provider: str, tool_input: str) -> str:
        env = base_env()
        env.update(AGENT_FABRIC_ROOT=FIXTURE_ROOT, AGENT_FABRIC_STATE_DIR=EMPTY_STATE,
                   CLAUDE_CONFIG_DIR=SCRATCH_HOME, AGENT_FABRIC_LAUNCH_PROVIDER=provider)
        return run(["bash", UNDER_TEST], payload(tool_input), env)[1]

    def vanilla(tool_input: str) -> str:
        return launched("anthropic", tool_input)

    def dec(out: str):
        return field(out, "hookSpecificOutput", "permissionDecision")

    reviewer_file("claude-opus-5[1m]")
    out = vanilla(R)
    check("review + fable + no isolation: an explicit allow", dec(out) == "allow", out)
    ui = field(out, "hookSpecificOutput", "updatedInput")
    check("…with the dispatch's model removed, so the reviewer file's claude-opus-5[1m] decides",
          ui is not None and "model" not in ui, out)
    ui = ui or {}
    check("…and everything else on the dispatch intact",
          ui.get("subagent_type") == "code-review" and ui.get("prompt") == "...", out)
    check("the reason names the pinned model", "claude-opus-5[1m]" in out, out)
    out = vanilla('{"subagent_type":"code-review","model":"opus","description":"Review PR 626 diff"}')
    check("the fable rule still holds first: a review on opus is denied even here", dec(out) == "deny", out)
    out = vanilla('{"subagent_type":"code-review","description":"Review PR 626 diff"}')
    check("…and an unset model is still denied (the dispatcher writes fable; the guard drops it)", dec(out) == "deny", out)
    out = vanilla('{"subagent_type":"code-high","model":"opus","isolation":"worktree","description":"Fix the parser"}')
    check("a coding class is untouched: code-high still asks and keeps its alias (its pin is the export)", dec(out) == "ask", out)
    out = vanilla('{"subagent_type":"code-plan","model":"fable","isolation":"worktree","description":"Plan the migration"}')
    check("code-plan: a premium class on fable, asks like code-high", dec(out) == "ask", out)
    out = vanilla('{"subagent_type":"code-plan","model":"opus","isolation":"worktree","description":"Plan the migration"}')
    check("code-plan on opus is denied: the class rides fable", dec(out) == "deny", out)
    out = vanilla('{"subagent_type":"blind-reviewer","model":"fable","description":"Review PR 626 diff"}')
    check("the retired type name is denied and the message names code-review",
          dec(out) == "deny" and "code-review" in out, out)
    # The broker path is the same route: the file carries the composite.
    composite = "deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim"
    reviewer_file(composite)
    out = launched("openrouter", R)
    ui = field(out, "hookSpecificOutput", "updatedInput")
    check("on the broker path the review dispatch hands the model to the file too, the composite",
          dec(out) == "allow" and ui is not None and "model" not in ui and composite in out, out)
    # A stale file: another launch of this account rewrote it.
    reviewer_file("claude-opus-5[1m]")
    out = launched("openrouter", R)
    check("a reviewer file that disagrees with this launch's resolution is denied, not run",
          dec(out) == "deny" and "rewritten" in out, out)

    # THE SAME STALENESS, FOR EFFORT. A level is written into every class's
    # file, not just the reviewer's model, so the cross-provider rewrite
    # strands any class. Compared only when the file carries a line: a missing
    # one is an install older than effort, and denying on it would block every
    # dispatch on every account until it relaunched.
    def class_file(name: str, model: str, level: str = "") -> None:
        os.makedirs(f"{SCRATCH_HOME}/agents", exist_ok=True)
        with open(f"{SCRATCH_HOME}/agents/{name}.md", "w", encoding="utf-8") as f:
            f.write(f"---\nname: {name}\nmodel: {model}\n" + (f"effort: {level}\n" if level else "") + "---\n")

    HIGH = '{"subagent_type":"code-high","model":"opus","isolation":"worktree","description":"do the thing"}'
    stranded = "think at a level nothing chose"
    class_file("code-high", "opus")
    out = vanilla(HIGH)
    check("no effort: line in the class file — an older install is not treated as another launch's value", stranded not in out, out)
    class_file("code-high", "opus", "high")
    out = vanilla(HIGH)
    check("the file's level agrees with this launch: not denied for it", stranded not in out, out)
    class_file("code-high", "opus", "low")
    out = vanilla(HIGH)
    check("a class file another launch rewrote to a different level is denied, not run",
          dec(out) == "deny" and stranded in out, out)
    os.remove(f"{SCRATCH_HOME}/agents/code-high.md")
    with open(f"{SCRATCH_HOME}/agents/code-review.md", "w", encoding="utf-8") as f:
        f.write("---\nname: code-review\nmodel: claude-opus-5[1m]\neffort: low\n---\n")
    out = vanilla(R)
    check("…and the review class is checked the same way", dec(out) == "deny" and "effort" in out, out)
    reviewer_file("claude-opus-5[1m]")

    # The runner may itself be a fabric-launched session; "unlaunched" is the variable absent, not inherited.
    _, out = run(["bash", UNDER_TEST], payload(R), base_env())
    check("unlaunched vanilla: plain allow, fable is the harness's", out == "", out)

    if failures:
        print(f"{failures} FAILED")
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(T, ignore_errors=True)
