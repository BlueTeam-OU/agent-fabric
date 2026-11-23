# memory/shared/

Field knowledge owned by two or more roles, stored once. The assembler
routes a claim whose `shared_with` names other roles here (a `domain`
claim) or to `memory/projects/<project>/shared/` (a project-scoped
class), and every owner's `INDEX.md` points at the one copy. Copies
would drift.

Empty at extraction: the old `.roles/shared/` was documented but never
materialised, because no claim had been shared. `tools/fabric/lint.py`
fails a slice here that lists fewer than two owners.
