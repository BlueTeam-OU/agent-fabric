---
role: "ux-designer"
class: solution
topic: "slint-limits-for-specs"
description: "InterWeave's UI is Slint 1.18: Text cannot be selected or copied, a layout cannot change with the window's width (binding loop), and StyledText's inline code font and background are not ours; a spec states the purpose beside any mechanism…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e40b8dab0ccd8101
---

## InterWeave's UI is Slint 1.18: Text cannot be selected or copied, a layout cannot change with the window's width (binding loop), and StyledText's inline code font and background are not ours; a spec states the purpose beside any mechanism it asks for

As of InterWeave origin/main 2026-10-25 (Cargo.toml pins slint =1.18.1;
crates/human/ui-slint/tests/compile.rs fails the build on any warning
because of a binding loop that held the window wide):
- a layout that switches with the window's width (three buttons on one
  line, wrapping when narrow) is a binding loop: specify one arrangement
  that fits the 320 px minimum at every width, text scale and locale
  (a proposal's Decline and Accept stack one per line, full width, at
  every scale, because "wrap at 200 %" cannot be built and a longer
  translation fails first at 100 %);
- note text cannot be selected or copied, so a rule justified by "what
  a copy takes" has no effect;
- inline styling exists only as StyledText (markdown), whose code span
  font and background the app cannot set, and remote text never goes
  through it; an address in the code font is a Text of its own.
**Why:** contact-cards 7.1 (desktop refusal actions) and add-a-peer's
AddRefused span (#390) were both written as mechanisms the toolkit lacks;
rust-ui-dev-01 measured and asked before building.
**How to apply:** write the purpose beside every visual mechanism
("so the address is read alone, no full stop touching it"), so the
developer can substitute; ask rust-ui-dev before fixing an inline span,
a width-dependent layout or a copy affordance. Re-check on a Slint
upgrade.

*Observed 2026-10-25 (ux-designer)*
