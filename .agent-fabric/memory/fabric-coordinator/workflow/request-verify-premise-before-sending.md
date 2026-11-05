---
role: "fabric-coordinator"
class: workflow
topic: "request-verify-premise-before-sending"
description: Before a REQUEST, INFO or broadcast, check its premises on origin/main (the code, caller, branch and field it names exist; search by purpose, not file name) and run each step it asks for in my own session; carry content, never a pointer…
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1ae437ddcc05bce1
  - 6946d46770829876
---

## Before a REQUEST, INFO or broadcast, check its premises on origin/main (the code, caller, branch and field it names exist; search by purpose, not file name) and run each step it asks for in my own session; carry content, never a pointer the recipient cannot read

Recipients caught a false premise in my messages again and again: a branch "not on origin", a field "NOT in any hook payload", nothing to wire a hint into, a module or oracle that "already existed on main" because I searched by the wrong file name, a grep hit taken for a read. Broadcast steps failed at the recipient too: "a job's notes" that fabric-jobs does not have, a `git worktree remove` that auto mode refused, an "install it yourself" that conflicted with the session-start rule. A REQUEST pointing at `fabric-plan show` reached roles that cannot read plans.

W43 added six of my own corrections. "Fails on main too" was never run. "Arm on the claude review" went out when `fabric-pr gate` showed no claude review. A record draft missed the owner's earlier answers. An ADR path was wrong. A disk broadcast described the sweep's keep rule from memory, not from `--help`. "No word needed" went to a security-boundary PR that `arm --dry-run` refused. Within two hours I told one holder that agent-fabric's count rule was 1 and another that it was 8. `policies/arming.json` says 8. Each one cost the recipient a round.

**Why:** a wrong premise stalls the recipient, and a bulk broadcast stalls many at once.
**How to apply:** before composing, read the named code on origin/main, `git ls-remote` any branch I cite, grep by docstring and purpose, and paste plan content into the message. Run every step of an instruction myself first. State an arming minimum, or whether a word is needed, only from `fabric-pr arm <n> --dry-run` on that head, and a command's behaviour only from its `--help`. Related: [[find-oracle-by-docstring]], [[request-check-authority-fence]], [[owner-commands-one-line]].

W44 (reflection 2026-W44) added two more kinds of premise. First, facts relayed from the owner or recalled from memory and fanned out to several agents unchecked: a device port (one higher in fact, found by a recipient's refused connection), a lease name short enough to let two agents share one phone, and environment advice to the owner that made 25 panes ask for a passphrase. Probe it, or say "unverified". Second, a negative claim ("no caller") from a path-limited grep. Grep the whole tree, unscoped. Messages: 01a18b21-667e-7895-8ebb-04a197262507, 01a18b22-b27e-76b0-8705-bbc873e7b58a, 01a18b2f-9f04-745e-b944-f62cc4d53a51, 01a18b15-74bf-7256-98b8-2fb4a71679b4, 01a175a6-98e4-78a5-ba96-129892a391a4, 01a175cd-c9fa-78f1-84e2-73d746452018.

*References: find-oracle-by-docstring, owner-commands-one-line, request-check-authority-fence*

*Observed 2026-11-01 (fabric-coordinator)*
