#!/usr/bin/env python3
"""tools/fabric/{hostexec,hostworker,fabric_host}.py: what tests/test_hostexec_cli.py
(the port's oracle, case for case from the bash) does not reach — argument
parsing, the quoting of the remote line, the registry's failure modes, the
signals a worker's command starts with, and the exit statuses of a command that
cannot start. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import fabric_host  # noqa: E402
import hostexec  # noqa: E402
import hostworker  # noqa: E402

WORKER = os.path.join(ROOT, "runtime", "hostexec", "worker")
HX = os.path.join(ROOT, "runtime", "hostexec", "hostexec")
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
if os.environ.get("AGENT_FABRIC_PYTHON"):
    ENV["AGENT_FABRIC_PYTHON"] = os.environ["AGENT_FABRIC_PYTHON"]


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    def run(argv: list[str], **kw) -> subprocess.CompletedProcess:
        return subprocess.run(argv, env=kw.pop("env", ENV), capture_output=True, text=True, timeout=60,
                              stdin=subprocess.DEVNULL, **kw)

    print("the worker's argument parsing")
    check("--as, --cwd and -- are read in either spelling",
          hostworker.parse(["--as", "a", "--cwd=/x", "--", "true", "-x"]) == ("a", "/x", ["true", "-x"])
          and hostworker.parse(["--as=a", "--cwd", "/x", "--", "true"]) == ("a", "/x", ["true"]))
    check("a command's own flags after -- are not the worker's", hostworker.parse(["--", "--as", "x"]) == ("", "", ["--as", "x"]))
    check("no command after -- is a usage error (2)", hostworker.parse(["--as", "a"]) == 2 and hostworker.parse(["--"]) == 2)
    check("an unknown argument before -- is a usage error (2)", hostworker.parse(["--bogus", "--", "true"]) == 2)
    check("a flag with no value is a usage error (2), not a crash", hostworker.parse(["--as"]) == 2 and hostworker.parse(["--cwd"]) == 2)
    check("@fabric/ is replaced at the start of an argument only",
          hostworker.at_fabric(["@fabric/a", "x@fabric/b", "@fabric", "--f=@fabric/c"], "/r") == ["/r/a", "x@fabric/b", "@fabric", "--f=@fabric/c"])
    r = run([WORKER, "--help"])
    check("--help prints the documentation, exit 0", r.returncode == 0 and "worker [--as <login>]" in r.stdout and "Contract" not in r.stdout, r.stdout[:200])

    print("the worker's command that cannot start, and the signals it starts with")
    r = run([WORKER, "--", "no-such-command-xyz"])
    check("not found: 127, said", r.returncode == 127 and "no-such-command-xyz: command not found" in r.stderr, (r.returncode, r.stderr))
    with tempfile.TemporaryDirectory() as tmp:
        plain = os.path.join(tmp, "plain")
        open(plain, "w").close()
        r = run([WORKER, "--", plain])
        check("not executable: 126, said", r.returncode == 126 and "Permission denied" in r.stderr, (r.returncode, r.stderr))
        r = run([WORKER, "--cwd", os.path.join(tmp, "absent"), "--", "true"])
        check("a --cwd that cannot be entered: 1, said", r.returncode == 1 and "worker: cd " in r.stderr, (r.returncode, r.stderr))
        r = run([WORKER, "--cwd", tmp, "--", "pwd"])
        check("--cwd is the command's directory (positive control)", r.returncode == 0 and r.stdout.strip() == os.path.realpath(tmp), r.stdout)
    r = run([WORKER, "--", "grep", "SigIgn", "/proc/self/status"])
    ignored = int(r.stdout.split()[-1], 16) if r.returncode == 0 else -1
    check("the command does not inherit Python's ignored SIGPIPE or SIGXFSZ",
          ignored >= 0 and not ignored & (1 << 12) and not ignored & (1 << 24), r.stdout)
    r = run([WORKER, "--as", "no-such-login-xyz", "--", "true"])
    check("an unknown login: 2, naming it", r.returncode == 2 and "no such login" in r.stderr and "no-such-login-xyz" in r.stderr, (r.returncode, r.stderr))

    print("hostexec: the remote line and the registry")
    words = ["--as", "a b", "--", "printf", "%s|", "it's", 'a"b', "$HOME", "", "a;b", "`x`", "é"]
    line = hostexec.remote_line("/srv/fabric", words)
    check("every word of the remote line comes back whole through a shell's word splitting",
          shlex.split(line) == ["/srv/fabric/runtime/hostexec/worker", *words], shlex.split(line))
    check("a space in the fabric path is quoted as one word", shlex.split(hostexec.remote_line("/a b/f", ["--"]))[0] == "/a b/f/runtime/hostexec/worker")
    check("~ and ~/x in the fabric path are left for the remote shell to expand",
          hostexec.remote_line("~", ["--"]).startswith("~/runtime/hostexec/worker ") and hostexec.remote_line("~/f", ["--"]).startswith("~/f/runtime/"))
    with tempfile.TemporaryDirectory() as tmp:
        reg = os.path.join(tmp, "reg.json")
        with open(reg, "w") as fh:
            json.dump({"hosts": {"h1": {"ssh": None, "operator": "u", "fabric": "/f"}, "h2": {"ssh": "u@h2", "operator": "u", "fabric": "~"},
                                 "bad": {"ssh": None}}}, fh)
        check("a local host resolves", hostexec.load_host(reg, "h1") == ("local", "-", "u", "/f"))
        check("an ssh host resolves with its destination", hostexec.load_host(reg, "h2") == ("ssh", "u@h2", "u", "~"))

        def refused(path: str, host: str) -> str:
            try:
                hostexec.load_host(path, host)
            except hostexec.Refused as e:
                return str(e)
            return ""
        check("an unknown host names the known ones", "unknown host 'zz'" in refused(reg, "zz") and "bad, h1, h2" in refused(reg, "zz"), refused(reg, "zz"))
        check("a host entry without its operator is a refusal, not a KeyError", "lacks its operator or fabric" in refused(reg, "bad"), refused(reg, "bad"))
        check("a missing registry is a refusal", "no host registry at" in refused(os.path.join(tmp, "absent"), "h1"))
        with open(os.path.join(tmp, "x.json"), "w") as fh:
            fh.write("{")
        check("a registry that is not JSON is a refusal, not a traceback", "is not JSON" in refused(os.path.join(tmp, "x.json"), "h1"))
        envr = {**ENV, "AGENT_FABRIC_HOSTS_REGISTRY": reg}
        for argv, want in ((["h1", "--as"], "--as needs a value"), (["h1", "h2", "--", "true"], "one host"), (["--wat"], "unknown flag --wat"),
                           ([], "no host named"), (["h1"], "no command after --")):
            r = run([HX, *argv], env=envr)
            check(f"hostexec {' '.join(argv) or '(nothing)'}: 2, {want!r}", r.returncode == 2 and want in r.stderr and "Traceback" not in r.stderr,
                  (r.returncode, r.stderr))
        r = run([HX, "h2", "--", "true"], env={**envr, "SSH": "no-such-ssh-xyz"})
        check("an ssh that is not installed: 127, said", r.returncode == 127 and "no-such-ssh-xyz: command not found" in r.stderr, (r.returncode, r.stderr))
        r = run([HX, "--help"])
        check("--help prints the documentation, exit 0", r.returncode == 0 and "hostexec <host>" in r.stdout and "Contract" not in r.stdout, r.stdout[:200])

    print("fabric-host")
    reg = {"hosts": {"a": {"platform": "debian", "ssh": None, "operator": "op"}}, "placement": {"x": "a", "y": "a", "z": "gone"}}
    check("list: a host with its sorted accounts, and the placements on an unknown host",
          fabric_host.list_text(reg).splitlines() == [f"{'a':20} {'debian':14} operator {'op':12} this host (direct)",
                                                       "                     accounts: x, y", "placed on an unknown host: z"],
          fabric_host.list_text(reg))
    check("usage is the synopsis block: the title, a blank line and every subcommand, ssh-pin included",
          fabric_host.usage_lines().startswith("bin/fabric-host") and "fabric-host ssh-pin <login>" in fabric_host.usage_lines()
          and "\n\n" in fabric_host.usage_lines() and "Every subcommand" not in fabric_host.usage_lines())
    saved = fabric_host.resolve_registry
    try:
        fabric_host.resolve_registry = lambda: (_ for _ in ()).throw(fabric_host.Refused("cannot resolve the hosts registry (x)", 1))
        r_status = fabric_host.main(["list"])
    finally:
        fabric_host.resolve_registry = saved
    check("a registry that cannot be resolved: 1, never the checkout's file", r_status == 1)
    with tempfile.TemporaryDirectory() as tmp:
        envr = {**ENV, "AGENT_FABRIC_HOSTS_REGISTRY": os.path.join(tmp, "r.json")}
        with open(envr["AGENT_FABRIC_HOSTS_REGISTRY"], "w") as fh:
            json.dump({"hosts": {"h": {"platform": "p", "ssh": None, "operator": "o", "fabric": "/f"}}, "placement": {}}, fh)
        fh_cmd = os.path.join(ROOT, "bin", "fabric-host")
        for argv, want in (([], 2), (["h"], 2), (["h", "moveto"], 2), (["h", "rename", "a", "b"], 2), (["h", "persist"], 2), (["h", "drain"], 2),
                           (["h", "wat"], 2)):
            r = run([fh_cmd, *argv], env=envr)
            check(f"fabric-host {' '.join(argv) or '(nothing)'}: exit {want}, no traceback", r.returncode == want and "Traceback" not in r.stderr, (r.returncode, r.stderr))
        keys = ["ssh-ed25519 AAAA"]
        pinreg = os.path.join(tmp, "pin.json")
        with open(pinreg, "w") as fh:
            json.dump({"hosts": {"h": {"platform": "p", "ssh": None, "operator": "o", "fabric": "/f",
                                       "sshd": {"address": "10.0.0.5", "port": 2222, "host_keys": keys}},
                                 "k": {"platform": "p", "ssh": "op@k", "operator": "o", "fabric": "/f"}},
                       "placement": {"pinned": "h", "unpinned": "k"}}, fh)
        pinenv = {**envr, "AGENT_FABRIC_HOSTS_REGISTRY": pinreg}
        r = run([fh_cmd, "ssh-pin", "pinned"], env=pinenv)
        check("fabric-host ssh-pin: a pinned sshd is `ssh <address> <port>`, exit 0", r.returncode == 0 and r.stdout == "ssh 10.0.0.5 2222\n", (r.returncode, r.stdout, r.stderr))
        r = run([fh_cmd, "ssh-pin", "unpinned"], env=pinenv)
        check("...a host with only the coordinator's `ssh` destination is `sudo`", r.returncode == 0 and r.stdout == "sudo\n", (r.returncode, r.stdout))
        r = run([fh_cmd, "ssh-pin"], env=pinenv)
        check("...no login is a usage error (2)", r.returncode == 2 and "needs the login" in r.stderr, (r.returncode, r.stderr))
        r = run([fh_cmd, "ssh-pin", "a", "b"], env=pinenv)
        check("...two logins too", r.returncode == 2, r.returncode)
        r = run([fh_cmd, "ssh-pin", "pinned"], env={**envr, "AGENT_FABRIC_HOSTS_REGISTRY": os.path.join(tmp, "absent.json")})
        check("...a registry that cannot be read is exit 1, one line, never `sudo`", r.returncode == 1 and r.stdout == "" and "unreadable" in r.stderr and "Traceback" not in r.stderr,
              (r.returncode, r.stdout, r.stderr))
        r = run([fh_cmd, "h", "persist"], env=envr)
        check("persist with no placements on the host is said", "no placements on h" in r.stderr, r.stderr)
        r = run([fh_cmd, "h", "drain", "someone"], env=envr)
        check("drain to a pipe, not a terminal, is accepted far enough to reach hostexec (positive control for the terminal refusal)",
              "redirect it" not in r.stderr, r.stderr)

    print(f"\ntest_hostexec_units: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
