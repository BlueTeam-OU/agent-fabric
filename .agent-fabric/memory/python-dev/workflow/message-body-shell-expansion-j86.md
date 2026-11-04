---
role: "python-dev"
class: workflow
topic: "message-body-shell-expansion-j86"
description: A backtick or $() in a gzcoord message written through the shell runs a command; write the body with a quoted heredoc or the Write tool
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5f709c8aca90f36c
---

## A backtick or $() in a gzcoord message written through the shell runs a command; write the body with a quoted heredoc or the Write tool

During the rule 13 live check (j85/j86) a message body with a backtick in it, written through an unquoted shell string, executed `chmod 1777` with no argument instead of printing it.

**Why:** the text between backticks is a command substitution to bash; the message went out with the output spliced in.

**How to apply:** write a message file with the Write tool or a quoted `<<'EOF'` heredoc, then `gzcoord-send <file>`; the same goes for commit bodies. See [[roster-row-admit-j83]].

*References: roster-row-admit-j83*

*Anchors: `tools/fabric/gzcoord/send.py::main`*

*Observed 2026-10-27 (python-dev)*
