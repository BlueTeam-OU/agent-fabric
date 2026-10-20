#!/usr/bin/env python3
"""The oracle for the review class's Bash fence: runtime/claude-code/hooks/
review-bash-guard.sh (the shim) and review-bash-guard.py beside it, the fence
around the review class, which runs unisolated in the session clone.

Two things held still: state-changing git, installs and printing the
environment or secret material are DENIED however they are spelled (leading
whitespace, chained after another command, sudo, global git flags, quotes,
continuations), and read-only git, validators, guards and no-install builds
are ALLOWED -- a fence that blocks the review's own tools is a fence the next
session removes. The decision table is tests/fixtures/
review-bash-guard-cases.json, one real payload piped through the real shim per
case; what a table cannot hold is here: the guard judged in time on crafted
input, and a guard that cannot run, runs late or dies denying.

Ported from runtime/claude-code/hooks/test_review-bash-guard.sh when its cases
took it past ADR-040's 150 lines; the cases were extracted from it as bash
expanded them, never retyped.

The hook under test is $REVIEW_BASH_GUARD, default the shim.
Exit codes: 0 all assertions passed, 1 one or more failed."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNDER_TEST = os.path.abspath(os.environ.get("REVIEW_BASH_GUARD") or os.path.join(
    HERE, "runtime", "claude-code", "hooks", "review-bash-guard.sh"))
CASES = os.path.join(HERE, "tests", "fixtures", "review-bash-guard-cases.json")
if not os.path.isfile(UNDER_TEST):
    sys.exit(f"test: not found: {UNDER_TEST}")

failures = 0


def check(label: str, good: bool, detail: str = "") -> None:
    global failures
    if good:
        print(f"  ok   {label}")
        return
    failures += 1
    print(f"  FAIL {label}: {detail}" if detail else f"  FAIL {label}")


def base_env(**extra: str) -> dict[str, str]:
    # The runner may be a fabric-launched session: its launch variables are
    # removed, never inherited; a case sets its own on purpose. The fleet's
    # Python is the shim's default, so AGENT_FABRIC_PYTHON passes through.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("AGENT_FABRIC_", "CLAUDE_", "GZCOORD_")) or k == "AGENT_FABRIC_PYTHON"}
    env.update(extra)
    return env


# Only a guard against a hang: a hook takes well under a second of CPU, and a host loaded a hundredfold stretches that
# past a minute, which says nothing of the hook.
HANG_S = 300


def run(payload: str, **extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", UNDER_TEST], input=payload, capture_output=True, text=True,
                          env=base_env(**extra), timeout=HANG_S)


def decision(command: str, **extra: str) -> str:
    r = run(json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "agent_type": "code-review"}), **extra)
    if not r.stdout.strip():
        return "allow"
    try:
        out = json.loads(r.stdout)["hookSpecificOutput"]
    except (ValueError, KeyError, TypeError):
        return "malformed"
    # A command let through comes back rewritten to run with a clean
    # environment, with no decision: that is an allow.
    if "permissionDecision" in out:
        return out["permissionDecision"]
    return "allow" if isinstance(out.get("updatedInput"), dict) else "malformed"


def rewritten(tool_input: dict) -> dict | None:
    r = run(json.dumps({"tool_name": "Bash", "tool_input": tool_input, "agent_type": "code-review"}))
    try:
        return json.loads(r.stdout)["hookSpecificOutput"]["updatedInput"]
    except (ValueError, KeyError, TypeError):
        return None


def expect(label: str, want: str, command: str, **extra: str) -> None:
    got = decision(command, **extra)
    check(label, got == want, f"want {want}, got {got} for: {command}")


def table() -> None:
    with open(CASES, encoding="utf-8") as f:
        doc = json.load(f)
    for sec in doc["sections"]:
        print(sec["section"])
        for c in sec["cases"]:
            label = c.get("label") or ("denied: " if c["want"] == "deny" else "allowed: ") + c["command"]
            expect(label, c["want"], c["command"])


GUARD_PY = os.path.join(os.path.dirname(UNDER_TEST), "review-bash-guard.py")
# What a crafted command may cost the verdict, in CPU seconds: the heaviest shape below takes ~0.16 s, and the
# backtracking this guards against took minutes. CPU time, never wall: the guard itself judges in a child under a 3 s
# wall budget and answers "slow" (a deny, by design) when the host starves that child, so a wall bound here, or an
# allow expected of the shim under load, fails on the host's load and says nothing of the patterns.
VERDICT_CPU_S = 1.0
# And a ceiling the kernel enforces on the child that measures it, so a pattern that backtracks without end fails in
# seconds instead of stalling the suite (the run has no bound of its own); whole seconds, as RLIMIT_CPU is. SIGXCPU
# ends it at the soft limit; the hard one is a margin above, as equal limits end it by SIGKILL instead.
VERDICT_CEILING_S = 5
# Run in the interpreter the hook ships with (the shim's own choice), so the budget is measured on its regex engine.
MEASURE = """
import importlib.util, json, resource, sys, time
resource.setrlimit(resource.RLIMIT_CPU, (%d, %d))
spec = importlib.util.spec_from_file_location("review_bash_guard_under_test", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
command = sys.stdin.read()
start = time.process_time()
got = mod.verdict(command)
print(json.dumps({"verdict": got, "cpu": time.process_time() - start}))
""" % (VERDICT_CEILING_S, VERDICT_CEILING_S + 5)


def hook_python() -> str:
    py = os.environ.get("AGENT_FABRIC_PYTHON") or "/usr/local/bin/fabric-python"
    return py if os.access(py, os.X_OK) else sys.executable


def verdict_cpu(command: str, guard: str = GUARD_PY) -> tuple[str | None, float] | str:
    """(verdict, CPU seconds it took) as the hook's interpreter measured them, or why there is none."""
    try:
        r = subprocess.run([hook_python(), "-c", MEASURE, guard], input=command, capture_output=True, text=True,
                           env=base_env(), timeout=HANG_S)
    except subprocess.TimeoutExpired:
        return f"no answer within {HANG_S} s"
    if r.returncode == -24:     # SIGXCPU: the ceiling above
        return f"ran past {VERDICT_CEILING_S} CPU s and was stopped"
    try:
        said = json.loads(r.stdout)
        return said["verdict"], said["cpu"]
    except (ValueError, KeyError, TypeError):
        return f"no measurement (rc {r.returncode}): {r.stderr.strip()[-200:]}"


def within_budget(got) -> bool:
    return isinstance(got, tuple) and got[0] is None and got[1] <= VERDICT_CPU_S


def burn_and_sleep() -> tuple[float, float]:
    """CPU seconds a 0.5 s sleep costs and CPU seconds a 0.3 s burn costs, on the clock verdict_cpu uses."""
    code = ("import time\n"
            "a = time.process_time(); time.sleep(0.5); b = time.process_time()\n"
            "end = b + 0.3\n"
            "while time.process_time() < end: pass\n"
            "print(b - a, time.process_time() - b)\n")
    out = subprocess.run([hook_python(), "-c", code], capture_output=True, text=True, env=base_env(), timeout=HANG_S).stdout.split()
    return float(out[0]), float(out[1])


def guard_reasons() -> dict[str, str]:
    """The guard's own reason text -> its key (slow is its late-verdict deny, error a crash)."""
    spec = importlib.util.spec_from_file_location("review_bash_guard_reasons", GUARD_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {text: key for key, text in mod.REASONS.items()}


def judgement_of(stdout: str, reasons: dict[str, str]) -> str:
    """allow; deny:<the guard's reason key>; or malformed."""
    try:
        out = json.loads(stdout)["hookSpecificOutput"]
    except (ValueError, KeyError, TypeError):
        return "allow" if not stdout.strip() else "malformed"
    if out.get("permissionDecision") == "deny":
        return "deny:" + reasons.get(out.get("permissionDecisionReason"), "unknown reason")
    return "allow" if isinstance(out.get("updatedInput"), dict) else "malformed"


def shim_judgement(command: str, **extra: str) -> str:
    r = run(json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "agent_type": "code-review"}), **extra)
    return judgement_of(r.stdout, guard_reasons())


