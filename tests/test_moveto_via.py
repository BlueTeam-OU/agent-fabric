#!/usr/bin/env python3
"""moveto --via ssh|sudo (ADR-048; job j78) and `fabric-host ssh-pin`, which says which is the default.

moveto's ssh path enters an account through its pinned sshd, whose forced command (enter-ssh) runs `enter`
in the workspace. What is pinned here: the exact ssh argv for each of the four words, the `--` OpenSSH
needs before a word that begins with `-`, the generated known_hosts, the default following the registry
(and degrading to sudo only where there is no registry to ask or an older fabric-host that cannot say),
the refusals (no key, a named clone, no pin for --via ssh), and that --via sudo never touches ssh.
A fake ssh records its argv; a fake getent and sudo place a role account `acct`. Plain script."""
from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from instance_fixtures import own_instance_tree  # noqa: E402

own_instance_tree()
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "runtime", "provisioning", "moveto"))
import fabric_host  # noqa: E402
import moveto  # noqa: E402

SHIM = os.path.join(HERE, "runtime", "provisioning", "moveto", "moveto")
ME = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True, timeout=10).stdout.strip()


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    print("the ssh argv, exactly")
    pin = ("127.0.0.1", 22)
    for mode, word in (("--wait", "--wait"), ("--watch", "--watch"), ("--resume", "--resume"), ("", "shell")):
        want = ["ssh", "-i", "/k", "-o", "IdentitiesOnly=yes", "-o", "UserKnownHostsFile=/kh", "-o", "StrictHostKeyChecking=yes",
                "-t", "acct@127.0.0.1", "--", word]
        check(f"mode {mode or '(none)'} → ... acct@127.0.0.1 -- {word}", moveto.ssh_argv("acct", mode, pin, "/kh", "/k") == want,
              moveto.ssh_argv("acct", mode, pin, "/kh", "/k"))
    check("a port other than 22 adds -p before -t", moveto.ssh_argv("acct", "", ("10.0.0.5", 2222), "/kh", "/k")[8:12] == ["StrictHostKeyChecking=yes", "-p", "2222", "-t"]
          or moveto.ssh_argv("acct", "", ("10.0.0.5", 2222), "/kh", "/k")[9:12] == ["-p", "2222", "-t"])

    print("fabric-host ssh-pin: sshd, never ssh")
    keys = ["ssh-ed25519 AAAA"]
    reg = {"hosts": {"h1": {"ssh": None, "sshd": {"address": "127.0.0.1", "port": 22, "host_keys": keys}},
                     "h2": {"ssh": "op@far", "sshd": None}, "h3": {"ssh": "op@far3"},
                     "h4": {"sshd": {"address": "a", "port": 22, "host_keys": []}},
                     "h5": {"sshd": {"address": "a", "port": True, "host_keys": keys}},
                     "h6": {"sshd": {"address": "", "port": 22, "host_keys": keys}},
                     "h7": {"sshd": {"address": "10.0.0.7", "port": 2222, "host_keys": keys}}},
           "placement": {"a": "h1", "b": "h2", "c": "h3", "d": "h4", "e": "h5", "f": "h6", "g": "h7", "z": "gone"}}
    pins = {k: fabric_host.ssh_pin(reg, k) for k in "abcdefgz"}
    check("a pinned sshd: `ssh <address> <port>`", pins["a"] == "ssh 127.0.0.1 22" and pins["g"] == "ssh 10.0.0.7 2222", pins)
    check("a null sshd, no sshd (the host's `ssh` destination is no pin), no keys, a bool port, an empty address: sudo",
          [pins[k] for k in "bcdef"] == ["sudo"] * 5, pins)
    check("a login placed on an unknown host, or nowhere: sudo", pins["z"] == "sudo" and fabric_host.ssh_pin(reg, "nobody") == "sudo")

    print("moveto, with a fake ssh, fabric-host, fabric-ssh-hosts, getent and sudo")
    with tempfile.TemporaryDirectory() as tmp:
        bin_, home = os.path.join(tmp, "bin"), os.path.join(tmp, "home")
        os.makedirs(bin_)
        os.makedirs(os.path.join(home, ".ssh"))
        open(os.path.join(home, ".ssh", "fabric_deck"), "w").close()
        log = os.path.join(tmp, "calls.log")
        acct_home = os.path.join(tmp, "acct-home")
        os.makedirs(os.path.join(acct_home, "projects", "agent-fabric"))

        def put(name: str, text: str) -> None:
            path = os.path.join(bin_, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(path, 0o755)
        put("ssh", f'#!/bin/sh\nprintf "ssh" >> "{log}"; for a in "$@"; do printf "\\t%s" "$a" >> "{log}"; done; echo >> "{log}"\nexit 0\n')
        put("sudo", f'#!/bin/sh\nprintf "sudo\\t%s\\n" "$*" >> "{log}"\nexit 0\n')
        put("getent", f'#!/bin/sh\n[ "$1" = passwd ] && [ "$2" = acct ] && {{ echo "acct:x:2000:2000::{acct_home}:/bin/bash"; exit 0; }}\nexit 2\n')
        put("fabric-ssh-hosts", '#!/bin/sh\necho "# generated"\necho "127.0.0.1 ssh-ed25519 AAAAfixture"\n')

        def fabric_host_says(answer: str, rc: int = 0, err: str = "") -> None:
            put("fabric-host", f'#!/bin/sh\nprintf "fabric-host\\t%s\\n" "$*" >> "{log}"\n[ -n "{err}" ] && echo "{err}" >&2\necho "{answer}"\nexit {rc}\n')

        env = {"PATH": f"{bin_}:/usr/bin:/bin", "HOME": home, "XDG_STATE_HOME": os.path.join(tmp, "state"), "LANG": "C.UTF-8"}
        if os.environ.get("AGENT_FABRIC_PYTHON"):
            env["AGENT_FABRIC_PYTHON"] = os.environ["AGENT_FABRIC_PYTHON"]

        def mv(*args: str, drop: tuple[str, ...] = ()) -> tuple[int, str, list[list[str]]]:
            open(log, "w").close()
            e = {k: v for k, v in env.items() if k not in drop}
            r = subprocess.run([SHIM, *args], env=e, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
            calls = [ln.split("\t") for ln in open(log, encoding="utf-8").read().splitlines()]
            return r.returncode, r.stdout + r.stderr, calls

        kh = os.path.join(tmp, "state", "fabric-deck", "known_hosts")
        key = os.path.join(home, ".ssh", "fabric_deck")

        def ssh_calls(calls: list[list[str]]) -> list[list[str]]:
            return [c[1:] for c in calls if c[0] == "ssh"]

        fabric_host_says("ssh 127.0.0.1 22")
        for word, flag in (("--wait", ["--wait"]), ("--watch", ["--watch"]), ("--resume", ["--resume"]), ("shell", [])):
            rc, out, calls = mv("acct", "--via", "ssh", *flag)
            want = ["-i", key, "-o", "IdentitiesOnly=yes", "-o", f"UserKnownHostsFile={kh}", "-o", "StrictHostKeyChecking=yes", "-t",
                    "acct@127.0.0.1", "--", word]
            check(f"--via ssh {' '.join(flag) or '(no mode)'}: exactly that argv, once, and no sudo", rc == 0 and ssh_calls(calls) == [want]
                  and not any(c[0] == "sudo" for c in calls), (rc, calls, out))
        check("the known_hosts is what fabric-ssh-hosts printed, private to the account",
              open(kh, encoding="utf-8").read() == "# generated\n127.0.0.1 ssh-ed25519 AAAAfixture\n"
              and stat.S_IMODE(os.stat(kh).st_mode) == 0o600 and stat.S_IMODE(os.stat(os.path.dirname(kh)).st_mode) == 0o700,
              oct(os.stat(kh).st_mode))
        rc, out, calls = mv("acct", "--via=ssh")
        check("--via=ssh spells the same", rc == 0 and len(ssh_calls(calls)) == 1 and ssh_calls(calls)[0][-2:] == ["--", "shell"], (rc, calls))
        rc, out, calls = mv("acct", "--wait")
        check("no --via and a pinned sshd: ssh is the default", rc == 0 and len(ssh_calls(calls)) == 1 and ssh_calls(calls)[0][-1] == "--wait", (rc, calls, out))
        rc, out, calls = mv("acct", "--via", "sudo", "--wait")
        check("--via sudo with a pin: sudo, and ssh is never run", rc == 0 and not ssh_calls(calls) and any(c[0] == "sudo" and "-u acct" in c[1] for c in calls), (rc, calls))
        rc, out, calls = mv("acct", "--print", "--wait")
        check("--print over ssh: the workspace, the account's title, the mode, `via: ssh`, and nothing spawned",
              rc == 0 and out == f"{acct_home}/projects\ntitle: acct\nthen: Enter to activate, then fabric-resume\nvia: ssh\n" and not ssh_calls(calls), (rc, out))

        print("moveto: refusals and the default's other answers")
        rc, out, calls = mv("acct", "--via", "ssh", "agent-fabric")
        check("--via ssh with a named clone: refused, nothing run", rc == 1 and "workspace only" in out and not ssh_calls(calls), (rc, out))
        os.rename(key, key + ".away")
        rc, out, calls = mv("acct", "--via", "ssh")
        check("no operator key: one line naming it and --via sudo, nothing run", rc == 1 and "fabric_deck" in out and "--via sudo" in out and not ssh_calls(calls), (rc, out))
        os.rename(key + ".away", key)
        for argv, want in ((["acct", "--via", "bogus"], "--via takes ssh or sudo"), (["acct", "--via"], "--via takes ssh or sudo"),
                           (["acct", "--via", "ssh", "--via", "sudo"], "one of --via ssh, --via sudo")):
            rc, out, calls = mv(*argv)
            check(f"{' '.join(argv)}: refused, {want!r}", rc == 1 and want in out and not ssh_calls(calls), (rc, out))
        fabric_host_says("sudo")
        rc, out, calls = mv("acct", "--wait")
        check("the registry says sudo: the default is sudo", rc == 0 and not ssh_calls(calls) and any(c[0] == "sudo" for c in calls), (rc, calls))
        rc, out, calls = mv("acct", "--via", "ssh")
        check("--via ssh where the registry has no pin: refused, naming sshd and --via sudo", rc == 1 and "no pinned sshd" in out and "--via sudo" in out and not ssh_calls(calls), (rc, out))
        fabric_host_says("", rc=1, err="fabric-host: the hosts registry is unreadable")
        rc, out, calls = mv("acct", "--wait")
        check("a registry that cannot be read is refused, not read as `no pin`", rc == 1 and "cannot read the registry's ssh pin" in out and not ssh_calls(calls) and not any(c[0] == "sudo" for c in calls), (rc, out, calls))
        fabric_host_says("", rc=2, err="fabric-host: unknown subcommand ssh-pin")
        rc, out, calls = mv("acct", "--wait")
        check("an older fabric-host (usage status 2): sudo, said", rc == 0 and "no ssh-pin" in out and any(c[0] == "sudo" for c in calls) and not ssh_calls(calls), (rc, out, calls))
        os.remove(os.path.join(bin_, "fabric-host"))
        rc, out, calls = mv("acct", "--wait")
        check("no fabric-host on the PATH (nothing to ask): sudo, as before", rc == 0 and any(c[0] == "sudo" for c in calls) and not ssh_calls(calls), (rc, out, calls))
        fabric_host_says("ssh 127.0.0.1 22")
        os.remove(os.path.join(bin_, "fabric-ssh-hosts"))
        rc, out, calls = mv("acct", "--via", "ssh")
        check("no fabric-ssh-hosts: refused naming --via sudo, ssh never run", rc == 1 and "known-hosts" in out and not ssh_calls(calls), (rc, out))
        put("fabric-ssh-hosts", '#!/bin/sh\nexit 1\n')
        rc, out, calls = mv("acct", "--via", "ssh")
        check("a fabric-ssh-hosts that fails: refused, ssh never run", rc == 1 and "no known_hosts" in out and not ssh_calls(calls), (rc, out))
        put("fabric-host", '#!/bin/sh\necho "ssh 127.0.0.1 22"\n')
        put("fabric-ssh-hosts", '#!/bin/sh\necho "127.0.0.1 ssh-ed25519 AAAAfixture"\n')
        rc, out, calls = mv("acct", "--via", "ssh", "--print")
        check("positive control: the same set-up with both tools answering enters", rc == 0 and "via: ssh" in out, (rc, out))

    print(f"\ntest_moveto_via: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
