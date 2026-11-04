#!/usr/bin/env python3
"""Tests for runtime/provisioning/moveto/moveto.py's internals; the
behaviour is tests/test_moveto_cli.py's, run unchanged
against the moveto shim (ADR-040 §5 rule 5). What is here is what that
suite does not reach: the exec into the entering shell, a directory
service that hangs, the shim run from an installed copy, and the details
of what reaches the terminal (control characters, padding, order). Plain
script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import io
import os
import pty
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "runtime", "provisioning", "moveto")
sys.path.insert(0, SRC)
import moveto as mv  # noqa: E402


def clean_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_"))}
    env.update(extra)
    return env


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

        # moveto asks `fabric-host ssh-pin` which way to enter an account: this machine's own fabric-host (an
        # older checkout, or a registry that pins an sshd) is not what these cases are about, so a stand-in
        # that says "sudo", as it does for a host with no pin, is first on the PATH of every case below.
        put(f"{tmp}/nohost/fabric-host", "#!/bin/sh\necho sudo\n", 0o755)
        os.environ["PATH"] = f"{tmp}/nohost:{os.environ['PATH']}"

        print("what reaches the terminal")
        check("C0, DEL and C1 controls are stripped; the printable rest stays",
              mv.display_safe("a\x1b]0;X\x07b\x7fc\x9bd") == "a]0;Xbcd")
        check("…and the line and paragraph separators a UTF-8 terminal breaks on",
              mv.display_safe("x\u2028y\u2029z") == "xyz")
        check("non-ASCII text that is not a control is kept", mv.display_safe("rôle ✓") == "rôle ✓")
        check("columns are padded by bytes, as bash's printf counts",
              mv.pad("ab", 5) == "ab   " and mv.pad("é", 4) == "é  " and mv.pad("longer-than", 4) == "longer-than")

        print("the role from the binding")
        bin_ = f"{tmp}/bin"
        put(f"{bin_}/getent", f"#!/usr/bin/env bash\necho \"$2:x:2000:2000::{tmp}/home/$2:/bin/bash\"\n", 0o755)
        put(f"{bin_}/sudo", "#!/usr/bin/env bash\nwhile [[ $1 == -* ]]; do [[ $1 == -u ]] && shift; shift; done\nexec \"$@\"\n",
            0o755)
        saved_path = os.environ["PATH"]
        os.environ["PATH"] = f"{bin_}:{saved_path}"
        try:
            b = f"{tmp}/home/acct/.local/state/agent-fabric/agents/acct/binding.json"
            put(b, '{"agent": "acct", "role": "first"}\n{"role": "second", "x": "y", "role": "last-on-line"}\n')
            check("the first line that names one, its last occurrence (sed's greedy .*)", mv.role_of("acct") == "first")
            put(b, '{"agent": "acct", "role": ""}\n')
            check("an empty role is -", mv.role_of("acct") == "-")
            put(b, "not json at all\n")
            check("no role at all is -", mv.role_of("acct") == "-")
        finally:
            os.environ["PATH"] = saved_path

        print("order")
        # In a locale whose collation is not byte order: under C.UTF-8 the
        # two agree, and the check would prove nothing.
        names = [b"web-dev-01", b"webdev-02", b"Alpha", b"alpha"]
        locales = subprocess.run(["locale", "-a"], capture_output=True, text=True, timeout=30).stdout.split()
        collating = next((loc for loc in ("en_US.utf8", "en_US.UTF-8", "C.utf8") if loc in locales), None)
        saved_lc = os.environ.get("LC_ALL")
        os.environ["LC_ALL"] = collating or "C"
        try:
            r = subprocess.run(["sort", "-z"], input=b"\0".join(names) + b"\0", capture_output=True, timeout=30)
            expected = [n for n in r.stdout.split(b"\0") if n]
            got = mv.sort_z(names)
        finally:
            if saved_lc is None:
                os.environ.pop("LC_ALL", None)
            else:
                os.environ["LC_ALL"] = saved_lc
        if collating and collating.startswith("en_US"):
            check(f"accounts and clones come in `sort`'s order under {collating}, which is not Python's bytes",
                  got == expected and expected != sorted(names), f"{got} vs {expected}")
        else:
            check(f"accounts and clones come in `sort`'s order (no collating locale here: {collating})", got == expected)
        check("…and nothing to sort is nothing", mv.sort_z([]) == [])

        print("the exec into the shell")
        calls = []
        saved = (mv.os.execv, mv.os.execvp, mv.me, mv.command, mv.run_as, mv.home_of, mv.list_clones)
        saved_pipe = signal.getsignal(signal.SIGPIPE)
        mv.os.execv = lambda path, argv: calls.append(("execv", path, argv)) or (_ for _ in ()).throw(SystemExit(0))
        mv.os.execvp = lambda path, argv: calls.append(("execvp", path, argv)) or (_ for _ in ()).throw(SystemExit(0))
        mv.home_of = lambda a: f"/h/{a}"
        mv.command = lambda args, stdin=None: (0, b"")
        mv.run_as = lambda a, *args: (0, b"")
        mv.list_clones = lambda a: (["c1"], "")
        try:
            mv.me = lambda: "op"
            try:
                with redirect_stdout(io.StringIO()), open(os.devnull, "w") as null:
                    sys.stderr, saved_err = null, sys.stderr
                    try:
                        mv.moveto(["acct"])
                    finally:
                        sys.stderr = saved_err
            except SystemExit:
                pass
            check("another account: sudo -n -u <it> -H enter <dir> <title>, nothing else",
                  calls == [("execvp", "sudo", ["sudo", "-n", "-u", "acct", "-H", mv.MOVETO_ENTER, "/h/acct/projects", "acct"])],
                  str(calls))
            calls.clear()
            mv.me = lambda: "acct"
            try:
                with redirect_stdout(io.StringIO()), open(os.devnull, "w") as null:
                    sys.stderr, saved_err = null, sys.stderr
                    try:
                        mv.moveto(["acct", "c1"])
                    finally:
                        sys.stderr = saved_err
            except SystemExit:
                pass
            check("this account: enter itself, no sudo", calls == [("execv", mv.MOVETO_ENTER, [mv.MOVETO_ENTER,
                                                                                               "/h/acct/projects/c1", "acct"])],
                  str(calls))
            calls.clear()
            mv.me = lambda: "op"
            try:
                with redirect_stdout(io.StringIO()), open(os.devnull, "w") as null:
                    sys.stderr, saved_err = null, sys.stderr
                    try:
                        mv.moveto(["acct", "--resume"])
                    finally:
                        sys.stderr = saved_err
            except SystemExit:
                pass
            check("--resume: the same sudo, enter told --resume as its third argument, nothing else",
                  calls == [("execvp", "sudo", ["sudo", "-n", "-u", "acct", "-H", mv.MOVETO_ENTER, "/h/acct/projects",
                                                "acct", "--resume"])], str(calls))
            for mode in ("--wait", "--watch"):
                calls.clear()
                try:
                    with redirect_stdout(io.StringIO()), open(os.devnull, "w") as null:
                        sys.stderr, saved_err = null, sys.stderr
                        try:
                            mv.moveto(["acct", mode, mode])
                        finally:
                            sys.stderr = saved_err
                except SystemExit:
                    pass
                check(f"{mode} (twice is once): enter told {mode} as its last argument, nothing else",
                      calls == [("execvp", "sudo", ["sudo", "-n", "-u", "acct", "-H", mv.MOVETO_ENTER,
                                                    "/h/acct/projects", "acct", mode])], str(calls))
            for pair in (("--wait", "--resume"), ("--watch", "--wait"), ("--resume", "--watch")):
                calls.clear()
                # The exec mock raises SystemExit(0): a pair let through
                # must fail this check, not end the script green.
                try:
                    with redirect_stdout(io.StringIO()), open(os.devnull, "w") as null:
                        sys.stderr, saved_err = null, sys.stderr
                        try:
                            mv.moveto(["acct", *pair])
                        finally:
                            sys.stderr = saved_err
                    refused = ""
                except mv.Refused as exc:
                    refused = str(exc)
                except SystemExit:
                    refused = ""
                check(f"{' '.join(pair)}: refused, nothing entered", "one of --wait, --resume, --watch" in refused and not calls,
                      (refused, calls))
        finally:
            mv.os.execv, mv.os.execvp, mv.me, mv.command, mv.run_as, mv.home_of, mv.list_clones = saved
            signal.signal(signal.SIGPIPE, saved_pipe)

        print("the entered shell's SIGPIPE (review of #80)")
        # The probe is sh, not Python: a Python child would ignore SIGPIPE at
        # its own start-up, whatever it inherited.
        probe = put(f"{tmp}/enter-probe", "#!/bin/sh\n"
                    "{ grep '^SigIgn' /proc/$$/status | cut -f2; echo \"${_MOVETO_PIPE_IGNORED-unset}\"; } > \"$1\"\n",
                    0o755)

        def entered(**env) -> tuple[bool, str]:
            out = f"{tmp}/entered"
            code = ("import sys; sys.path.insert(0, %r); import moveto as mv; mv.MOVETO_ENTER = %r; "
                    "mv.me = lambda: 'acct'; mv.enter('acct', sys.argv[1], 'title')") % (SRC, probe)
            subprocess.run([sys.executable, "-c", code, out], env=clean_env(**env), timeout=60)
            with open(out, encoding="utf-8") as fh:
                mask, leaked = fh.read().split()
            os.remove(out)
            return bool(int(mask, 16) & (1 << (signal.SIGPIPE - 1))), leaked
        check("a caller's default SIGPIPE reaches the shell as the default, not Python's ignore",
              entered() == (False, "unset"))
        check("…one the caller ignored stays ignored, and the hand-over variable goes no further",
              entered(_MOVETO_PIPE_IGNORED="1") == (True, "unset"))
        fake_py = put(f"{tmp}/fake-python", "#!/bin/sh\necho \"${_MOVETO_PIPE_IGNORED-unset}\"\n", 0o755)
        shim_env = clean_env(AGENT_FABRIC_PYTHON=fake_py, _MOVETO_PIPE_IGNORED="1")
        # This process ignores SIGPIPE (Python's start-up): restore_signals
        # off hands that to the shim, on hands it the default.
        ign = subprocess.run(["bash", os.path.join(SRC, "moveto")], env=shim_env, capture_output=True, text=True,
                             timeout=60, restore_signals=False).stdout
        dfl = subprocess.run(["bash", os.path.join(SRC, "moveto")], env=shim_env, capture_output=True, text=True,
                             timeout=60).stdout
        check("the shim says which it was given, never passing on a stale value", (ign, dfl) == ("1\n", "unset\n"),
              repr((ign, dfl)))

        print("a reader that went away (review of #80)")
        put(f"{bin_}/sudo", "#!/usr/bin/env bash\nwhile [[ $1 == -* ]]; do [[ $1 == -u ]] && shift; shift; done\nexec \"$@\"\n",
            0o755)
        os.makedirs(f"{tmp}/gone-home/projects", exist_ok=True)
        put(f"{bin_}/getent", f"#!/usr/bin/env bash\necho \"gone:x:2000:2000::{tmp}/gone-home:/bin/bash\"\n", 0o755)
        r_fd, w_fd = os.pipe()
        os.close(r_fd)
        try:
            p = subprocess.run([sys.executable, os.path.join(SRC, "moveto.py"), "gone", "--print"], stdout=w_fd,
                               stderr=subprocess.PIPE, text=True, timeout=60,
                               env=clean_env(PATH=f"{bin_}:{saved_path}"))
        finally:
            os.close(w_fd)
        check("--print into a closed pipe: exit 141, nothing on stderr", p.returncode == 141 and p.stderr == "",
              f"rc={p.returncode} {p.stderr}")

        print("a directory service that hangs")
        put(f"{bin_}/getent", "#!/usr/bin/env bash\nexec sleep 60\n", 0o755)
        saved_timeout = mv.TIMEOUT_S
        mv.TIMEOUT_S = 1
        os.environ["PATH"] = f"{bin_}:{saved_path}"
        try:
            t0 = time.monotonic()
            home = mv.home_of("acct")
            took = time.monotonic() - t0
            check("reads as the command failing within its bound: no home, not a hung prompt",
                  home == "" and took < 10, f"took {took:.1f} s")
        finally:
            os.environ["PATH"] = saved_path
            mv.TIMEOUT_S = saved_timeout

        print("the command line")
        fx = f"{tmp}/fx"
        put(f"{fx}/bin/getent", f"""#!/usr/bin/env bash
