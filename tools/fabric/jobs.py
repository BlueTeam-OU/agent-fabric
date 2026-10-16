#!/usr/bin/env python3
"""tools/fabric/jobs.py — the agent's own job list (agent-fabric ADR-037),
behind bin/fabric-jobs.

    fabric-jobs add "<title>" [--topic T] [--project P] [--working-copy W] [--priority P]
    fabric-jobs add --request <MESSAGE-ID|seq> [--topic T] [--working-copy W] [--priority P]
    fabric-jobs list [--all] [--json] [--stored] [--cached]
    fabric-jobs prio <id> <blocking|high|normal|low>
    fabric-jobs start <id>
    fabric-jobs pause <id> "<why>"
    fabric-jobs block <id> "<on what>"
    fabric-jobs block <id> --on-request <MESSAGE-ID> ["<on what>"]
    fabric-jobs block <id> --on <blocker> [--on <blocker>…] ["<on what>"]   blocker: pr:<owner/repo>#<n> | request:<message-id> | job:<login>/j<n>
    fabric-jobs deliver <id> <artifact>...
    fabric-jobs retract <id> <artifact>                          remove one artifact, exactly as recorded, in any state; noted in the log
    fabric-jobs done <id>
    fabric-jobs drop <id> "<why>"
    fabric-jobs show <id> [--json]
    fabric-jobs switch [<id>] [--json] [--type feat|fix|docs|chore|test|refactor] [--needs-merged]
    fabric-jobs next [<id>] ...                                  alias of switch
    fabric-jobs pool-list [--role R] [--json]
    fabric-jobs pool-claim <pool id> [--topic T] [--working-copy W]

The list is agents/<login>/jobs.json, read and written only through
runtime/identity.py, under the agent lock. A job's project and working
copy are the ones the directory it was added in resolves to, unless given;
its topic is a label the agent sets, never guessed.
At most one job is active: `start` refuses a second, because "what am I
doing" has one answer.

`add --request` is how a receiver puts a GZCoord request it takes on its
list: the title, sender and project are read from the message through the
inbox's own replay (addressed to this login, or refused, SPEC §17), and
a message already on the list is refused by name. Only the receiver runs
it (ADR-037 rule 4). The automatic intake in the GZCoord send
(tools/fabric/gzcoord/send.py) calls it with
--auto, which skips quietly what is not a REQUEST or is already listed;
that path runs only under AGENT_FABRIC_JOBS_AUTO_INTAKE=1, which nothing
sets (rule 5). A REQUEST addressed to a login is another path, always on:
the inbox queues it on delivery and the host operator's send asks the control
plane's jobs-add for it (tools/fabric/gzcoord/intake.py), both under the
title "<SUBJECT> (REQUEST <MESSAGE-ID>)"; `add --request` for a job
the sender's half made (it records no message id) adds a second job, so look
at `list` first.

A job has a priority (ADR-037 rule 7): blocking, high, normal or low;
normal when none was set, and in a list written before priorities
existed. A stored value outside the four is not read as normal: `next`
refuses to order a queue it cannot rank, and names the job.

A job blocked on a request names it (`block --on-request`, rule 8): the
message id is kept as `waits_on`, and this account's control agent says it
in its state record (tools/fabric/control/sessions.py) while the job stays
blocked, so the job that request asked for ranks blocking wherever it is
queued. Leaving `blocked` drops it: an id kept on a job that no longer
waits would be said by nobody, and read as a wait by a person.

A job can be blocked on something the tool can check (`block --on`, tools/fabric/jobsparts/blockers.py is the
contract): a pull request (`pr:<owner/repo>#<n>`, cleared when it is merged or closed), a request this login sent
(`request:<message-id>`, cleared when a message of any type, a DECISION as well as a REPLY, with a non-empty IN-REPLY-TO naming it is in the journal) or a peer's job (`job:<login>/j<n>`, cleared
when it is delivered, or closed after it was seen open; read through fabric-ctl, a host operator's op), several
allowed and all of them must clear. `list`, `next` and `block` check them, a blocker at most once every ten
minutes (a cleared one never again: <state dir>/jobs-blockers.json), and a job whose blockers have all cleared reads
"blocker cleared: <what>", is listed first, and is what `next` takes before anything queued: the agent moves it on
itself. `--stored` and `--cached` check nothing and read that cache (the control agent's `jobs` op, a hook).
`list --json` and the control plane's `jobs` carry, for such a job only, `blockers` ([{spec, state, detail,
checked_at}]; state cleared, waiting or unknown, and unknown never clears) and `cleared` (true, false, or null
while none is told). A request blocker is also kept as `waits_on`, as `--on-request` always kept it, and
`--on-request` is now the same blocker. A free-text blocker behaves as it always did; one that names a pull
request or a message id says once that a checkable form exists. Leaving `blocked` drops the blockers.

The other half: a queued job whose source message is in any account's
waits_on ranks blocking, its stored priority kept. `list` and `next` read
the state stream for it through tools/fabric/control/queue.py (the control
plane's shapes stay in that module) — only when a queued job came from a message,
since nothing else can match — and `list` shows both priorities and the
address that waits. A stream that cannot be read leaves stored priorities
to decide, and is said on stderr; it never fails the command. A waiter
whose state record is older than the stream's bound still counts (rule
8: the block is in its jobs.json whether or not its agentd runs), and is
named with the record's age and said stale. `--stored`
skips the stream (the control agent's `jobs` op, which answers in
seconds).

A role has an open pool (rule 9), held by one control agent
(tools/fabric/control/pool.py). `pool-list` lists the bound role's (or
--role's) unclaimed jobs, highest priority first; `pool-claim` asks the
holder for one — the holder checks the role this login's own control
agent reports — and puts the job it gets on this list as queued, source
`pool`. A claim the holder recorded but this list could not take is said
with the command that lands it: the same login claiming again gets the job
again, and a job already on the list by its pool id is not added twice.
With nothing queued, `next` offers the pool's first job and says so; it
claims nothing.

`pause <id> "<why>"` sets the active job aside (rule 2: blocked is a wait the agent does not control, paused is its own
choice). It records the branch checked out where it runs, unless that is the default branch, and `switch` asks that this
branch is pushed. A paused job is offered before queued jobs of the same priority, never ahead of a higher one, and is
taken back by `switch <id>` or when it is first in the order.

`switch` (alias `next`) is the transition between jobs (rule 10, amended 2026-10-14), three steps, a refusal naming every
check that failed and changing nothing:
  1. The job this session worked last is settled with its evidence, by the state it is left in. done: a pull request merged or
     a commit or a branch (a contributor branch: name or origin/<name>) whose head is on origin's default branch; delivered: a pull
     request open or a branch on origin; blocked: a checkable blocker not yet cleared, or
     "owner: <the decision awaited>" as text; paused: its branch pushed; dropped: a reason. Evidence is read from the job's
     artifacts (owner/repo#N, #N, a pull request URL, a commit sha, or reply:<MESSAGE-ID>, the reply's own id or the id it
     answers, which counts for a job whose artifact is an answer, a message of this login with an IN-REPLY-TO, a REPLY or a DECISION alike, when the journal holds it as sent: accepted by the carrier); a job with topic reflection is also landed by this login's
     fabric-reflect cursor, closed after the job started (ADR-058 rule 4). Whatever the outcome: no uncommitted change in the job's working
     copy, its worktree or this directory's checkout; every inbound REQUEST or QUESTION received since the job or this session started, whichever is earlier, addressed to this login with REPLY-EXPECTED: yes
     or whose record cannot be read or whose receipt time cannot be read (such a row is owed, never let through), has an answer of this login in the journal (any accepted outbound message whose IN-REPLY-TO names it, a DECISION as well as a REPLY); and a file changed since the job last became active in the memory directory of
     the working copy, of its repository's main checkout, or of an ancestor of either below the home (any memory directory
     of the login for a job with topic reflection). A check that cannot be told is a failure, said as such, never a pass.
     `deliver <id> <artifact>` on a done job appends evidence and leaves it closed (a dropped job takes none).
     `retract <id> <artifact>` removes one recorded artifact whatever the job's state, so a mistaken one cannot hold the job; it refuses,
     naming the artifacts, when the string is not there, and notes what was removed in the job's log.
  2. The next job starts in a fresh session after a worked one (rule 3, unchanged): `fabric-fresh --job <id>` is printed.
  3. Its branch is chosen before any work: the job's own branch when it has begun one that no pull request merged; else this
     login's open pull request in the repository when it can take more commits (not armed or queued, fewer than 16 work
     commits), with the default branch merged into it first (locally, not pushed); else, with --needs-merged, the job is blocked
     on that pull request and not started; else a new branch <host>/<login>/<type>/<job id and title words> off the freshly
     fetched default branch. Each is checked out in a worktree beside the job's working copy, which stays where it is; the
     job keeps `branch` and `worktree`, and the opening prompt of its fresh session names them. Two open pull requests of this
     login, no working copy, or an origin that cannot be asked are refused.
Each switch appends one line to the old and one to the new job's log: the outcome and its evidence, and the branch.
`switch` still never passes an active job, takes the job named or the first in the order (a blocked job whose blockers
cleared first, then queued and paused by priority, paused first, then the oldest), and with nothing queued offers the pool's.
A session that has worked no job has nothing to settle and takes the job in place; "worked" is read from the list: a
transition whose old or new state is `active` (a start, a block, a delivery, a finish or a drop of the active job) writes
the harness session id (CLAUDE_CODE_SESSION_ID), when the environment has one, into the job's log entry, and a session is one
that appears in any entry, so a session launched with its job already active is known once it finishes it.
With no session id in the environment (an unlaunched shell) the job that last left `active` counts, so `switch` says fresh.
Every job starts in a fresh session (the owner, 2026-10-11): a fresh launch reads the fabric anew, which a running session
never does, and a warm prompt cache is no reason to continue. The agent runs the command it prints, never the owner.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys

# The parts, a package loaded BY PATH as fabric_jobs: the shim runs this file
# without -I's sys.path help, and a fixture fabric on sys.path must not answer
# for its imports. A second jobs.py in one process (a fixture's copy beside the
# real one) loads its own parts, never the first one's from sys.modules.
for _name in [n for n in sys.modules if n == "fabric_jobs" or n.startswith("fabric_jobs.")]:
    del sys.modules[_name]
_spec = importlib.util.spec_from_file_location(
    "fabric_jobs", os.path.join(os.path.dirname(os.path.realpath(__file__)), "jobsparts", "__init__.py"),
    submodule_search_locations=[os.path.join(os.path.dirname(os.path.realpath(__file__)), "jobsparts")])
sys.modules["fabric_jobs"] = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sys.modules["fabric_jobs"])
# Every name the parts define, from here as before: the tests and the intake reach them as jobs.<name>.
from fabric_jobs.base import HERE, FABRIC_ROOT, _JobKeys, Job, _load, identity, STATES, OPEN, TERMINAL, MESSAGE_ID, POOL_ID, PRIORITIES, DEFAULT_PRIORITY, Refused, NothingQueued, Stale, mutate  # noqa: E402, F401
from fabric_jobs import blockers  # noqa: E402, F401
from fabric_jobs.ranking import stored_priority, message_of, waiters, effective_priority, queue_order, named  # noqa: E402, F401
from fabric_jobs.records import find, active, transition, own_project, working_copy_of, new_job, INBOX, fetch_message, request_job  # noqa: E402, F401
from fabric_jobs.queue import QUEUE, QUEUE_TIMEOUT_S, Unreachable, ask_queue, stream_waits  # noqa: E402, F401
from fabric_jobs.pool import Unanswered, ask_pool, pool_offer, PROJECT_SLUG, claimed_job, pool_job, printable, pool_line  # noqa: E402, F401
from fabric_jobs.render import line, show, summary  # noqa: E402, F401
from fabric_jobs.branching import TYPES  # noqa: E402, F401
from fabric_jobs.verbs import decide, add, pool_list, pool_claim, list_jobs, show_job, switch_job, change  # noqa: E402, F401


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabric-jobs", description="this agent's job list (agent-fabric ADR-037)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="add a queued job")
    a.add_argument("title", nargs="?")
    a.add_argument("--request", metavar="MESSAGE-ID", help="a GZCoord message addressed to this login")
    a.add_argument("--auto", action="store_true", help=argparse.SUPPRESS)
    a.add_argument("--owner", metavar="ADDRESS", help=argparse.SUPPRESS)   # the control agent's jobs-add
    a.add_argument("--topic")
    a.add_argument("--project")
    a.add_argument("--working-copy")
    a.add_argument("--priority", choices=PRIORITIES, default=DEFAULT_PRIORITY)
    ls = sub.add_parser("list", help="open jobs (--all: closed ones too)")
    ls.add_argument("--all", action="store_true")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--stored", action="store_true", help="stored priorities only; the state stream is not read, nor a blocker checked")
    ls.add_argument("--cached", action="store_true", help="checkable blockers are read from the cache, not checked")
    pr = sub.add_parser("prio", help="set a job's priority")
    pr.add_argument("id")
    pr.add_argument("priority", choices=PRIORITIES)
    for name in ("start", "done"):
        sub.add_parser(name).add_argument("id")
    b = sub.add_parser("block")
    b.add_argument("id")
    b.add_argument("on", nargs="?")
    b.add_argument("--on", dest="on_spec", action="append", metavar="BLOCKER",
                   help="a checkable blocker: pr:<owner/repo>#<n>, request:<message-id> or job:<login>/j<n>; repeatable, all must clear")
    b.add_argument("--on-request", metavar="MESSAGE-ID", help="the GZCoord request this job waits on")
    d = sub.add_parser("deliver")
    d.add_argument("id")
    d.add_argument("artifacts", nargs="+")
    rt = sub.add_parser("retract", help="remove one artifact from a job, exactly as recorded")
    rt.add_argument("id")
    rt.add_argument("artifact")
    dr = sub.add_parser("drop")
    dr.add_argument("id")
    dr.add_argument("why")
    s = sub.add_parser("show")
    s.add_argument("id")
    s.add_argument("--json", action="store_true")
    s.add_argument("--line", action="store_true", help="one line, for an opening prompt")
    s.add_argument("--field", help="one field's value, for the launcher")
    pa = sub.add_parser("pause", help="set the active job aside, to be taken back by name")
    pa.add_argument("id")
    pa.add_argument("why")
    for name, helptext in (("switch", "settle the job being left with its evidence, start the next and choose its branch"),
                           ("next", "alias of switch")):
        n = sub.add_parser(name, help=helptext)
        n.add_argument("id", nargs="?")
        n.add_argument("--json", action="store_true")
        n.add_argument("--type", choices=TYPES, default="feat", help="the kind of a new branch's name (default feat)")
        n.add_argument("--needs-merged", action="store_true", help="the job needs this agent's open pull request merged first: if it cannot take more commits, block on it")
    pl = sub.add_parser("pool-list", help="the open jobs of a role's pool (default: the bound role)")
    pl.add_argument("--role")
    pl.add_argument("--json", action="store_true")
    pc = sub.add_parser("pool-claim", help="claim a pool job; it lands on this list, queued")
    pc.add_argument("id")
    pc.add_argument("--topic")
    pc.add_argument("--working-copy")
    args = ap.parse_args(argv)

    verb = {"add": add, "pool-list": pool_list, "pool-claim": pool_claim, "list": list_jobs, "show": show_job, "switch": switch_job, "next": switch_job}.get(args.cmd, change)
    try:
        return verb(args)
    except Refused as exc:
        print(f"fabric-jobs: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
