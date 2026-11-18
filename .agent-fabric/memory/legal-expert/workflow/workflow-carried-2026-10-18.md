---
role: "legal-expert"
class: workflow
topic: "workflow-carried-2026-10-18"
description: "Reading Swiss federal law from Fedlex needs moli with --wait-selector '#art_1'; WebFetch gets only the splash screen, and moli's default wait a splash (1.1.19) or an empty dump (1.1.23)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "legal-expert-ch"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1f12466b8051c34d
  - 71a457d8eaed17f3
  - b3c29867664a6e2b
---

## Reading Swiss federal law from Fedlex needs moli with --wait-selector '#art_1'; WebFetch gets only the splash screen, and moli's default wait a splash (1.1.19) or an empty dump (1.1.23)

Fedlex (fedlex.admin.ch, the Swiss federal law platform) is an Angular app. WebFetch gets only its "JavaScript required" splash page (tested 2026-10-17 and 2026-10-20).

**Without --wait-selector, moli gets nothing usable**, and what it gets depends on the version:
- On 1.1.15 and 1.1.19, `--wait-until done` gives the 1.2 KB splash (re-tested 2026-11-01).
- On 1.1.23 it gives an **empty dump and still exits 0**. devex-tooling's smoke test (REQUEST 01a1c620) reported this, and fabric-coordinator relayed it (01a1cba8). I have not re-run it myself. An empty file is therefore a failed read, never "no such text".
- `--wait-selector '#lawcontent'` gives the page shell with the act's metadata, but the body is still loading.

**What works** on 1.1.15, 1.1.19 and, by devex-tooling's smoke test, 1.1.23:

`moli fetch --dump markdown --wait-selector '#art_1' --timeout 80000 <url> > file.md`

It returns the full consolidated text, the SR status line ("Stand am …", "État le …") and the article anchors. Use another article id if an act has no Art. 1.
- Read 2026-11-11 on 1.1.19: the CO in de/fr/it, about 1.3 MB each, "Stand am 1. Oktober 2026".
- devex-tooling's smoke test on 1.1.23: the ZGB, 1206 KB.
- Grep the file, or slice it with a script; never print it whole.
- Lettered articles have the anchor `#art_335_a` and the heading `Art. 335***a*`. Match on the anchor.

ELIs read: PublG `2004/745`, ZGB `24/233_245_233`, DSG `2022/491`, BV `1999/404`, BGFA `2002/153`, OR `27/317_321_377`. An unknown ELI is found on the SR index page `/de/cc/internal-law/<n>` (wait for `a[href*="/eli/cc/"]`).

**Why it matters:** from 2026-10-17 to 2026-10-20 moli was missing, and three deliveries had to carry Swiss statements marked unverified. moli is an account tool, pinned in projects/registry.json. This login installs it itself (`fabric-tools --install moli`) and does not wait for the owner.

**How to apply:** before any Swiss opinion:
1. Check `moli --version` against the registry's current pin, and install if it is missing or behind.
2. Read the act with the command above.
3. Check that the file is non-empty and carries the status line.
4. Record the SR status date and the AS source the page names. Where the version that matters is in doubt, read the AS text (`/eli/oc/...`).
5. Mark a Swiss citation unverified only when moli truly cannot read it.

Related: [[persona-seraina-huber]], [[ch-co-361-362-lists]].

*References: ch-co-361-362-lists, persona-seraina-huber*

*Anchors: `policies/moli-web/SKILL.md::--wait-selector`*

*Observed 2026-11-11 (legal-expert)*
