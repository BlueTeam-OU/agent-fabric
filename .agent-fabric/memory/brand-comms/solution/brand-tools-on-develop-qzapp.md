---
role: "brand-comms"
class: solution
topic: "brand-tools-on-develop-qzapp"
description: "Where the logo, icon and font tools live on develop-qzapp (resvg, vtracer, scour, fonttools, uharfbuzz), so no throwaway venv is built."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 544f001b9d7ff763
---

## Where the logo, icon and font tools live on develop-qzapp (resvg, vtracer, scour, fonttools, uharfbuzz), so no throwaway venv is built.

As of 2026-10-18, verified from brand-comms-01's shell:
- `resvg` (/usr/local/bin): SVG to PNG. Use it for icons and favicons
  instead of driving headless Chrome.
- `vtracer` (/usr/local/bin): traces a colour image to SVG. `potrace`
  traces one colour at a time.
- `scour` (/usr/bin): optimises an SVG before commit. svgo is not
  installed on purpose: it is not packaged, and installing it would
  need a global npm install.
- `fontTools` 4.61 and `uharfbuzz` 0.51.5 import in the **system
  `python3`**, not in fabric-python, which stays stdlib-only. Use them
  to instance a variable font, shape text with kerning, and outline a
  wordmark into SVG paths.
- Also present: potrace, Pillow, numpy, google-chrome.

devex-tooling installed these (their j133), at the owner's request.
They arrive through the fedora-43-develop TemplateVM. If one is
missing on another host or qube, ask devex-tooling; don't build a venv
in the scratchpad.

*Observed 2026-10-18 (brand-comms)*