def in_time() -> None:
    # Python's re backtracks where grep did not, and a hook past its timeout
    # does not refuse: each shape below once ran for minutes (CodeQL on #96,
    # and a misplaced lookahead the fuzz caught). Allowed means judged in time:
    # a late verdict would have been a deny.
    print("Python backtracks where grep did not: a crafted command is judged in time (CodeQL on #96)")
    shapes = {
        "git followed by 3000 options": "git" + "\t--" * 3000 + "!",
        "env -C -- repeated 3000 times, then text": "env\t" + "-C\t--\t" * 3000 + "!",
        "git -A repeated 3000 times, then text": "git\t-A" + "\t-A" * 3000 + "!",
        "the word git 20000 times": "git " * 20000 + "x",
        "git -C -C repeated 3000 times, then text": "git" + " -C -C" * 3000 + "!",
        "git --attr-source repeated 3000 times, then text": "git" + " --attr-source" * 3000 + "!",
    }
    # The clock first: process time counts CPU and not waiting, which is what lets a loaded host leave the verdict alone.
    slept, burnt = burn_and_sleep()
    check("the clock counts CPU and not waiting (a sleep of 0.5 s costs none, a burn of 0.3 s costs it)",
          slept < 0.2 and burnt >= 0.25, f"slept {slept:.3f}, burnt {burnt:.3f}")
    for label, command in shapes.items():
        got = verdict_cpu(command)
        check(f"judged within {VERDICT_CPU_S} CPU s, and allowed: {label}", within_budget(got), f"{got!r}")
    # The measure can fail: stand-in guards that are quick, slow, and without end, each a verdict() and nothing else.
    with tempfile.TemporaryDirectory() as tmp:
        def stand_in(name: str, body: str) -> str:
            path = os.path.join(tmp, name + ".py")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("import time\ndef verdict(cmd):\n" + body)
            return path
        quick = verdict_cpu("x", stand_in("quick", "    return None\n"))
        slow = verdict_cpu("x", stand_in("slow", "    end = time.process_time() + 1.6\n    while time.process_time() < end: pass\n    return None\n"))
        endless = verdict_cpu("x", stand_in("endless", "    while True: pass\n"))
        check("positive control: a verdict that returns at once is within the budget", within_budget(quick), f"{quick!r}")
        check(f"a verdict that takes 1.6 CPU s is past the budget, though it ends", isinstance(slow, tuple) and not within_budget(slow), f"{slow!r}")
        check("a verdict without end is stopped at the CPU ceiling and said so, not waited for",
              isinstance(endless, str) and "was stopped" in endless and not within_budget(endless), f"{endless!r}")
    # Through the shim, as the harness runs it: the verdict or the guard's own late-verdict deny, never another answer.
    for label, command in shapes.items():
        got = shim_judgement(command)
        check(f"through the shim, allowed or denied for being late and never otherwise: {label}", got in ("allow", "deny:slow"), got)
    got = verdict_cpu("git commit -m x")
    check("positive control: the verdict of a command a rule denies is that rule's, by the measuring child as well",
          isinstance(got, tuple) and got[0] == "git", f"{got!r}")
    got = shim_judgement("git commit -m x")
    check("positive control: through the shim that command is the rule's deny, or the late one, and never a crash or an allow",
          got in ("deny:git", "deny:slow"), got)
    got = shim_judgement("ls")
    check("positive control: a plain command is allowed (or late) too", got in ("allow", "deny:slow"), got)
    # What cannot depend on the load: the reading of an answer, and the late deny a budget of zero always produces.
    reasons = guard_reasons()
    deny = lambda key: json.dumps({"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": key}})  # noqa: E731
    texts = {key: text for text, key in reasons.items()}
    check("the reading of an answer: a rule's deny, the late deny, a crash, an unknown text, an allow and no answer",
          [judgement_of(deny(texts["git"]), reasons), judgement_of(deny(texts["slow"]), reasons), judgement_of(deny(texts["error"]), reasons),
           judgement_of(deny("something else"), reasons), judgement_of(json.dumps({"hookSpecificOutput": {"updatedInput": {}}}), reasons),
           judgement_of("", reasons)]
          == ["deny:git", "deny:slow", "deny:error", "deny:unknown reason", "allow", "allow"], "")
    got = shim_judgement("ls", AGENT_FABRIC_REVIEW_GUARD_BUDGET="0")
    check("a budget of zero is the late deny, through the shim", got == "deny:slow", got)


