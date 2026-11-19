---
role: "python-dev"
class: solution
topic: "assembler-drain-defects-j120"
description: "j120 #519 — anchorkeep, unbound-role hold, one-line titles, code-span citations; traps in the assembler and in running a review round"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - effd15816199e1b7
---

## j120 #519 — anchorkeep, unbound-role hold, one-line titles, code-span citations; traps in the assembler and in running a review round

PR 519 (j120): four assembler fixes, each in tests/test_assemble_drain_defects.py. Facts that were not obvious:

- A section's anchors are part of its rendered text, so an anchor that differs is a collision or a same-agent supersede, not a no-op. `assembler/anchorkeep.py` therefore rewrites the claim's anchors to the corpus's BEFORE the pre-pass (judged by `memory_check.judge_anchor`, stale-hard incoming + resolving corpus, same path+string).
- `hold_unbound_roles` (intake.py) reuses the `--hold` machinery (`held_back`, `held_evidence` keeps the store mark below). A held role is still in `run.all_claims` (also as the AUTHOR of a shared slice), so `owning_roles` would still index it: `run.unbound_held_roles` + the `emptied` filter in assemble.py. Review caught both the per-role and the shared-author case.
- The fabric's own project (agent-fabric) must be exempt: its taxonomy binds 3 roles while its project memory is every role's.
- The "description read two ways" defect was not two readers: lint and `writer.described` decode alike. It is a title with a decoded line break (YAML `\n`) splitting the heading and cutting the INDEX entry. lint.py/layout.py are excluded from python-dev's entry, so the lint half goes to fabric-coordinator as a patch in a message.
- The harvest cites every `[[x]]` of a body (code or not); the assembler filters at intake (`cited_outside_code`, slices.py), because bundles are replayed without re-harvesting.

Replay round (merged 2026-11-09, head 96595a24, rounds 6-10): the requester's replay of the real drain found two more defects the fixtures missed. (1) A shared slice is held only when NO owner is bound; with a bound owner it is written and `shared_owners -= unbound` keeps the unbound owners out of every index. (2) `titles_one_lined` ({slice, breaks, title}) is recorded in `bucket_claims`, after `screen_hygiene`: a refused claim has no entry, the slice is named as filed (`shared/...` when other owners), and the OLD title is never copied — a hygiene lookbehind such as `(?<=clone )` needs the space `one_line` made, so the pre-break text can carry what hygiene replaced in the committed report. `fabric-pr arm` refuses on ANY open finding in a review chain, P3 included: fix the P3s too (each fix moves the head and needs a covering review). `tools/fabric/assembler` comments must not name a managed project (lint, failed platform-smoke only).

Method traps: a background `cmd1 && git commit && ... &` inside one Bash call runs the whole thing in the background; a `$HOME` or `$TMPDIR` in a call that commits trips the job-copy guard; `$TMPDIR/..` is the HOME, not the scratchpad; do not edit the tree while `tests/run.sh` runs on it; the monitor `^exit` pattern also matches a log line "exit codes" — match `^exit [0-9]+$`; `post-review` needs the reviewer's coverage block in the file and the bare command; `fabric-review next` needs the request's range to be the previous head and `--head` a full 40-char id, and `card_base` set when the range base is `origin/main`.

*Anchors: `tools/fabric/assembler/anchorkeep.py::keep_resolving_anchors`, `tools/fabric/assembler/intake.py::hold_unbound_roles`, `tools/fabric/assembler/slices.py::cited_outside_code`*

*Observed 2026-11-09 (python-dev)*
