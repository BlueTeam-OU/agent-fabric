#!/usr/bin/env python3
"""tools/fabric/history.py (fabric-history) over a scratch journal seeded
through episodic.py: threads both ways, failed sends hidden, filters, the
newest within --limit, cutting, credential masking in both output forms,
the banner, and another agent's journal refused."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(HERE, "tools", "fabric", "history.py")
SHIM = os.path.join(HERE, "bin", "fabric-history")
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
AGENT = "01a0f782-7e06-7dee-811f-0a860ed93bf3"
TOKEN = "ghp_" + "Z" * 30   # credential-shaped, built so this file carries none


def msg(mid: str, body: str, reply: str | None = None, sender: str = "develop-qzapp/peer") -> str:
    return (f"[GZCOORD/1] INFO\nFROM: {sender}\nROLE: x\nTO: develop-qzapp/me\n"
            + (f"IN-REPLY-TO: {reply}\n" if reply else "") + f"MESSAGE-ID: {mid}\nSUBJECT: s\n\nINFO:\n{body}\n")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:600]}"))
        fails += not good

    tmp = tempfile.mkdtemp(prefix="history-")
    try:
        store = os.path.join(tmp, "store")
        os.makedirs(store)
        with open(os.path.join(store, ".agent-id"), "w") as f:
            f.write(AGENT + "\n")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_FABRIC_", "GITHUB_"))}
        env.update(AGENT_FABRIC_STATE_DIR=os.path.join(tmp, "state"), AGENT_FABRIC_SECRET_STORE=store)
        os.environ.update(AGENT_FABRIC_STATE_DIR=env["AGENT_FABRIC_STATE_DIR"], AGENT_FABRIC_SECRET_STORE=store)

        def ids(out: str) -> list[str]:
            """The MESSAGE-ID of each episode heading, oldest first (a
            heading's "(re …)" names another, so never match the text)."""
            return [m.group(1) for m in re.finditer(r"^## \S+ [←→] \S+ (\S+)", out, re.M)]

        def run(*a: str, e: dict | None = None) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, TOOL, *a], env=e or env, capture_output=True, text=True, timeout=60)

        r = run()
        check("no journal yet: said, exit 1", r.returncode == 1 and "no journal yet" in r.stderr, r.stderr)

        import episodic as ep
        conn = ep.connect()
        ins = lambda recs: ep.inbound(conn, recs, project="agent-fabric")  # noqa: E731
        ins([{"content": msg("q-1", "a question about the pin"), "seq": 1, "ts": "2026-10-01T09:00:00Z"}])
        ep.out_pending(conn, msg("a-1", "the answer", reply="q-1", sender=ep.own_address()), project="agent-fabric")
        ep.out_final(conn, "a-1", "accepted", 2)
        ins([{"content": msg("f-1", "a follow-up", reply="a-1"), "seq": 3, "ts": "2026-10-01T11:00:00Z"}])
        ins([{"content": msg("x-1", "unrelated, other project"), "seq": 4, "ts": "2026-10-01T12:00:00Z"}])
        conn.execute("UPDATE episodes SET project='gzapp' WHERE message_id='x-1'")
        ep.out_pending(conn, msg("lost-1", "never got out", sender=ep.own_address()))
        ep.out_final(conn, "lost-1", "failed")
        ins([{"content": msg("s-1", f"the token is {TOKEN} keep it"), "seq": 5, "ts": "2026-10-01T13:00:00Z"}])
        ins([{"content": msg("long-1", "x" * 2000), "seq": 6, "ts": "2026-10-01T14:00:00Z"}])
        conn.close()

        r = run("--limit", "50")
        check("the banner comes first", r.returncode == 0 and r.stdout.startswith("# history, not current truth"), r.stdout[:200])
        check("a failed send is hidden by default", "lost-1" not in r.stdout and "q-1" in r.stdout)
        check("…and shown with --include-failed", "lost-1 [failed]" in run("--include-failed", "--limit", "50").stdout)
        heads = ids(r.stdout)
        check("oldest first", heads.index("q-1") < heads.index("f-1") < heads.index("long-1"), heads)

        t = run("--thread", "a-1").stdout
        check("a thread walks IN-REPLY-TO both ways from the middle",
              sorted(ids(t)) == ["a-1", "f-1", "q-1"] and "(re q-1)" in t, ids(t))
        check("text filter, case-insensitive", ids(run("THE PIN").stdout) == ["q-1"], ids(run("THE PIN").stdout))
        check("project filter", ids(run("--project", "gzapp").stdout) == ["x-1"])
        check("--since", "q-1" not in ids(run("--since", "2026-10-01T10:00:00Z").stdout))
        # The outbound a-1 is stamped with the real time, so it is the newest.
        lim = ids(run("--limit", "2").stdout)
        check("--limit keeps the newest", lim == ["long-1", "a-1"], lim)
        check("a long message is cut, and says how to see it", "more characters: --full" in run("long-1").stdout
              and "more characters" not in run("long-1", "--full").stdout)

        s, j = run("token").stdout, run("token", "--json").stdout
        check("a credential-shaped value is withheld, by kind and episode",
              TOKEN not in s and "[withheld: credential" in s, s)
        check("…in --json too", TOKEN not in j and "withheld" in json.loads(j)["episodes"][0]["content"], j[:300])
        check("--json carries the banner", json.loads(j)["banner"].startswith("history, not current truth"))

        other = os.path.join(tmp, "other-store")
        os.makedirs(other)
        with open(os.path.join(other, ".agent-id"), "w") as f:
            f.write("01a0f7ea-15b0-7ed9-a176-6eb006592db1\n")
        r = run(e={**env, "AGENT_FABRIC_SECRET_STORE": other})
        check("another agent's journal is refused", r.returncode == 1 and "belongs to agent" in r.stderr, r.stderr)
        r = subprocess.run(["bash", SHIM, "--limit", "1"], env=env, capture_output=True, text=True, timeout=60)
        check("the shim runs it", r.returncode == 0 and "1 episode(s)" in r.stdout, r.stderr)
        check("usage: --limit 0 refused", run("--limit", "0").returncode == 2)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
