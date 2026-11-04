---
role: "python-dev"
class: solution
topic: "j160-observe-verb-merged-362"
description: "fabric-accounts observe + observer /usage --verbose merged in #362 (532d5ef8); what the reviews kept finding, the moving-head loop, how to end it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0552243ebc7e2de5
---

## fabric-accounts observe + observer /usage --verbose merged in #362 (532d5ef8); what the reviews kept finding, the moving-head loop, how to end it

`fabric-accounts observe [--write]` (tools/fabric/control/account_observe.py) and `read_account --verbose` merged in #362 (2026-10-24, merge 532d5ef8, head 40dc73b5; arm on the owner's word, 1 work / 10 fix). The coordinator distributes; the owner runs the dry run.

**Why/what to remember**
- The one key is *spliced into the file text* (raw_decode of the top-level members), never re-serialised: that is how "every other byte kept" holds. Empty objects keep the whitespace inside the braces; NaN, duplicate key, depth (RecursionError) refuse the file by name.
- `settings_put(src, expect_head=)` takes `settings.remote_tip(store)`; compare the remote tip, never HEAD (bringing the store up to its remote re-signs unpushed commits, so HEAD moves with nothing new). Templates are read under the lock, the lock is let go for the network probes, retaken to write with the same tip.
- Header/field values from a network reply: every figure goes through one normaliser (finite, >=0, scaled finite, time representable, js.number OverflowError for "0x"+300 digits) and an all-null window is no window. A free-text error from the harness is never kept (cut at 200 chars it can leave the front of a token that a whole-token scrub misses).
- `util.read_json`: O_NONBLOCK + fstat S_ISREG *before* fdopen, close the fd on every refusal path (fdopen of a directory does not take ownership: one leaked fd per call in the keeper).
- A mutation that removes O_NONBLOCK hangs the test (FIFO): the mutation runner needs a per-run timeout and a finally-restore, or it dies mid-run with the source mutated.

**How to apply / process**
- A review round per head: every push makes the previous engines' reviews stale and Codex *refuses to post* if the PR head moves while it reads. Commit locally, push only when both engines are idle; stop at P3s (name them in a judgement comment) after the P1/P2 that are real. Codex returns a P1 on "shorter token fragment" every round: judge it once (a reply can only echo a token it holds), do not chase window sizes.
- A re-review whose reviewer marks unchanged paths "not read" is *partial coverage* and does not count; a fresh primary review of the whole range at the final head does. Coverage paths must be only the range's changed files.
- `fabric-review next` derived a round-2 brief over caa94129..head, not the last fix commit alone; either paste the full brief or a primary review.
- Open point left to the requester: sign-in /usage failure keeps status ok + observed.signin (exit 1); strict reading would blank the record.

Related: [[bounded-subprocess-three-seams]] [[post-review-pins-the-head-it-sees]] [[reading-git-objects-under-a-hostile-git-dir]]

*References: bounded-subprocess-three-seams, post-review-pins-the-head-it-sees, reading-git-objects-under-a-hostile-git-dir*

*Anchors: `tools/fabric/control/account_observe.py::set_key`, `tools/fabric/secretstore/settings.py::remote_tip`, `tools/fabric/control/ops/util.py::read_json`*

*Observed 2026-10-24 (python-dev)*
