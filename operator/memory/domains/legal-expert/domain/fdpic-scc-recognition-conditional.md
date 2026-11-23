---
role: "legal-expert"
class: domain
topic: "fdpic-scc-recognition-conditional"
description: Whether the EU 2021 SCCs carry Swiss data under Art. 16(2)(d) DSG — FDPIC recognition is conditional on Swiss adaptations; where to read it; DPF list not queryable here
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "legal-expert-ch"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e0db2227a1e4ab60
---

## Whether the EU 2021 SCCs carry Swiss data under Art. 16(2)(d) DSG — FDPIC recognition is conditional on Swiss adaptations; where to read it; DPF list not queryable here

Art. 16(2)(d) DSG admits standard clauses "die der EDÖB vorgängig genehmigt, ausgestellt oder anerkannt hat" (FR/IT agree). The FDPIC's notice of 27 Aug 2021 recognises the EU SCCs (Decision 2021/914) only "sofern die für eine Verwendung unter Schweizer Datenschutzrecht notwendigen Anpassungen und Ergänzungen vorgenommen werden". The guidance PDF (rev. 12.02.2025, linked from edoeb.admin.ch/de/27082021-ubermittlung-von-personendaten-in-ein-land-ohne-angemessenes-datenschutzniveau) lists them:
- the FDPIC in Annex I.C;
- a Swiss forum under Clause 18(c), "zwingend";
- GDPR references read as DSG ones, except under "Option 2";
- the governing law under Clause 17.

Unadapted SCCs therefore fall outside the recognition. An EU Commission adequacy decision has no Swiss effect: only DSV Annex 1 counts, and it lists the US for Swiss-US DPF-certified organisations only (unchanged since AS 2024 435; DSV status 1 Dec 2025).

Read 2026-11-10 for j19 (opinion docs/legal/2026-11-10-fadp-eu-sccs-openai-us-copy.md, commit 0624d246). That day OpenAI's DPA (1 Dec 2025) had no Swiss adaptations.

**How to apply:** the FDPIC site has no stable paths. Find pages through the sitemap (edoeb.admin.ch/sitemap/de.xml) and read them with moli; the PDFs come with curl and pdftotext. The DPF list (dataprivacyframework.gov/list) renders, but its API (POST dpfapi.azurewebsites.net/api/participants) refused both curl and in-page fetch (CORS), so a DPF certification stays unverified unless the owner checks it. Related: [[workflow-carried-2026-10-18]], [[fadp-art14-representative-reading]].

*References: fadp-art14-representative-reading, workflow-carried-2026-10-18*

*Observed 2026-11-10 (legal-expert)*
