# Carrier give-up waves of 11-15 and 11-18, and the idle sessions left deaf — 2026-11-22

*Host develop-qzapp, account `user` (fabric-coordinator), job j1015, with
python-dev-01's measurement for j266 (BlueTeam-OU/agent-fabric#686). Every
account ran fabric `4f5b61d5` (`fabric-ctl all fabric`) when this was read,
on 11-22 and again on 11-23. The claim covers the watch logs as `fabric-ctl
all interweave-evidence` returned them on 11-22, and for the fourth window
on 11-23, and the panes as they stood.*

## What the job said, and what the logs say instead

j1015 was opened on 11-21 as "eight idle sessions deaf after exit 5 at about
11-20 22:30". No watch on any of the 30 accounts ended with exit 5 between
2026-11-19T00:00Z and 2026-11-21T12:00Z, so none gave up at 11-20 22:30Z.
The date in the title was wrong. The give-ups happened on 11-15 and 11-18. python-dev-01's record on #686
repeated the 11-20 date from the request. Its fix does not depend on the date.

## What was measured

`fabric-ctl all interweave-evidence` was run over three windows:
11-15T00Z–11-19T00Z, 11-19T00Z–11-21T12Z and 11-21T12Z–11-22T18:40Z, and on
11-23 over a fourth, 11-22T18:40Z–19:10Z, for the restarts of 19:01–19:03Z. Each
account's `gzcoord-watch.jsonl` writes a `start` line and an `end` line with a
code and a reason. A watch killed outright writes no `end`.

**Give-up waves (`end`, code 5, `gave-up`), every account:**

| when (Z) | accounts | primary then |
|---|---|---|
| 11-15 07:13:26, to the second | 24 | relay, inferred: the move to `carrier-record` finished 11-18T13:17Z; each account's mode on 11-15 is not read here |
| 11-15 07:14–07:29 | 26 | relay, inferred as above |
| 11-18 18:29:35–18:30:14 | 19 | carrier |
| 11-18 19:25:01–19:25:10 | 4 | carrier |
| 11-18 19:54:10–19:54:59 | 16 | carrier |

Counts are distinct accounts per wave.

**Accounts that ended on an 11-18 give-up and logged no further watch until
11-21 or later:** backend-dev-02, db-admin, flutter-dev-01,
language-culture-en, language-culture-ge, legal-expert-ch,
legal-expert-ee-eu and web-dev-02. These are the eight in the job's title.
language-culture-ge came back on 11-21T06:14Z, when it was restarted, and
language-culture-en on 11-21T08:40Z. The other six came back between
11-22T08:43Z and 08:45Z, when they were relaunched.
p2p-network-dev-01 also gave up at 11-18 19:54Z, but its session was active
again by 11-19T09:48Z.

## Why the carrier "stopped answering" on 11-18

It did not stop answering. Each fleet upgrade that evening (#656, #659, #661 and
#665, through `fabric-ctl all upgrade fabric`) restarted every account's
`interweave-client@gzcoord`. The client takes 80–180 s to report `up`.
language-culture-ru's journal, quoted in its OBSERVATION of 11-18T19:57Z,
shows each give-up seconds after a restart: restart 18:29:43Z, exit 18:29:50Z;
restart 19:54:13Z, exit 19:54:18Z (its journal reads +04). Each restart falls
inside the 18:29Z and 19:54Z waves. Which upgrade caused which wave is not
read here. #659 was reported merged at 18:28Z, and #665's distribution was
requested at 19:52Z, so the two match. The 19:25Z wave is unmatched.
Only the client restarted: language-culture-ru's transport daemon,
`interweave-daemon@gzcoord`, had been up since 11-16 with `NRestarts=0`, and
mine has been up since 11-15 with `NRestarts=0`.

The watch measured silence from the first failure of an earlier outage, not
from the carrier's last answer. One arm runs for up to an hour of slices, so
the down flag set by one restart outlived the recovery, and the next restart
was counted from the old failure. The watch exited 5 within seconds and said
"15 minutes". python-dev-02 fixed this for j169 in `b40ac2e4d`
(BlueTeam-OU/agent-fabric#666, merged 2026-11-19T06:28Z).

## Why the sessions stayed deaf

An idle session has no turn in which to run its watch again. The Stop hook
(`runtime/claude-code/hooks/watch-on-stop.py`) passes while the carrier marker
stands and the carrier's socket does not answer. That was correct at the
moment of the give-up, because the client was still restarting. Nothing ran
later, once the carrier was back. #686 (python-dev-01, j266, merged
2026-11-22T13:37Z) removes the give-up for a carrier primary: the watch
retries until its `--deadline` and exits 0, so the session runs it again. The
relay primary keeps exit 5.

## What cannot be read: the host journal

The system journal on develop-qzapp rotates a 56 MB file about every 74
minutes. Its oldest file ends 2026-11-22 00:36 CET (11-21T23:36Z), so at the
read, about 18:40Z on 11-22, it covered about 19 hours, and every per-user
journal file ends later than that.
No 11-18 or 11-20 entry is left on the host, so no group membership would
recover one. The watch logs (`gzcoord-watch.jsonl`, collected by
`interweave-evidence`) were the record that survived. python-dev-01's
"boot of 2026-11-21 22:10 CET" was the start of the retained journal, not a
reboot.

## A second cause, found while reading: the harness reaps idle watches

At 2026-11-21 17:34–17:35Z Claude Code (2.1.322) stopped the background
`gzcoord inbox wait` with "stopped because the system is running low on
memory". The panes of five sessions show that line.

On 21 accounts, the watch open at 17:34:00Z never logged an `end`. A watch
killed at any moment leaves that same trace. p2p-network-dev-02, for
example, logs starts without ends on 11-20 too. So the logs alone do not
pin every one of the 21 on the reap. When each account next started a
watch:

- **17:35–17:37Z:** four accounts (legal-expert-ge, p2p-network-dev-01,
  rust-services-dev-02, web-dev-01). Whether their earlier watch was reaped
  is not read.
- **17:59Z:** architect-cto-01.
- **20:42–20:44Z:** five accounts (python-dev-01, -02, -04,
  rust-services-dev-01, rust-ui-dev-01).
- **11-22, 06:47–08:47Z:** six accounts, when they were relaunched.
- **11-22, 19:01–19:03Z:** backend-dev-01, brand-comms-01, devex-tooling,
  domain-transit and ux-designer-01, after `fabric-ctl <login> restart`; their
  first `start` lines are 19:01:21Z (ux-designer-01) to 19:03:18Z
  (domain-transit), in the fourth window.
  These are the five panes. Each session had said it would not restart the
  watch because "memory may still be short", and was waiting for its human.
  They had been deaf for 25 hours.

brand-comms-01's pane also shows its `session-state.py` UserPromptSubmit
hook timing out after 5 s at that moment. `watch-on-stop.py` runs with the
same 5 s timeout. Three of the five panes were searched for hook lines, and
none shows watch-on-stop asking for the watch after the reap. Whether it
timed out, or passed for another reason, is not established. At 18:40Z on
11-22, `MemAvailable` was 16 of 31 GiB.

This is the 2026-10-23 failure (j366) again, which led to the hook's `ASKED`
line. It is a separate defect from the carrier give-up, and its own job
carries it.

## What this decides

- j1015's carrier cause is the watch's own counting, fixed by #666. The
  re-arm when the carrier returns is #686. Both are on main and on every
  account.
- Nothing about the carrier itself needs fixing.
- A session made idle and deaf by something outside it can be helped only from
  outside it. That is the contract for the reap follow-up.
