#!/usr/bin/env python3
"""Tests for tools/fabric/agent_sudo.py: which accounts it covers, what
apply runs and writes (against a scratch sudoers path and a recording
runner, never the real system), that a rule visudo refuses replaces
nothing, and that passwd refuses inside a model session."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(HERE, "tools", "fabric", "agent_sudo.py")
spec = importlib.util.spec_from_file_location("agent_sudo", TOOL)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

NO_GROUP = "agent-sudo-test-no-such-group"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        reg = os.path.join(tmp, "registry.json")
        with open(reg, "w") as fh:
            json.dump({"hosts": {"h1": {"operator": "op"}, "h2": {"operator": "op2"}},
                       "placement": {"op": "h1", "b-dev": "h1", "a-dev": "h1", "far": "h2"}}, fh)
        check("the accounts: this host's placement, sorted, without its operator",
              a.accounts("h1", reg) == ["a-dev", "b-dev"], a.accounts("h1", reg))
        try:
            a.accounts("nowhere", reg)
            check("an unknown host is refused", False)
        except a.SudoError as e:
            check("an unknown host is refused", "not a host" in str(e), e)

        sudoers = os.path.join(tmp, "sudoers.d", "agent-sudo")
        os.makedirs(os.path.dirname(sudoers))
        ran: list[list[str]] = []

        def run(argv):
            ran.append(argv)
        check("plan names every step against a missing group and file",
              a.plan(["a-dev", "b-dev"], NO_GROUP, sudoers) == [f"create group {NO_GROUP}", f"add a-dev to {NO_GROUP}",
                                                               f"add b-dev to {NO_GROUP}", f"write {sudoers}"],
              a.plan(["a-dev", "b-dev"], NO_GROUP, sudoers))
        done = a.apply(["a-dev", "b-dev"], NO_GROUP, sudoers, run)
        check("apply creates the group, adds each account, checks the rule with visudo, writes it",
              [r[0] for r in ran] == ["groupadd", "usermod", "usermod", "visudo"]
              and ran[1] == ["usermod", "-aG", NO_GROUP, "a-dev"] and done[-1] == f"wrote {sudoers}", (ran, done))
        body = open(sudoers).read()
        check("the rule: a password at every sudo, for the group, mode 0440",
              "Defaults:%agent-sudo timestamp_timeout=0\n%agent-sudo ALL=(ALL) ALL\n" in body
              and os.stat(sudoers).st_mode & 0o777 == 0o440, (body, oct(os.stat(sudoers).st_mode)))
        check("check reports a missing group and nothing about a file that is right",
              a.check(["a-dev"], NO_GROUP, sudoers) == [f"no group {NO_GROUP}"], a.check(["a-dev"], NO_GROUP, sudoers))
        ran.clear()
        check("a second write of the same rule writes nothing and runs no visudo",
              a.write_sudoers(sudoers, run) is False and ran == [], ran)

        os.chmod(sudoers, 0o640)
        with open(sudoers, "w") as fh:
            fh.write("%agent-sudo ALL=(ALL) NOPASSWD: ALL\n")

        def refuse(argv):
            raise a.SudoError("visudo: parse error")
        try:
            a.write_sudoers(sudoers, refuse)
            check("a rule visudo refuses is refused", False)
        except a.SudoError:
            check("…and replaces nothing, leaving no temporary file",
                  open(sudoers).read() == "%agent-sudo ALL=(ALL) NOPASSWD: ALL\n" and os.listdir(os.path.dirname(sudoers)) == ["agent-sudo"],
                  os.listdir(os.path.dirname(sudoers)))
        check("check names a rule that differs", f"{sudoers} differs from the rule" in a.check([], NO_GROUP, sudoers))

        try:
            a.set_passwords(["a-dev"], env={"CLAUDECODE": "1"}, run_tty=lambda argv: 0)
            check("passwd refuses inside a model session", False)
        except a.SudoError as e:
            check("passwd refuses inside a model session", "model session" in str(e), e)

    # Where /etc is volatile: the snapshot apply keeps under /rw, and the
    # boot script that puts the group and the rule back, in scratch roots.
    with tempfile.TemporaryDirectory() as tmp:
        etc, snap, rcd = (os.path.join(tmp, d) for d in ("etc", "snap", "rcd"))
        os.makedirs(os.path.join(etc, "sudoers.d"))
        with open(os.path.join(etc, "group"), "w") as fh:
            fh.write("root:x:0:\nagent-sudo:x:1990:a-dev,b-dev\n")
        with open(os.path.join(etc, "gshadow"), "w") as fh:
            fh.write("root:::\nagent-sudo:!::a-dev,b-dev\n")
        done = a.snapshot("agent-sudo", etc, snap, rcd)
        check("snapshot keeps the group's two lines and the rule, root's, and installs the boot script",
              open(os.path.join(snap, "group")).read() == "agent-sudo:x:1990:a-dev,b-dev\n"
              and open(os.path.join(snap, "gshadow")).read() == "agent-sudo:!::a-dev,b-dev\n"
              and os.stat(snap).st_mode & 0o777 == 0o700 and os.stat(os.path.join(snap, "group")).st_mode & 0o777 == 0o600
              and os.access(os.path.join(rcd, a.RC_NAME), os.X_OK) and len(done) == 4, done)
        check("a second snapshot writes nothing", a.snapshot("agent-sudo", etc, snap, rcd) == [])
        check("snapshot_problems: none when the snapshot holds the live lines",
              a.snapshot_problems("agent-sudo", etc, snap, rcd) == [], a.snapshot_problems("agent-sudo", etc, snap, rcd))
        with open(os.path.join(etc, "group"), "w") as fh:
            fh.write("root:x:0:\nagent-sudo:x:1990:a-dev,b-dev,c-dev\n")
        check("…a member joined since: the group's snapshot is stale, said",
              any("group does not hold the live" in x for x in a.snapshot_problems("agent-sudo", etc, snap, rcd)))

        # The boot: a volatile /etc without the group.
        boot = os.path.join(tmp, "boot-etc")
        os.makedirs(os.path.join(boot, "sudoers.d"))
        with open(os.path.join(boot, "group"), "w") as fh:
            fh.write("root:x:0:\n")
        with open(os.path.join(boot, "gshadow"), "w") as fh:
            fh.write("root:::\n")
        fake = os.path.join(tmp, "visudo")
        with open(fake, "w") as fh:
            fh.write("#!/usr/bin/env bash\ngrep -q 'timestamp_timeout=0' \"$2\"\n")
        os.chmod(fake, 0o755)
        rc = os.path.join(rcd, a.RC_NAME)
        env = {**os.environ, "AGENT_FABRIC_SUDO_SNAPSHOT": snap, "AGENT_FABRIC_ETC": boot, "AGENT_FABRIC_VISUDO": fake}
        r = subprocess.run(["bash", rc], env=env, capture_output=True, text=True)
        check("at boot the group and the rule come back, the rule 0440",
              r.returncode == 0 and "agent-sudo:x:1990:a-dev,b-dev" in open(os.path.join(boot, "group")).read()
              and "agent-sudo:!::a-dev,b-dev" in open(os.path.join(boot, "gshadow")).read()
              and "timestamp_timeout=0" in open(os.path.join(boot, "sudoers.d", "agent-sudo")).read()
              and os.stat(os.path.join(boot, "sudoers.d", "agent-sudo")).st_mode & 0o777 == 0o440, r.stderr)
        subprocess.run(["bash", rc], env=env, capture_output=True, text=True)
        check("…a second boot adds nothing twice", open(os.path.join(boot, "group")).read().count("agent-sudo:") == 1)
        clash = os.path.join(tmp, "clash-etc")
        os.makedirs(os.path.join(clash, "sudoers.d"))
        with open(os.path.join(clash, "group"), "w") as fh:
            fh.write("root:x:0:\nother:x:1990:\n")
        r = subprocess.run(["bash", rc], env={**env, "AGENT_FABRIC_ETC": clash}, capture_output=True, text=True)
        check("a gid taken by another group: not re-added, said",
              "agent-sudo" not in open(os.path.join(clash, "group")).read() and "gid 1990 is taken" in r.stderr, r.stderr)
        with open(os.path.join(snap, "sudoers"), "w") as fh:
            fh.write("%agent-sudo ALL=(ALL) NOPASSWD: ALL\n")
        fresh = os.path.join(tmp, "fresh-etc")
        os.makedirs(os.path.join(fresh, "sudoers.d"))
        for f in ("group", "gshadow"):
            with open(os.path.join(fresh, f), "w") as fh:
                fh.write("root:x:0:\n" if f == "group" else "root:::\n")
        r = subprocess.run(["bash", rc], env={**env, "AGENT_FABRIC_ETC": fresh}, capture_output=True, text=True)
        check("a rule visudo refuses is not placed at boot, and nothing is left beside",
              os.listdir(os.path.join(fresh, "sudoers.d")) == [] and "does not pass visudo" in r.stderr, r.stderr)

    p = subprocess.run([sys.executable, TOOL, "wipe"], capture_output=True, text=True)
    check("an unknown command is usage, exit 2", p.returncode == 2 and "usage" in p.stderr, p.stderr)
    if os.geteuid() != 0:
        p = subprocess.run([sys.executable, TOOL, "apply"], capture_output=True, text=True)
        check("apply refuses without root, naming how to run it", p.returncode == 1 and "needs root" in p.stderr, p.stderr)

    print("all passed" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
