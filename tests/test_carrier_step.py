#!/usr/bin/env python3
"""tools/fabric/provisioning/carrier_step.py and account_carrier.py: steps 7c-7e of a new-agent run
(the relay-free cutover's W14). The CLI suite (test_new_agent_cli.py) runs the whole sequence; this one
pins each step's failure classes against a stub worker: a failed install, a roster-row that fails or prints
what is not a row, no user manager, a unit or carrier start that fails, and the account-side reply-to-exit mapping.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import io
import json
import os
import stat
import socket
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord.carrier import admit  # noqa: E402
from provisioning import account_carrier, carrier_step  # noqa: E402

fails = 0


def ok(label: str, good: bool, detail: str = "") -> None:
    global fails
    print(f"  {'ok  ' if good else 'FAIL'} {label}")
    if not good and detail:
        print("      " + detail.replace("\n", "\n      "))
    fails += not good


class Dead(Exception):
    pass


class Stub:
    """A Worker with the account's commands answered from a table: the first entry whose words all occur in the argv."""
    def __init__(self, tmp: str, answers: dict[str, tuple[int, str]], dry: bool = False, manager: bool = True) -> None:
        self.a = SimpleNamespace(login="scratch-login", dry=dry)
        self.home, self.py = "/home/scratch-login", "py"
        self.env = {"XDG_STATE_HOME": f"{tmp}/state", "AGENT_FABRIC_RUN_USER": f"{tmp}/run"}
        self.answers, self.manager, self.said, self.ran = answers, manager, [], []

    def say(self, text: str) -> None:
        self.said.append(text)

    def die(self, text: str) -> None:
        self.said.append(text)
        raise Dead(text)

    def sudo_test(self, flag: str, path: str) -> bool:
        return self.manager and flag == "-S"

    def as_login(self, argv, *, login_shell=True, env=None, stderr=None, **kw):
        self.ran.append((argv, env))
        for key, (rc, out) in self.answers.items():
            if all(w in " ".join(argv) for w in key.split()):
                return subprocess.CompletedProcess(argv, rc, out, out if stderr == subprocess.PIPE else None)
        return subprocess.CompletedProcess(argv, 0, "", None)


def run(fn, w):
    try:
        return fn(w), None
    except Dead as e:
        return None, str(e)


