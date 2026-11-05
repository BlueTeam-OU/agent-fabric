---
role: "fabric-coordinator"
class: workflow
topic: "guard-inert-text-not-parse"
description: "A Bash-command guard decides on text the shell provably never runs (comments, single quotes, quoted heredoc bodies), never on a parse of what runs; one linear pass, over-reports pinned in the test"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1c79007347241555
---

## A Bash-command guard decides on text the shell provably never runs (comments, single quotes, quoted heredoc bodies), never on a parse of what runs; one linear pass, over-reports pinned in the test

#451 (j540), post-review-shape-guard.py: two review rounds broke two designs. A text regex over command positions let `time …`, `{ …; }`, `bash -c "…"` through, denied quoted mentions and was quadratic (22 s). A shlex walk of command positions let `"$(…)"`, `time -p`, `sudo -E bash -c`, `bash <<EOF` through, went quadratic on `x;`×50k and on a DOTALL heredoc regex (21 s), and recursed into a RecursionError on nested eval (the hook exited 1, which the harness reads as no objection). The third design inverted the question. The command is refused unless every mention is in inert text, meaning a comment, a single-quoted string or a quoted-delimiter heredoc body; inert text counts as live again when a shell, eval or source is named. The check is one linear character pass, and BARE is greedy over classes that exclude `<`.

**Why:** a guard against a habit does not need to know what runs; it needs a safe default. Every parse of what runs leaves the next wrapper through, and pipe-status-guard's history showed the same ("each narrower rule left one").

**How to apply:** for any new PreToolUse Bash guard:
- Over-report by default, and carve out only the text the shell never runs.
- Pin the over-reported cases in their own test list, and have the deny name the way through.
- Time-test adversarial shapes: glued separators, many short commands, unterminated heredocs, nested eval, and a long run of spaces after the bare prefix.
- Catch every exception into a deny, not an exit 1.

Related: [[post-review-run-bare]], [[lint-overreport-not-model]], [[checks-need-a-control]].

*References: checks-need-a-control, lint-overreport-not-model, post-review-run-bare*

*Anchors: `runtime/claude-code/hooks/post-review-shape-guard.py::live_text`, `tests/test_post_review_shape_guard.py::over_reported`*

*Observed 2026-11-01 (fabric-coordinator)*
