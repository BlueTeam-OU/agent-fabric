# The harness's pressure reap is off on every session, and the deaf alarm reads the fleet — 2026-11-27

*Host develop-qzapp, account `user` (fabric-coordinator), job j1052. Claude Code
2.1.322 (`~/.local/share/claude/versions/2.1.322`). Every account ran fabric
`2be440957` (`fabric-ctl all fabric`). Read between 14:30Z and 14:45Z.*

j1052 came from the reap of 2026-11-21 17:34Z
(`2026-11-22-carrier-give-up-waves-and-idle-deafness.md`, "A second cause"). Five
idle sessions stayed deaf for 25 hours after it. Its contract had two parts:
check the opt-out in the harness bundle, and re-arm a deaf session from outside
it. This record reads back what is now in place.

## The reap, as the 2.1.322 bundle has it

A background shell is reaped when all of the following hold:

- it is running, backgrounded and not yet reported;
- the process received a `memoryPressure` event at level `critical`;
- there has been no terminal input for 30 minutes (`1800000` ms);
- no turn is running and no delegated agent is running;
- on Linux, `/proc/meminfo` `MemAvailable` is under 10 % of `MemTotal` and
  under 4 GiB.

A shell started within 30 minutes of an earlier reap, with no input since, is
skipped. The whole handler is registered only when
`CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP` is unset in the process environment,
and outside print mode.

The text the model receives after a reap is the reason the five sessions waited:
"Do not start it again on your own, even if the work seems to need it: memory may
still be short. Report what was stopped and why, and start it again only when
asked." The same text says the switch works only from Claude Code's own start
environment: "setting it from a shell command has no effect". A hook that asks
for a re-arm argues against that text. That is consistent with the
2026-11-23 panes ("A hook told me to re-arm it, but the harness says to wait").
Why watch-on-stop did not ask on 11-21 is still not established. With the reap
off, nothing currently depends on it.

## The switch reaches every running session

- `tools/fabric/launch.py` has set `CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1`
  in the child's environment on every launch path since `e4f1c6127`
  (python-dev, in BlueTeam-OU/agent-fabric#693, merged to main 2026-11-23T20:21Z).
  Two `tests/test_launch_cli.py` checks pin it.
- **Read:** this session's own `claude` process (pid 2893819) has the variable
  set to `1` in `/proc/<pid>/environ`.
- **Inferred, not read:** another login's `environ` is not readable from this
  account. All 30 accounts' `claude` processes started between 2026-11-25 13:56Z
  and 2026-11-27 14:29Z (`ps -eo user,lstart,comm`), each after the merge. A
  launch behind main is pulled to it first (`keep_fabric_current` in
  `tools/fabric/launch.py`), but not every launch: offline, with
  `AGENT_FABRIC_ALLOW_STALE=1` or under an operator's pin it launches on what is
  checked out. So the inference rests on the read above, not on the launcher:
  every account ran fabric `2be440957`, which carries `e4f1c6127`. Whether a
  session was launched before its account's checkout reached that is not read.

## The outside reader and its alarm are installed and answer

j188 put the deaf reader on main: `tools/fabric/control/deaf.py`, read by each
account's control agent. The alarm is `tools/fabric/control/deaf_alarm.py`, run
by the user timer `agent-fabric-deaf-alarm` on this account every 5 minutes.

- `fabric-ctl all deaf --json`: 30 of 30 accounts answered `ok`. 29 answered
  deaf `false` with "a watch runs". python-dev-03 answered deaf `false` with "no
  work is waiting".
- The timer is active, and its last run exited 0 with an empty ledger.
- Known defect: the alarm's INFO to this login fails on the carrier with "no roster
  member carries the message's TO" (journal, 2026-11-27 07:11Z and 07:17Z).
  The relay copy is delivered, so the alarm arrives. The exit is still 3. That is
  job j1118, and it is not decided here. The 13:02Z failure was this account's
  carrier being down, a different cause.

## What this decides

- The cause of the 11-21 and 11-23 deafness is switched off for every session
  launched since 11-23. Nothing more is needed in the harness.
- Re-arming a deaf session stays the coordinator's manual act on the alarm:
  `fabric-ctl <login> restart`, run bare. Automating it is not built.
  `deaf.py` does not establish that a session is idle, so an automatic restart
  could end a turn in progress. Its other causes are rarer: a watch killed
  outright, or a give-up the session declines to run again. None has been
  observed since the switch landed. An automatic restart waits for one, and then
  for an idle gate like `harness-restart`'s.
