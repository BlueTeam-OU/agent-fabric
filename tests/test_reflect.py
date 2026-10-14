#!/usr/bin/env python3
"""tools/fabric/reflect.py (fabric-reflect) over a scratch journal seeded
through episodic.py: own journal only, credential withholding in both forms,
grouping (chains, then subject), the bound and its "left for the next pass"
line, and the cursor — moved by `done` only, so an unfinished pass reads the
same messages again."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(HERE, "tools", "fabric", "reflect.py")
SHIM = os.path.join(HERE, "bin", "fabric-reflect")
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
AGENT = "01a0f782-7e06-7dee-811f-0a860ed93bf3"
TOKEN = "ghp_" + "Z" * 30   # credential-shaped, built so this file carries none


def msg(mid: str, body: str, reply: str | None = None, sender: str = "develop-qzapp/peer",
        to: str = "develop-qzapp/me", subject: str = "s") -> str:
    return (f"[GZCOORD/1] INFO\nFROM: {sender}\nROLE: x\nTO: {to}\n"
            + (f"IN-REPLY-TO: {reply}\n" if reply else "") + f"MESSAGE-ID: {mid}\nSUBJECT: {subject}\n\nINFO:\n{body}\n")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:600]}"))
        fails += not good

    tmp = tempfile.mkdtemp(prefix="reflect-")
    try:
        store = os.path.join(tmp, "store")
        os.makedirs(store)
        with open(os.path.join(store, ".agent-id"), "w") as f:
            f.write(AGENT + "\n")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_FABRIC_", "GITHUB_"))}
        env.update(AGENT_FABRIC_STATE_DIR=os.path.join(tmp, "state"), AGENT_FABRIC_SECRET_STORE=store)
        os.environ.update(AGENT_FABRIC_STATE_DIR=env["AGENT_FABRIC_STATE_DIR"], AGENT_FABRIC_SECRET_STORE=store)

        def run(*a: str, e: dict | None = None) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, TOOL, *a], env=e or env, capture_output=True, text=True, timeout=60)

        def ids(out: str) -> list[str]:
            return [m.group(1) for m in re.finditer(r"^## \S+ [←→] \S+ \S+ (\S+)", out, re.M)]

        r = run()
        check("no journal yet: said, exit 1", r.returncode == 1 and "no journal yet" in r.stderr, r.stderr)

        import episodic as ep
        conn = ep.connect()
        me = ep.own_address()
        ins = lambda recs: ep.inbound(conn, recs, project="agent-fabric")  # noqa: E731
        ins([{"content": msg("q-1", "a question about the pin", subject="pin"), "seq": 1, "ts": "2026-10-01T09:00:00Z"}])
        ep.out_pending(conn, msg("a-1", "the answer", reply="q-1", sender=me, to="develop-qzapp/peer", subject="Re: pin"))
        ep.out_final(conn, "a-1", "accepted", 2)
        ins([{"content": msg("f-1", "a follow-up", reply="a-1", subject="Re: pin"), "seq": 3, "ts": "2026-10-01T11:00:00Z"}])
        ins([{"content": msg("n-1", "first note", subject="release"), "seq": 4, "ts": "2026-10-01T12:00:00Z"}])
        ins([{"content": msg("n-2", "second note", subject="release"), "seq": 5, "ts": "2026-10-01T12:30:00Z"}])
        ep.out_pending(conn, msg("lost-1", "never got out", sender=me))
        ep.out_final(conn, "lost-1", "failed")
        ins([{"content": msg("s-1", f"the token is {TOKEN} keep it", subject="secret"), "seq": 6, "ts": "2026-10-01T13:00:00Z"}])
        ins([{"content": msg("long-1", "x" * 2000, subject="long"), "seq": 7, "ts": "2026-10-01T14:00:00Z"}])
        ins([{"content": msg("r-1", "a reply", reply=TOKEN, subject="tok"), "seq": 8, "ts": "2026-10-01T15:00:00Z"}])
        conn.close()

        r = run("--max", "100")
        out = r.stdout
        check("a pass reads, exit 0, banner first", r.returncode == 0 and out.startswith("# your own messages, history not current truth"), r.stderr + out[:200])
        check("every message once, a failed send tagged",
              sorted(ids(out)) == sorted(["q-1", "a-1", "f-1", "n-1", "n-2", "lost-1", "s-1", "long-1", "r-1"])
              and "lost-1 [failed]" in out, ids(out))
        check("direction, peer and date shown",
              "2026-10-01T09:00:00Z ← develop-qzapp/peer INFO q-1" in out and "→ develop-qzapp/peer INFO a-1" in out, out[:600])
        check("an IN-REPLY-TO chain is one thread, in order",
              ids(out)[:3] == ["q-1", "a-1", "f-1"] and out.count("### pin") == 1 and "### Re: pin" not in out, out[:900])
        check("messages in no chain group by subject", out.count("### release") == 1
              and ids(out).index("n-2") == ids(out).index("n-1") + 1, out)
        check("a long body is cut and says how to read it", "more characters: fabric-history --thread long-1 --full" in out)
        check("--full does not cut", "more characters" not in run("--full").stdout)
        check("a credential-shaped value is withheld, by kind and episode",
              TOKEN not in out and "[withheld: credential" in out, out)
        check("…including a credential-shaped IN-REPLY-TO", "(re [withheld: credential" in out)

        j = run("--json")
        d = json.loads(j.stdout)
        flat = [m for t in d["threads"] for m in t]
        check("--json: same messages, withheld, never cut, with through/left",
              TOKEN not in j.stdout and len(flat) == 9 and d["left"] == 0 and isinstance(d["through"], int)
              and any(len(m["content"]) > 2000 for m in flat), j.stdout[:300])
        check("--json is a pass too: the cursor did not move", run("status").stdout.startswith("cursor: row 0"))

        broken = os.path.join(tmp, "broken-fabric")
        os.makedirs(os.path.join(broken, "policies"))
        with open(os.path.join(broken, "policies", "hygiene.json"), "w") as f:
            f.write("{not json")
        r = run(e={**env, "AGENT_FABRIC_ROOT": broken})
        check("a broken hygiene list: refused in one line, nothing shown",
              r.returncode == 1 and r.stdout == "" and "Traceback" not in r.stderr and "hygiene" in r.stderr, r.stderr[-300:])

        # The bound, and the cursor that only `done` moves.
        r1 = run("--max", "3")
        check("the bound: 3 shown, 6 left for the next pass", len(ids(r1.stdout)) == 3 and "6 more message(s) wait for the next pass" in r1.stdout, r1.stdout[-300:])
        again = run("--max", "3")
        check("an unfinished pass is read again, identically", ids(again.stdout) == ids(r1.stdout) and again.stdout == r1.stdout)
        st = run("status")
        check("status: no pass closed, 9 wait", "no pass closed yet" in st.stdout and "9 message(s) wait" in st.stdout, st.stdout)
        through = json.loads(run("--max", "3", "--json").stdout)["through"]
        h1 = re.search(r"run `fabric-reflect done --through (\d+)`", r1.stdout)
        check("the printed hint closes exactly the pass shown, whatever --max the done has (review of #256)",
              h1 is not None and int(h1.group(1)) == through, r1.stdout[-300:])
        d1 = run("done", *h1.group(0)[len("run `fabric-reflect done"):-1].split())
        check("done closes the pass", d1.returncode == 0 and f"through row {through}" in d1.stdout, d1.stdout + d1.stderr)
        with open(os.path.join(env["AGENT_FABRIC_STATE_DIR"], "agents", subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip(), "reflect-cursor.json")) as f:
            cur = json.load(f)
        check("the cursor records the row, the owner, no message id", cur["row"] == through and cur["agent_id"] == AGENT
              and "message_id" not in cur and "q-1" not in json.dumps(cur), cur)
        # The hint of a pass that fits names its row; a placeholder would be pasted as is (review of #256).
        fit = run("--max", "100").stdout
        check("the hint of a pass that fits names its row, no placeholder",
              re.search(r"`fabric-reflect done --through \d+` closes", fit) is not None and "{through}" not in fit, fit[-300:])
        r2 = run("--max", "3")
        check("the next pass starts after it", not set(ids(r2.stdout)) & set(ids(r1.stdout)) and "3 more message(s)" in r2.stdout, r2.stdout[-300:])
        # The hint a pass prints closes exactly that pass (review of #256, finding 2).
        check("done never moves the cursor back", "nothing to close" in run("done", "--through", "1").stdout)
        check("done with no --through closes the first --max", "closed through" in run("done", "--max", "100").stdout
              and "nothing waits since the last pass" in run().stdout)
        check("…and again with nothing waiting is a no-op", "nothing to close" in run("done").stdout)

        # A message that arrives after the cursor is read by the next pass.
        conn = ep.connect()
        ep.inbound(conn, [{"content": msg("late-1", "later", subject="late"), "seq": 9, "ts": "2026-10-02T09:00:00Z"}], project="agent-fabric")
        conn.close()
        check("a later message is the next pass", ids(run().stdout) == ["late-1"])

        # Refusals.
        check("done --through a row that does not exist", run("done", "--through", "9999").returncode == 1)
        check("--through belongs to done", run("--through", "2").returncode == 2)
        check("usage: --max 0 refused", run("--max", "0").returncode == 2)
        cpath = os.path.join(env["AGENT_FABRIC_STATE_DIR"], "agents", subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip(), "reflect-cursor.json")
        with open(cpath, "w") as f:
            f.write("{torn")
        r = run()
        check("an unreadable cursor is refused, not read as none", r.returncode == 1 and r.stdout == "" and "unreadable" in r.stderr, r.stderr)
        with open(cpath, "w") as f:
            json.dump({"agent_id": AGENT, "row": 999, "episode": "x"}, f)
        r = run("status")
        check("a cursor past the end of the journal is refused", r.returncode == 1 and "ends at row" in r.stderr, r.stderr)
        with open(cpath, "w") as f:
            json.dump({"agent_id": "01a0f7ea-15b0-7ed9-a176-6eb006592db1", "row": 1, "episode": "x"}, f)
        r = run()
        check("a cursor written for another agent id is refused", r.returncode == 1 and "belongs to agent" in r.stderr, r.stderr)
        with open(cpath, "w") as f:
            json.dump({"agent_id": AGENT, "row": 2, "episode": "not-the-episode-at-row-2"}, f)
        r = run()
        check("a cursor whose episode is not at its row is refused (restored journal)", r.returncode == 1 and "does not match" in r.stderr, r.stderr)
        os.unlink(cpath)

        other = os.path.join(tmp, "other-store")
        os.makedirs(other)
        with open(os.path.join(other, ".agent-id"), "w") as f:
            f.write("01a0f7ea-15b0-7ed9-a176-6eb006592db1\n")
        r = run(e={**env, "AGENT_FABRIC_SECRET_STORE": other})
        check("another agent's journal is refused", r.returncode == 1 and "belongs to agent" in r.stderr and r.stdout == "", r.stderr)
        r = subprocess.run(["bash", SHIM, "status"], env=env, capture_output=True, text=True, timeout=60)
        check("the shim runs it", r.returncode == 0 and "message(s) wait" in r.stdout, r.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
