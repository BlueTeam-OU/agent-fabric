#!/usr/bin/env python3
"""Tests for tools/fabric/status.py's internals; the behaviour is
tests/test_fabric_status_cli.py's, run against the bin/fabric-status shim
(ADR-040 §5 rule 5). Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import socket
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import status  # noqa: E402

LOGIN = pwd.getpwuid(os.getuid()).pw_name
HOST = socket.gethostname().split(".")[0]
SHIM = os.path.join(HERE, "bin", "fabric-status")


def clean_env(**extra) -> dict:
    """What a fabric process sees in CI: nothing of this session's launch."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "ANTHROPIC_", "CLAUDE_", "OPENROUTER_", "MOVETO_"))}
    env.update(extra)
    return env


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        os.makedirs(home)

        def put(path: str, text: str) -> str:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            return path

        saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(clean_env(HOME=home))
        try:
            print("which API path")
            check("no base URL: vanilla, not launched", status.api_path({})[:2] == (
                "anthropic", "vanilla claude, Anthropic direct, not launched by the fabric (harness defaults for every tier)"))
            check("launched by the fabric", status.api_path({"AGENT_FABRIC_LAUNCH_PROVIDER": "anthropic"})[1].endswith(", launched by the fabric"))
            check("another launch provider is not 'launched'", status.api_path({"AGENT_FABRIC_LAUNCH_PROVIDER": "openrouter"})[1].endswith("(harness defaults for every tier)"))
            check("openrouter.ai is the broker", status.api_path({"ANTHROPIC_BASE_URL": "https://openrouter.ai/api"})[:2] == ("openrouter", "broker (ori)"))
            check("a subdomain is the broker", status.api_path({"ANTHROPIC_BASE_URL": "https://eu.openrouter.ai/x"})[0] == "openrouter")
            check("a look-alike host is custom", status.api_path({"ANTHROPIC_BASE_URL": "https://evilopenrouter.ai/x"})[1] == "custom base URL (evilopenrouter.ai)")
            check("a launch provider does not change a custom path", status.api_path({"ANTHROPIC_BASE_URL": "http://h:1", "AGENT_FABRIC_LAUNCH_PROVIDER": "anthropic"})[1] == "custom base URL (h)")
            check("an unparsable URL has no host and is custom", status.api_path({"ANTHROPIC_BASE_URL": "http://[::1"})[1:3] == ("custom base URL ()", ""))

            # The session's credentials are read from the harness process
            # (its Bash holds none now): a fake /proc, a bash under a claude.
            proc = os.path.join(tmp, "proc")
            for pid, comm, ppid, env in ((40, "bash", 30, b"PATH=/x\0"), (30, "claude", 20, b"CLAUDE_CODE_OAUTH_TOKEN=t\0A=b=c\0"),
                                         (20, "python3", 1, b"")):
                os.makedirs(os.path.join(proc, str(pid)))
                for name, body in (("comm", f"{comm}\n".encode()), ("status", f"Name:\t{comm}\nPPid:\t{ppid}\n".encode()),
                                   ("environ", env)):
                    with open(os.path.join(proc, str(pid), name), "wb") as fh:
                        fh.write(body)
            check("the nearest claude ancestor's environment is the session's",
                  status.harness_environ(40, proc) == {"CLAUDE_CODE_OAUTH_TOKEN": "t", "A": "b=c"})
            check("no claude up the chain: None, and the caller uses its own", status.harness_environ(20, proc) is None)
            check("an unreadable /proc: None, never a crash", status.harness_environ(99, proc) is None)
            found = lambda: {"CLAUDE_CODE_OAUTH_TOKEN": "t"}  # noqa: E731
            check("outside a session's Bash the harness is never asked",
                  status.session_environ({}, found) is None and status.session_environ({"CLAUDECODE": "0"}, found) is None)
            check("…inside one it is", status.session_environ({"CLAUDECODE": "1"}, found) == {"CLAUDE_CODE_OAUTH_TOKEN": "t"})

            print("the fallback marker")
            fb = os.path.join(tmp, "fb")
            alive = os.getpid()
            put(os.path.join(fb, "a.json"), json.dumps({"pid": alive, "from_model": "x", "to_model": "y", "at": "t"}))
            env = {"AGENT_FABRIC_FALLBACK_DIR": fb}
            m = status.fallback_marker(env)
            check("a live marker is found", bool(m) and m["from_model"] == "x")
            check("…and said as drift with both models", "fell back from x to y at t" in (status.fallback_drift_line(m) or ""))
            check("no marker, no line", status.fallback_drift_line(None) is None)
            # 2**22 - 5 can be live where pid_max is 2**22; no pid reaches 2**22.
            put(os.path.join(fb, "a.json"), json.dumps({"pid": 2 ** 22 + 1}))
            check("a dead pid is not a fallback", status.fallback_marker(env) is None)
            put(os.path.join(fb, "a.json"), json.dumps({"pid": 0}))
            check("pid 0 is not a fallback", status.fallback_marker(env) is None)
            put(os.path.join(fb, "a.json"), "[1]")
            check("a marker that is not an object is skipped, not a crash", status.fallback_marker(env) is None)
            put(os.path.join(fb, "a.json"), "{{")
            check("garbage is skipped", status.fallback_marker(env) is None)
            put(os.path.join(fb, "7.json"), json.dumps({"pid": alive, "from_model": "mine"}))
            put(os.path.join(fb, "a.json"), json.dumps({"pid": alive, "from_model": "other"}))
            check("CLAUDE_PID picks its own marker over the scan", status.fallback_marker({**env, "CLAUDE_PID": "7"})["from_model"] == "mine")
            check("CLAUDE_PID without a file falls back to the scan", status.fallback_marker({**env, "CLAUDE_PID": "8"})["from_model"] in ("other", "mine"))
            check("a missing directory is no marker", status.fallback_marker({"AGENT_FABRIC_FALLBACK_DIR": os.path.join(tmp, "none")}) is None)

            print("the sign-in")
            fp = hashlib.sha256(b"tok").hexdigest()[:12]
            check("fp12 is the first twelve hex of sha256", status.fp12("tok") == fp)
            check("no record: None", status.synced_template_token() is None)
            rec = os.path.join(home, ".config", "agent-fabric", "secrets.env")
            for text, want in (("export CLAUDE_CODE_OAUTH_TOKEN='tok'\n", "tok"), ('export CLAUDE_CODE_OAUTH_TOKEN="tok"\n', "tok"),
                               ("export CLAUDE_CODE_OAUTH_TOKEN=tok\n", "tok"), ("export CLAUDE_CODE_OAUTH_TOKEN=\n", None),
                               ("export CLAUDE_CODE_OAUTH_TOKEN=''\n", None), ("export CLAUDE_CODE_OAUTH_TOKEN='\n", "'"),
                               ("# c\nexport X=1\nexport CLAUDE_CODE_OAUTH_TOKEN=tok  \n", "tok"), ("export OTHER=1\n", None)):
                put(rec, text)
                check(f"record {text.strip()!r} -> {want!r}", status.synced_template_token() == want)
            os.remove(rec)
            check("env and record agree: no drift", status.signin_drift_line("a", "a", "") is None)
            check("env and record both absent: no drift", status.signin_drift_line(None, None, "") is None)
            check("no env, a record, direct path: drift naming the record", "runs on no token, the login's synced record names setup-token" in (status.signin_drift_line(None, "tok", "") or ""))
            check("no env, a record, broker: the launcher removed it, no drift", status.signin_drift_line(None, "tok", "https://openrouter.ai") is None)
            check("env differs from record on the broker: still drift", status.signin_drift_line("a", "b", "https://openrouter.ai") is not None)
            check("env, no record: drift says none", "names none" in (status.signin_drift_line("a", None, "") or ""))
            check("the token is fingerprinted, never printed", "tok-secret" not in (status.signin_drift_line("tok-secret", "other", "") or "")
                  and "tok-secret" not in status.claude_sign_in("tok-secret", None, {}))
            check("the environment outranks the record", "CLAUDE_CODE_OAUTH_TOKEN in this session" in status.claude_sign_in("e", "r", {}))
            check("the record when there is no environment", "the login's synced record" in status.claude_sign_in(None, "r", {}))
            check("no token, no profile", status.claude_sign_in(None, None, {}) == "own /login (none recorded)")
            put(os.path.join(home, ".claude.json"), json.dumps({"oauthAccount": {"emailAddress": "a@b.c"}}))
            check("no token: the email", status.claude_sign_in(None, None, {}) == "own /login (a@b.c)")
            put(os.path.join(tmp, "cfg", ".claude.json"), json.dumps({"oauthAccount": {"emailAddress": "cfg@x"}}))
            check("CLAUDE_CONFIG_DIR outranks HOME", status.claude_sign_in(None, None, {"CLAUDE_CONFIG_DIR": os.path.join(tmp, "cfg")}) == "own /login (cfg@x)")
            put(os.path.join(home, ".claude.json"), "{x")
            check("an unparsable profile is 'none recorded'", status.claude_sign_in(None, None, {}) == "own /login (none recorded)")

            print("the launched prompt")
            state = os.path.join(tmp, "state")
            body = b"prompt text\n"
            digest = "sha256:" + hashlib.sha256(body).hexdigest()
            check("no digest, no question", status.prompt_drift_line(None, state) is None)
            check("a digest and no file: gone", "the launched prompt file is gone (" in (status.prompt_drift_line(digest, state) or ""))
            os.makedirs(state)
            with open(os.path.join(state, "launch-prompt.md"), "wb") as fh:
                fh.write(body)
            check("a digest that matches: no drift", status.prompt_drift_line(digest, state) is None)
            check("a digest that differs: rewritten", "was rewritten since launch" in (status.prompt_drift_line("sha256:0", state) or ""))

            print("placement")
            ctx = {"agent": LOGIN, "host": HOST}
            reg = os.path.join(tmp, "reg.json")
            env = {"AGENT_FABRIC_HOSTS_REGISTRY": reg}
            put(reg, json.dumps({"placement": {LOGIN: HOST}}))
            check("placed here: the placement and no drift", status.placement_of(ctx, HERE, env) == (HOST, None))
            put(reg, json.dumps({"placement": {LOGIN: "elsewhere"}}))
            p, d = status.placement_of(ctx, HERE, env)
            check("placed elsewhere: both hosts named", p == "elsewhere" and f"registered on elsewhere, running on {HOST}" in d)
            put(reg, json.dumps({"placement": {}}))
            check("not placed: said", status.placement_of(ctx, HERE, env)[1].startswith("not placed in runtime/hosts/registry.json"))
            put(reg, "{x")
            check("an invalid registry says nothing", status.placement_of(ctx, HERE, env) == (None, None))
            check("a missing registry says nothing", status.placement_of(ctx, HERE, {"AGENT_FABRIC_HOSTS_REGISTRY": reg + ".none"}) == (None, None))

            print("the job summary")

            class Fake:
                def __init__(self, doc=None, exc=None):
                    self.doc, self.exc = doc, exc

                def read_jobs(self, agent):
                    if self.exc:
                        raise self.exc
                    return self.doc

            jobs = [{"id": "j1", "state": "queued"}, {"id": "j2", "state": "active", "title": "x" * 80, "working_copy": "/w"},
                    {"id": "j3", "state": "blocked"}, {"id": "j4", "state": "delivered"}, {"id": "j5", "state": "done"}, "junk"]
            s = status.jobs_summary(Fake({"jobs": jobs}), "a")
            check("counts by state, done and junk left out", (s["queued"], s["blocked"], s["delivered"]) == (1, 1, 1))
            check("the active job, its working copy, its title whole", s["active"] == {"id": "j2", "title": "x" * 80, "working_copy": "/w"})
            check("none active", status.jobs_summary(Fake({"jobs": []}), "a")["active"] is None)
            check("a refusal (SystemExit) is said, not raised", status.jobs_summary(Fake(exc=SystemExit("identity: bad")), "a") == {"error": "identity: bad"})
            check("an OSError is said by its strerror", status.jobs_summary(Fake(exc=OSError(13, "Permission denied")), "a") == {"error": "Permission denied"})

            print("the human report")
            report = {
                "agent": "a", "host": "h", "placement": None, "role": None, "project": None, "working_copy": None, "session": None,
                "binding_updated": None, "launched_role": None, "launch_prompt_digest": None, "drift": None,
                "session_effort": None, "undrained_memories": None, "jobs": {"active": None, "queued": 0, "blocked": 0, "delivered": 0},
                "api": {"provider": "anthropic", "path": "vanilla claude", "base_url_host": None, "session_model": "m", "launch_profile": None,
                        "pins": "none (harness defaults)", "credentials": "none visible in the environment", "claude_sign_in": "own /login (none recorded)"},
                "capabilities": {"code-low": "haiku"}, "routing_check": "clean", "host_tools": {"moveto": {"installed": False}}, "control_plane": "/r",
            }
            lines = status.render(report, "")
            check("the minimal report, line for line", lines == [
                "agent        a@h", "role         (none — bin/fabric-role bind <role>, from a login shell)",
                "project      (none)    working copy  (none)", "session      (unknown)    binding updated -",
                "jobs         none active; 0 queued, 0 blocked, 0 delivered  (fabric-jobs list)", "", "api          vanilla claude", "session model m",
                "pins         none (harness defaults)", "credentials  none visible in the environment", "claude sign-in own /login (none recorded)", "",
                "capabilities on anthropic (bin/fabric-model list for every choice, per provider, with its source):",
                "  code-low     haiku", "routing      clean", "control plane /r"])
            report.update(launched_role="r", drift=["d1", "d2"], undrained_memories={"drainable": 1, "no_roles_class": 2, "since": "the last drain", "dir": "/m"},
                          session_effort={"asked": "high", "reported": "high", "launched": None}, routing_check=["f1", "f2"])
            report["host_tools"] = {"moveto": {"installed": True, "status": "drift", "detail": "behind"}}
            report["api"].update(launch_profile="p", pins={"A": "1", "B": "2"}, credentials={"K": "set"})
            text = "\n".join(status.render(report, "https://x"))
            check("launched as, with the no-digest placeholder", "launched as  r    prompt (no digest stamped)" in text)
            check("one DRIFT line per drift, after launched-as", text.index("launched as") < text.index("DRIFT        d1\nDRIFT        d2") < text.index("project "))
            check("unpinned effort: asked, with the running level confirmed", "session effort high (asked; not pinned at launch) (confirmed)" in text)
            check("launch profile, pins and credentials", "launch profile p\npins         A=1, B=2\ncredentials  K: set" in text)
            check("a base URL says the sign-in is plain claude's", "claude sign-in own /login (none recorded)  (plain claude's; this session goes to vanilla claude and uses neither)" in text)
            check("findings are counted and joined", "routing      2 finding(s): f1; f2" in text)
            check("memory line", "memory       1 drainable (roles_class set) and 2 private (none) written since the last drain — /m" in text)
            check("moveto drift carries its detail", "moveto       drift: behind" in text)
            report["jobs"] = {"error": "boom"}
            check("an unreadable job list is said", "jobs         unreadable: boom" in "\n".join(status.render(report, "")))
            report["jobs"] = {"active": {"id": "j9", "title": "t" * 70, "working_copy": None}, "queued": 1, "blocked": 2, "delivered": 3}
            check("the active title is cut at 60", f"active j9 ({'t' * 60}); 1 queued, 2 blocked, 3 delivered" in "\n".join(status.render(report, "")))
        finally:
            os.environ.clear()
            os.environ.update(saved)

        print("the shim and the contract")
        text = open(SHIM, encoding="utf-8").read()
        check("the shim runs the pinned Python and nothing else", 'exec "$py"' in text
              and 'py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"' in text
              and not any(w in text.split("exec", 1)[1] for w in ("readlink", "$(", "`", "\ncd ")))
        check("the shim has no logic of its own to drift from the module", len(text.splitlines()) < 30)
        with open(os.path.join(HERE, "policies", "bash-allowlist.json"), encoding="utf-8") as fh:
            check("bin/fabric-status is off the bash allowlist", "bin/fabric-status" not in json.load(fh)["scripts"])
        doc = status.__doc__
        check("the header freezes argv, env, stdout, exit and the json shape", all(w in doc for w in ("argv", "env", "stdout", "exit", "--json object")))

        sb = os.path.join(tmp, "sb")
        agent_dir = os.path.join(sb, "state", "agents", LOGIN)
        os.makedirs(agent_dir)
        with open(os.path.join(agent_dir, "binding.json"), "w", encoding="utf-8") as fh:
            json.dump({"agent": LOGIN, "host": HOST, "role": "db-admin", "updated_at": "x"}, fh)
        reg = os.path.join(sb, "reg.json")
        with open(reg, "w", encoding="utf-8") as fh:
            json.dump({"placement": {LOGIN: HOST}}, fh)
        env = clean_env(HOME=os.path.join(sb, "home"), AGENT_FABRIC_STATE_DIR=os.path.join(sb, "state"), AGENT_FABRIC_HOSTS_REGISTRY=reg)

        def run(path, *args, **kw):
            return subprocess.run(["bash", path, *args], env=env, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL, cwd=sb, **kw)

        a, b, c = run(SHIM), run(SHIM, "--json"), run(SHIM, "--help")
        check("exit 0 and nothing on stderr", (a.returncode, a.stderr) == (0, "") and (b.returncode, b.stderr) == (0, ""))
        check("an unknown argument is ignored: the same report", c.stdout == a.stdout and c.returncode == 0)
        check("only the FIRST argument selects --json, as the bash's ${1:-}", run(SHIM, "x", "--json").stdout == a.stdout
              and run(SHIM, "--json", "x").stdout == b.stdout)
        secret = "sk-secret-value-123"
        leaky = subprocess.run(["bash", SHIM], env={**env, "ANTHROPIC_AUTH_TOKEN": secret, "OPENROUTER_API_KEY": secret}, capture_output=True,
                               text=True, timeout=120, stdin=subprocess.DEVNULL, cwd=sb)
        leaky_json = subprocess.run(["bash", SHIM, "--json"], env={**env, "ANTHROPIC_AUTH_TOKEN": secret}, capture_output=True,
                                    text=True, timeout=120, stdin=subprocess.DEVNULL, cwd=sb)
        check("a credential variable is reported set, never echoed, in both forms",
              "ANTHROPIC_AUTH_TOKEN: set" in leaky.stdout and secret not in leaky.stdout + leaky.stderr
              and json.loads(leaky_json.stdout)["api"]["credentials"]["ANTHROPIC_AUTH_TOKEN"] == "set" and secret not in leaky_json.stdout)
        # The pinned Python, present and absent (python_pin.py's own check).
        with open(os.path.join(HERE, "runtime", "python.json"), encoding="utf-8") as fh:
            pin = json.load(fh)
        built = os.path.join(sb, "py", f"python-{pin['python']}+{pin['release']}", "bin")
        os.makedirs(built)
        with open(os.path.join(built, "python3"), "w") as fh:
            fh.write(f"#!/bin/sh\necho {pin['python']}\n")
        os.chmod(os.path.join(built, "python3"), 0o755)
        os.symlink(os.path.join(built, "python3"), os.path.join(sb, "fabric-python"))
        here_env = {**env, "AGENT_FABRIC_PYTHON_PREFIX": os.path.join(sb, "py"), "AGENT_FABRIC_PYTHON_LINK": os.path.join(sb, "fabric-python")}
        present = subprocess.run(["bash", SHIM, "--json"], env=here_env, capture_output=True, text=True, timeout=120,
                                 stdin=subprocess.DEVNULL, cwd=sb)
        absent = subprocess.run(["bash", SHIM], env={**here_env, "AGENT_FABRIC_PYTHON_LINK": os.path.join(sb, "nope")},
                                capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL, cwd=sb)
        check("the pinned Python is reported: as pinned when the link reaches it, MISSING with the install command when not",
              json.loads(present.stdout)["host_tools"]["python"]["status"] == "ok"
              and "python       MISSING: " in absent.stdout and "python_pin.py install" in absent.stdout)
        # The episodic journal (ADR-041): none yet, then counted, and
        # another agent's named as such.
        store = os.path.join(sb, "store"); os.makedirs(store)
        with open(os.path.join(store, ".agent-id"), "w") as fh:
            fh.write("01a0f782-7e06-7dee-811f-0a860ed93bf3\n")
        # Its own state: the reports compared below must not see this journal.
        jenv = {**env, "AGENT_FABRIC_SECRET_STORE": store, "AGENT_FABRIC_STATE_DIR": os.path.join(sb, "journal-state")}
        def journal_state(e):
            return json.loads(subprocess.run(["bash", SHIM, "--json"], env=e, capture_output=True, text=True, timeout=120,
                                             stdin=subprocess.DEVNULL, cwd=sb).stdout)["host_tools"]["journal"]
        before = journal_state(jenv)
        subprocess.run([sys.executable, os.path.join(HERE, "tools", "fabric", "episodic.py"), "gzcoord-in"], env=jenv,
                       input=json.dumps({"content": "[GZCOORD/1] INFO\nFROM: h/x\nMESSAGE-ID: j-1\n\nINFO:\nx\n", "seq": 1}) + "\n",
                       capture_output=True, text=True, timeout=60, check=True)
        after = journal_state(jenv)
        with open(os.path.join(store, ".agent-id"), "w") as fh:
            fh.write("01a0f7ea-15b0-7ed9-a176-6eb006592db1\n")
        foreign = journal_state(jenv)
        check("the journal is reported: none yet, then counted, and another agent's named",
              before["status"] == "none" and after["status"] == "ok" and after["detail"].startswith("1 episode(s)")
              and foreign["status"] == "foreign")
        drifted = subprocess.run(["bash", SHIM], env={**env, "AGENT_FABRIC_LAUNCH_ROLE": "backend-dev", "AGENT_FABRIC_LAUNCH_PROMPT_DIGEST": "sha256:0",
                                      "AGENT_FABRIC_LAUNCH_PROVIDER": "anthropic", "AGENT_FABRIC_LAUNCH_SESSION_MODEL": "claude-sonnet-5"},
                                 capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL, cwd=sb).stdout
        check("DRIFT lines come in the contract's order: role, model, prompt",
              0 < drifted.index("DRIFT        launched as backend-dev") < drifted.index("DRIFT        launched on claude-sonnet-5")
              < drifted.index("DRIFT        the launched prompt file is gone"))
        saved_env = dict(os.environ)
        os.environ.clear()
        os.environ.update(env)
        try:
            import contextlib
            import io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = status.main([])
            check("main() exports AGENT_FABRIC_ROOT for the modules it loads, when unset",
                  rc == 0 and os.environ.get("AGENT_FABRIC_ROOT") == status.ROOT and buf.getvalue().startswith("agent        "))
        finally:
            os.environ.clear()
            os.environ.update(saved_env)
        obj = json.loads(b.stdout)
        check("--json is one object with the frozen keys", list(obj) == [
            "agent", "host", "placement", "role", "project", "working_copy", "session", "binding_updated", "launched_role",
            "launch_prompt_digest", "drift", "session_effort", "undrained_memories", "jobs", "api", "capabilities", "routing_check",
            "host_tools", "control_plane"])
        check("…whose api keys are frozen too", list(obj["api"]) == [
            "provider", "path", "base_url_host", "session_model", "launch_profile", "pins", "credentials", "claude_sign_in"])
        check("the control plane is the repository the shim is in", obj["control_plane"] == HERE)
        link = os.path.join(sb, "linked", "fabric-status")
        os.makedirs(os.path.dirname(link))
        os.symlink(SHIM, link)
        d = run(link)
        check("reached through a symlink (the ~/.local/bin link) it finds its module", d.returncode == 0 and d.stdout == a.stdout)
        os.remove(os.path.join(agent_dir, "binding.json"))
        e = run(SHIM)
        check("no binding is still a report, not a crash", e.returncode == 0 and "role         (none" in e.stdout)
        with open(os.path.join(agent_dir, "binding.json"), "w", encoding="utf-8") as fh:
            fh.write("{nope")
        f = run(SHIM)
        check("an unreadable binding fails loudly, not as a silent clean report", f.returncode != 0 and f.stdout == "" and f.stderr.strip() != "")

    print("ok" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
