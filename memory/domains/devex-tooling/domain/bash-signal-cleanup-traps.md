---
role: "devex-tooling"
class: domain
topic: "bash-signal-cleanup-traps"
description: "Writing cleanup for a CI shell script, or a self-test that signals one: EXIT trap suffices for INT/TERM; & jobs start with INT ignored"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 4ebe8d2120ee2bae
---

## Writing cleanup for a CI shell script, or a self-test that signals one: EXIT trap suffices for INT/TERM; & jobs start with INT ignored

bash runs `trap cleanup EXIT` when the script dies of SIGINT or SIGTERM, so extra
`trap 'exit 130' INT` / `trap 'exit 143' TERM` lines are dead code. A self-test with
the extra trap removed still passed, and an INT and a TERM sent to a `setsid` group
both ran the EXIT trap (2026-10-08, InterWeave tools/ci/build_previous_builds.sh,
9f525f63).

The trap in the self-test: a `&` job of a non-interactive bash starts with SIGINT
IGNORED, and bash cannot un-ignore a signal it inherited as ignored. Start the job
through `python3 -c 'signal.signal(SIGINT, SIG_DFL); os.setsid(); os.execvp(...)'`
and send the signal to the group (`kill -INT -- -$pid`) so the stubbed child dies
too. Mutation control: a script with `trap '' INT` added must fail the case.

`git worktree prune` drops only registrations whose directory is gone, so in a
cleanup it must run AFTER the scratch `rm -rf`, or it is an inert backstop.
Related: [[grep-q-pipefail-silent-pass]], [[review-class-cannot-write-scratch]].

*References: grep-q-pipefail-silent-pass, review-class-cannot-write-scratch*

*Observed 2026-10-08 (devex-tooling)*
