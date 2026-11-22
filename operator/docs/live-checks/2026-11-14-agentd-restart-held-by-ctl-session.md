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
| upgrade 07:22:56Z | the distribution of #594, `fabric-ctl all upgrade fabric` | 30 rows; 29 peers by InterWeave, the operator's own row by relay. The operator's own upgrade ran 07:22:56Z–07:24:01Z (65 s, agentd's journal) and answered last, after the last InterWeave reply (07:23:50Z): the race did not happen |
| upgrade 08:01Z | a second fleet upgrade, every daemon on #594 | the same: 29 by InterWeave between 08:01:14Z and 08:01:29Z, own exit at 08:01:44Z ("the fabric moved (upgrade fabric)"), after them. Not an exercise of the hold either |
| drill 1, 08:10:44.99Z | `fabric-ctl all status`, `touch` at 08:10:46.71Z | the command lasted 5.8 s (it ended at 08:10:50.81Z). The restart was asked 2–3 s after the touch (08:10:48.7–49.7Z); agentd left at 08:10:50.62Z, 0.19 s before `fabric-ctl` ended: held 0.9–1.9 s, to the session's end. A short hold, weak on its own |
| drill 2, 08:11:31Z | `touch` of `tools/fabric/gzcoord/carrier/control_link.py`, then `fabric-ctl all status` at once | touch 08:11:31.89Z, so the restart was asked by about 08:11:34.9Z; the 29 peers' replies arrived by InterWeave at 08:11:52Z; agentd logged "source changed; exiting" at 08:11:53.47Z; `fabric-ctl` ended at 08:11:53.60Z, exit 0, 30 rows `ok` |

In drill 2 the daemon stayed 18.6–19.6 s after it was asked to leave
(the ask fell between 08:11:33.9Z and 34.9Z: up to `WATCH_POLL_S` to
see the touch, then `QUIET_S`), and left as the session ended. Every
InterWeave reply came in that window. Without the hold the daemon would have left by 08:11:35Z,
and those 29 replies would have reached no listener. Neither drill's
journal has the line a session opened with a restart already pending
logs ("opened with a restart pending: it holds nothing"), so in both
the session held from its start.

**The operator's own row** comes by relay in every run (628 of 628 of
its own replies since 2026-11-12, by `control-arrivals.jsonl`): agentd
does not send a reply to its own account over InterWeave ("not sent:
this account (the relay carries it)"). That is a separate question for
the InterWeave-only cutover, not this defect.

**The "is not reading … dropped" lines** in the operator's agentd
journal (134 since 2026-11-13) are not explained here. They are not the
late copies: for request 01a1d915-9176 (`identity`, 08:04Z), the
InterWeave copies that came after `fabric-ctl` had kept the relay ones
are logged in `control-arrivals.jsonl` as `no-waiter` (28 rows). The
"is not reading" lines at 08:04:27–29Z belong to a request whose
session was still open. No drill produced one. They are a separate
job, not this defect.

**Not measured.** Drill 2 ran with the relay up. The relay-down case
(InterWeave as the only carrier) is `tests/test_control_dual.py`'s
fleet ping from #594. The held exit path is the same, because the
hold is taken on the socket whichever carrier delivers. The
`HOLD_MAX_S` cap was not reached live, and no session opened with a
restart already pending; `tests/test_control_agentd_dual.py` covers
both.

**Decides.** j852 is closed: an operator's own restart during a fleet
command no longer cuts off the InterWeave leg. ADR-029 rule 18 is
amended to say so (A 2026-11-14).
