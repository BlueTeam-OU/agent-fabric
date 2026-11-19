---
role: "fabric-coordinator"
class: solution
topic: "self-kill-guard-data-heredoc"
description: "why a message body naming a watch's pid was denied by the self-kill guard, and which heredoc readers count as data"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a66ec07ca29794cb
---

## why a message body naming a watch's pid was denied by the self-kill guard, and which heredoc readers count as data

runtime/claude-code/hooks/self-kill-guard.py: kills() and pid_candidates() searched the raw command
text, heredoc bodies included, while lift()/unevaluated() already dropped bodies not read by a shell —
so `gzcoord-send - <<X` naming a live watch's pid was denied as killing it (j866, OBSERVATION 01a1d8ab).
Fixed in 73ad2775 (#612): drop_data_heredoc_bodies drops a body only when every command on the opening
line is in DATA_READERS (cat, tee, gzcoord-send, gzcoord-compose, gzmsg). git and gh were left out on
purpose: an alias (`git -c alias.x='!sh' x`, `gh alias set --shell`) runs a shell on stdin, which
SHELLS and tool_commands miss. Quoted args (`--body "kill <pid>"`) still deny — rephrase via heredoc/file.
Probing this guard: write the probe script with the Write tool; a Bash line holding kill + a live pid
is refused by the guard itself.

*Anchors: `runtime/claude-code/hooks/self-kill-guard.py::DATA_READERS`, `runtime/claude-code/hooks/self-kill-guard.py::drop_data_heredoc_bodies`*

*Observed 2026-11-14 (fabric-coordinator)*
