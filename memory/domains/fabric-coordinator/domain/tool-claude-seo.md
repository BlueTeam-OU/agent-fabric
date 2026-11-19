---
role: "fabric-coordinator"
class: domain
topic: "tool-claude-seo"
description: "claude-seo (github.com/<owner>/claude-seo): a Claude Code SEO plugin; evaluated 2026-11-10 at the owner's ask, told to brand-comms; not installed — ADR-043 makes it a rule 5/8 proposal"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fb759fcfbca7cf79
---

## claude-seo (github.com/<owner>/claude-seo): a Claude Code SEO plugin; evaluated 2026-11-10 at the owner's ask, told to brand-comms; not installed — ADR-043 makes it a rule 5/8 proposal

What it is (read 2026-11-10 from the repository page with moli and the GitHub API; owner a User account, MIT, v2.5.0,
created 2026-02-07, last push 2026-11-01, ~27.9k stars): a Claude Code plugin (`.claude-plugin/plugin.json`,
marketplace `agricidaniel-claude-seo`, installed by `/plugin install` or an `install.sh`) with 26 skills and 19
subagents under `/seo …`: site audit fanned out to parallel agents, technical SEO, E-E-A-T content checks, Schema.org
detect/validate/generate, sitemaps, hreflang, Core Web Vitals, local/maps, backlinks (Moz, Bing, Common Crawl),
e-commerce, GEO/AEO (AI Overviews), "agent readiness" (llms.txt, WebMCP, Lighthouse agentic), drift monitoring in
SQLite, and Google APIs (GSC, PageSpeed, CrUX, GA4, Indexing) with PDF/Excel reports. About 60 Python scripts under
`scripts/`. `/seo setup` builds its own Python venv and a Chromium. Nine optional extensions (Ahrefs, DataForSEO,
Firecrawl, SE Ranking, Profound, Bing Webmaster, Matomo, Unlighthouse, an image generator), each with its own
install.sh and mostly MCP servers on paid accounts with your own keys. One hook: PostToolUse on Edit|Write, exec form,
`node run-python-hook.js validate-schema.py <file_path>`, which feeds JSON-LD errors back (exit 2).

**What it means for the fleet:** nothing loads it as is. On a fleet host a user-installed plugin never loads
(ADR-043 rule 1, `allowManagedModsOnly`, `disableSideloadFlags`). Using it is a rule 5 proposal to the coordinator:
`claude plugin validate`, its hooks and calls named, a blind review, and an install into the managed marketplace.
Its scripts run through Bash, so the fleet's guards see them. Its MCP extensions fall under rule 8: each server
reviewed and pinned in `allowedMcpServers`, so none comes before that. Its setup downloads a browser and a
venv, so it meets the tools-install path (pinned versions), not an ad-hoc `pip`/`npx`. The cheaper path for
brand work: read its skills as references (checklists for schema, hreflang, E-E-A-T, llms.txt), and run audits
with moli fetch, which the fleet already has.

**Who was told:** brand-comms, 2026-11-10 (INFO), as something that exists; no install offered.
See [[external-tools-evaluated]], [[moli-approved-for-web]].

*References: external-tools-evaluated, moli-approved-for-web*

*Observed 2026-11-10 (fabric-coordinator)*
