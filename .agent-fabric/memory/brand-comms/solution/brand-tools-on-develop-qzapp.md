---
role: "brand-comms"
class: solution
topic: "brand-tools-on-develop-qzapp"
description: "Where the logo, icon and font tools live on develop-qzapp (resvg, vtracer, scour, fonttools, uharfbuzz), so no throwaway venv is built."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 544f001b9d7ff763
  - 99f7d2982d68cbf9
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
  The `fonttools`, `pyftsubset` and `ttx` commands are not installed,
  because Fedora packages them separately. Run `python3 -m fontTools.subset …`
  and `python3 -m fontTools ttx …` instead; it is the same code
  (devex-tooling, 01a15196-8863).
- `markdown-it-py` 3.0.0 (Fedora's python3-markdown-it-py) imports in
  the system `python3`, which is 3.14 as of 2026-10-24. gzapp.decks'
  `scripts/doc.py` needs it, and its HTML is byte-identical to Node's
  markdown-it 14 in `js-default` mode.
- Also present: potrace, Pillow, numpy, google-chrome.
- fabric-coordinator is listing these tools in the registry for
  gzapi.brand and blueteam.ee with roles [brand-comms], so `fabric-tools`
  can check them in those working copies.

devex-tooling installed these (their j133), at the owner's request.
They arrive through the fedora-43-develop TemplateVM. If one is
missing on another host or qube, ask devex-tooling; don't build a venv
in the scratchpad. A system package is the owner's to install in the
template, followed by a restart of the qube that ends every session
(runtime/provisioning/platform/README.md). Installing it in this qube
is lost at the next restart, and a `! sudo …` typed into a session
fails because there is no terminal for the password. Until the restart,
park the dependent job as blocked and say so; don't wait on it idle.

*Observed 2026-10-19 (brand-comms)*
