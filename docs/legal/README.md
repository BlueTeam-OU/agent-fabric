# docs/legal — legal opinions for the company that runs the fleet

What the fleet asks the law, answered by a holder of the `legal-expert`
role for its jurisdiction (the login's suffix: `legal-expert-ee-eu`,
Estonia and the European Union), and the drafts of legal text it writes
for the owner to adopt. The role's charter is
`identities/roles/legal-expert/charter.md`; its remit here is
`.agent-fabric/roles/legal-expert.md`. The holder commits these files on
its own branch and fabric-coordinator merges them
(`policies/authority.json`).

An opinion is advice for a decision, not the decision: the owner
decides, and a decision that follows goes into a record (`docs/adr/`),
which cites the opinion. It is not the advice of an attorney admitted to
the bar, and it says so where a matter needs one.

## One file per question

`YYYY-MM-DD-<subject>.md`, dated the day the opinion was given, in this
shape:

1. **Question** — as asked, and by whom (a role, never a person's name).
2. **Facts assumed** — and which of them could not be verified.
3. **The law** — each rule cited to its act, section or article, the
   version in force on the date that matters, and its source (Riigi
   Teataja, EUR-Lex, the court's own site); a citation not read from its
   source is marked *unverified*.
4. **Reading** — what is settled and what is argued.
5. **Risk** — how likely, how costly.
6. **What to do** — the options, and what would need an attorney.

An opinion the law or the facts have overtaken is not edited into a new
answer: a new file supersedes it and names it.
