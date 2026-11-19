---
role: "legal-expert"
class: solution
topic: "disclaimer-page-redraft-j29"
description: "blueteam.ee disclaimer (service-scope) page plain-language redraft — where it is, what conditions it holds under, who places it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "legal-expert-ee-eu"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f3619a19d46b3988
---

## blueteam.ee disclaimer (service-scope) page plain-language redraft — where it is, what conditions it holds under, who places it

The plain-language redraft of blueteam.ee `src/pages/disclaimer.astro` (owner go 2026-11-11, incl. "where it differs from this page, the contract applies") is `docs/legal/2026-11-11-disclaimer-service-scope-blueteam-ee-draft.md`, commits 24438c43 and 89b25462 (#560 F4: At-a-glance AI bullet now says "every deliverable produced with AI is reviewed independently, and a consultant is responsible", matching its section) on `develop-qzapp/legal-expert-ee-eu/for/user/j29-disclaimer-plain-scope`. On 2026-11-11 it went to brand-comms-01 to place it (REQUEST 01a1cbbb-7b5b) and to `user` to fold it (REQUEST 01a1cbbb-7d25); folded onto agent-fabric #560 (merge cb2399a5), brand-comms-01 placing it as its j57.

It holds only if BlueTeam issues no crypto-assets, holds none for others, runs no trading platform and takes Bitcoin as payment only, and if the AI Act conditions hold ([[ai-act-scope-sentence-condition]]). Before any consumer-facing service starts, the liability paragraph is read again against VÕS § 42(3).

**Why:** a register edit to the liability section, the crypto "We do not" list or the AI Scope paragraph can change what the page excludes, so that kind of edit comes back to legal-expert ([[legal-wording-over-language-culture]]).
Native-read sync (j31) is 50e6e791 on the same branch, pushed 2026-11-11; INFO 01a1cbe1 asked the coordinator to fold it onto #560.
Second MiCA read (j32, REQUEST 01a1cbe0 from brand-comms-01, REPLY 01a1cbe3): 049e6b86 on the same branch, pushed 2026-11-11, INFO 01a1cbe6 asked the coordinator to fold it onto #560. It adds "funds (money)", "We are also not", the Art 3(1)(16) list as examples, and a point (h)/Art 3(1)(24) sentence that holds only while BlueTeam gives no client personalised recommendations on crypto-asset transactions or on which crypto-asset services/providers to use (not stated by the owner in those words; if that changes, the sentence comes back).
Third MiCA read (j33, REQUEST 01a1cc24, REPLY 01a1cc26): 7c691e3b on the same branch, pushed 2026-11-11 — point (h) clause split into its own sentence with "advice on crypto-assets" quoted; owner confirmed 2026-11-11 the company recommends no crypto-asset services/providers to clients (section 4 now a supplied fact). #560 merged (13d5b230) at 89b25462 only, so 50e6e791, 049e6b86 and 7c691e3b need a new fold; INFO 01a1cc29 told fabric-coordinator.
Placed on blueteam.ee main at d30dba0 (brand-comms-01 REPLY 01a1cc41, 2026-11-11); MiCA paragraph read there and matches the accepted span. Upload to the host (edge-hosting) still pending at that date.
j34 (2026-11-12, REQUEST 01a1cfc2, REPLY 01a1cfc4): owner ruled the "How we use AI" section takes the crypto section's shape (plain bullets + small legal paragraph), blueteam.ee 6ba3fb7 on brand-comms-01's j61 branch. Ruled: bullets 1, 2, "the AI Act" pointer and the legal paragraph hold; bullet 3 reworded (general-purpose AI models; offer or use high-risk systems of our own; build or use for prohibited purposes); bullet 4 reworded to keep the Art 3(3) condition ("that you offer or use under your own name"), and Art 25(1)(a),(b) named as a condition. Pending: language-culture-en native read; then sync docs/legal's draft of the page in one commit (promised in the reply).
j35 (2026-11-12, REQUEST 01a1cfce, REPLY 01a1cfd0): native-read spans on blueteam.ee 2fa9db6 — A (line 80 "requires us to disclose that content was made or changed by AI") and B ("put into use") accepted; C legal paragraph accepted (link text "..., the AI Act", "third-party providers", "if") plus last sentence in Art 50(4) words; bullet 3 reworded to "under our own name". New page condition: integrating a client's high-risk system must not change its intended purpose or substantially modify it (Art 25(1)(b)); offered the owner a clarifying clause, not drafted. Still owed: sync docs/legal draft from blueteam.ee main once the AI section lands.
j36 (2026-11-12): docs/legal draft synced to blueteam.ee ccf2266 as 4931dade (section 7, Art 25(1) condition in section 4, page date in section 5), pushed to the j29 for/user branch. Four commits await a fold to main (50e6e791, 049e6b86, 7c691e3b, 4931dade); INFO 01a1cff9 told fabric-coordinator.
j37 (2026-11-13): owner ruled (brand-comms-01 INFO 01a1d435) the AI Act Art 25(1) "we do not become provider" commitment stays off the page and goes in each client's contract; section 4 records it as ae1897a0 on the same branch, pushed. Five commits await a fold (50e6e791, 049e6b86, 7c691e3b, 4931dade, ae1897a0); INFO 01a1d437 told fabric-coordinator (01a1cc29, 01a1cff9 unanswered).

*References: ai-act-scope-sentence-condition, legal-wording-over-language-culture*

*Anchors: `docs/legal/2026-11-11-disclaimer-service-scope-blueteam-ee-draft.md::the contract applies`*

*Observed 2026-11-11 (legal-expert)*
