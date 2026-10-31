---
role: "rust-ui-dev"
class: domain
topic: "slint-name-clash-traps"
description: "Slint 1.18 traps -- a component property named row/text shadows builtins; indentation in app.slint lies about nesting"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 3ad61d79f2f64509
---

## Slint 1.18 traps -- a component property named row/text shadows builtins; indentation in app.slint lies about nesting

Seen building the card screens (j53, 2026-10-24, `crates/human/ui-slint/ui/app.slint`):

1. A component inheriting Rectangle cannot declare `in property <T> row` ("Cannot override
   property 'row'": a grid-layout builtin). Name it `card`, `item`, etc.
2. A component with its own `text` property makes `accessible-role: text;` in a child resolve to
   that property ("Cannot convert string to AccessibleRole"). Name the property `value`.
3. app.slint's indentation does not follow its braces (the message row's `for` closes at a
   misleading indent). Never splice by indent or by "the first `}` after X": compute brace depth
   from the parent element's opening line. A loop placed inside the per-message row repeated
   zero times with no messages, and only the tree dump showed it.
4. A slice between two marker comments must check the second marker occurs once and after the
   first: a comment repeated earlier in the file made `s[a:b]` empty and duplicated a third of
   the window.
5. An element created by the same press that bumps `focus-seq` never sees the change: give it a
   one-shot `Timer` that focuses it (the Details/share pattern). In tests, advance mock time over
   two turns (`mock_elapsed_time` + `update_timers_and_animations`).

**How to apply:** before editing app.slint by script, print brace depth at the insertion point.
Related: [[slint-layout-traps-seen-rendered]].

*References: slint-layout-traps-seen-rendered*

*Observed 2026-10-24 (rust-ui-dev)*
