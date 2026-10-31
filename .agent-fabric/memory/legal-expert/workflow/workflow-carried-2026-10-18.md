---
role: "legal-expert"
class: workflow
topic: "workflow-carried-2026-10-18"
description: "Reading Swiss federal law from Fedlex needs moli with --wait-selector '#art_1'; WebFetch and moli's default wait get only the splash screen"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "legal-expert-ch"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 71a457d8eaed17f3
  - 72894e3237864a4c
---

## Reading Swiss federal law from Fedlex needs moli with --wait-selector '#art_1'; WebFetch and moli's default wait get only the splash screen

Fedlex (fedlex.admin.ch, the Swiss federal law platform) is an Angular app. WebFetch gets only its "JavaScript required" splash page (tested 2026-10-17 and 2026-10-20). moli 1.1.15 gets the same splash with `--wait-until done`. With `--wait-selector '#lawcontent'` it gets the rendered page shell with the act's metadata (Abkürzung, Inkrafttreten, AS source) but the body is still loading. What works, tested 2026-10-20 on the DSG (`eli/cc/2022/491/de`): 

`moli fetch --dump markdown --wait-selector '#art_1' --timeout 80000 <url> > file.md`

That returns the full consolidated text (82 KB), the SR status line ("Stand am 7. Juli 2025") and the article anchors. Use another article id if an act has no Art. 1. Grep the file; never print it whole.

ELIs read 2026-10-20: PublG `2004/745` (not `2005/14`), ZGB `24/233_245_233`, DSG `2022/491`, BV `1999/404`, BGFA `2002/153`; an unknown ELI is found on the SR index page `/de/cc/internal-law/<n>` (wait for `a[href*="/eli/cc/"]`).

**Why it matters:** from 2026-10-17 to 2026-10-20 moli was missing, and three deliveries had to carry Swiss statements marked unverified (the addenda reissue 7ab8dd7 corrected them, live in the prompt since 2026-10-22). moli is an account tool with an install pin in projects/registry.json, so this login installs it itself with `fabric-tools --install moli`. It does not wait for the owner. Earlier sessions got this wrong and waited.

**How to apply:** before any Swiss opinion, check `moli --version` and install it with `fabric-tools --install moli` if it is missing. Read the act with the command above, and record the SR status date and the AS source the page names. Where the version that matters is in doubt, read the AS text (`/eli/oc/...`). Mark a Swiss citation unverified only when moli truly cannot read it. Related: [[persona-seraina-huber]].

*References: persona-seraina-huber*

*Anchors: `policies/moli-web/SKILL.md::--wait-selector`, `projects/registry.json::"version": "1.1.15"`*

*Observed 2026-10-20 (legal-expert)*
