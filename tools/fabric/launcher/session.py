"""tools/fabric/launcher/session.py — the session prepared, run as a child, reported, and its restart marker read.
A part of tools/fabric/launch.py, whose docstring is the contract."""
from __future__ import annotations

import datetime
import json
import os
import signal
import stat
import subprocess
import sys
import time
import traceback
from fabric_launcher.base import INSTALL_TIMEOUT_S, RESTART_WAIT_S, OPENING, WAIT_TAIL, die, say, helper, stripped, env_with


def require_files(*paths: str) -> None:
    for path in paths:
        if not os.path.isfile(path):
            die(f"{path} is missing.")


def make_tmpdir(path: str, *, ours: bool = True) -> None:
    """mkdir -p -m 700: the mode on the directory made, whatever the umask;
    one that exists is left as it is, if it is this account's own directory.
    /var/tmp is world-writable and sticky: another account can make
    /var/tmp/agent-fabric-<agent> first, or a symlink by that name, and the
    session would write its scratch where that account reads it and this one
    cannot remove it. The bash's mkdir -p took either (review of #80); the
    launch is refused instead, naming the path, so the person moves it. A
    TMPDIR the account set itself (`ours` false) is its own choice, /tmp
    included, and is taken as it is."""
    # Made first, checked after: a check before the mkdir left a window in
    # which another account's directory or symlink, made between the two,
    # was taken unchecked (review of #87). mkdir never follows a symlink.
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.mkdir(path, 0o700)
        os.chmod(path, 0o700)
    except OSError:
        pass
    if not ours:
        return
    try:
        st = os.lstat(path)
    except OSError:
        return
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        die(f"TMPDIR {path} exists and is not a directory (a symlink is refused too); remove it or set TMPDIR")
    if st.st_uid != os.geteuid():
        die(f"TMPDIR {path} belongs to uid {st.st_uid}, not this account; remove it as that account or root, "
            "or set TMPDIR")


def print_report(d: dict, routing, *, label: str, agent: str, role: str, provider: str, session: str,
                 effective_session: str, session_effort: str, caller_effort: bool, prompt_file: str,
                 prompt_flag: str) -> None:
    s = d["session"]
    cap = s.get("capability")
    print(f"# resolved profile for {label} (agent {agent}, role {role}, provider {provider})")
    print(f"  session : {session}" + (f"  (the {cap} class)" if cap else ""))
    skipped = s.get("skipped") or ""
    if skipped:
        print(f"  (the merged session {skipped} is not an Anthropic model; the {s['source']} layer's is used "
              "on plain claude)")
    print(f"  (from the {s['source']} layer; bin/fabric-model list --provider {provider} shows every choice with "
          "its source)")
    if effective_session != session:
        print(f"  (overridden by --model on the command line: {effective_session})")
    if session_effort:
        print(f"  effort  : {session_effort}" + ("  (--effort on the command line)" if caller_effort
                                                 else "  (routing/effort.json)"))
    # Never "the model expresses none" without knowing that: a caller's
    # valueless --effort empties this too (re-review, N4).
    elif caller_effort:
        print("  effort  : -  (--effort on the command line carries no value; none is added)")
    else:
        print("  effort  : -  (this session's model expresses none; no --effort is passed)")
    # A --print missing half its profile must fail, not look successful:
    # the bash's block here could die on its first class, print a traceback
    # to stderr, and leave --print exiting 0 with the lines around it intact
    # — measured. A crash here is exit 1.
    try:
        for klass, res in d["classes"].items():
            if res["via"] == "harness":
                how = "(harness default for its tier)"
            elif res["via"] == "file":
                how = "(pinned in the agent file; the dispatch guard applies it; from %s)" % res["source"]
            else:
                how = "(exported for its tier; from %s)" % res["source"]
            # Effort is routed beside the model (routing/effort.json), so it is
            # printed beside it: `asked -> served` whenever they differ, because
            # a downgrade nobody can see is the defect the dimension exists for.
            eff = routing.effort_phrase(res.get("effort"))
            eff = "  " + eff if eff else ""
            if d.get("provider") == "anthropic":
                print("  %-12s: %s  %s%s" % (klass, res["model"], how, eff))
            else:
                print("  %-12s: %s  shim %s  => %s  %s%s" % (klass, res["model"], res["shim"] or "-",
                                                            res["composite"], how, eff))
        print()
        for k, v in sorted(d["exports"].items()):
            print("  export %s=%s" % (k, v))
    except Exception:
        sys.stdout.flush()
        traceback.print_exc()
        sys.exit(1)
    env = os.environ
    for var in ("AGENT_FABRIC_LAUNCH_SESSION_MODEL", "AGENT_FABRIC_LAUNCH_PROFILE", "AGENT_FABRIC_LAUNCH_PROVIDER",
                "AGENT_FABRIC_LAUNCH_ROLE", "AGENT_FABRIC_LAUNCH_PROMPT_DIGEST"):
        print(f"  export {var}={env.get(var, '')}")
    with open(prompt_file, "rb") as fh:
        prompt = fh.read()
    print(f"  prompt  : {prompt_file} ({len(prompt)} bytes; {prompt_flag})")
    if env.get("AGENT_FABRIC_LAUNCH_CLAUDE_VERSION"):
        print(f"  export AGENT_FABRIC_LAUNCH_CLAUDE_VERSION={env['AGENT_FABRIC_LAUNCH_CLAUDE_VERSION']} (the prompt is "
              "replaced; runtime/claude-code/harness/en.md names the build it was captured from)")
    first = prompt.split(b"\n", 1)[0].decode("utf-8", "surrogateescape")
    print(f"            {first}")


