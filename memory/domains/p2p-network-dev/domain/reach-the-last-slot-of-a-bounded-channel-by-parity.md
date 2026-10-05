---
role: "p2p-network-dev"
class: domain
topic: "reach-the-last-slot-of-a-bounded-channel-by-parity"
description: "Testing \"a command took the channel's last slot and its follow-up found it full\" -- overfilling makes the test vacuous; alternate two sends and run padded 0 and 1 so one run is odd"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 7a9019cfab1ac6a4
---

## Testing "a command took the channel's last slot and its follow-up found it full" -- overfilling makes the test vacuous; alternate two sends and run padded 0 and 1 so one run is odd

#144 re-review 2 F1 (2026-09-28): a cancelled join's guard queued its leave with `try_send`, and on
a full command channel the fallback SPAWNED the leave outside the session lock, so it could land
after the session's next join and undo it. The fix parks the leave in the session, sent under the
lock before the next join/leave and by teardown.

The first test OVERFILLED the channel (256 cancelled leaves, depth 64) and passed against the old
spawn code and against two mutations of the new one: on an overfilled channel the cancelled join is
never sent, so its owed leave is a no-op. The case that matters is the join taking the LAST slot and
its leave finding the channel full. Without knowing how many commands the runtime already has
queued: a run of cancelled joins of one channel alternates join/leave, so a join takes the last slot
exactly when the free slots are odd; run each phase twice, padded by 0 and by 1 cancelled no-op
command, after an awaited call that drains the channel. Then all three mutations failed
(`a_leave_owed_on_a_full_channel_is_sent_before_the_next_join`,
tests/local-client-conformance/tests/in_process.rs).

Also measured: on a current-thread runtime the spawned-leave race did NOT show -- the spawned task
takes a freed permit before the waiting joiner is re-polled -- so "the race does not reproduce here"
is not "the race is absent"; remove the mechanism rather than chase its schedule.

**Why:** a test that never reaches the boundary agrees with any implementation of it.
**How to apply:** any bounded-queue fallback path (try_send fails): make the triggering command
take the last slot by parity, then mutation-check the fallback. See [[cancel-a-future-after-one-poll]].

**The parity trick was not enough either (re-review 3, same day).** Other senders on the shared
channel shifted the free slots between the padded passes, and an instrumented run showed NEITHER
stray pass reached the last slot -- the leave-flush mutation survived. What holds: DETECT the case.
A status ask queues behind every command already sent, so right after the cancel loop the
substrate's join references read one above the pre-loop value exactly when a join took the last
slot and its leave is owed. Try pads 0..8, act only on a pass seen to hold the owed join, and fail
if none does (`cancel_joins_until_full` in in_process.rs). Then six mutations failed and the test
passed 10/10. Rule: a test that depends on reaching a boundary must OBSERVE that it reached it.

*References: cancel-a-future-after-one-poll*

*Observed 2026-09-28 (p2p-network-dev)*
