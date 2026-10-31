---
role: "legal-expert"
class: solution
description: "Which providers hold Blueteam's personal data (email, hosting, accounting, payments, AI) and their GDPR role, as the owner stated on 2026-10-15"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "legal-expert-ee-eu"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3a56833ef3d64694
---

## Which providers hold Blueteam's personal data (email, hosting, accounting, payments, AI) and their GDPR role, as the owner stated on 2026-10-15

Stated by the owner on 2026-10-15, while reviewing blueteam.ee/privacy.html (updated 2026-06-22):
- email: Proton AG, Switzerland (adequacy: Commission Decision 2000/518/EC, kept in force by GDPR Art 45(9))
- website hosting: 1984 ehf, Iceland (EEA)
- accounting: SmartAccounts (Smart Accounts OÜ, reg. 12041731, Tallinn); its policy states no DPA, no sub-processor list, no hosting location
- outside accountant: Wisor (wisor.ee), stated 2026-10-15; role and entity not yet checked
- payments: Holvi (Holvi Payment Services Oy, Finland), probably an independent controller; entity not verified from Holvi's own site
- AI: Anthropic Max (consumer plan, training setting off) and an OpenAI business account; the fleet's routing (ADR-005) also has a broker route (DeepSeek, GLM), and its use for client data is unanswered
Main open risk: Anthropic consumer plans have no processing agreement (Anthropic acts as its own controller, and still uses safety-flagged content and feedback for training), so client personal data processed by the fleet has no Art 28 cover there.
Clients (owner, 2026-10-15): Gzapi is in [redacted], outside GDPR as a controller; a Georgian lawyer handles its side. BlueTeam has no Italian clients, so Italian law (e.g. L. 132/2025) is out. BlueTeam is still bound by GDPR as an EU processor for Gzapi (Art 3(1), Art 44 binds processors).
Most clients are in Switzerland and are not projects in agent-fabric (owner, 2026-10-15): Swiss law (FADP) reaches them and is outside the -ee-eu jurisdiction.
Decision (owner, 2026-10-15): option B, no personal data of clients, their people or visitors goes into any AI tool (OpenAI or Anthropic); the privacy notice redraft is written on it.
How to apply: re-check these with the owner before drafting the privacy notice or a client DPA; [[privacy-notice-review-2026-10]].

*References: privacy-notice-review-2026-10*

*Anchors: `routing/profiles.json::deepseek`*

*Observed 2026-10-15 (legal-expert)*