def record_launch_provider(state_dir: str, provider: str) -> None:
    """The provider the agent files were last installed for, so a run with
    no provider of its own (bootstrap from the control agent, an upgrade,
    fabric-model apply) installs for this one rather than for anthropic
    (install_agent_files.py reads it). Atomic; a failure is said, not fatal:
    the files themselves are installed."""
    path = os.path.join(state_dir, "launch-provider.json")
    try:
        os.makedirs(state_dir, exist_ok=True)
        tmp = f"{path}.tmp-{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"provider": provider, "at": datetime.datetime.now(datetime.timezone.utc)
                       .strftime("%Y-%m-%dT%H:%M:%SZ")}, fh)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        say(f"launch: could not record the provider in {path}: {exc}")


def install_agent_files(fabric_root: str, provider: str, state_dir: str | None = None) -> None:
    try:
        r = subprocess.run(["bash", f"{fabric_root}/runtime/claude-code/install-agent-files.sh", "--provider",
                            provider], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           timeout=INSTALL_TIMEOUT_S)
        installed = r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        installed = False
    if not installed:
        die(f"could not install the capability-class agent files for {provider} "
            "(runtime/claude-code/install-agent-files.sh).")
    if state_dir:
        record_launch_provider(state_dir, provider)


def mark_onboarding_done(path: str) -> None:
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except FileNotFoundError:
        d = {}
    except (OSError, ValueError) as exc:
        say(f"launch: {path}: {exc}")
        die(f"could not mark the harness's onboarding done in {path}; nothing started.")
    if not isinstance(d, dict):
        say(f"launch: {path} is not a JSON object")
        die(f"could not mark the harness's onboarding done in {path}; nothing started.")
    if d.get("hasCompletedOnboarding") is not True:
        d["hasCompletedOnboarding"] = True
        tmp = f"{path}.fabric-tmp"
        try:
            with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as fh:
                json.dump(d, fh, indent=2)
            os.replace(tmp, path)
        except OSError as exc:
            say(f"launch: {path}: {exc}")
            die(f"could not mark the harness's onboarding done in {path}; nothing started.")
        say("launch: marked the harness's onboarding done — a template login has no /login to onboard")


def session_command(provider: str, session: str, caller_model: bool, session_effort: str, caller_effort: bool,
                    prompt_flag: str, prompt_file: str, args: list[str]) -> list[str]:
    """The session's command line up to the caller's own arguments: the
    launcher's --model and --effort only where the caller passed none, so
    the child sees one of each and the stamps say what it applies."""
    cmd = ([] if provider == "anthropic" else ["ori"]) + ["claude"]
    if not caller_model:
        cmd += ["--model", session]
    if not caller_effort and session_effort:
        cmd += ["--effort", session_effort]
    return cmd + [prompt_flag, prompt_file, *args]


def opening_prompt(fabric_root: str) -> str:
    text = OPENING
    # A session that ended its own job (bin/fabric-fresh) left a note for this
    # one: said in the opening prompt, then dropped from the environment.
    if "AGENT_FABRIC_FRESH_NOTE" in os.environ:
        note = os.environ.pop("AGENT_FABRIC_FRESH_NOTE")
        text = (text.removesuffix(WAIT_TAIL) + " The previous session of this agent finished its job and started "
                "this one fresh" + (f": {note}" if note else "") + "." + WAIT_TAIL)
    # fabric-fresh --job: the fresh session is for that job (ADR-037), and
    # the job, as the list holds it, replaces the wait for instructions.
    job = os.environ.get("AGENT_FABRIC_FRESH_JOB", "")
    if job:
        line = stripped(helper([sys.executable, f"{fabric_root}/tools/fabric/jobs.py", "show", job, "--line"],
                               env=env_with(AGENT_FABRIC_ROOT=fabric_root), quiet=True))
        if line:
            text = (text.removesuffix(WAIT_TAIL) + f" It is for your job {line}: read it in full with "
                    f"fabric-jobs show {job}, and start on it.")
        del os.environ["AGENT_FABRIC_FRESH_JOB"]
    return text


