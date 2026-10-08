#!/usr/bin/env python3
"""bin/fabric-resume (tools/fabric/resume.py) in a scratch account: the
binding's session resumed in the directory its transcript names; a fresh
start said, in the working copy, when there is no session, no transcript
or no directory; refused inside a session; the launcher run with exactly
--resume <id> (or nothing) after the caller's own arguments."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(HERE, "bin", "fabric-resume")
SID = "0f0e0d0c-1111-4222-8333-444455556666"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="test_fabric_resume.") as tmp:
        state, cfg, wc, ran = (os.path.join(tmp, n) for n in ("state", "claude", "wc", "launched"))
        os.makedirs(wc)
        agent = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
        host = subprocess.run(["hostname", "-s"], capture_output=True, text=True, check=True).stdout.strip()
        bdir = os.path.join(state, "agents", agent)
        os.makedirs(bdir)

        def bind(session: str | None) -> None:
            with open(os.path.join(bdir, "binding.json"), "w") as f:
                json.dump({"agent": agent, "host": host, "updated_at": "x", "role": "python-dev",
                           "working_copy": wc, "session": session}, f)

        def transcript(cwd: str) -> None:
            d = os.path.join(cfg, "projects", "-slug")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, f"{SID}.jsonl"), "w") as f:
                f.write(json.dumps({"type": "summary"}) + "\n" + json.dumps({"type": "user", "cwd": cwd}) + "\n")

        stub = os.path.join(tmp, "launch")
        with open(stub, "w") as f:
            f.write(f'#!/bin/sh\nprintf "%s|%s\\n" "$PWD" "$*" > "{ran}"\n')
        os.chmod(stub, 0o755)
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CONFIG_DIR")
               and not k.startswith(("AGENT_FABRIC_", "GITHUB_"))}
        env.update(AGENT_FABRIC_STATE_DIR=state, CLAUDE_CONFIG_DIR=cfg, AGENT_FABRIC_RESUME_LAUNCHER=stub,
                   AGENT_FABRIC_PYTHON=sys.executable)

        def run(*args: str, **extra: str) -> subprocess.CompletedProcess:
            return subprocess.run(["bash", SHIM, *args], env={**env, **extra}, capture_output=True, text=True,
                                  timeout=60)

        bind(SID)
        session_dir = os.path.join(tmp, "launched-from")
        os.makedirs(session_dir)
        transcript(session_dir)
        r = run("--print")
        check("a session with its transcript: resumed where it ran", r.returncode == 0
              and r.stdout.strip() == f"resuming session {SID} in {session_dir}", r.stdout + r.stderr)
        r = run("--", "--provider", "anthropic")
        line = open(ran).read().strip() if os.path.exists(ran) else ""
        check("…the launcher runs there, the caller's arguments first, then --resume <id>",
              r.returncode == 0 and line == f"{session_dir}|--provider anthropic --resume {SID}", line or r.stderr)

        os.rmdir(session_dir)
        r = run("--print")
        check("its directory gone: a fresh start in the working copy, said",
              f"directory is gone; starting fresh in {wc}" in r.stdout, r.stdout)
        os.remove(os.path.join(cfg, "projects", "-slug", f"{SID}.jsonl"))
        r = run("--print")
        check("no transcript: a fresh start, said", f"no transcript of session {SID}" in r.stdout, r.stdout)
        os.remove(ran)
        r = run()
        line = open(ran).read().strip() if os.path.exists(ran) else ""
        check("…and the launcher runs with no --resume, in the working copy", line == f"{wc}|", line)
        bind(None)
        check("no session recorded: a fresh start, said", "no session recorded" in run("--print").stdout)
        bind("../../etc/passwd")
        check("a session id that is not one: no transcript is looked up",
              "no transcript of session" in run("--print").stdout)
        r = run("--print", CLAUDECODE="1")
        check("inside a session: refused, exit 2", r.returncode == 2 and "not inside a session" in r.stderr, r.stderr)
        r = run("--bogus")
        check("an unknown argument: exit 2", r.returncode == 2, r.stderr)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
