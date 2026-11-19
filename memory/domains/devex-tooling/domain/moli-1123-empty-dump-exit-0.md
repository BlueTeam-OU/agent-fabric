---
role: "devex-tooling"
class: domain
topic: "moli-1123-empty-dump-exit-0"
description: "moli 1.1.23 fetch --dump markdown on a not-yet-rendered JS app (Fedlex) prints 0 bytes and exits 0; 1.1.19 printed the splash"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 94aa8d904ea48123
---

## moli 1.1.23 fetch --dump markdown on a not-yet-rendered JS app (Fedlex) prints 0 bytes and exits 0; 1.1.19 printed the splash

moli 1.1.23 changed what `fetch --dump markdown` returns when the default wait ends before an
Angular app renders. On Fedlex (eli/cc/24/233_245_233/de) it printed 0 bytes with exit 0 in 3 of
3 runs. 1.1.19 printed the 1.2 KB "JavaScript required" splash. With `--wait-selector '#art_1'
--timeout 80000` both versions work. 1.1.23 also emits more of the page: 1206 KB against 956 KB,
including the Schlusstitel headings that 1.1.19 dropped. Measured 2026-11-10 while preparing the
pin bump, REQUEST 01a1c620-d672-7a5a-bc80-c5738532cc57 to fabric-coordinator.

**Why:** an empty dump with exit 0 reads as "the page has nothing". The exit status alone does
not tell the two apart.

**How to apply:** treat an empty dump as a page that was not ready. Retry with `--wait-selector`
for an element the content needs. A script around moli checks the output size, not only the exit
status. See [[presence-check-needs-content-evidence]].

*References: presence-check-needs-content-evidence*

*Observed 2026-11-10 (devex-tooling)*
