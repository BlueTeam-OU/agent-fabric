#!/usr/bin/env python3
"""runtime/hostexec/hostexec: one command, two backends, the same result.
Ported from runtime/hostexec/test_hostexec.sh (ADR-040 Wave 6), case for
case.

A fixture registry with the local host and a remote one; a fake ssh that
records what it was asked and runs the remote line in a local shell (so the
SAME worker runs, as it would on the target); a fake sudo that drops
`-n -u X -H` and runs the rest. What is proved: the backend is the
registry's choice, the remote line quotes every word, stdin and the exit
status pass through both backends, --as reaches the worker, @fabric/
resolves on the target, a host absent from the registry is a refusal, and
fabric-host's check compares what the host reports with the id it was
reached as. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import pwd
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HX = os.path.join(ROOT, "runtime", "hostexec", "hostexec")
FH = os.path.join(ROOT, "bin", "fabric-host")
ME = pwd.getpwuid(os.geteuid()).pw_name
# `hostname -s` itself, as the bash test and fabric-host's check read it.
LOCAL = subprocess.run(["hostname", "-s"], capture_output=True, text=True, check=True, timeout=30).stdout.strip()


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as sandbox:
        bin_ = os.path.join(sandbox, "bin")
        os.makedirs(bin_)
        sshlog, sudolog, fault = (os.path.join(sandbox, n) for n in ("ssh.log", "sudo.log", "fault"))
        far_home = os.path.join(sandbox, "home", "zz-far-login")
        os.makedirs(far_home)
        registry = os.path.join(sandbox, "registry.json")
        with open(registry, "w", encoding="utf-8") as fh:
            json.dump({"version": 1,
                       "hosts": {LOCAL: {"platform": "fedora-qubes", "ssh": None, "operator": ME, "fabric": ROOT},
                                 "far-host": {"platform": "debian", "ssh": "op@far.example", "operator": "op",
                                              "fabric": ROOT}},
                       "placement": {ME: LOCAL, "zz-far-login": "far-host"}}, fh)

        def put(name: str, text: str) -> None:
            path = os.path.join(bin_, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(path, 0o755)

        # The fake ssh: `ssh -o BatchMode=yes [-t] <dest> -- <line>` → record,
        # then run <line> through a local shell, as the remote operator's
        # shell would.
        put("ssh", "#!/usr/bin/env bash\n"
                   f'printf \'%s\\n\' "$*" >> "{sshlog}"\n'
                   'args=("$@"); line="${args[-1]}"\n'
                   f'grep -qsxF down "{fault}" && {{ echo "ssh: connect to host far.example port 22: Connection refused" >&2; exit 255; }}\n'
                   'exec bash -c "$line"\n')
        put("sudo", "#!/usr/bin/env bash\n"
                    '[[ "$1" == -n ]] && shift; '
                    f'[[ "$1" == -u ]] && {{ echo "sudo-as $2" >> "{sudolog}"; shift 2; }}; [[ "$1" == -H ]] && shift\n'
                    'exec "$@"\n')
        put("getent", "#!/usr/bin/env bash\n"
                      f'[[ "$1" == passwd && "$2" == zz-far-login ]] && {{ echo "zz-far-login:x:1000:1000::{far_home}:/bin/bash"; exit 0; }}\n'
                      'exec /usr/bin/getent "$@"\n')
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
        env.update(PATH=f"{bin_}:/usr/bin:/bin", AGENT_FABRIC_HOSTS_REGISTRY=registry,
                   SUDO=os.path.join(bin_, "sudo"), SSH=os.path.join(bin_, "ssh"))

        def run(*argv: str, stdin: str | None = None, merge: bool = False) -> tuple[int, str]:
            r = subprocess.run(list(argv), env=env, input=stdin, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT if merge else None, text=True, timeout=60,
                               stdin=None if stdin is not None else subprocess.DEVNULL)
            return r.returncode, r.stdout

        def log(path: str) -> str:
            try:
                with open(path, encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                return ""

        def clear(path: str) -> None:
            open(path, "w").close()

        print("hostexec: the backend is the registry's choice")
        _, out = run(HX, "--resolve", LOCAL)
        check("the local host resolves to the local backend", "backend local" in out, out)
        _, out = run(HX, "--resolve", "far-host")
        check("another host resolves to ssh with its destination",
              "backend ssh, destination op@far.example" in out, out)
        rc, out = run(HX, "nowhere", "--", "true", merge=True)
        check("an unregistered host is a refusal naming the known ones",
              rc == 2 and "unknown host 'nowhere'" in out and "far-host" in out, f"rc={rc}\n{out}")

        print("hostexec: the same command, both backends")
        _, out = run(HX, LOCAL, "--", "sh", "-c", 'echo "local:$(id -un)"')
        check("local: runs as the operator", out.rstrip("\n") == f"local:{ME}", out)
        check("…and ssh was never called for the local host", not log(sshlog), log(sshlog))
        _, out = run(HX, "far-host", "--", "sh", "-c", 'echo "far:$(id -un)"')
        check("ssh: the worker ran on the far side (here, through the fake)", out.rstrip("\n") == f"far:{ME}", out)
        check("…as: ssh -o BatchMode=yes <destination> -- <fabric>/runtime/hostexec/worker",
              f"-o BatchMode=yes op@far.example -- {ROOT}/runtime/hostexec/worker" in log(sshlog), log(sshlog))
        clear(sshlog)
        _, out = run(HX, "far-host", "--", "printf", "%s|", "two words", "it's", 'a"b', "$HOME")
        check("every word reaches the far side whole (spaces, quotes, no expansion)",
              out == "two words|it's|a\"b|$HOME|", out)
        for h in (LOCAL, "far-host"):
            _, out = run(HX, h, "--", "cat", stdin="secret-on-stdin\n")
            check(f"{h}: stdin passes through", out.rstrip("\n") == "secret-on-stdin", out)
            rc, _ = run(HX, h, "--", "sh", "-c", "exit 7")
            check(f"{h}: the exit status is the command's", rc == 7, f"rc={rc}")
        check("…and never in argv", "secret-on-stdin" not in log(sshlog), log(sshlog))

        print("hostexec: --as, --cwd, @fabric/")
        _, out = run(HX, "far-host", "--as", "zz-far-login", "--", "sh", "-c", 'echo "$HOME|$PWD"')
        check("--as reaches the worker: sudo -u, HOME and cwd the account's",
              out.rstrip("\n") == f"{far_home}|{far_home}" and "sudo-as zz-far-login" in log(sudolog), out)
        _, out = run(HX, LOCAL, "--cwd", "/tmp", "--", "pwd")
        check("--cwd sets the directory (operator)", out.rstrip("\n") == "/tmp", out)
        _, out = run(HX, "far-host", "--", "@fabric/runtime/hostexec/worker", "--", "echo", "via-fabric")
        check("@fabric/<rel> resolves on the target host (the operator's checkout)",
              out.rstrip("\n") == "via-fabric", out)
        rc, out = run(HX, "far-host", "--as", "zz-far-login", "--", "@fabric/x", merge=True)
        check("…as an account: the account's own checkout, refused when it has none",
              rc == 2 and f"no fabric checkout at {far_home}/projects/agent-fabric" in out, f"rc={rc}\n{out}")
        probe = os.path.join(far_home, "projects", "agent-fabric", "bin", "probe")
        os.makedirs(os.path.dirname(probe))
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("#!/usr/bin/env bash\necho mine\n")
        os.chmod(probe, 0o755)
        _, out = run(HX, "far-host", "--as", "zz-far-login", "--", "@fabric/bin/probe")
        check("…and resolves there when it exists", out.rstrip("\n") == "mine", out)
        clear(sshlog)
        run(HX, "far-host", "--tty", "--", "true")
        check("--tty asks ssh for a terminal (-t)", " -t op@far.example " in log(sshlog), log(sshlog))

        print("hostexec: the connection drops")
        with open(fault, "w", encoding="utf-8") as fh:
            fh.write("down\n")
        rc, out = run(HX, "far-host", "--", "true", merge=True)
        check("ssh's failure is the caller's, with its status", rc == 255 and "Connection refused" in out,
              f"rc={rc}\n{out}")
        os.remove(fault)

        print("fabric-host")
        _, out = run(FH, "list")
        check("list: hosts with their placements",
              re.search(r"far-host.*ssh op@far\.example", out) is not None and "accounts: zz-far-login" in out, out)
        rc, out = run(FH, LOCAL, "check")
        check("check: this host answers as its id", rc == 0 and f"answers as {LOCAL}" in out, f"rc={rc}\n{out}")
        rc, out = run(FH, "far-host", "check", merge=True)
        check("check: a host answering under another name is refused (the fake far host is this machine)",
              rc == 1 and f"answers as '{LOCAL}'" in out and "registry id is the host's short hostname" in out,
              f"rc={rc}\n{out}")
        _, out = run(FH, "far-host", "run", "--as", "zz-far-login", "--", "sh", "-c", 'echo "$HOME"')
        check("run: hostexec with --as", out.rstrip("\n") == far_home, out)
        clear(sshlog)
        run(FH, "far-host", "rename", "zz-far-login", "old", "new", "--dry-run", merge=True)
        check("rename: the target's own rename-working-copy.sh",
              "@fabric/runtime/provisioning/rename-working-copy.sh zz-far-login old new --dry-run" in log(sshlog),
              log(sshlog))
        clear(sshlog)
        run(FH, "far-host", "drain", "zz-far-login", "--dry-run", merge=True)
        check("drain: the account's own harvest, as the account, bundle to stdout",
              "--as zz-far-login -- python3 @fabric/tools/fabric/harvest_memory.py --bundle - --dry-run" in log(sshlog),
              log(sshlog))

        print("fabric-host: the registry is roots.py's to find")
        op_tree = os.path.join(sandbox, "operator")
        os.makedirs(os.path.join(op_tree, "runtime", "hosts"))
        with open(os.path.join(op_tree, "runtime", "hosts", "registry.json"), "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "hosts": {"op-only-host": {"platform": "debian", "ssh": None, "operator": ME, "fabric": ROOT}},
                       "placement": {"zz-op-login": "op-only-host"}}, fh)

        def run_with(extra: dict[str, str], drop: tuple[str, ...], *argv: str) -> tuple[int, str]:
            e = {k: v for k, v in env.items() if k not in drop}
            e.update(extra)
            r = subprocess.run(list(argv), env=e, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
            return r.returncode, r.stdout + r.stderr

        rc, out = run_with({"AGENT_FABRIC_OPERATOR": op_tree}, ("AGENT_FABRIC_HOSTS_REGISTRY",), FH, "list")
        check("list: a separate operator's registry, not the checkout's own",
              rc == 0 and "op-only-host" in out and "zz-op-login" in out and "far-host" not in out, f"rc={rc}\n{out}")
        rc, out = run_with({}, ("AGENT_FABRIC_HOSTS_REGISTRY", "AGENT_FABRIC_OPERATOR"), FH, "list")
        check("…and with no operator set, the checkout's (positive control)", rc == 0 and "op-only-host" not in out, f"rc={rc}\n{out}")
        rc, out = run_with({"AGENT_FABRIC_OPERATOR": op_tree}, (), FH, "list")
        check("AGENT_FABRIC_HOSTS_REGISTRY outranks the operator's tree", rc == 0 and "far-host" in out and "op-only-host" not in out, f"rc={rc}\n{out}")
        rc, out = run_with({"AGENT_FABRIC_OPERATOR": op_tree}, ("AGENT_FABRIC_HOSTS_REGISTRY",), FH, "op-only-host", "run", "--", "echo", "via-operator")
        check("hostexec, run by fabric-host, reads the same registry", rc == 0 and out.strip() == "via-operator", f"rc={rc}\n{out}")
        rc, out = run_with({"AGENT_FABRIC_OPERATOR": op_tree}, ("AGENT_FABRIC_HOSTS_REGISTRY",), HX, "op-only-host", "--", "echo", "direct")
        check("…whereas hostexec alone keeps its own default (it is the host executor and stays shell)",
              rc == 2 and "unknown host 'op-only-host'" in out, f"rc={rc}\n{out}")
        put("broken-python", "#!/bin/sh\nexit 1\n")
        _, plain = run_with({}, ("AGENT_FABRIC_HOSTS_REGISTRY", "AGENT_FABRIC_OPERATOR", "AGENT_FABRIC_ROOT"), FH, "list")
        for label, tree in (("an empty tree", os.path.join(sandbox, "nothing")), ("another clone with a registry of its own", op_tree)):
            os.makedirs(tree, exist_ok=True)
            rc, out = run_with({"AGENT_FABRIC_ROOT": tree}, ("AGENT_FABRIC_HOSTS_REGISTRY", "AGENT_FABRIC_OPERATOR"), FH, "list")
            check(f"AGENT_FABRIC_ROOT naming {label} does not move the registry (every session exports one)",
                  rc == 0 and out == plain and "op-only-host" not in out, f"rc={rc}\n{out}")
        rc, out = run_with({"AGENT_FABRIC_PYTHON": os.path.join(bin_, "broken-python")}, (), FH, "--help")
        check("--help does not wait on the registry or the interpreter beyond its presence", rc == 0 and "fabric-host list" in out, f"rc={rc}\n{out}")
        broken = os.path.join(bin_, "broken-python")
        rc, out = run_with({"AGENT_FABRIC_PYTHON": broken}, (), FH, "list")
        check("a roots.py that cannot answer is a refusal, never the checkout's file",
              rc == 1 and "cannot resolve the hosts registry" in out and "far-host" not in out, f"rc={rc}\n{out}")
        rc, out = run_with({"AGENT_FABRIC_PYTHON": os.path.join(sandbox, "absent")}, (), FH, "list")
        check("no pinned Python: 127 with the install command", rc == 127 and "python_pin.py install" in out, f"rc={rc}\n{out}")

    print(f"\ntest_hostexec_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
