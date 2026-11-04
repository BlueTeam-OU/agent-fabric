---
role: "fabric-coordinator"
class: workflow
topic: "post-review-run-bare"
description: "fabric-pr is already allowed by a Bash(fabric-pr *) permission rule (commands.json → user settings); run `fabric-pr post-review [--repo o/n] N < report` as one bare command, no `cd … &&` or trailing commands, so the rule matches and the…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7c0ef2bccfc24aa6
---

## fabric-pr is already allowed by a Bash(fabric-pr *) permission rule (commands.json → user settings); run `fabric-pr post-review [--repo o/n] N < report` as one bare command, no `cd … &&` or trailing commands, so the rule matches and the classifier is not asked

On 2026-10-27, `fabric-pr post-review` of my own PR was refused by the auto-mode classifier twice, and python-dev-03 was refused once on #400. A refusal holds for the rest of the session, so the owner had to post by hand. Adding a prose allow entry to policies/auto-mode.json (#396) did not stop it. The real permission already exists: `runtime/claude-code/commands.json` lists `fabric-pr`, and `user-settings.py` writes `Bash(fabric-pr *)` into every account's settings (mine has it). The refused calls were compound commands (`cd <worktree> && fabric-pr post-review N < f; git log …`), and a compound with a `cd` or a second command does not match a `Bash(fabric-pr *)` prefix rule, so it goes to the classifier. Some cd-prefixed posts did pass, so this is likely, not proven.

**Why:** a refusal holds for the whole session and hands the post to the owner, who then has to run another login's script in that login's pane.

**How to apply:** post with one bare command, `fabric-pr post-review <n> < <report>`, using `--repo <owner/name>` for another repository instead of `cd`, with nothing chained before or after. Related: [[post-review-self-approval-refused]], [[post-review-own-pr-only]].

*References: post-review-own-pr-only, post-review-self-approval-refused*

*Anchors: `runtime/claude-code/commands.json`, `runtime/claude-code/user-settings.py`*

*Observed 2026-10-27 (fabric-coordinator)*
