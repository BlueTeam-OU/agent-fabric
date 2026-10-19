---
role: "rust-ui-dev"
class: domain
topic: "terminal-keys-no-collision"
description: "Choosing key bindings for a terminal multiplexer that hosts agent harnesses -- every key reaches the pane; own actions on keys no harness, shell or desktop uses, pinned by a test"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5f69806b1053b93a
---

## Choosing key bindings for a terminal multiplexer that hosts agent harnesses -- every key reaches the pane; own actions on keys no harness, shell or desktop uses, pinned by a test

A multiplexer in front of interactive harnesses must pass every key through unchanged
(ctrl+c even with a selection, ctrl+v, PageUp/PageDown) and keep its own actions on
sequences nobody downstream uses. Check candidates against each harness's keymap (Claude
Code's defaults and chords, Codex CLI's keymap, readline, the tty's own control chars) and
the desktop/terminal emulator's reservations. Terminals often send ctrl+alt+<key> as ESC +
ctrl+<key>, which readline and some harnesses read as a binding (Codex binds ctrl+alt+v to
paste-image). tmux-style ctrl+b is Claude Code's background-task key; ctrl+6 (0x1e) was the
one control key all of them left free. Pin the no-collision list in a byte-for-byte pty
test, and put the pass-through in code, not a config default.

*Observed 2026-10-15 (rust-ui-dev)*
