#!/usr/bin/env python3
"""bin/fabric-resume (tools/fabric/resume.py) in a scratch account: the
binding's session resumed in the directory its transcript names; a fresh
start said, in the working copy, when there is no session, no transcript
or no directory; refused inside a session; the launcher run with the
account's last provider (unless the caller names one), the caller's own
arguments, then --resume <id> (or nothing). Never a second session: any
live session in the account's session state refuses a resume and a fresh
start alike, a dead or reused pid does not, nor an entry with no process
older than 20 min; resume.lock held by another
process refuses, naming its pid, and the launcher it execs holds it;
--print takes none."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(HERE, "bin", "fabric-resume")
SID = "0f0e0d0c-1111-4222-8333-444455556666"


def start_of(pid: int) -> int:
    raw = open(f"/proc/{pid}/stat").read()
    return int(raw[raw.rindex(")") + 2:].split()[19])


def never_second(check, run, bind, transcript, bdir: str, tmp: str, env: dict, session_dir: str) -> None:
    """The refusal and the lock (docs/fleet-deck/tab-states.md)."""
    states = os.path.join(bdir, "session-state.json")
    lock = os.path.join(bdir, "resume.lock")
    other = "aaaabbbb-1111-4222-8333-444455556666"

    def sessions(doc) -> None:
        with open(states, "w") as f:
            f.write(doc if isinstance(doc, str) else json.dumps({"sessions": doc}))

    os.makedirs(session_dir, exist_ok=True)
    bind(SID)
    transcript(session_dir)
    sleeper = subprocess.Popen(["sleep", "300"])
    try:
        sessions({other: {"state": "working", "since": "x", "pid": sleeper.pid, "start": start_of(sleeper.pid)}})
        r = run()
        check("a live session that is not the binding's: a resume refused, exit 3, naming it",
              r.returncode == 3 and f"refused: session {other} is alive" in r.stderr, (r.returncode, r.stderr))
        bind(None)
        r = run()
        check("…and a fresh start refused alike", r.returncode == 3 and other in r.stderr, (r.returncode, r.stderr))
        r = run("--print")
        check("…said the same under --print", r.returncode == 3 and other in r.stderr and not r.stdout,
              (r.returncode, r.stdout, r.stderr))
        bind(SID)
        sessions({other: {"state": "idle", "since": "x", "pid": sleeper.pid, "start": start_of(sleeper.pid) + 1}})
        r = run("--print")
        check("a pid alive with another start time is a reused pid: no session", r.returncode == 0, r.stderr)
        def ago(minutes: int) -> str:
            return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - minutes * 60))
        sessions({other: {"state": "idle", "since": ago(5), "pid": None, "start": None}})
        r = run("--print")
        check("an entry that records no process, within 20 min of its since: counted", r.returncode == 3
              and other in r.stderr, (r.returncode, r.stderr))
        sessions({other: {"state": "idle", "since": ago(25)}})
        r = run("--print")
        check("…older than that: not counted, and said, naming it", r.returncode == 0
              and f"session {other} records no process and its state is older than 20 min; not counted" in r.stderr,
              (r.returncode, r.stderr))
        sessions({other: {"state": "idle", "since": "x"}})
        check("…a since that is not a time: not counted", run("--print").returncode == 0)
        sessions({other: {"state": "gone-ish", "since": "x", "pid": sleeper.pid, "start": start_of(sleeper.pid)}})
        check("an entry in no known state is no session", run("--print").returncode == 0)
        for shape in ("[]", "{}", '{"sessions": []}'):
            sessions(shape)
            r = run("--print")
            check(f"a session state of another shape ({shape}) refuses, never reads as none",
                  r.returncode == 3 and "not the session-state hook's shape" in r.stderr, (r.returncode, r.stderr))
        sessions("{torn")
        r = run("--print")
        check("a session state that cannot be read refuses: unknown is never none",
              r.returncode == 3 and "cannot be read" in r.stderr, (r.returncode, r.stderr))
    finally:
        sleeper.kill()
        sleeper.wait()
    sessions({other: {"state": "working", "since": "x", "pid": sleeper.pid, "start": 1}})
    r = run("--print")
    check("a dead pid record does not count", r.returncode == 0 and "--resume" in r.stdout, (r.returncode, r.stderr))
    os.remove(states)

    # A child holds the lock as a running launcher would.
    holder = subprocess.Popen([sys.executable, "-c", (
        "import fcntl,os,sys\n"
        "fd=os.open(sys.argv[1],os.O_RDWR|os.O_CREAT,0o600); fcntl.flock(fd,fcntl.LOCK_EX)\n"
        "if sys.argv[2]=='pid': os.ftruncate(fd,0); os.write(fd,b'%d\\n'%os.getpid())\n"
        "print('held',flush=True); sys.stdin.read()"), lock, "pid"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        holder.stdout.readline()
        r = run()
        check("a held lock refuses, exit 3, naming the holder's pid",
              r.returncode == 3 and f"(pid {holder.pid})" in r.stderr, (r.returncode, r.stderr))
        r = run("--print")
        check("…said the same under --print, which takes none", r.returncode == 3 and f"pid {holder.pid}" in r.stderr,
              (r.returncode, r.stderr))
        r = run("--", "--print")
        check("…and under the launcher's own --print", r.returncode == 3, (r.returncode, r.stderr))
    finally:
        holder.stdin.close()
        holder.wait()
    # The last holder's pid is still in the file, its process gone: the
    # new holder has locked and not yet written.
    gone = subprocess.Popen(["true"])
    gone.wait()
    with open(lock, "w") as f:
        f.write(f"{gone.pid}\n")
    holder = subprocess.Popen([sys.executable, "-c", (
        "import fcntl,os,sys\n"
        "fd=os.open(sys.argv[1],os.O_RDWR); fcntl.flock(fd,fcntl.LOCK_EX)\n"
        "print('held',flush=True); sys.stdin.read()"), lock],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        holder.stdout.readline()
        r = run()
        check("a lock held with no pid of its own in it yet: said so, never the last holder's",
              r.returncode == 3 and "pid not yet written" in r.stderr and str(gone.pid) not in r.stderr, r.stderr)
    finally:
        holder.stdin.close()
        holder.wait()

    # The launcher it execs: is the descriptor open there, and locked?
    seen = os.path.join(tmp, "lock-seen")
    stub = os.path.join(tmp, "launch-lock")
    with open(stub, "w") as f:
        f.write(f"#!{sys.executable}\n" + (
            "import fcntl,json,os,sys\n"
            "lock=sys.argv[0] and os.environ['LOCK']\n"
            "fds=[int(d) for d in os.listdir('/proc/self/fd') if os.path.realpath(f'/proc/self/fd/{d}')==lock]\n"
            "locked,written=False,None\n"
            "if os.path.exists(lock):\n"
            "    probe=os.open(lock,os.O_RDONLY); written=open(lock).read().strip()\n"
            "    try:\n        fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
            "    except BlockingIOError:\n        locked=True\n"
            "json.dump({'fds':fds,'locked':locked,'pid':os.getpid(),'written':written,"
            "'args':sys.argv[1:]},open(os.environ['SEEN'],'w'))\n"))
    os.chmod(stub, 0o755)
    os.remove(lock)
    r = run(AGENT_FABRIC_RESUME_LAUNCHER=stub, LOCK=os.path.realpath(lock), SEEN=seen)
    got = json.load(open(seen)) if os.path.exists(seen) else {}
    check("the exec'd launcher has the lock open and held, its own pid written",
          r.returncode == 0 and len(got.get("fds", [])) == 1 and got.get("locked") is True
          and got.get("written") == str(got.get("pid")), (r.returncode, r.stderr, got))
    check("…and the lock goes with it", run("--print").returncode == 0)
    os.remove(seen)
    os.remove(lock)
    r = run("--", "--print", AGENT_FABRIC_RESUME_LAUNCHER=stub, LOCK=os.path.realpath(lock), SEEN=seen)
    got = json.load(open(seen)) if os.path.exists(seen) else {}
    check("--print passed to the launcher: no lock taken", r.returncode == 0 and "--print" in got.get("args", [])
          and not got.get("fds") and not os.path.exists(lock), (r.returncode, r.stderr, got))
    r = run("--print")
    check("--print: no lock taken", r.returncode == 0 and not os.path.exists(lock), (r.returncode, r.stderr))
    if os.path.exists(seen):
        os.remove(seen)


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
        never_second(check, run, bind, transcript, bdir, tmp, env, os.path.join(tmp, "launched-from"))
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
        real = os.environ.get("AGENT_FABRIC_OPERATOR")
        os.environ["AGENT_FABRIC_OPERATOR"] = root
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
            if real is None:
                os.environ.pop("AGENT_FABRIC_OPERATOR", None)
            else:
                os.environ["AGENT_FABRIC_OPERATOR"] = real
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
