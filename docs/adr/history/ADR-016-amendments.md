# ADR-016 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-28 — Lint checks the occasion and the description

The comparison of an external skill-layer plugin with the fabric (the
owner chose its idea 4 for agent-fabric #58) found rule 1 held by review
alone, as §6 said, and a skill's description checked by nothing although
it is all a session sees before loading one. #58 added `skill_findings`
to lint; its blind review found it scanned only the body, not the
description, and missed a number glued to a word ("PR#57"), and that this
record still called such a lint a candidate. The lint scans both, rule 6
records the description's occasion, and §6/§7 say what is enforced. The
nine skills in the tree pass.
