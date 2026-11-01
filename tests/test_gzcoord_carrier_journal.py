#!/usr/bin/env python3
"""tools/fabric/episodic.py's out_final under two carriers (ADR-064 rule 7):
the first carrier to accept sets the row's provenance, name and sequence
together, and a later accept leaves them; a failed row that the other carrier
then accepts takes THAT carrier's provenance; a failure never changes an
accepted row. The journal is a scratch sqlite file, nothing else. Plain script:
prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import episodic  # noqa: E402

fails = 0
MSG = ("[GZCOORD/1] INFO\nFROM: h/me\nROLE: r\nBROADCAST: true\nMESSAGE-ID: {mid}\nSUBJECT: s\n\nCONTEXT:\nx\n")
AGENT_ID = "01a0f782-7e06-7dee-811f-0a860ed93bf3"


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gz-jr-") as d:
        conn = episodic.connect(os.path.join(d, "e.db"), AGENT_ID)

        def row(mid: str):
            return conn.execute("SELECT state, carrier, carrier_seq FROM episodes WHERE message_id=?", (mid,)).fetchone()

        for mid in ("A", "B", "C", "D"):
            episodic.out_pending(conn, MSG.format(mid=mid))
        episodic.out_final(conn, "A", "accepted", 42, "claude-bridge")
        episodic.out_final(conn, "A", "accepted", None, "interweave")
        check("a later accept leaves the first accepter's name and sequence", row("A") == ("accepted", "claude-bridge", 42), str(row("A")))

        episodic.out_final(conn, "B", "accepted", None, "interweave")
        episodic.out_final(conn, "B", "accepted", 7, "claude-bridge")
        check("the first accepter may be InterWeave, and the relay's later accept leaves it",
              row("B") == ("accepted", "interweave", None), str(row("B")))

        episodic.out_final(conn, "C", "failed", None, "claude-bridge")
        check("a failed row is failed", row("C")[0] == "failed")
        episodic.out_final(conn, "C", "accepted", None, "interweave")
        check("a failed row the other carrier then accepts takes that carrier's provenance",
              row("C") == ("accepted", "interweave", None), str(row("C")))

        episodic.out_final(conn, "D", "accepted", 9, "claude-bridge")
        episodic.out_final(conn, "D", "failed", None, "interweave")
        check("a failure never changes an accepted row", row("D") == ("accepted", "claude-bridge", 9), str(row("D")))
        conn.close()

    # The interleaving itself: the other carrier's write lands after out_final
    # has decided and before its UPDATE runs. now() is the last call between
    # the two in both the old and the new shape, so wrapping it makes the
    # interleaving deterministic.
    with tempfile.TemporaryDirectory(prefix="gz-jr-race-") as d:
        path = os.path.join(d, "e.db")
        conn = episodic.connect(path, AGENT_ID)
        other = episodic.connect(path, AGENT_ID)
        for mid in ("R1", "R2"):
            episodic.out_pending(conn, MSG.format(mid=mid))
        real_now = episodic.now

        def after_read(sql: str):
            def hooked():
                episodic.now = real_now
                other.execute(sql)
                return real_now()
            episodic.now = hooked

        try:
            after_read("UPDATE episodes SET state='accepted', carrier='interweave', carrier_seq=5 WHERE message_id='R1'")
            episodic.out_final(conn, "R1", "failed", None, "claude-bridge")
            got = conn.execute("SELECT state, carrier, carrier_seq FROM episodes WHERE message_id='R1'").fetchone()
            check("a failed after a concurrent accept leaves the row accepted", got == ("accepted", "interweave", 5), str(got))

            after_read("UPDATE episodes SET state='accepted', carrier='interweave', carrier_seq=6 WHERE message_id='R2'")
            episodic.out_final(conn, "R2", "accepted", 9, "claude-bridge")
            got = conn.execute("SELECT state, carrier, carrier_seq FROM episodes WHERE message_id='R2'").fetchone()
            check("a second accept after a concurrent first keeps the first carrier and sequence",
                  got == ("accepted", "interweave", 6), str(got))
        finally:
            episodic.now = real_now
        other.close()
        conn.close()
    print(f"\ntest_gzcoord_carrier_journal: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
