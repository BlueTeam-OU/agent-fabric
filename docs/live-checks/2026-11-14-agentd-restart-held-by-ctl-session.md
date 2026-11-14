# 2026-11-14: agentd's restart held by an open fabric-ctl session

**Why.** On 2026-11-13 at 21:57 a `fabric-ctl all upgrade fabric`
upgraded the operator's own account, and its agentd left for new code
("source changed") while the command was still collecting the other
accounts' replies. `control_link.py` reported that the daemon closed the
connection, and the relay carried the rest. With control on InterWeave
alone, those replies would have been lost (j852, blocking j814).
python-dev-02's BlueTeam-OU/agent-fabric#594 (j146, merged 06:26Z)
makes an open socket session hold the restart, up to `HOLD_MAX_S`. Its
tests run in the suite; this is the read-back on the operator's own,
running daemon. It decides whether j852 is closed.

**What ran.** On develop-qzapp, as `user` (fabric-coordinator, the
operator), against the fleet on origin/main `441ebcd7` (which contains
#594), `control_carrier` `dual`. The operator's agentd unit runs from
`/home/user/projects/agent-fabric` (`AGENT_FABRIC_ROOT` in its
environment). Its source watch compares each loaded module's mtime,
size and inode, polls every 1 s and waits 2 s for quiet
(`WATCH_POLL_S`, `QUIET_S`), so a `touch` of a loaded module asks for a
restart without changing any code.

**Measured.**

| run | what | result |
|---|---|---|
| upgrade 07:23Z | the distribution of #594, `fabric-ctl all upgrade fabric` | 30 rows; 29 peers by InterWeave, the operator's own row by relay. The operator's own upgrade took 65 s and answered last, at 07:24:01Z, after the last InterWeave reply (07:23:50Z): the race did not happen |
| upgrade 08:01Z | a second fleet upgrade, every daemon on #594 | the same: 29 by InterWeave between 08:01:14Z and 08:01:29Z, own exit at 08:01:44Z ("the fabric moved (upgrade fabric)"), after them. Not an exercise of the hold either |
| drill 1, 08:10:45Z | `fabric-ctl all status`, `touch` 1.7 s in | inconclusive: the restart was asked about 2–3 s after the touch, and the daemon left at 08:10:50.62Z, inside the window in which it would have left with no hold |
| drill 2, 08:11:31Z | `touch` of `tools/fabric/gzcoord/carrier/control_link.py`, then `fabric-ctl all status` at once | touch 08:11:31.89Z, so the restart was asked by about 08:11:34.9Z; the 29 peers' replies arrived by InterWeave at 08:11:52Z; agentd logged "source changed; exiting" at 08:11:53.47Z; `fabric-ctl` ended at 08:11:53.60Z, exit 0, 30 rows `ok` |

In drill 2 the daemon stayed for 18.6 s after it was asked to leave,
and left as the session ended. Every InterWeave reply came in that
window. Without the hold the daemon would have left around 08:11:35Z,
and those 29 replies would have reached no listener.

**The operator's own row** comes by relay in every run (628 of 628 of
its own replies since 2026-11-12, by `control-arrivals.jsonl`): agentd
does not send a reply to its own account over InterWeave ("not sent:
this account (the relay carries it)"). That is a separate question for
the InterWeave-only cutover, not this defect.

**The "is not reading … dropped" lines** that follow each fleet command
in the operator's agentd journal (134 since 2026-11-13) are InterWeave
copies arriving after `fabric-ctl` had kept the relay copy and closed.
For request 01a1d915 (08:04Z, `identity`), the relay reply reached
`fabric-ctl` at 08:04:17Z and the InterWeave copy reached agentd at
08:04:27Z. These are late duplicates while running dual, not losses.

**Not measured.** Drill 2 ran with the relay up. The relay-down case
(InterWeave as the only carrier) is `tests/test_control_dual.py`'s
fleet ping from #594. The held exit path is the same, because the
hold is taken on the socket whichever carrier delivers. The
`HOLD_MAX_S` cap was not reached live; `tests/test_control_agentd_dual.py`
covers it.

**Decides.** j852 is closed: an operator's own restart during a fleet
command no longer cuts off the InterWeave leg. ADR-029 rule 18 is
amended to say so (A 2026-11-14).