def main() -> int:
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
        # getent is the real one: the uid of the user running the test, under a name it knows.
        me = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()

        def stub(answers, **kw):
            w = Stub(tmp, answers, **kw)
            w.a.login = me
            return w
        print("carrier_step: install (7c)")
        w = stub({"account_carrier install": (1, '{"status": "failed", "reason": "no GH_TOKEN"}')})
        _, died = run(carrier_step.install, w)
        ok("a failed install stops the run, said with the reason's line", died is not None and "step failed" in died
           and any("no GH_TOKEN" in s for s in w.said), str(w.said))
        w = stub({"account_carrier install": (0, '{"status": "current"}')})
        run(carrier_step.install, w)
        ok("a release already there is said as such", "7c. carrier release already installed" in w.said, str(w.said))

        print("carrier_step: the roster row (7d)")
        w = stub({"render-config": (2, "")})
        open_, died = run(carrier_step.roster_row, w)
        ok("a row that is not valid and cannot be written stops the run", died and "roster-row" in died, str(w.said))
        w = stub({"render-config": (2, ""), "roster-row": (0, "not json")})
        _, died = run(carrier_step.roster_row, w)
        ok("…and so does an answer that is not a row", died is not None)
        w = stub({"render-config": (2, ""), "roster-row": (2, "refused: the lineage and identities/keys on origin/main hold no key for agent 01a\n")})
        open_, died = run(carrier_step.roster_row, w)
        ok("a roster-row refusal (the key not on origin/main yet) leaves the run open with the carrier's own words, not failed",
           died is None and open_ and "refused" in open_[0] and "hold no key for agent 01a" in open_[0]
           and "re-run" in open_[0], f"{open_} {died}")
        w = stub({"render-config": (2, ""), "roster-row": (2, "refused: transportctl does not match the pinned digest\n")})
        _, died = run(carrier_step.roster_row, w)
        ok("…and any other refusal of it (a program that is not the release's) is a failed step: merging keys would not fix it",
           died and "exit 2" in died and any("pinned digest" in s for s in w.said), str(w.said))
        class NoKeys:   # a lineage without the agent: what a first run of a new login meets
            def lineage(self): return {}
            def public_key(self, agent_id): return None
        try:
            admit._committed(NoKeys(), "01a")
            said_by_carrier = ""
        except admit.AdmitError as e:
            said_by_carrier = str(e)
        ok("the phrase 7d opens on is the one the carrier's own refusal says (reworded there, the first run would fail)",
           carrier_step.NO_KEY_REFUSAL in said_by_carrier, said_by_carrier)
        w = stub({"render-config": (2, ""), "roster-row": (1, "Traceback: boom\n")})
        _, died = run(carrier_step.roster_row, w)
        ok("…while any other failure of roster-row (a crash) stays a failed step, with its last line said",
           died and "exit 1" in died and any("boom" in s for s in w.said), str(w.said))
        row = {"agent_id": "01a-x", "login": me, "peer_id": "12D3KooWx"}
        w = stub({"render-config": (2, ""), "roster-row": (0, json.dumps(row))})
        open_, died = run(carrier_step.roster_row, w)
        path = carrier_step.row_file(w)
        ok("a row the coordinator has not countersigned is written 0644 and left open, with the command to sign",
           died is None and open_ and f"roster-admit {path} --port" in open_[0] and f"{path} on {socket.gethostname().split('.')[0]}" in open_[0] and json.load(open(path, encoding="utf-8")) == row
           and stat.S_IMODE(os.stat(path).st_mode) == 0o644, f"{open_} {died}")
        ok("…and never signed by this module: the account's calls are render-config and roster-row only",
           [a[0][-1] for a in w.ran] == ["render-config", "roster-row"], str(w.ran))
        w = stub({"render-config": (0, "")})
        ok("a valid row leaves nothing open and writes nothing", run(carrier_step.roster_row, w)[0] == [], str(w.said))

        print("carrier_step: agentd and the carrier (7e)")
        w = stub({}, manager=False)
        open_, died = run(carrier_step.start, w)
        ok("no user manager is open, said with linger, and nothing was started", died is None and open_
           and "enable-linger" in open_[0] and w.ran == [], f"{open_} {w.ran}")
        w = stub({"systemctl": (1, "Failed to connect to bus")})
        _, died = run(carrier_step.start, w)
        ok("a unit that cannot be enabled stops the run before the carrier", died and "enable --now" in died
           and not any("account_carrier" in " ".join(a[0]) for a in w.ran), str(w.said))
        w = stub({"account_carrier start": (1, '{"status": "refused", "reason": "no row"}')})
        _, died = run(carrier_step.start, w)
        ok("a carrier start the action refuses stops the run", died and "account_carrier.py start" in died, str(w.said))
        w = stub({})
        open_, died = run(carrier_step.start, w)
        ok("started: agentd first, both commands in the account's manager (XDG_RUNTIME_DIR and the bus), nothing open",
           open_ == [] and "systemctl" in w.ran[0][0] and "account_carrier.py" in w.ran[1][0][2]
           and all(e and e[0].startswith("XDG_RUNTIME_DIR=") and e[1].startswith("DBUS_SESSION_BUS_ADDRESS=unix:path=") for _, e in w.ran),
           str(w.ran))
        w = stub({"render-config": (0, "")})
        run(carrier_step.carrier_steps, w)
        inst = [e for a, e in w.ran if "account_carrier.py" in " ".join(a) and "install" in a]
        ok("the install runs in the account's user manager (XDG_RUNTIME_DIR and the bus), as agentd's own does",
           len(inst) == 1 and inst[0] and inst[0][0].startswith("XDG_RUNTIME_DIR=") and inst[0][1].startswith("DBUS_SESSION_BUS_ADDRESS="), str(w.ran))
        w = stub({}, dry=True)
        ok("a dry run says what it would do and runs nothing", run(carrier_step.carrier_steps, w)[0] == []
           and w.ran == [], str(w.ran))

        w = stub({"render-config": (2, ""), "roster-row": (0, json.dumps(row))})
        open_, _ = run(carrier_step.carrier_steps, w)
        ok("an open row ends the steps: nothing of 7e ran (no systemctl, no start)", open_
           and not any("systemctl" in " ".join(a[0]) or "start" in a[0] for a in w.ran), str(w.ran))

        print("account_carrier: the reply is the exit status")
        from control import carrier_install as ci
        real = (ci.carrier_install, ci.carrier_start)
        try:
            for verb, status, rc in (("install", "installed", 0), ("install", "current", 0), ("install", "failed", 1),
                                     ("install", "refused", 1), ("start", "started", 0), ("start", "failed", 1),
                                     ("start", "current", 1)):      # "current" is not a start's answer: unknown stays unknown
                reply = {"status": status}
                ci.carrier_install = ci.carrier_start = lambda request, _r=reply: _r
                buf = io.StringIO()
                with redirect_stdout(buf):
                    got = account_carrier.main([verb])
                ok(f"{verb} -> {status}: exit {rc}, the reply one JSON line", got == rc and json.loads(buf.getvalue()) == reply, buf.getvalue())
        finally:
            ci.carrier_install, ci.carrier_start = real
        err = io.StringIO()
        with redirect_stderr(err):
            ok("anything but install|start is usage, exit 2", account_carrier.main(["stop"]) == 2 and account_carrier.main([]) == 2)
    print(f"{'FAILED' if fails else 'ok'}: {fails} check(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
