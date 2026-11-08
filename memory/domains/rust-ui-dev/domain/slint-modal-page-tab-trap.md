---
role: "rust-ui-dev"
class: domain
topic: "slint-modal-page-tab-trap"
description: "a Slint modal page or a dialog over it lets TAB walk out to what is behind; a TapArea is no focus stop; a two-stop order test passes a mutant"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 476d66422478b20a
---

## a Slint modal page or a dialog over it lets TAB walk out to what is behind; a TapArea is no focus stop; a two-stop order test passes a mutant

Slint 1.18's TAB navigation runs over the whole window's focus chain. On a page drawn over the window (the InterWeave identity page, a FocusScope over Chats), TAB past the page's last stop goes on to the controls behind it (measured: conversations-heading, then app-options). The page has to take Tab/Backtab in its own key-pressed and move focus over its own stops. The InterWeave way is a focus-target plus a focus-seq bump, which each stop's `changed focus-seq` turns into focus(). A TapArea or a Rectangle with accessible-role: button is NOT a keyboard stop: it gets no TAB focus and writes no focus= trace line. Make it a FocusScope that handles Return/Space. Both were fixed in InterWeave e87e1462 (j200, 2026-11-03); tests in crates/human/ui-slint/tests/trace.rs.

**How to apply:** for any overlay or modal page, test that TAB comes round again (the trace shows only the page's own keys), and give every action a focus key.

**A dialog over the page is a second trap (j208, #544 F5, fixed 22321132).** The ActionButtons inside the dialog reject TAB, so it bubbles up to the page's handler, which steps over the page's stops from a stale focus-id and lands behind the scrim. Put a FocusScope inside the dialog (focus-on-click and focus-on-tab-navigation false) that takes Tab/Backtab and focuses its named buttons directly (`b.has-focus`/`b.focus()`). The page handler also has to cover the case where focus is still behind the scrim: the dialog's opening focus is a deferred `changed`, so in the testing backend the first key still arrives at the page. A modal's ordering test needs three or more stops: with two, next(1) and next(-1) reach the same stop, so a mutant passes (F6).

*Observed 2026-11-03 (rust-ui-dev)*
