---
role: "fabric-coordinator"
class: workflow
topic: "owner-commands-one-line"
description: "A command for the human owner is ONE line, ready after `!`, and I run it (or every part I can) myself first: an untried line cost a live check on 2026-10-10"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2f602b641cbf3ad0
  - 861467ae0fdfb407
---

## A command for the human owner is ONE line, ready after `!`, and I run it (or every part I can) myself first: an untried line cost a live check on 2026-10-10

The owner, 2026-10-10: "when an agent give a command to human to execute, this must be a
one liner". Earlier the same week they answered a multi-line script with "too long - a
one line".

**Why:** the owner runs it by pasting after `!` in a session or in a shell; a multi-line
block breaks on paste, and a heredoc or continuation is easy to cut wrong.

**How to apply:** join steps with `&&` (or `;` when a failure should not stop the
rest); put anything longer in a script in the tree or the scratchpad and give the one
line that runs it; no heredoc, no backslash continuation. To be written into the fabric's
CLAUDE.md "Working here" (my next agent-fabric PR) so every agent applies it.

**Try it before handing it over (the owner, 2026-10-10, "try one liner next time").** The
check-6 line I gave cut the last byte of each token with `head -c -1` on the assumption
that `pass show` adds a newline; the entries had none, both tokens were truncated and the
live check failed with 401s. Run the line (or every part of it that does not need the
owner's hand) in my own session first, against the real inputs, checking shapes without
printing secrets; hand over only what I have seen work, and say which part I could not run.

**"One line" means one line on screen, not one logical line.** A 300-character `&&` chain
wraps to three lines in the owner's terminal and was refused ("thats not a one liner - it
is 3 lines"). Anything past roughly 100 characters goes into a short script (in the
owner-readable place it belongs, e.g. `$XDG_RUNTIME_DIR/<task>/run` for a one-off with
secrets, or the tree), tried with a dry-run switch, and the owner gets `! <path>`;
accepted with "this is a one liner, thank".

*Observed 2026-10-10 (fabric-coordinator)*