def clean_environment() -> None:
    # The structural half of the fence: whatever a spelling slips past the
    # patterns, the command it is in runs without the account's secrets
    # (docs/live-checks/2026-10-05-hook-updated-input.md).
    print("a command let through runs with a clean environment, and otherwise as asked")
    probe = "python3 tests/fixtures/clean-env-probe.py"
    got = rewritten({"command": probe, "timeout": 5000, "description": "names", "run_in_background": False})
    check("the rewrite reads no shell init file (--norc --noprofile): bash reads ~/.bashrc for a socket stdin",
          bool(got) and " bash --norc --noprofile -c " in got.get("command", ""), str(got))
    check("the rewrite keeps the rest of the input (timeout, description, background)",
          bool(got) and got.get("timeout") == 5000 and got.get("description") == "names"
          and got.get("run_in_background") is False, str(got))
    if not got:
        return
    shell_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/tmp"),
                 "LANG": "C.UTF-8", "PLANTED_GH_TOKEN": "planted", "PLANTED_SIGNING_KEY": "planted",
                 "SOME_UNLISTED": "x"}
    r = subprocess.run(["bash", "-c", got["command"]], capture_output=True, text=True, env=shell_env,
                       cwd=HERE, timeout=HANG_S)
    names = set(r.stdout.split())
    check("…a planted secret-shaped variable never reaches the command",
          r.returncode == 0 and not names & {"PLANTED_GH_TOKEN", "PLANTED_SIGNING_KEY"}, f"rc={r.returncode} {sorted(names)}")
    check("…nor an unlisted one, while PATH, HOME and LANG stay",
          "SOME_UNLISTED" not in names and {"PATH", "HOME", "LANG"} <= names, str(sorted(names)))
    check("…and an unset listed one stays unset (TZ is not set to empty)", "TZ" not in names, str(sorted(names)))
    marked = subprocess.run(["bash", "-c", got["command"]], capture_output=True, text=True,
                            env={**shell_env, "CLAUDECODE": "1", "AGENT_FABRIC_LAUNCH_PROFILE": "p"}, cwd=HERE, timeout=HANG_S)
    check("…and the session markers stay, so a tool still refuses inside a model session",
          {"CLAUDECODE", "AGENT_FABRIC_LAUNCH_PROFILE"} <= set(marked.stdout.split()), marked.stdout)
    got = rewritten({"command": "exit 3"})
    r = subprocess.run(["bash", "-c", got["command"]], capture_output=True, text=True, env=shell_env, timeout=HANG_S)
    check("…its exit status is the command's", r.returncode == 3, f"rc={r.returncode}")
    quoted = """printf '%s|' "it's" 'a$b' "$((1+2))" '"q"'"""
    got = rewritten({"command": quoted})
    direct = subprocess.run(["bash", "-c", quoted], capture_output=True, text=True, env=shell_env, timeout=HANG_S)
    r = subprocess.run(["bash", "-c", got["command"]], capture_output=True, text=True, env=shell_env, timeout=HANG_S)
    check("…and its quoting survives the rewrite", r.stdout == direct.stdout and r.stdout != "",
          f"direct=[{direct.stdout}] wrapped=[{r.stdout}]")


def fails_closed() -> None:
    print("a guard that cannot run, runs late or dies denies; it never silently allows")
    expect("with the fleet's Python unavailable the guard denies, even a harmless command", "deny", "ls",
           AGENT_FABRIC_PYTHON="/nonexistent")
    expect("a module that fails (any exit but 0) is a deny, even for ls", "deny", "ls",
           AGENT_FABRIC_PYTHON="/bin/false")
    expect("a verdict later than the budget is a deny, even for ls", "deny", "ls",
           AGENT_FABRIC_REVIEW_GUARD_BUDGET="0")
    print("malformed input allows and never exits 2")
    for payload in ("{}", "not json", ""):
        r = run(payload)
        check(f"payload ({payload or 'empty'}) allows (rc={r.returncode})",
              r.returncode != 2 and not r.stdout.strip(), f"rc={r.returncode} out=[{r.stdout}]")


def main() -> int:
    table()
    in_time()
    clean_environment()
    fails_closed()
    print()
    if failures:
        print(f"{failures} assertion(s) failed", file=sys.stderr)
        return 1
    print("all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
