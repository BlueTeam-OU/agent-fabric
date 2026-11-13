# ADR-070 — This organisation's porting programme: its projects' Node scripts move to Python

**Date:** 2026-11-12
**Status:** Accepted
**Ratified:** owner, 2026-11-11, the answer to the classification's question (docs/split/move-plan.md §5, ADR-045 A 2026-11-11): the records are split, and ADR-040's own ratification, owner, 2026-09-30, by the merge of agent-fabric #70 (f15baa2), with the owner's request of 2026-10-19 for Wave 10, carries to the rule and the rows moved here
**Decision Makers:** the owner (Wave 10, the managed projects' Node scripts to Python); drafted by fabric-coordinator
**Scope:** Wave 10: which of this organisation's managed projects' Node scripts are ported to Python, deleted or exempt, and who holds each; not the language of the fabric's own code, which is ADR-040
**Pillar:** P1
**Class:** organisational

## 1. Context and Problem

ADR-040 set Python as the fabric's implementation language and ported the fabric's own scripts in waves 0 to 9. Its rule 10 and §7's Wave 10 rows went further, to the Node scripts of this organisation's managed projects (gzapp, gzapp.decks, blueteam.ee, gzapi.ge, herdr), a porting programme the owner asked for. That is one organisation's work on its own projects, not a rule of the engine: rules 1 to 9 and waves 0 to 9 bind the fabric's own code and are what the shims cite. When ADR-040 was split under ADR-045 §5 rule 4 the programme moved here, its text unchanged but for the citations that named ADR-040's other sections; ADR-040 keeps the number and its rules 1 to 9.

Wave 10 ports the managed projects' Node scripts. When it was set the
projects held 16 `.mjs` scripts of their own, 2,897 lines, beside the
framework configurations; the fabric itself has none since Wave 8.
Each port is the holder's of the path in its project's taxonomy, one
pull request per project and holder, under that project's arming rules.

| project | what | files | lines | holder | note |
|---|---|---|---|---|---|
| gzapp | `tools/validate_api_surface/`: `deprecated-refs.mjs`, `validate.js` and their three tests | 5 | 1,601 | devex-tooling | YAML: the project's own dependency, not the fabric's standard-library rule. `validate.js` joins the wave with the two tests that import it; the old script is the oracle on the four real documents, and the OpenAPI validator that replaces its check 4 is the holder's choice |
| gzapp | `tools/one-shot/split_adr_amendments.mjs` | 1 | 327 | devex-tooling | deleted, not ported: it ran once |
| gzapp | `tools/build_glyphs/build-glyphs.mjs` | 1 | 271 | devex-tooling | exempt: fontnik and `@mapbox/glyph-pbf-composite` are native Node addons with no Python binding, and `check` compares the committed glyph ranges byte for byte with a fresh render, which a Python rasteriser would not reproduce (its holder's finding) |
| gzapp | `apps/admin_web/scripts/import-table.mjs` | 1 | 157 | web-dev | exempt: it walks the AST of the project's pinned TypeScript compiler, which has no Python binding; a re-implementation missed real imports (its holder's proposal) |
| gzapp.decks | `scripts/*.mjs` | 8 | 1,092 | brand-comms | `doc.mjs` drives puppeteer: exempt or ported to the fleet's browser, the holder says |
| blueteam.ee | `deploy/check-dist.mjs` | 1 | 109 | edge-hosting | the taxonomy's note gives it the deploy; its paths are empty |

`astro.config.mjs` in blueteam.ee and gzapi.ge is exempt (rule 1). herdr's `scripts/docs/*.mjs` came from
the upstream FleetDeck tracks (`herdrdev/herdr`) and stay as they are.

## 2. Decision

The managed projects' Node scripts are ported to Python in Wave 10, by the rule in §5 and the inventory in §1.

## 3. Alternatives Considered

- **No port wave in a project** (ADR-040 §5 rule 9, which stands for bash): a script a project changes is ported when it changes. Rejected for Node by the owner's request: the managed projects' Node scripts were to move as one wave, each holder one pull request.
- **Port everything, application code included.** Rejected: a project's TypeScript or JavaScript application, its packages and its build are the product, in the language the product chose.

## 4. Rationale

The same reasons as ADR-040 §1: a script's bugs cluster in what the language makes easy to get wrong, and the fabric keeps one standard-library language for its scripts. The exemptions are the cases where a port would be wrong or impossible: a fork's upstream code, a framework's own configuration, a script bound to a Node library.

## 5. Binding Rules

1. A managed project's own Node scripts move to Python in Wave 10
   (§1), the one port wave a project has; the owner asked for it. A `.mjs` file a project runs as a script, written
   by us, is ported, and none is added; one a fork took from the
   upstream it tracks stays the upstream's and is never ported (it
   would only make the fork diverge), and a project's application
   code (a TypeScript or JavaScript app, its packages and its build)
   is the product, in the language the product chose, never a script
   to port; a `.js` or `.cjs` script of ours may join the wave, and one
   that is to be updated or fixed is ported instead. Exempt, and named in the wave's
   inventory with why: a framework's own configuration it loads itself
   (`astro.config.mjs`), and a script that works inside a Node library's
   API with no Python counterpart (gzapp's `import-table.mjs`, bound to
   the pinned TypeScript compiler). An
   exemption a holder finds is proposed to the coordinator and added to
   the inventory, never assumed. A port follows ADR-040 §5 rules 3 to 5: the
   contract frozen, the command kept, the old script the oracle. ADR-040 §5 rule 9's "no port waves in a project" stands for bash.

## 6. Consequences

- Each port is the holder's of the path in its project's taxonomy, one pull request per project and holder, under that project's arming rules.
- A managed project's copies and forwarders are the project's: after the wave, its owners are told which module replaced which script (ADR-040 §6).

## 7. Future Evolution

A new Node script of ours in a project is not added (rule 1); an exemption a holder finds is proposed and added to the inventory in §1.

## 8. Decision Status

Accepted. Wave 10 is dispatched: the managed projects' Node scripts are ported by their holders.

## References

- ADR-040 — the language, rules 1 to 9, waves 0 to 9; the record this one was split from.
- ADR-045 §5 rule 4 — a mixed record is split.
- ADR-011 — a project's code is its own.