accounts="solo:2000 sys:999 mult:2001"
if [[ $1 == passwd && $# -eq 2 ]]; then
  for a in $accounts; do [[ ${{a%%:*}} == "$2" ]] && {{ echo "$2:x:${{a#*:}}:${{a#*:}}::{fx}/home/$2:/bin/bash"; exit 0; }}; done; exit 2
fi
for a in $accounts; do echo "${{a%%:*}}:x:${{a#*:}}:${{a#*:}}::{fx}/home/${{a%%:*}}:/bin/bash"; done
""", 0o755)
        put(f"{fx}/bin/sudo", "#!/usr/bin/env bash\nwhile [[ $1 == -* ]]; do [[ $1 == -u ]] && shift; shift; done\nexec \"$@\"\n",
            0o755)
        for acct, clone in (("solo", "one"), ("sys", "sysclone"), ("mult", "a"), ("mult", "b\x1b]0;X\x07c")):
            os.makedirs(f"{fx}/home/{acct}/projects/{clone}", exist_ok=True)

        def cli(*args):
            return subprocess.run(["bash", os.path.join(SRC, "moveto"), *args], capture_output=True, text=True,
                                  timeout=60, env=clean_env(AGENT_FABRIC_PYTHON=sys.executable,
                                                            PATH=f"{fx}/bin:{os.environ['PATH']}"))
        r = cli()
        check("no arguments: the usage on stdout, exit 0", r.returncode == 0 and r.stdout == mv.USAGE)
        r = cli("--list")
        check("--list leaves out accounts below uid 1000 (system accounts)",
              r.returncode == 0 and "solo" in r.stdout and "sys" not in r.stdout.split(), r.stdout)
        r = cli("nobody", "--list")
        check("<account> --list for an account that does not exist is refused by name",
              r.returncode == 1 and r.stderr == "moveto: no such account: nobody\n", r.stderr)
        r = cli("mult", "--list")
        check("<account> --list prints its clones with no control character",
              r.returncode == 0 and r.stdout == "a\nb]0;Xc\n", repr(r.stdout))
        r = cli("solo", "--bogus")
        check("an unknown option is refused, with where to look",
              r.returncode == 1 and r.stderr == "moveto: unknown option '--bogus' (try --help)\n", r.stderr)
        r = cli("mult", "a", "b")
        check("two clones are refused: one at a time", r.returncode == 1 and r.stderr == "moveto: one clone at a time\n")

        print("the terminal after ssh (j103)")
        # The fake ssh switches on what Claude Code switches on in the operator's terminal, then ends as asked;
        # moveto's stdout is a pty, which is what the deck's pane is. The wanted sequences are spelt out here
        # and not taken from the module, so a changed reset cannot agree with itself.
        sshd = f"{tmp}/sshfx"
        for name, body in (
            ("fabric-host", "#!/bin/sh\necho \"ssh $FX_ADDR $FX_PORT\"\n"),
            ("fabric-ssh-hosts", "#!/bin/sh\necho \"$FX_ADDR ssh-ed25519 AAAAfixture\"\n"),
            ("getent", f"#!/bin/sh\necho \"$2:x:2000:2000::{sshd}/home:/bin/bash\"\n"),
            ("ssh", "#!/bin/sh\nprintf '%s\\n' \"$*\" > \"$FX_ARGV\"\n"
                    "printf '\\033[>1u\\033[?1000h\\033[?1006h\\033[?1004h\\033[?2004h\\033[>4;2m\\033[?25l'\n"
                    "case $FX_END in exit0) exit 0;; drop) exit 255;; hup) : > \"$FX_READY\"; exec sleep 60;; nap) : > \"$FX_READY\"; exec sleep 1;; stop) : > \"$FX_READY\"; kill -STOP $$; exit 7;; stopdie) echo $$ > \"$FX_READY\"; kill -STOP $$; exit 7;; esac\n"),
        ):
            put(f"{sshd}/bin/{name}", body, 0o755)
        put(f"{sshd}/home/.ssh/fabric_deck", "")
        enabled = "\x1b[>1u\x1b[?1000h\x1b[?1006h\x1b[?1004h\x1b[?2004h\x1b[>4;2m\x1b[?25l"
        wanted = ["\x1b[<u\x1b[<u", "\x1b[=0;1u", *(f"\x1b[?{n}l" for n in (1000, 1002, 1003, 1005, 1006, 1015, 1004, 2004)),
                  "\x1b[>4;0m", "\x1b[?25h"]

        def via_ssh(end: str, host: str = "127.0.0.1", port: str = "22", tty: bool = True, sig: int = signal.SIGHUP,
                    ignored: tuple = ()) -> tuple[int, str, str]:
            env = clean_env(PATH=f"{sshd}/bin:/usr/bin:/bin", HOME=f"{sshd}/home", XDG_STATE_HOME=f"{sshd}/state",
                            FX_ADDR=host, FX_PORT=port, FX_END=end, FX_ARGV=f"{sshd}/argv", FX_READY=f"{sshd}/ready")
            if os.path.exists(f"{sshd}/ready"):
                os.remove(f"{sshd}/ready")
            if tty:
                master, slave = pty.openpty()
            else:
                master, slave = os.pipe()
            p = subprocess.Popen([sys.executable, os.path.join(SRC, "moveto.py"), "acct", "--via", "ssh"], env=env,
                                 stdin=subprocess.DEVNULL, stdout=slave, stderr=subprocess.DEVNULL,
                                 preexec_fn=lambda: [signal.signal(i, signal.SIG_IGN) for i in ignored])
            os.close(slave)
            try:
                if end in ("hup", "nap"):
                    for _ in range(300):
                        if os.path.exists(f"{sshd}/ready"):
                            break
                        time.sleep(0.05)
                    p.send_signal(sig)      # as the deck's hang-up does, to moveto
                rc = p.wait(timeout=60)
                got = b""
                while True:
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:                   # EIO: the pty's other side is closed
                        break
                    if not chunk:
                        break
                    got += chunk
            finally:
                os.close(master)
            return rc, got.decode("utf-8", "replace").replace("\r\n", "\n"), open(f"{sshd}/argv", encoding="utf-8").read()

        def reset_after_enabling(out: str) -> bool:
            if not out.startswith(enabled):
                return False
            tail, at = out[len(enabled):], 0
            for seq in wanted:
                at = tail.find(seq, at)
                if at < 0:
                    return False
            return True
        for end, rc_want, label in (("exit0", 0, "ssh exits 0"), ("drop", 255, "ssh exits 255, a dropped connection"),
                                    ("hup", 129, "ssh is SIGHUP'd through moveto, as the deck does")):
            rc, out, argv = via_ssh(end)
            check(f"{label}: the modes are switched off on moveto's stdout, ssh's status kept ({rc_want})",
                  rc == rc_want and reset_after_enabling(out), f"rc={rc} out={out!r}")
        for sig, want in ((signal.SIGTERM, 143), (signal.SIGINT, 130)):
            rc, out, argv = via_ssh("hup", sig=sig)
            check(f"{sig.name} to moveto is forwarded: ssh dies of it, {want}, and the reset is still written",
                  rc == want and reset_after_enabling(out), f"rc={rc} out={out!r}")
        rc, out, argv = via_ssh("nap", sig=signal.SIGINT, ignored=(signal.SIGINT,))
        check("a SIGINT the caller ignored stays ignored for ssh (nohup, a background job): ssh runs on to its own exit 0",
              rc == 0 and reset_after_enabling(out), f"rc={rc} out={out!r}")
        rc, out, argv = via_ssh("exit0", host="10.0.0.7", port="2222")
        check("a host that is not loopback, as --via ssh to a second host: the same reset, and ssh's argv names it",
              rc == 0 and reset_after_enabling(out) and "-p 2222" in argv and "acct@10.0.0.7" in argv, f"{out!r} {argv!r}")
        # ssh's ~^Z stops ssh alone; the pane's bash waits for moveto, so moveto must stop too (WUNTRACED) and, when
        # continued, continue ssh. Only moveto is signalled here, as bash's fg would when ssh is not in its job.
        env = clean_env(PATH=f"{sshd}/bin:/usr/bin:/bin", HOME=f"{sshd}/home", XDG_STATE_HOME=f"{sshd}/state",
                        FX_ADDR="127.0.0.1", FX_PORT="22", FX_END="stop", FX_ARGV=f"{sshd}/argv", FX_READY=f"{sshd}/ready")
        if os.path.exists(f"{sshd}/ready"):
            os.remove(f"{sshd}/ready")
        master, slave = pty.openpty()
        p = subprocess.Popen([sys.executable, os.path.join(SRC, "moveto.py"), "acct", "--via", "ssh"], env=env,
                             stdin=subprocess.DEVNULL, stdout=slave, stderr=subprocess.DEVNULL)
        os.close(slave)
        try:
            # Reading the state of a child that is not ours to reap: a stopped moveto shows as T in /proc.
            state = ""
            for _ in range(200):
                try:
                    state = open(f"/proc/{p.pid}/stat", encoding="ascii").read().rsplit(")", 1)[1].split()[0]
                except OSError:
                    state = "?"
                if state == "T" and os.path.exists(f"{sshd}/ready"):
                    break
                time.sleep(0.05)
            check("ssh stops itself (~^Z): moveto stops too, so the pane's shell gets its prompt back", state == "T", state)
            p.send_signal(signal.SIGCONT)
            rc = p.wait(timeout=60)
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
            os.close(master)
        check("…and continued, moveto continues ssh, which runs on to its own status (7)", rc == 7, f"rc={rc}")
        # ssh dies while stopped (kill -9, the OOM killer, bash's kill %1): the SIGCONT moveto sends makes Popen reap it,
        # and the raw waitpid then has no child. moveto must still return ssh's status and write the reset.
        env["FX_END"] = "stopdie"
        os.remove(f"{sshd}/ready")
        master, slave = pty.openpty()
        p = subprocess.Popen([sys.executable, os.path.join(SRC, "moveto.py"), "acct", "--via", "ssh"], env=env,
                             stdin=subprocess.DEVNULL, stdout=slave, stderr=subprocess.PIPE)
        os.close(slave)
        try:
            for _ in range(200):
                try:
                    state = open(f"/proc/{p.pid}/stat", encoding="ascii").read().rsplit(")", 1)[1].split()[0]
                    ssh_pid = int(open(f"{sshd}/ready", encoding="ascii").read().strip() or 0)
                except (OSError, ValueError):
                    state, ssh_pid = "?", 0
                if state == "T" and ssh_pid:
                    break
                time.sleep(0.05)
            check("positive control: ssh and moveto are both stopped before ssh is killed", state == "T" and ssh_pid > 0, state)
            if ssh_pid:
                os.kill(ssh_pid, signal.SIGKILL)
            p.send_signal(signal.SIGCONT)
            rc = p.wait(timeout=60)
            err = p.stderr.read().decode("utf-8", "replace")
            got = b""
            while True:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                got += chunk
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
            p.stderr.close()
            os.close(master)
        check("ssh killed while stopped: moveto returns its status (137), writes the reset, and prints no traceback",
              rc == 137 and reset_after_enabling(got.decode("utf-8", "replace").replace("\r\n", "\n")) and "Traceback" not in err,
              f"rc={rc} err={err[-300:]!r}")
        # A forwarded signal's Popen.send_signal polls first and can reap ssh behind the raw waitpid: no child is left to wait for.
        reaped = subprocess.Popen(["sh", "-c", "exit 3"])
        for _ in range(200):
            if os.path.exists(f"/proc/{reaped.pid}") and open(f"/proc/{reaped.pid}/stat", encoding="ascii").read().rsplit(")", 1)[1].split()[0] == "Z":
                break
            time.sleep(0.05)
        reaped.poll()
        try:
            got_rc = mv.wait_for_exit(reaped)
            note = ""
        except ChildProcessError as exc:
            got_rc, note = None, repr(exc)
        check("a child that Popen already reaped is not waited for again: ssh's code comes back, no ChildProcessError",
              got_rc == 3 and not note, f"{got_rc} {note}")
        for end, rc_want in (("exit0", 0), ("drop", 255)):
            rc, out, argv = via_ssh(end, tty=False)
            check(f"stdout a pipe ({end}): ssh's output only, no reset, status {rc_want}", rc == rc_want and out == enabled, f"rc={rc} out={out!r}")

        print("an installed copy")
        prefix = f"{tmp}/usr-local"
        r = subprocess.run(["sh", os.path.join(SRC, "install.sh")], env=clean_env(MOVETO_PREFIX=prefix),
                           capture_output=True, text=True, timeout=60)
        check("install.sh puts the module beside enter and rc, and records it",
              r.returncode == 0 and os.path.isfile(f"{prefix}/share/moveto/moveto.py")
              and "share/moveto/moveto.py" in open(f"{prefix}/share/moveto/installed.sha256").read(), r.stderr)
        sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
        import hosttools
        check("fabric-status reads a fresh install as in sync", hosttools.moveto_drift(prefix, root=HERE)["status"] == "in sync")
        with open(f"{prefix}/share/moveto/moveto.py", "a", encoding="utf-8") as fh:
            fh.write("# an older copy\n")
        drift = hosttools.moveto_drift(prefix, root=HERE)
        check("…and an installed module behind the repository as drift, naming it",
              drift["status"] == "drift" and "share/moveto/moveto.py" in drift["detail"], str(drift))
        moved = f"{tmp}/elsewhere"
        shutil.copytree(prefix, moved)
        r = subprocess.run([f"{moved}/bin/moveto", "--help"], env=clean_env(AGENT_FABRIC_PYTHON=sys.executable),
                           capture_output=True, text=True, timeout=60)
        check("the installed shim runs its own copy of the module, with no checkout behind it",
              r.returncode == 0 and r.stdout == mv.USAGE, r.stderr)
        r = subprocess.run([f"{moved}/bin/moveto", "--help"], env=clean_env(AGENT_FABRIC_PYTHON=f"{tmp}/no-python"),
                           capture_output=True, text=True, timeout=60)
        check("no pinned interpreter: exit 127, one line", r.returncode == 127 and r.stderr.count("\n") == 1
              and "python_pin.py install" in r.stderr)

    print("test_moveto.py: OK" if not fails else f"test_moveto.py: {fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
