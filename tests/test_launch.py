#!/usr/bin/env python3
"""Tests for tools/fabric/launch.py's internals; the behaviour is
tests/test_launch_cli.py's, run against the
runtime/openrouter/launch shim (ADR-040 §5 rule 5). What is here is what
that suite cannot reach: the paths that only crash or hang, the signal
handling around the session, the relaunch's environment, and the shim's
own refusal. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import io
import json
import os
import pwd
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import launch  # noqa: E402

SHIM = os.path.join(HERE, "runtime", "openrouter", "launch")
MODULE = os.path.join(HERE, "tools", "fabric", "launch.py")


def clean_env(**extra) -> dict:
    """What a fabric process sees in CI: nothing of this session's launch."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "ANTHROPIC_", "CLAUDE_", "OPENROUTER_"))}
    env.update(extra)
    return env


def fake_routing(**over) -> types.SimpleNamespace:
    """The routing calls launch.resolve makes, answering for one class."""
    res = {"via": "export", "composite": "vendor/m@preset/s", "model": "vendor/m", "shim": "preset/s",
           "source": "defaults", "effort": ("high", "high")}
    r = types.SimpleNamespace(
        normalize_layer=lambda layer, name: None,
        resolve=lambda klass, provider, role, agent, local: dict(res),
        ADAPTERS={"openrouter": types.SimpleNamespace(is_runtime=lambda c: True)},
        exports=lambda provider, role, agent, local: {"ANTHROPIC_DEFAULT_OPUS_MODEL": {"model": "vendor/m@preset/s"}},
        resolve_session=lambda role, agent, local, provider: {"composite": "vendor/s", "source": "defaults"},
        load_review_grade=lambda: {"capability": "code-review"},
        review_grade_ok=lambda model: True,
        effort_phrase=lambda e: "effort high")
    for k, v in over.items():
        setattr(r, k, v)
    return r


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        def put(path: str, text: str, mode: int = 0o644) -> str:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(path, mode)
            return path

        print("argv")
        check("--print anywhere; --provider spaced and =; the rest in order",
              launch.parse_argv(["-p", "x", "--print", "--provider", "anthropic", "--verbose"])
              == (True, "anthropic", ["-p", "x", "--verbose"]))
        check("--provider= form", launch.parse_argv(["--provider=anthropic"]) == (False, "anthropic", []))
        check("--print as --provider's value is --print, not a provider",
              launch.parse_argv(["--provider", "--print"]) == (True, "openrouter", []))
        check("a caller's --model, spaced, = and trailing",
              launch.caller_value(["--model", "a"], "--model") == ("a", True, False)
              and launch.caller_value(["--model=b"], "--model") == ("b", True, False)
              and launch.caller_value(["-p", "--model"], "--model") == (None, True, True)
              and launch.caller_value(["-p"], "--model") == (None, False, False))

        print("the session's effort")
        check("the routed level, unless the caller passed one",
              launch.effort_for([], "high") == ("high", False)
              and launch.effort_for(["--effort", "low"], "high") == ("low", True)
              and launch.effort_for(["--effort=max"], "high") == ("max", True))
        check("a trailing bare --effort is the caller's: no level added, none stamped",
              launch.effort_for(["--version", "--effort"], "high") == ("", True)
              and launch.effort_for(["--effort", "low", "--effort"], "high") == ("", True))

        print("the session's command line")
        args = ["--effort", "low", "--model", "m"]
        cmd = launch.session_command("anthropic", "claude-x", True, "low", True, "--append-system-prompt-file", "p", args)
        check("the caller's --model and --effort reach claude once each, the launcher adding neither",
              cmd.count("--effort") == 1 and cmd.count("--model") == 1 and cmd[:3] == ["claude", "--append-system-prompt-file", "p"])
        cmd = launch.session_command("openrouter", "s@p", False, "high", False, "--append-system-prompt-file", "p", [])
        check("…and the launcher's own when the caller passed none, through ori on the broker",
              cmd == ["ori", "claude", "--model", "s@p", "--effort", "high", "--append-system-prompt-file", "p"])

        print("the files a launch needs")
        present = put(f"{tmp}/routing/capabilities.json", "{}")
        try:
            launch.require_files(present, f"{tmp}/routing/aliases.json")
            check("a missing routing file is refused", False)
        except launch.Refused as exc:
            check("a missing routing file is refused, by its path", str(exc) == f"{tmp}/routing/aliases.json is missing.")

        # End to end through the shim: the call in launch() is what refuses,
        # not only the helper. A fixture fabric with an identity and a
        # binding, and no routing/capabilities.json.
        fixture, state = f"{tmp}/fixture", f"{tmp}/fixture-state"
        os.makedirs(f"{fixture}/runtime")
        os.makedirs(f"{fixture}/tools/fabric")
        os.makedirs(f"{fixture}/projects")
        for rel in ("runtime/identity.py", "tools/fabric/workingcopy.py", "projects/registry.json"):
            with open(os.path.join(HERE, rel), encoding="utf-8") as src:
                put(f"{fixture}/{rel}", src.read())
        login = pwd.getpwuid(os.getuid()).pw_name
        put(f"{state}/agents/{login}/binding.json", json.dumps({"agent": login, "role": "backend-dev"}))
        put(f"{tmp}/bin/ori", "#!/usr/bin/env bash\nexit 0\n", 0o755)
        os.makedirs(f"{tmp}/nowhere")
        r = subprocess.run(["bash", SHIM, "--print"], cwd=f"{tmp}/nowhere", capture_output=True, text=True, timeout=60,
                           env=clean_env(AGENT_FABRIC_ROOT=fixture, AGENT_FABRIC_STATE_DIR=state, HOME=f"{tmp}/home",
                                         PATH=f"{tmp}/bin:{os.environ['PATH']}", PWD=f"{tmp}/nowhere",
                                         AGENT_FABRIC_PYTHON=sys.executable))
        check("a launch with no capabilities.json is refused before anything else, by its path",
              r.returncode == 1 and r.stderr == f"launch: {fixture}/routing/capabilities.json is missing.\n")

        print("settings scopes")
        repo, other = f"{tmp}/repo", f"{tmp}/other"
        for d in (repo, other):
            os.makedirs(d)
            subprocess.run(["git", "init", "-q", d], check=True, timeout=30)
        os.makedirs(f"{repo}/sub")
        saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(clean_env(REPO_ROOT=other))
        try:
            scopes = launch.settings_scopes(f"{tmp}/home", f"{repo}/sub")
        finally:
            os.environ.clear()
            os.environ.update(saved)
        check("launched from a subdirectory: the repository's scopes and the directory's, never an inherited "
              "REPO_ROOT's",
              f"{repo}/.claude/settings.local.json" in scopes and f"{repo}/sub/.claude/settings.json" in scopes
              and not any(p.startswith(other) for p in scopes))
        check("pins are named", launch.settings_pins(put(f"{tmp}/s1.json", json.dumps(
            {"env": {"ANTHROPIC_MODEL": "x", "OTHER": "y"}, "modelOverrides": {}, "maxEffortLevel": "low"})))
            == ["env.ANTHROPIC_MODEL", "modelOverrides", "maxEffortLevel"])
        check("null and [] are empty, as `or {}` had them",
              launch.settings_pins(put(f"{tmp}/s2.json", "null")) == []
              and launch.settings_pins(put(f"{tmp}/s3.json", "[]")) == [])
        check("an unreadable or non-JSON file is not evidence of pins",
              launch.settings_pins(put(f"{tmp}/s4.json", "{not json")) == []
              and launch.settings_pins(f"{tmp}/absent.json") == [])
        check("JSON that is not an object is told apart (None)",
              launch.settings_pins(put(f"{tmp}/s5.json", "[1]")) is None
              and launch.settings_pins(put(f"{tmp}/s6.json", '"text"')) is None)
        err = io.StringIO()
        saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(clean_env())
        try:
            with redirect_stderr(err):
                launch.refuse_pins([f"{tmp}/s5.json"], "local")
            refused = False
        except launch.Refused:
            refused = True
        finally:
            os.environ.clear()
            os.environ.update(saved)
        check("…and is said in one line, never a traceback, and does not refuse the launch (it never did)",
              not refused and err.getvalue().count("\n") == 1 and "not a JSON object" in err.getvalue()
              and "Traceback" not in err.getvalue())

        print("resolve")
        local = put(f"{tmp}/local.json", "{}")
        aliases = put(f"{tmp}/aliases.json", json.dumps({"aliases": {"code-high": "opus"}, "env": {}}))
        got = launch.resolve(fake_routing(), aliases, local, "r", "a", "openrouter")
        check("the resolution reaches the report through JSON: a tuple is a list",
              got["classes"]["code-high"]["effort"] == ["high", "high"])
        refusing = fake_routing(ADAPTERS={"openrouter": types.SimpleNamespace(is_runtime=lambda c: False)})
        try:
            launch.resolve(refusing, aliases, local, "r", "a", "openrouter")
            check("a pinned model the adapter does not accept is refused", False)
        except launch.ResolveError as exc:
            check("a pinned model the adapter does not accept is refused, by class",
                  "resolved code-high is 'vendor/m@preset/s', not a model reference the openrouter adapter accepts"
                  == str(exc))
        put(local, "[]")
        try:
            launch.resolve(fake_routing(), aliases, local, "r", "a", "openrouter")
            check("a local override that is not an object is refused", False)
        except launch.ResolveError as exc:
            check("a local override that is not an object is refused, by its type",
                  str(exc) == "model-profile.local.json is list, not an object")

        print("--print")
        prompt = put(f"{tmp}/prompt.md", "first line\nsecond\n")
        out, err = io.StringIO(), io.StringIO()
        boom = fake_routing(effort_phrase=lambda e: 1 / 0)
        code = None
        try:
            with redirect_stdout(out), redirect_stderr(err):
                launch.print_report(json.loads(json.dumps(got)), boom, label="r/a", agent="a", role="r",
                                    provider="openrouter", session="vendor/s", effective_session="vendor/s",
                                    session_effort="high", caller_effort=False, prompt_file=prompt,
                                    prompt_flag="--append-system-prompt-file")
        except SystemExit as exc:
            code = exc.code
        check("a class block that crashes fails --print (exit 1) with its traceback, never a quiet 0",
              code == 1 and "ZeroDivisionError" in err.getvalue())

        out = io.StringIO()
        skipping = json.loads(json.dumps(got))
        skipping["session"] = {"composite": "claude-x", "source": "agents", "skipped": "z-ai/glm-5.3"}
        with redirect_stdout(out):
            launch.print_report(skipping, fake_routing(), label="r/a", agent="a", role="r", provider="anthropic",
                                session="claude-x", effective_session="claude-x", session_effort="",
                                caller_effort=False, prompt_file=prompt, prompt_flag="--append-system-prompt-file")
        check("a session the merge skipped is said, with the layer used instead",
              "  (the merged session z-ai/glm-5.3 is not an Anthropic model; the agents layer's is used on plain "
              "claude)\n" in out.getvalue())

        print("TMPDIR")
        old_umask = os.umask(0o022)
        try:
            launch.make_tmpdir(f"{tmp}/var/agent-fabric-x")
            made = os.stat(f"{tmp}/var/agent-fabric-x").st_mode & 0o777
            os.chmod(f"{tmp}/var/agent-fabric-x", 0o755)
            launch.make_tmpdir(f"{tmp}/var/agent-fabric-x")
            kept = os.stat(f"{tmp}/var/agent-fabric-x").st_mode & 0o777
        finally:
            os.umask(old_umask)
        check("a new per-login TMPDIR is 700 whatever the umask; one that exists is left as it is",
              made == 0o700 and kept == 0o755)
        os.symlink(f"{tmp}/var/agent-fabric-x", f"{tmp}/var/agent-fabric-link")
        try:
            launch.make_tmpdir(f"{tmp}/var/agent-fabric-link")
            linked = None
        except launch.Refused as exc:
            linked = str(exc)
        check("a symlink where the per-login TMPDIR goes is refused, naming it",
              linked is not None and "agent-fabric-link" in linked, linked)
        with open(f"{tmp}/var/agent-fabric-file", "w") as f:
            f.write("not a directory\n")
        try:
            launch.make_tmpdir(f"{tmp}/var/agent-fabric-file")
            plain = None
        except launch.Refused as exc:
            plain = str(exc)
        check("…and so is a regular file of this account's own",
              plain is not None and "agent-fabric-file" in plain and "not a directory" in plain, plain)
        real_euid = os.geteuid
        os.geteuid = lambda: real_euid() + 1
        try:
            try:
                launch.make_tmpdir(f"{tmp}/var/agent-fabric-x")
                foreign = None
            except launch.Refused as exc:
                foreign = str(exc)
            launch.make_tmpdir(f"{tmp}/var/agent-fabric-x", ours=False)
            set_by_account = True
        except launch.Refused:
            set_by_account = False
        finally:
            os.geteuid = real_euid
        check("a per-login TMPDIR another account owns is refused, naming its owner",
              foreign is not None and f"uid {os.geteuid()}" in foreign, foreign)
        check("…but a TMPDIR the account set itself is taken whoever owns it (/tmp is root's)", set_by_account)

        print("the agent files")
        fab = f"{tmp}/fab"
        put(f"{fab}/runtime/claude-code/install-agent-files.sh", "exit 3\n")
        rec_state = f"{tmp}/state-rec"
        try:
            launch.install_agent_files(fab, "anthropic", rec_state)
            check("an installer that fails stops the launch", False)
        except launch.Refused as exc:
            check("an installer that fails stops the launch, naming the provider",
                  "could not install the capability-class agent files for anthropic" in str(exc))
        put(f"{fab}/runtime/claude-code/install-agent-files.sh", "exit 0\n")
        try:
            launch.install_agent_files(fab, "anthropic")
            check("…and one that succeeds does not", True)
        except launch.Refused:
            check("…and one that succeeds does not", False)
        check("…a failed install records no provider", not os.path.exists(f"{rec_state}/launch-provider.json"))
        launch.install_agent_files(fab, "openrouter", rec_state)
        recorded = json.load(open(f"{rec_state}/launch-provider.json"))
        check("a successful install records its provider for the next run with none (install_agent_files.py)",
              recorded.get("provider") == "openrouter" and recorded.get("at", "").endswith("Z")
              and not [n for n in os.listdir(rec_state) if ".tmp-" in n], (recorded, os.listdir(rec_state)))

        check("a help read asks for help; a prompt after -- that says --help does not",
              launch.asks_help(["--help"]) and launch.asks_help(["--model", "x", "-h"])
              and not launch.asks_help(["--", "--help"]) and not launch.asks_help(["--version"]))

        print("the session is a child")
        # The launcher ignores Ctrl-C while the session runs, forwards
        # SIGTERM to it, and returns the session's status.
        child = ("trap 'echo got-term; exit 7' TERM; echo ready; while :; do sleep 0.1; done")
        p = subprocess.Popen([sys.executable, "-c",
                              f"import sys; sys.path.insert(0, {os.path.dirname(MODULE)!r}); import launch; "
                              f"sys.exit(launch.run_session(['bash', '-c', {child!r}]))"],
                             stdout=subprocess.PIPE, text=True, start_new_session=True)
        ready = p.stdout.readline().strip()
        p.send_signal(signal.SIGINT)
        time.sleep(0.3)
        alive_after_int = p.poll() is None
        p.send_signal(signal.SIGTERM)
        rest, _ = p.communicate(timeout=10)
        check("SIGINT to the launcher leaves it and the session running", ready == "ready" and alive_after_int)
        check("SIGTERM is forwarded and the session's status is the launcher's",
              "got-term" in rest and p.returncode == 7)
        check("a session ended by a signal is 128+n",
              launch.run_session(["bash", "-c", "kill -TERM $$"]) == 143)
        with redirect_stderr(io.StringIO()) as err:
            status = launch.run_session([f"{tmp}/no-such-command"])
        check("a session that cannot start is 127 and one line, not a traceback",
              status == 127 and err.getvalue().count("\n") == 1)

        print("the relaunch")
        calls = []
        launch_reexec = launch.reexec
        launch.reexec = lambda env, args: calls.append((env, args)) or (_ for _ in ()).throw(SystemExit(0))
        state = f"{tmp}/state"
        put(f"{state}/binding.json", json.dumps({"session": "sess-9"}))
        when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 5))
        put(f"{state}/restart.json", json.dumps({"requested_at": when, "status": "done", "piece": "claude",
                                                 "from": "1", "to": "2"}))
        saved = dict(os.environ)
        os.environ["AGENT_FABRIC_PULLED"] = "1"
        try:
            with redirect_stderr(io.StringIO()):
                launch.restart(state, int(time.time()), True, 143, ["--resume", "old", "-p", "x"], tmp, tmp)
        except SystemExit:
            pass
        finally:
            os.environ.clear()
            os.environ.update(saved)
            launch.reexec = launch_reexec
        check("a relaunch drops AGENT_FABRIC_PULLED (the next launch may pull again) and resumes the stopped session",
              len(calls) == 1 and "AGENT_FABRIC_PULLED" not in calls[0][0]
              and calls[0][1] == ["-p", "x", "--resume", "sess-9"])
        check("…and the marker is consumed", not os.path.exists(f"{state}/restart.json"))
        check("the caller's resume flags are replaced, a bare -r keeps the option after it",
              launch.without_resume(["-c", "--resume=a", "-r", "--model", "m", "--continue", "x"])
              == ["--model", "m", "x"])
        check("only path options' values are made absolute; JSON and absolute paths are left",
              launch.absolute_path_options(["--add-dir", "d", "--settings", "{}", "--mcp-config=/m", "--model", "f",
                                            "--settings=s"], "/w")
              == ["--add-dir", "/w/d", "--settings", "{}", "--mcp-config=/m", "--model", "f", "--settings=/w/s"])

        print("an upgrade the launcher waits for")
        marker = put(f"{tmp}/up/restart.json", json.dumps({"requested_at": when, "status": "pending",
                                                           "piece": "claude", "from": "1", "to": "2"}))
        binding = put(f"{tmp}/up/binding.json", json.dumps({"session": "sess-7"}))

        def finish_later() -> None:
            time.sleep(1.5)
            put(marker, json.dumps({"requested_at": when, "status": "done", "piece": "claude", "from": "1",
                                    "to": "2", "installed": "2"}))
        t = threading.Thread(target=finish_later)
        t.start()
        err = io.StringIO()
        with redirect_stderr(err):
            resumed = launch.read_restart(marker, int(time.time()), binding, "30")
        t.join()
        check("a pending upgrade is waited for, and the session resumed once it is done",
              resumed == "sess-7" and "waiting for it" in err.getvalue()
              and "claude upgraded 1 → 2; resuming the session on it." in err.getvalue())
        put(marker, json.dumps({"requested_at": when, "status": "pending", "piece": "claude", "to": "2"}))
        r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {os.path.dirname(MODULE)!r}); "
                            f"import launch; print(launch.read_restart({marker!r}, 0, {binding!r}, '1'))"],
                           capture_output=True, text=True, timeout=20)
        check("…and one that never finishes is waited for no longer than AGENT_FABRIC_RESTART_WAIT_S",
              r.stdout.strip() == "sess-7" and "did not finish within 1 s" in r.stderr)

        print("the restart wait (review of #79)")
        put(f"{state}/binding.json", json.dumps({"session": "sess-9"}))

        def restart_with(wait):
            put(f"{state}/restart.json", json.dumps({"requested_at": when, "status": "done", "piece": "claude",
                                                     "from": "1", "to": "2"}))
            calls.clear()
            launch.reexec = lambda env, args: calls.append((env, args)) or (_ for _ in ()).throw(SystemExit(0))
            saved = dict(os.environ)
            os.environ["AGENT_FABRIC_RESTART_WAIT_S"] = wait
            err = io.StringIO()
            try:
                with redirect_stderr(err):
                    launch.restart(state, int(time.time()), True, 143, [], tmp, tmp)
            except SystemExit:
                pass
            finally:
                os.environ.clear()
                os.environ.update(saved)
                launch.reexec = launch_reexec
            return err.getvalue()
        restart_with("")
        check("an EMPTY AGENT_FABRIC_RESTART_WAIT_S is the default, as the bash's :-600 had it: the session resumes",
              len(calls) == 1 and calls[0][1] == ["--resume", "sess-9"], str(calls))
        said = restart_with("ten")
        check("a malformed one is said in one launch: line naming it, and the resume is given up",
              calls == [] and said.count("\n") == 1 and said.startswith("launch: AGENT_FABRIC_RESTART_WAIT_S is 'ten'"),
              said)

        print("a pull the bound ends (review of #79)")
        GitError = launch.git.GitError

        def fake_git_run(repo, *args, check=True, timeout=120, **kw):
            if args[:1] == ("pull",):
                raise GitError("git pull", f"no answer within {timeout:g} s")
            out = "1\n" if args[:1] == ("rev-list",) else ""
            return types.SimpleNamespace(returncode=0, stdout=out, stderr="")
        saved_run, launch.git.run = launch.git.run, fake_git_run
        saved_env = dict(os.environ)
        os.environ.pop("AGENT_FABRIC_ALLOW_STALE", None)
        os.environ.pop("AGENT_FABRIC_PULLED", None)
        try:
            with redirect_stderr(io.StringIO()):
                launch.keep_fabric_current(tmp, [])
            check("a timed-out pull is refused", False)
        except launch.Refused as exc:
            check("a timed-out pull is said as a timeout, with the lock it may leave, never as 'cannot fast-forward'",
                  "did not answer within 120 s" in str(exc) and "index.lock" in str(exc)
                  and "cannot fast-forward" not in str(exc), str(exc))
        finally:
            launch.git.run = saved_run
            os.environ.clear()
            os.environ.update(saved_env)
        check("the departures list names both new bounds", "git.py's 120 s" in launch.__doc__
              and "HELPER_TIMEOUT_S" in launch.__doc__)

        print("the session's signals and descriptors (review of #79)")
        # The session here is a Python child reading its own mask and
        # descriptor table: bash cannot be the probe, since `bash -c` on
        # these hosts ignores SIGQUIT itself, whatever it inherited. SIGQUIT
        # starts at its default, as in a terminal; whatever runs this suite
        # may ignore it already.
        child = ("import os; m = [l for l in open('/proc/self/status') if l.startswith('SigIgn')][0].split()[1]; "
                 "open(%r, 'w').write(m); open(%r, 'w').write('leaked' if os.path.exists('/proc/self/fd/%%d' %% "
                 "int(os.environ['W'])) else 'clean')") % (f"{tmp}/sig", f"{tmp}/fds")
        probe = ("import os, signal, sys; signal.signal(signal.SIGQUIT, signal.SIG_DFL); "
                 "sys.path.insert(0, %r); import launch; "
                 "r, w = os.pipe(); os.set_inheritable(w, True); os.environ['W'] = str(w); "
                 "sys.exit(launch.run_session([sys.executable, '-c', %r]))") % (os.path.dirname(launch.__file__), child)
        subprocess.run([sys.executable, "-c", probe], timeout=60)
        ignored = int(open(f"{tmp}/sig").read().strip(), 16)
        check("the session ignores SIGINT and SIGQUIT, as bash's `&` job did",
              bool(ignored & (1 << 1)) and bool(ignored & (1 << 2)), hex(ignored))
        check("…and a descriptor the launcher holds does not reach it (close_fds)",
              open(f"{tmp}/fds").read().strip() == "clean")

        print("the opening")
        saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(clean_env())
        try:
            check("a bare launch opens; a caller's prompt, -p, --version or -- does not",
                  launch.wants_opening([]) and launch.wants_opening(["--resume", "abc"])
                  and launch.wants_opening(["--resume"]) and not launch.wants_opening(["do it"])
                  and not launch.wants_opening(["-p"]) and not launch.wants_opening(["--"]))
        finally:
            os.environ.clear()
            os.environ.update(saved)

        print("ori's auth")
        check("authenticated AND from the environment, nothing less",
              launch.ori_auth_ok('{"ok":true,"data":{"authenticated":true,"source":{"kind":"environment"}}}')
              and not launch.ori_auth_ok('{"data":{"authenticated":true,"source":{"kind":"workspace"}}}')
              and not launch.ori_auth_ok('{"data":{"authenticated":false,"source":{"kind":"environment"}}}')
              and not launch.ori_auth_ok("not json") and not launch.ori_auth_ok("[]"))

        print("the launch directory")
        real = os.path.join(tmp, "real")
        os.makedirs(real)
        link = os.path.join(tmp, "link")
        os.symlink(real, link)
        r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {os.path.dirname(MODULE)!r}); "
                            "import launch; print(launch.logical_cwd())"], cwd=link,
                           env=clean_env(PWD=link), capture_output=True, text=True, timeout=30)
        check("$PWD as bash has it: the symlinked path the launch was given", r.stdout.strip() == link)
        r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {os.path.dirname(MODULE)!r}); "
                            "import launch; print(launch.logical_cwd())"], cwd=real,
                           env=clean_env(PWD="/"), capture_output=True, text=True, timeout=30)
        check("…and the real directory when PWD names another", r.stdout.strip() == real)

        print("a closed stdout")
        code = ("import sys; sys.path.insert(0, %r); import launch\n"
                "def flood(argv):\n    [print('x' * 80) for _ in range(100000)]\n    return 0\n"
                "launch.launch = flood\nsys.exit(launch.main([]))\n") % os.path.dirname(MODULE)
        r = subprocess.run(["bash", "-c", 'set -o pipefail; "$0" -c "$1" | head -c 1 >/dev/null; echo "rc=${PIPESTATUS[0]}"',
                            sys.executable, code], capture_output=True, text=True, timeout=60)
        check("`--print | head` ends quietly with 141, as bash's SIGPIPE did",
              r.stdout.strip() == "rc=141" and "Traceback" not in r.stderr and "Exception" not in r.stderr)

        print("the shim")
        r = subprocess.run(["bash", SHIM, "--print"], env=clean_env(AGENT_FABRIC_PYTHON=f"{tmp}/no-python"),
                           capture_output=True, text=True, timeout=30)
        check("no pinned interpreter: exit 127, one line naming the path and the install",
              r.returncode == 127 and r.stdout == "" and r.stderr.count("\n") == 1
              and f"{tmp}/no-python" in r.stderr and "python_pin.py install" in r.stderr)
        r = subprocess.run(["bash", SHIM, "--provider", "nowhere"], env=clean_env(AGENT_FABRIC_PYTHON=sys.executable),
                           capture_output=True, text=True, timeout=30)
        check("the shim runs the module by absolute path, its argv untouched",
              r.returncode == 1 and r.stderr == "launch: --provider must be openrouter or anthropic, not 'nowhere'\n")

        print("two launchers in one process")
        # A fixture copy and the real launcher loaded in one process each run
        # their own parts: the package is loaded by path, and a second load
        # must not take the first one's cached parts (#102's review).
        copy = f"{tmp}/copy/tools/fabric"
        os.makedirs(copy)
        shutil.copytree(os.path.join(os.path.dirname(MODULE), "launcher"), f"{copy}/launcher",
                        ignore=shutil.ignore_patterns("__pycache__"))
        for f in ("launch.py", "git.py"):
            shutil.copy(os.path.join(os.path.dirname(MODULE), f), f"{copy}/{f}")
        code = ("import importlib.util, inspect, sys\n"
                "def load(name, path):\n"
                "    spec = importlib.util.spec_from_file_location(name, path)\n"
                "    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m\n"
                "a = load('launch_a', sys.argv[1]); b = load('launch_b', sys.argv[2])\n"
                "print(inspect.getsourcefile(a.helper)); print(inspect.getsourcefile(b.helper))\n"
                "print(a.helper is b.helper)\n")
        r = subprocess.run([sys.executable, "-I", "-c", code, MODULE, f"{copy}/launch.py"],
                           capture_output=True, text=True, timeout=60)
        files = r.stdout.splitlines()
        # Resolved on both sides: launch.py names its parts by realpath, and a
        # clone or $TMPDIR may sit behind a symlink.
        real = [os.path.realpath(f) for f in files[:2]]
        check("each launcher runs its own parts, whichever loaded first",
              r.returncode == 0 and len(files) == 3
              and real[0].startswith(os.path.realpath(os.path.dirname(MODULE)) + os.sep)
              and real[1].startswith(os.path.realpath(copy) + os.sep) and files[2] == "False", f"{r.stdout}{r.stderr}")

    print("test_launch.py: OK" if not fails else f"test_launch.py: {fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
