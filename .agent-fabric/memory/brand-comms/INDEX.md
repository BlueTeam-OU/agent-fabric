---
role: "brand-comms"
class: index
description: "What brand-comms knows and where it lives."
tier: 1
distilled_at: "2026-10-18"
---

# brand-comms — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/brand-comms/charter.md`](identities/roles/brand-comms/charter.md) — The company's public voice on every surface that is not the product: brand, bilingual copy, decks, the website's content, assets and what may be claimed.

## brief

- [`identities/roles/brand-comms/brief.md`](identities/roles/brand-comms/brief.md) — How brand-comms works day to day, in any project: authors every language, keeps the brand's source of authority its own, checks claims by audience, proposes and holds the gate while the owner decides.

## domain

- [`memory/domains/brand-comms/domain.md`](memory/domains/brand-comms/domain.md) — The three instruments a national innovation agency offers startups — staged accelerator grants, matching grants, regional grants — with the figures verified 2026-09-17 for the one this company applies to.
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## solution

- [`.agent-fabric/memory/brand-comms/solution/avatar-style-guide.md`](.agent-fabric/memory/brand-comms/solution/avatar-style-guide.md) — ADR-056 avatar generation — where the style guide is, the fixed prompt template, and what gpt-image-1 does with framing words
- [`.agent-fabric/memory/brand-comms/solution/blueteam-brand-repo.md`](.agent-fabric/memory/brand-comms/solution/blueteam-brand-repo.md) — blueteam.brand is BlueTeam OÜ's brand source of authority (created 2026-10-15); blueteam.ee copies its tokens at a pinned commit
- [`.agent-fabric/memory/brand-comms/solution/brand-tools-on-develop-qzapp.md`](.agent-fabric/memory/brand-comms/solution/brand-tools-on-develop-qzapp.md) — Where the logo, icon and font tools live on develop-qzapp (resvg, vtracer, scour, fonttools, uharfbuzz), so no throwaway venv is built.

## rationale

- [`.agent-fabric/memory/brand-comms/rationale/blueteam-logo-woven-star.md`](.agent-fabric/memory/brand-comms/rationale/blueteam-logo-woven-star.md) — Owner's 2026-10-15 rulings on the new BlueTeam logo (woven star, Outfit wordmark, one blue) and how the mark was made
- [`.agent-fabric/memory/brand-comms/rationale/blueteam-positioning-human-plus-agentic.md`](.agent-fabric/memory/brand-comms/rationale/blueteam-positioning-human-plus-agentic.md) — Owner ruling on how blueteam.ee characterises BlueTeam OÜ — human consultants plus agentic efficiency; no team page yet

## workflow

- [`.agent-fabric/memory/brand-comms/workflow/agent-store-written-only-by-its-tool.md`](.agent-fabric/memory/brand-comms/workflow/agent-store-written-only-by-its-tool.md) — An agent's fabric-agent-<id> repository is its secrets store — never clone, commit or push to it by hand, even for persona files
- [`.agent-fabric/memory/brand-comms/workflow/avatar-appearance-follows-surname-culture.md`](.agent-fabric/memory/brand-comms/workflow/avatar-appearance-follows-surname-culture.md) — ADR-056 avatars — the face is drawn from the surname's culture (the surnames.json `from`), not cast freely; the owner's ruling
- [`.agent-fabric/memory/brand-comms/workflow/blueteam-owner-wants-imagery-flag-curves.md`](.agent-fabric/memory/brand-comms/workflow/blueteam-owner-wants-imagery-flag-curves.md) — What the owner rejects and wants in blueteam.ee's look — never a text-only page; the flag's blue/black/white sections with curves; woven imagery
- [`.agent-fabric/memory/brand-comms/workflow/finding-in-one-language-check-the-other.md`](.agent-fabric/memory/brand-comms/workflow/finding-in-one-language-check-the-other.md) — When a language review finds a defect in one language, or a ruling changes one language, check the same span in every other language against the same rule before release
- [`.agent-fabric/memory/brand-comms/workflow/fleet-avatars-kept-current.md`](.agent-fabric/memory/brand-comms/workflow/fleet-avatars-kept-current.md) — Owner standing instruction 2026-10-16 — a new agent gets its avatar drawn as soon as it can be, and the fleet sheet is rebuilt after every draw
- [`.agent-fabric/memory/brand-comms/workflow/publish-request-after-merges-settle.md`](.agent-fabric/memory/brand-comms/workflow/publish-request-after-merges-settle.md) — When asking edge-hosting to publish a site, wait until the owner's run of merges settles; if main moves after the request, send an update naming the new commit and its delta.
- [`.agent-fabric/memory/brand-comms/workflow/third-party-names-from-their-own-pages.md`](.agent-fabric/memory/brand-comms/workflow/third-party-names-from-their-own-pages.md) — A partner's or venue's name on a brand surface — check it against the institution's own pages in each language; a name from memory can belong to a different site of the same institution

## recall

- [`identities/roles/brand-comms/recall.md`](identities/roles/brand-comms/recall.md) — Where brand-comms's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
