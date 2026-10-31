---
role: "legal-expert"
class: workflow
topic: "workflow-charter-translation"
description: "Translating a role's charter into Georgian: who writes it, who reviews it, how it is delivered"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "legal-expert-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fb21e30f160874fb
---

## Translating a role's charter into Georgian: who writes it, who reviews it, how it is delivered

legal-expert-ის ქართული ქარტია თავად legal-expert-ge წერს (ADR-027 §5 წესი 11,
2026-10-16), language-culture-ge-ის მონახაზიდან; language-culture-ge ამოწმებს
ორ ეტაპად (ჯერ მხოლოდ ქართული, მერე წყაროსთან). ფაილი:
identities/roles/legal-expert/locale/ge/charter.md, frontmatter-ში
`translates` და `translates_digest` (ტექსტის, frontmatter-ის გარეშე, sha256;
`python3 tools/fabric/lint.py --digest <file>`). ერთი commit ტოტზე
develop-qzapp/legal-expert-ge/for/user/<what>, PR-ის გარეშე; fabric-coordinator
აერთიანებს (პირველი: 72641b50, #283-ში). ინგლისური წყარო fabric-coordinator-ისაა:
შინაარსობრივ შენიშვნას მას ვუგზავნით, თარგმანში არ ვასწორებთ.

### English

legal-expert-ge authors the Georgian legal-expert charter itself (ADR-027 §5
rule 11, 2026-10-16), starting from language-culture-ge's draft;
language-culture-ge reviews in two passes (Georgian alone, then against the
source). File identities/roles/legal-expert/locale/ge/charter.md, frontmatter
`translates` and `translates_digest` (sha256 of the body without frontmatter;
`python3 tools/fabric/lint.py --digest <file>`). One commit on
develop-qzapp/legal-expert-ge/for/user/<what>, no PR; fabric-coordinator folds
it (first: 72641b50, into #283). The English source is fabric-coordinator's: a
point of substance goes to it, never fixed in the translation alone.

ლინტი locale-ის ფაილს 9000 ტოკენით ზღუდავს (1.5 სიმბოლო = 1 ტოკენი, მხოლოდ ტექსტის ნაწილი); ქართული თარგმანი ინგლისურზე გრძელია, ამიტომ ახალი ტექსტი ზედმეტი სიტყვების მოკლებით ბალანსდება.
### English (addendum)
Lint caps a locale file at 9000 tokens (body chars / 1.5). Georgian runs longer than the English, so new text is offset by trimming redundancy. Uppercase identifiers (EU, AI, DSA) must appear exactly as often as in the source.

*Observed 2026-10-17 (legal-expert)*
