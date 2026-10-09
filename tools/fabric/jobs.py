#!/usr/bin/env python3
"""tools/fabric/jobs.py — the agent's own job list (agent-fabric ADR-037),
behind bin/fabric-jobs.

    fabric-jobs add "<title>" [--topic T] [--project P] [--working-copy W] [--priority P]
    fabric-jobs add --request <MESSAGE-ID|seq> [--topic T] [--working-copy W] [--priority P]
    fabric-jobs list [--all] [--json] [--stored]
    fabric-jobs prio <id> <blocking|high|normal|low>
    fabric-jobs start <id>
    fabric-jobs block <id> "<on what>"
    fabric-jobs block <id> --on-request <MESSAGE-ID> ["<on what>"]
    fabric-jobs deliver <id> <artifact>...
    fabric-jobs done <id>
    fabric-jobs drop <id> "<why>"
    fabric-jobs show <id> [--json]
    fabric-jobs next [<id>] [--json]
    fabric-jobs pool-list [--role R] [--json]
    fabric-jobs pool-claim <pool id> [--topic T] [--working-copy W]

The list is agents/<login>/jobs.json, read and written only through
runtime/identity.py, under the agent lock. A job's project and working
copy are the ones the directory it was added in resolves to, unless given;
its topic is a label the agent sets, compared by `next` and never guessed.
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
in its state record (runtime/control/sessions.mjs) while the job stays
blocked, so the job that request asked for ranks blocking wherever it is
queued. Leaving `blocked` drops it: an id kept on a job that no longer
waits would be said by nobody, and read as a wait by a person.

The other half: a queued job whose source message is in any account's
waits_on ranks blocking, its stored priority kept. `list` and `next` read
the state stream for it through runtime/control/queue.mjs (the control
plane's shapes stay in Node) — only when a queued job came from a message,
since nothing else can match — and `list` shows both priorities and the
address that waits. A stream that cannot be read leaves stored priorities
to decide, and is said on stderr; it never fails the command. A waiter
whose state record is older than the stream's bound still counts (rule
8: the block is in its jobs.json whether or not its agentd runs), and is
named with the record's age and said stale. `--stored`
skips the stream (the control agent's `jobs` op, which answers in
seconds).

A role has an open pool (rule 9), held by one control agent
(runtime/control/pool.mjs). `pool-list` lists the bound role's (or
--role's) unclaimed jobs, highest priority first; `pool-claim` asks the
holder for one — the holder checks the role this login's own control
agent reports — and puts the job it gets on this list as queued, source
`pool`. A claim the holder recorded but this list could not take is said
with the command that lands it: the same login claiming again gets the job
again, and a job already on the list by its pool id is not added twice.
With nothing queued, `next` offers the pool's first job and says so; it
claims nothing.

`next` is the restart rule (ADR-022 rule 12). It never passes an active
job, which is never preempted, and takes the job named, or the queued job
of highest priority, the oldest first (the list's order is the order jobs
were added); a blocked job keeps its place and is taken only by name. It
compares that job with the job that last left
`active`, or, when none has, with the directory it runs in:
the same project, working copy and topic continue in this session; any
difference is a fresh session, and `next` prints the one command that
starts it (`fabric-fresh --job <id>`). The agent confirms by running it.
A topic missing on either side leaves only the repository to compare,
and `next` says so rather than guessing whether the subjects differ.
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
from fabric_jobs.ranking import stored_priority, message_of, waiters, effective_priority, queue_order, named  # noqa: E402, F401
from fabric_jobs.records import find, active, transition, own_project, working_copy_of, new_job, INBOX, fetch_message, request_job  # noqa: E402, F401
from fabric_jobs.queue import QUEUE, QUEUE_TIMEOUT_S, Unreachable, ask_queue, stream_waits  # noqa: E402, F401
from fabric_jobs.pool import Unanswered, ask_pool, pool_offer, PROJECT_SLUG, claimed_job, pool_job, printable, pool_line  # noqa: E402, F401
from fabric_jobs.render import line, show, summary  # noqa: E402, F401
from fabric_jobs.verbs import decide, add, pool_list, pool_claim, list_jobs, show_job, next_job, change  # noqa: E402, F401


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
    ls.add_argument("--stored", action="store_true", help="stored priorities only; the state stream is not read")
    pr = sub.add_parser("prio", help="set a job's priority")
    pr.add_argument("id")
    pr.add_argument("priority", choices=PRIORITIES)
    for name in ("start", "done"):
        sub.add_parser(name).add_argument("id")
    b = sub.add_parser("block")
    b.add_argument("id")
    b.add_argument("on", nargs="?")
    b.add_argument("--on-request", metavar="MESSAGE-ID", help="the GZCoord request this job waits on")
    d = sub.add_parser("deliver")
    d.add_argument("id")
    d.add_argument("artifacts", nargs="+")
    dr = sub.add_parser("drop")
    dr.add_argument("id")
    dr.add_argument("why")
    s = sub.add_parser("show")
    s.add_argument("id")
    s.add_argument("--json", action="store_true")
    s.add_argument("--line", action="store_true", help="one line, for an opening prompt")
    s.add_argument("--field", help="one field's value, for the launcher")
    n = sub.add_parser("next", help="start the next job and say whether it needs a fresh session")
    n.add_argument("id", nargs="?")
    n.add_argument("--json", action="store_true")
    pl = sub.add_parser("pool-list", help="the open jobs of a role's pool (default: the bound role)")
    pl.add_argument("--role")
    pl.add_argument("--json", action="store_true")
    pc = sub.add_parser("pool-claim", help="claim a pool job; it lands on this list, queued")
    pc.add_argument("id")
    pc.add_argument("--topic")
    pc.add_argument("--working-copy")
    args = ap.parse_args(argv)

    verb = {"add": add, "pool-list": pool_list, "pool-claim": pool_claim, "list": list_jobs, "show": show_job, "next": next_job}.get(args.cmd, change)
    try:
        return verb(args)
    except Refused as exc:
        print(f"fabric-jobs: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
