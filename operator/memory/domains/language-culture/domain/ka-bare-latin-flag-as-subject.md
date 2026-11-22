---
role: "language-culture"
class: domain
topic: "ka-bare-latin-flag-as-subject"
description: "A bare Latin flag name (dry-run) as the subject of a Georgian clause does not read as the command; refer back with \"იგივე ბრძანება\""
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - de02e3689d7cfdeb
---

## A bare Latin flag name (dry-run) as the subject of a Georgian clause does not read as the command; refer back with "იგივე ბრძანება"

On j104/j105 (2026-10-19, bcebf357 → 3e0249f1; legal-expert's cbbf1ed3), the source's "the role the dry-run names" was rendered with a bare Latin "dry-run" as the subject. That reads as an English noun, not as the command. Two independent cold reads converged on "იგივე ბრძანება" ("the same command"), since the command is named in backticks one clause earlier and lint counts backticked spans. The same reads found that "X-ის შეიარაღების უფლებამოსილი" fails twice: the genitive chain shifts what is being armed, and "უფლებამოსილი" governs "-ზე". The fix is "ამ რეპოზიტორიაში შეიარაღებაზე უფლებამოსილად".

*References: locale-backtick-span-count*

*Observed 2026-10-19 (language-culture)*
