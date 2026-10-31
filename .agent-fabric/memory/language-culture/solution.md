---
role: "language-culture"
class: solution
description: "header/team/memory/brief-missing-ის ქართული თარგმანი identities/prompt/locale/ge/-ში გადავიდა; ქარტია და ბრიფი როლთან რჩება"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d803f7b4b49d1b63
---

## header/team/memory/brief-missing-ის ქართული თარგმანი identities/prompt/locale/ge/-ში გადავიდა; ქარტია და ბრიფი როლთან რჩება

ტოტზე develop-qzapp/user/feat/holder-addenda-stage3 (abdf5db8, „the shared prompt pieces' translations live once per language“) header.md, team.md, memory.md და brief-missing.md გადატანილია identities/roles/language-culture/locale/ge/-დან identities/prompt/locale/ge/-ში (R100, ყოველი ენისთვის ერთხელ). charter.md და brief.md როლის locale/ge/-ში რჩება. როცა stage 3 main-ზე დაჯდება, team.md/memory.md-ის ცვლილება ახალ გზაზე კეთდება. ჩემი ლოკალის carve-out-ი (identities/roles/<role>/locale/<suffix>/) ახალ გზას ფარავს თუ არა — origin/main-ის AGENTS.md-ში გადაამოწმე, სანამ იქ დააკომიტებ.

**How to apply:** j83-ის სახის ცვლილებამდე `git ls-tree origin/main identities/prompt/locale/ge/`.

### English
On develop-qzapp/user/feat/holder-addenda-stage3 (abdf5db8), header.md, team.md, memory.md and brief-missing.md moved from identities/roles/language-culture/locale/ge/ to identities/prompt/locale/ge/ (pure renames, once per language). charter.md and brief.md stay in the role's locale/ge/. Once stage 3 lands, edits to team.md/memory.md go to the new path; check origin/main's AGENTS.md for whether the locale carve-out covers it before committing there.

*Observed 2026-10-17 (language-culture)*
