---
role: "python-dev"
class: workflow
topic: "gzcoord-send-empty-body-lessons"
description: "#261 gzcoord-send empty-section refusal — dictionary keys are outside the python-dev entry, the i18n test reads only literal t(\"...\") calls"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4041a37287de5962
---

## #261 gzcoord-send empty-section refusal — dictionary keys are outside the python-dev entry, the i18n test reads only literal t("...") calls

#261 (merged 2026-10-14): `send.empty_body` refuses a message whose own section is empty. A new user-facing line needs a key in `communication/gzcoord/i18n/en-US.json` plus every active locale (ru, ka): outside the python-dev entry, so ask fabric-coordinator early with the exact text and placeholders; they commit en-US and ask the language-culture holders, onto your branch.

**Why:** tests/test_gzcoord_i18n.py finds used keys only as literal `t("key")` calls; `t(key_variable)` reads as "nothing prints it" and goes red. A joiner word in code (" or ".join) is English in every locale — use one key per shape.

**How to apply:** two literal calls in two branches; fold the supplied commits unrebased and re-run the full suite (it exceeds 600 s: background it). `settings`-style fixtures that built a typed message without its own section (the `addressed()` OBSERVATION) must now carry one. Fill a composed skeleton by a script and read the file before sending: an exception between compose and send still sent an empty INFO once.

*Anchors: `tools/fabric/gzcoord/send.py::empty_body`*

*Observed 2026-10-14 (python-dev)*
