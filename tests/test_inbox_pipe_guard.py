#!/usr/bin/env python3
"""Tests for runtime/claude-code/hooks/inbox-pipe-guard.py: which gzcoord-inbox runs are refused for piping or
capturing a consuming run's page, which pass, and the hook's protocol end to end (j1090). No case here runs a real
gzcoord-inbox: the guard only reads the command text, and a real drain would consume this login's inbox."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory

# Held by tests/test_own_instance_tree.py: this file names AGENT_FABRIC_ROOT. The fallback cases build a closed
# environment, so no exported operator reaches them; the call changes nothing this suite does.
own_instance_tree()

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(HERE, "runtime", "claude-code", "hooks", "inbox-pipe-guard.py")
spec = importlib.util.spec_from_file_location("inbox_pipe_guard", HOOK)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


def run(payload: str, hook: str = HOOK) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", "-S", hook], input=payload, capture_output=True, text=True, timeout=60)


def decision(out: str) -> str | None:
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out.strip() else None


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    refused = [
        ("the 2026-11-24 shape: the drain into head", "gzcoord-inbox | head -n 20"),
        ("stderr folded in, then a pipe", "gzcoord-inbox 2>&1 | tail -5"),
        ("|& alone", "gzcoord-inbox |& cat"),
        ("--wait into grep", "gzcoord-inbox --wait 60 | grep X"),
        ("--follow piped", "gzcoord-inbox --follow | head"),
        ("--until-delivery piped", "gzcoord-inbox --until-delivery | tail -1"),
        ("the dispatcher's spelling", "fabric gzcoord inbox | head"),
        ("the dispatcher's spelling with --wait", "fabric gzcoord inbox --wait 30 | head"),
        ("after cd &&", "cd x && gzcoord-inbox | sed -n 1,5p"),
        ("a multi-line command", "cd /tmp\ngzcoord-inbox \\\n  | head -n 3\necho done"),
        ("an absolute path to the link", "/home/someone/.local/bin/gzcoord-inbox | head"),
        ("bin/ in a checkout", "bin/gzcoord-inbox | head"),
        ("behind a wrapper", "timeout 60 gzcoord-inbox --wait 5 | head"),
        ("behind an assignment", "LC_ALL=C gzcoord-inbox | head"),
        ("run by an interpreter", "python3 -I bin/gzcoord-inbox | head"),
        ("the module by path", "fabric-python -I tools/fabric/gzcoord/inbox.py | head"),
        ("tee: refused like any pipe", "gzcoord-inbox | tee \"$f\""),
        ("--help drains: inbox.py does not read it", "gzcoord-inbox --help | head"),
        ("-h drains too", "gzcoord-inbox -h | head"),
        ("--replay=ID is no replay to inbox.py, which tests the whole word", "gzcoord-inbox --replay=01a | head"),
        ("a single-quoted shell payload", "bash -c 'gzcoord-inbox | head'"),
        ("a single-quoted shell payload, the pipe outside", "bash -c 'gzcoord-inbox' | head"),
        ("a double-quoted shell payload", 'bash -c "gzcoord-inbox | head"'),
        ("captured by a substitution", "x=$(gzcoord-inbox)"),
        ("captured in a double-quoted substitution", 'echo "$(gzcoord-inbox)" | head'),
        ("captured by backticks", "x=`gzcoord-inbox`"),
        ("read by a process substitution", "while read -r l; do :; done < <(gzcoord-inbox)"),
        ("written into a process substitution", "gzcoord-inbox > >(head)"),
        ("a brace group piped", "{ gzcoord-inbox; } | head"),
        ("a subshell piped", "( gzcoord-inbox ) | head"),
        ("a loop piped", "while gzcoord-inbox --wait 5; do :; done | head"),
    ]
    for label, cmd in refused:
        check(f"refused: {label}", g.refused(cmd), cmd)

    allowed = [
        ("the bare drain", "gzcoord-inbox"),
        ("the armed watch, as session-start and the gzcoord-receive skill spell it", "gzcoord-inbox --until-delivery"),
        ("the watch re-armed in place", "gzcoord-inbox --until-delivery --replace"),
        ("--wait bare", "gzcoord-inbox --wait 60"),
        ("to a file", 'gzcoord-inbox > "$f"'),
        ("appended to a file, then read whole", "gzcoord-inbox >> inbox.txt; cat inbox.txt"),
        ("&> a file", "gzcoord-inbox &> inbox.txt"),
        ("--replay piped: nothing is consumed", "gzcoord-inbox --replay 01a2b3 | head"),
        ("--history piped", "gzcoord-inbox --history | tail"),
        ("--held piped", "gzcoord-inbox --held | cat"),
        ("--replay in the dispatcher's spelling", "fabric gzcoord inbox --replay 01a | head"),
        ("a substitution of a read-only mode", "echo $(gzcoord-inbox --history) | head"),
        ("the word as echo's argument: a mention, not a run", "echo gzcoord-inbox | cat"),
        ("the word in a grep", "grep -rn gzcoord-inbox docs | head"),
        ("the word in a double-quoted commit message", 'git commit -m "gzcoord-inbox | head lost messages"'),
        ("the self-kill guard's incident, single-quoted", "pgrep -f 'gzcoord-inbox --follow' | xargs kill"),
        ("a comment", "ls # gzcoord-inbox | head"),
        ("a quoted heredoc body", "cat <<'EOF' | gzcoord-send -\ngzcoord-inbox | head\nEOF"),
        ("a pipe in another command after ;", "gzcoord-inbox; git log | head"),
        ("a pipe in another command after &&", "gzcoord-inbox && git log | head"),
        ("a subshell, no pipe", "(gzcoord-inbox)"),
        ("stdout to /dev/null: outside the contract, the coordinator's call", "gzcoord-inbox > /dev/null"),
        ("no inbox at all", "git log | head"),
        ("another inbox", "ls ~/inbox | head"),
    ]
    for label, cmd in allowed:
        check(f"allowed: {label}", not g.refused(cmd), cmd)

    # The protocol, run the way the settings run it (-I -S, by path).
    deny = run(json.dumps({"tool_name": "Bash", "tool_input": {"command": "gzcoord-inbox | head -n 3"}}))
    got = json.loads(deny.stdout) if deny.stdout.strip() else {}
    reason = got.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
    check("deny: one PreToolUse deny line, exit 0, nothing on stderr",
          deny.returncode == 0 and decision(deny.stdout) == "deny" and deny.stdout.count("\n") == 1 and not deny.stderr,
          (deny.returncode, deny.stdout, deny.stderr))
    check("deny: the reason names the way out (bare, a file, --replay)",
          "bare" in reason and "file" in reason and "gzcoord-inbox --replay <MESSAGE-ID>" in reason, reason)
    sub = run(json.dumps({"tool_name": "Bash", "agent_id": "a1", "agent_type": "code-low",
                          "tool_input": {"command": "gzcoord-inbox | tail -2"}}))
    check("a subagent's call is judged as the session's", decision(sub.stdout) == "deny", sub.stdout)
    for label, payload in (("not JSON", "not json"), ("an array", "[1]"), ("tool_input a string", '{"tool_input": "x"}'),
                           ("no command", '{"tool_input": {}}'), ("a number for the command", '{"tool_input": {"command": 3}}'),
                           ("an allowed command", json.dumps({"tool_input": {"command": "gzcoord-inbox"}}))):
        r = run(payload)
        check(f"passed with nothing printed, exit 0: {label}", (r.returncode, r.stdout) == (0, ""), (r.returncode, r.stdout, r.stderr))

    with tempfile.TemporaryDirectory() as tmp:
        # A guard that cannot decide exits non-zero with nothing on stdout, which hook_entry.py and the settings
        # fallback turn into an ask; it must never print an allow. Its sibling missing is such a failure.
        hooks = os.path.join(tmp, "runtime", "claude-code", "hooks")
        os.makedirs(hooks)
        shutil.copy(HOOK, hooks)
        r = run(json.dumps({"tool_input": {"command": "gzcoord-inbox | head"}}), os.path.join(hooks, "inbox-pipe-guard.py"))
        check("its sibling missing: exit non-zero, nothing on stdout (the caller asks)", r.returncode != 0 and r.stdout == "",
              (r.returncode, r.stdout))
        r = run(json.dumps({"tool_input": {"command": "git log | head"}}), os.path.join(hooks, "inbox-pipe-guard.py"))
        check("its sibling missing: a command naming no inbox still passes, nothing loaded",
              (r.returncode, r.stdout) == (0, ""), (r.returncode, r.stdout))
        # An unreadable command table leaves the spelled names: "unreadable" is not "no drain".
        for sib in ("post-review-shape-guard.py", "inbox-watch.py"):
            shutil.copy(os.path.join(HERE, "runtime", "claude-code", "hooks", sib), hooks)
        for label, cmd in (("gzcoord-inbox", "gzcoord-inbox | head"), ("fabric gzcoord inbox", "fabric gzcoord inbox | head")):
            r = run(json.dumps({"tool_input": {"command": cmd}}), os.path.join(hooks, "inbox-pipe-guard.py"))
            check(f"no command table: the spelled name {label} is still refused", decision(r.stdout) == "deny",
                  (r.returncode, r.stdout, r.stderr[-300:]))
        r = run(json.dumps({"tool_input": {"command": "gzcoord-inbox --replay 01a | head"}}),
                os.path.join(hooks, "inbox-pipe-guard.py"))
        check("no command table: a read-only mode still passes", (r.returncode, r.stdout) == (0, ""), (r.returncode, r.stdout))

    # The managed entry knows it, so a managed host runs it and asks when it cannot.
    sys.path.insert(0, os.path.join(HERE, "runtime", "claude-code", "managed"))
    import hook_entry  # noqa: E402
    check("hook_entry's table names it on PreToolUse, with a label",
          hook_entry.GUARDS.get("inbox-pipe-guard", ("", "", ""))[:2] == ("runtime/claude-code/hooks/inbox-pipe-guard.py",
                                                                         "PreToolUse")
          and "inbox-pipe-guard" in hook_entry.LABEL)

    # Registered where every session runs it, in both settings files, with the fallback that asks.
    for rel in (".claude/settings.json", "runtime/claude-code/workspace/settings.json"):
        with open(os.path.join(HERE, rel), encoding="utf-8") as fh:
            pre = json.load(fh)["hooks"]["PreToolUse"]
        hooked = [h["command"] for e in pre if e.get("matcher") == "Bash" for h in e["hooks"]]
        check(f"registered on Bash in {rel}", any("inbox-pipe-guard.py" in c for c in hooked), hooked)
        pin = "/usr/local/bin/fabric-python"
        cmds = [h["command"] for e in pre for h in e["hooks"] if "hooks/inbox-pipe-guard.py" in h.get("command", "")]
        check(f"{rel}: one fallback, none on python3", len(cmds) == 1 and "python3 " not in cmds[0], cmds)
        if len(cmds) != 1:
            continue
        shadow = tempfile.mkdtemp(prefix="guard-shadow-")
        with open(os.path.join(shadow, "json.py"), "w", encoding="utf-8") as fh:
            fh.write("import sys; sys.exit(0)\n")
        cmd = cmds[0].replace("/etc/claude-code/managed-settings.json", os.path.join(shadow, "no-managed.json"))
        env = {"PATH": "/usr/bin:/bin", "HOME": shadow, "CLAUDE_PROJECT_DIR": HERE, "AGENT_FABRIC_ROOT": HERE}
        payload = {"tool_name": "Bash", "tool_input": {"command": "gzcoord-inbox | head"}}
        for label, c, extra, want in (
                ("the pin runs it", cmd.replace(pin, sys.executable), {}, "deny"),
                ("PYTHONPATH does not silence it", cmd.replace(pin, sys.executable), {"PYTHONPATH": shadow}, "deny"),
                ("a missing pin asks", cmd.replace(pin, os.path.join(shadow, "no-python")), {}, "ask"),
                ("a missing guard file asks",
                 cmd.replace(pin, sys.executable).replace("hooks/inbox-pipe-guard.py", "hooks/no-such-guard.py"), {}, "ask")):
            r = subprocess.run(["sh", "-c", c], input=json.dumps(payload), capture_output=True, text=True,
                               env={**env, **extra}, timeout=60)
            check(f"{rel}: fallback: {label}", r.returncode == 0 and decision(r.stdout) == want, (r.returncode, r.stdout[-200:]))
        r = subprocess.run(["sh", "-c", cmd.replace(pin, sys.executable)], input=json.dumps({"tool_input": {"command": "ls"}}),
                           capture_output=True, text=True, env=env, timeout=60)
        check(f"{rel}: fallback: an allowed command passes with no output", (r.returncode, r.stdout) == (0, ""),
              (r.returncode, r.stdout[-200:]))
        shutil.rmtree(shadow, True)

    print(f"{'PASS' if not fails else 'FAIL'}: inbox pipe guard ({fails} failed)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
