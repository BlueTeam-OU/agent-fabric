# A peer's job: blocker, read by a non-operator — 2026-11-09

Before #527, a `job:<login>/j<n>` blocker read `unknown` forever for every
login but the host operator, because the only way to read a peer's job was
the operator-only `jobs` op (devex-tooling's j306 was stuck on it). #527 added
the public op `job-state` (agent-fabric ADR-029, ADR-037 §5 rule 8). The suite
checked the op and its callers against fakes. This is the first read through
real control agents.

**Run.** 2026-11-09, around 16:20Z, on develop-qzapp, by fabric-coordinator,
after #527 merged (a4b54d78, 16:09:37Z). `fabric-ctl all status` showed every
account's fabric at a4b54d78, so no upgrade was needed. Each waiter's own list
was read with `fabric-ctl <login> jobs --json`. That op runs
`tools/fabric/jobs.py` as the waiter's login, so the blocker is checked in the
waiter's identity, and that waiter is not an operator.

## Result

- **The sender as waiter.** p2p-network-dev-02's j103 is blocked on
  `job:user/j698`, and j698 was taken from p2p-network-dev-02's own REQUEST
  (`source: request from develop-qzapp/p2p-network-dev-02`). The blocker read
  `state: waiting, detail: queued`, checked 16:12:31Z. j698 was in fact
  queued.
- **The control, a waiter that is not the sender.** ux-designer-01's j95 is
  blocked on `job:rust-ui-dev-01/j213`. The blocker read `state: unknown`,
  with detail "rust-ui-dev-01's control agent: refused: job-state answers the
  sender of the request the job was taken from", checked 16:17:33Z.

## What it decides

1. **The op is live on both sides.** The asking side reaches it as a
   non-operator, and the answering side applies the sender condition. The
   refusal comes from rust-ui-dev-01's agent with the module's own wording, so
   the `waiting` answer above was produced by the op itself, not by a fallback
   board read. A non-operator cannot read a board, so that fallback was not
   available to it anyway.
2. **A waiter that is not the sender still reads `unknown`, by design**
   (`tools/fabric/control/jobs.py`, WHAT IS NOT CHECKED; ADR-037 §5 rule 8: "a
   refusal is a board not read, so a `job:` blocker stays unknown"). The
   blocker now gives the reason in its detail, so the waiter can see it and
   hold the wait on something it can check, such as a `pr:` or a clock.