def ignore_quit() -> None:
    """In the session, before it starts: SIGQUIT ignored, as bash gave every
    `&` job of a script (without job control, an asynchronous command
    ignores SIGINT and SIGQUIT). SIGINT is ignored here already, and
    inherited."""
    signal.signal(signal.SIGQUIT, signal.SIG_IGN)


def run_session(cmd: list[str]) -> int:
    """THE SESSION IS A CHILD, NOT AN EXEC (owner, 2026-09-16). This process
    outlives the session, which is what lets it bring the session back
    after an upgrade or an account move (the restart marker, below). It
    once also sent a GOODBYE, a type now retired; presence is the control
    plane's.
    Signals: Ctrl-C is the session's (one interrupts a turn, two end it),
    so the launcher ignores SIGINT while the child runs; SIGTERM and SIGHUP
    — the terminal closing — are forwarded so the child can end. The
    child's exit status is the launcher's, 128+n for a signal, as bash's
    `wait` reported it. Same process group and the terminal as stdin, so
    Ctrl-C reaches the child directly."""
    child: subprocess.Popen | None = None

    def forward(signum, _frame):  # end the child the way we were asked to
        if child is not None and child.returncode is None:
            try:
                child.send_signal(signum)
            except ProcessLookupError:
                pass

    sys.stdout.flush()
    sys.stderr.flush()
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGHUP, forward)
    try:
        child = subprocess.Popen(cmd, preexec_fn=ignore_quit)
        status = child.wait()
    except OSError as exc:
        say(f"launch: {cmd[0]}: {exc.strerror}")
        status = 127 if isinstance(exc, FileNotFoundError) else 126
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, signal.SIG_DFL)
    return 128 - status if status < 0 else status


# ── back on the new version: the restart an action asked for ─────────
# The control agent's `upgrade` or `secrets-sync --restart`
# (runtime/control/{upgrade,secrets}.mjs) writes
# $STATE_DIR/restart.json, then stops this session with SIGTERM — the
# harness's graceful shutdown. This process is still in the session's
# terminal, so it is the one that can bring the session back: it waits
# while the upgrade runs, then re-executes itself — through the same pull
# and checks as any launch — resuming the session it was running
# (ADR-009). A marker older than this launch belongs to
# another session and is removed, never obeyed; an upgrade that failed
# still restarts, on what is installed, and says so.
def read_restart(marker: str, started: int, binding: str, wait_s_text: str) -> str | None:
    """What to come back as: "fresh:<job>:<note>", the session id to resume
    ("" for --continue), or None for a marker not to obey."""
    try:
        wait_s = int(wait_s_text)
    except ValueError:
        say(f"launch: AGENT_FABRIC_RESTART_WAIT_S is '{wait_s_text}', not a number of seconds; not resuming the "
            f"session (unset it for the default, {RESTART_WAIT_S} s).")
        return None

    def load():
        try:
            with open(marker, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}
    m = load()
    try:
        at = datetime.datetime.fromisoformat(str(m.get("requested_at", "")).replace("Z", "+00:00")).timestamp()
    except ValueError:
        at = 0
    if at < started:
        return None
    if m.get("fresh"):
        # The session ended its own job (bin/fabric-fresh): nothing to wait
        # for, nothing to resume. The note travels to the next opening prompt.
        note = " ".join(str(m.get("note") or "").split())[:300]
        job = str(m.get("job") or "").replace(":", "")
        say(f"launch: the session finished its job{': ' + note if note else ''}; starting a fresh one"
            f"{' for job ' + job if job else ''}.")
        return f"fresh:{job}:{note}"
    deadline = time.time() + wait_s
    if m.get("status") == "pending":
        say(f"launch: the session was stopped for an upgrade of {m.get('piece')} to {m.get('to')}; waiting for it…")
    while m.get("status") == "pending" and time.time() < deadline:
        time.sleep(1)
        m = load()
    st = m.get("status")
    if st == "done":
        verb = "moved" if m.get("piece") == "the Claude account" else "upgraded"
        say(f"launch: {m.get('piece')} {verb} {m.get('from')} → {m.get('installed') or m.get('to')}; "
            "resuming the session on it.")
    elif st == "failed":
        say(f"launch: the upgrade of {m.get('piece')} to {m.get('to')} FAILED ({m.get('reason') or 'no reason given'}); "
            "resuming the session on what is installed.")
    else:
        say(f"launch: the upgrade of {m.get('piece')} did not finish within {wait_s} s; resuming the session on "
            "what is installed.")
    try:
        with open(binding, encoding="utf-8") as fh:
            return str(json.load(fh).get("session") or "").rstrip("\n")
    except (OSError, ValueError):
        return ""
