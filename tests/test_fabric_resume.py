#!/usr/bin/env python3
"""bin/fabric-resume (tools/fabric/resume.py) in a scratch account: the
binding's session resumed in the directory its transcript names; a fresh
start said, in the working copy, when there is no session, no transcript
or no directory; refused inside a session; the launcher run with the
account's last provider (unless the caller names one), the caller's own
arguments, then --resume <id> (or nothing)."""
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
        # The live routing/profiles.json names a launch_provider for some
        # logins: the subprocess runs read a fixture with none, so the result
        # never depends on which login runs the suite (review of the branch).
        noprof = os.path.join(tmp, "profiles-none.json")
        with open(noprof, "w") as f:
            json.dump({"version": 1, "defaults": {}}, f)
        env.update(AGENT_FABRIC_STATE_DIR=state, CLAUDE_CONFIG_DIR=cfg, AGENT_FABRIC_RESUME_LAUNCHER=stub,
                   AGENT_FABRIC_PYTHON=sys.executable, AGENT_FABRIC_RESUME_PROFILES=noprof)

        def run(*args: str, **extra: str) -> subprocess.CompletedProcess:
            return subprocess.run(["bash", SHIM, *args], env={**env, **extra}, capture_output=True, text=True,
                                  timeout=60)

        bind(SID)
        session_dir = os.path.join(tmp, "launched-from")
        os.makedirs(session_dir)
        transcript(session_dir)
        r = run("--print")
        check("a session with its transcript: resumed where it ran", r.returncode == 0
              and r.stdout.strip() == f"resuming session {SID} in {session_dir}: --resume {SID}", r.stdout + r.stderr)
        withprof = os.path.join(tmp, "profiles-role.json")
        with open(withprof, "w") as f:
            json.dump({"version": 1, "defaults": {}, "roles": {"python-dev": {"launch_provider": "openrouter"}}}, f)
        r = run("--print", AGENT_FABRIC_RESUME_PROFILES=withprof)
        check("no launch on record: the profile's launch_provider for the binding's role",
              r.stdout.strip().endswith(f": --provider openrouter --resume {SID}"), r.stdout + r.stderr)
        with open(os.path.join(bdir, "launch-provider.json"), "w") as f:
            json.dump({"provider": "anthropic"}, f)
        run()
        line = open(ran).read().strip() if os.path.exists(ran) else ""
        check("…on the provider the account last launched on, not the launcher's default",
              line == f"{session_dir}|--provider anthropic --resume {SID}", line)
        r = run("--", "--provider=openrouter")
        line = open(ran).read().strip() if os.path.exists(ran) else ""
        check("…unless the caller names one", line == f"{session_dir}|--provider=openrouter --resume {SID}", line)
        r = run("--", "--provider", "anthropic")
        line = open(ran).read().strip() if os.path.exists(ran) else ""
        check("…the launcher runs there, the caller's arguments first, then --resume <id>",
              r.returncode == 0 and line == f"{session_dir}|--provider anthropic --resume {SID}", line or r.stderr)

        os.rmdir(session_dir)
        r = run("--print")
        check("its directory gone: a fresh start in the working copy, said",
              f"directory is gone, or not this account's; starting fresh in {wc}" in r.stdout, r.stdout)
        os.remove(os.path.join(cfg, "projects", "-slug", f"{SID}.jsonl"))
        r = run("--print")
        check("no transcript: a fresh start, said", f"no transcript of session {SID}" in r.stdout, r.stdout)
        os.remove(ran)
        r = run()
        line = open(ran).read().strip() if os.path.exists(ran) else ""
        check("…and the launcher runs with no --resume, in the working copy", line == f"{wc}|--provider anthropic", line)
        bind(None)
        check("no session recorded: a fresh start, said", "no session recorded" in run("--print").stdout)
        # Planted where an unchecked id would reach: projects/-slug/../../etc/x.jsonl.
        os.makedirs(os.path.join(cfg, "etc"))
        with open(os.path.join(cfg, "etc", "x.jsonl"), "w") as f:
            f.write(json.dumps({"type": "user", "cwd": wc}) + "\n")
        for bad in ("../../etc/x", "abc\x1b]0;t\x07def", 42):
            bind(bad)  # type: ignore[arg-type]
            r = run("--print")
            check(f"a binding session {bad!r} is no session, never a path", "no session recorded" in r.stdout
                  and "--resume" not in r.stdout, r.stdout)
        r = run("--print", CLAUDECODE="1")
        check("inside a session: refused, exit 2", r.returncode == 2 and "not inside a session" in r.stderr, r.stderr)
        r = run("--bogus")
        check("an unknown argument: exit 2", r.returncode == 2, r.stderr)

        # A first launch (no launch-provider.json): the profile's
        # launch_provider, the agent's layer before the role's before the
        # defaults'; an unknown value or an unreadable file is none.
        sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
        import resume
        root = os.path.join(tmp, "fabric")
        os.makedirs(os.path.join(root, "routing"))

        def profiles(doc) -> None:
            with open(os.path.join(root, "routing", "profiles.json"), "w") as f:
                f.write(doc if isinstance(doc, str) else json.dumps(doc))
        real = resume.FABRIC
        resume.FABRIC = root
        try:
            profiles({"defaults": {"launch_provider": "openrouter"}, "roles": {"python-dev": {"launch_provider": "anthropic"}},
                      "agents": {"pd-x": {"launch_provider": "openrouter"}}})
            check("the agent's layer first", resume.profile_provider("pd-x", "python-dev") == "openrouter")
            check("…then the role's", resume.profile_provider("pd-y", "python-dev") == "anthropic")
            check("…then the defaults'", resume.profile_provider("pd-y", "web-dev") == "openrouter")
            last, who = resume.install_agent_files.last_launch_provider, resume.identity.current_agent
            try:
                resume.identity.current_agent = lambda: "pd-x"
                resume.install_agent_files.last_launch_provider = lambda: None
                check("a first launch takes the profile's provider",
                      resume.provider_args([], {"role": "python-dev"}) == ["--provider", "openrouter"])
                resume.install_agent_files.last_launch_provider = lambda: "anthropic"
                check("…a recorded launch wins over it", resume.provider_args([], {"role": "python-dev"}) == ["--provider", "anthropic"])
                check("…and the caller's --provider over both", resume.provider_args(["--provider", "x"], {}) == [])
            finally:
                resume.install_agent_files.last_launch_provider, resume.identity.current_agent = last, who
            profiles({"defaults": {}, "agents": {"pd-x": {"launch_provider": "moon"}}})
            check("an unknown provider is none", resume.profile_provider("pd-x", None) is None)
            profiles("not json")
            check("an unreadable file is none", resume.profile_provider("pd-x", None) is None)
            for wrong in ([], {"agents": ["pd-x"]}, {"roles": "python-dev", "defaults": 3}):
                profiles(wrong)
                check(f"a file of the wrong shape is none, never a traceback ({json.dumps(wrong)})",
                      resume.profile_provider("pd-x", "python-dev") is None)
        finally:
            resume.FABRIC = real
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
