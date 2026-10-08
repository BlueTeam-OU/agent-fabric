# ADR-018 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-28 — The charter tripwire runs on every branch

§6 recorded a known gap: `check_charter_authority.sh` was tested but
no CI step ran it, so its one property the repository-wide fence lacks —
reading `policies/authority.json` from the base of the diff, so that a
branch cannot appoint itself — was not in force, and
`policies/AUTHORITY.md` named it as the enforcement for charters,
briefs and the catalogue. §6 left the choice open between wiring it
into `tests/run.sh` and retiring it. An audit of the coordinator's
queue on 2026-09-28 found it still open; it is wired, beside the
`.agent-fabric/` tripwire, with the same base.

### Amendment 2026-09-30 — Doppler is retired: the stores replace it

Doppler is removed (ADR-038, agent-fabric #69): the reference names credentials and the stores as this role's, not the Doppler project.

### Amendment 2026-10-01 — A contributor role commits its entry's paths

The owner asked for a Python developer to share the port of the
fabric's bash (ADR-040) and its new tooling, and chose, of the two
options put to them, to let that role commit agent-fabric's code rather
than only send patches. The fence admitted no role but the coordinator
outside a locale: a second role could not make one commit, and
`policies/AUTHORITY.md`'s "open a pull request" was a step no other role
could take. The carve-out names the role and its paths in
`policies/authority.json`, read from the base in CI as the owner role
already was; definitions stay out of every entry, and every contributed
commit reaches main inside the coordinator's pull request, under its blind
review.

### Amendment 2026-10-01 — The fence's own code stays out; a guarded commit declares its binding

The blind review of the carve-out reproduced a contributor committing
its own charter: the hook read the entry from the working tree, where
an unstaged edit widened it, and `commit-msg` kept a typed owner
trailer, which CI then accepted. It also found the first entry
admitting the code that enforces the fence — `git.py`, which the CI
guard imports, the reviewer's agent file, the harness hooks and their
installers — and a lint that only caught rules broader than its sample
files. The hooks now read the entry as HEAD has it, a guarded commit
declaring a role other than its binding is refused, what a role is and
what enforces the fence is never in an entry, and lint compares rules
by prefix.

### Amendment 2026-10-01 — CI judges a branch with main's guards

The re-review of the carve-out found that a contributor's entry, which
admits `tools/` and `tests/`, could reach the guard that judges it in
CI: a module beside the guards named after a standard-library module
they import is imported in its place, and a helper the suite runner
sources runs before the check. The first was run and confirmed
(`docs/live-checks/2026-10-01-guard-shadowing.md`). Python resolves an
import by name, so no exclusion closes the class; CI now runs main's
copy of the guards, isolated, before any of the branch's code.

### Amendment 2026-10-04 — A merge is judged on its own change

Rule 3 exempted a merge whose guarded tree equalled one parent's, and
rule 4 had CI skip merges. Two consequences, both reported: a branch
carrying a coordinator-supplied `fabric-ref` could not fold a main that
a drain had moved, since the merged `.agent-fabric/` equalled neither
parent (devex-tooling, gzapp #1028); and a hand edit carried in a merge,
a conflict resolution or a commit made past the hook, passed CI unseen.
Both now compare a merge with the clean three-way merge of its parents
(`git merge-tree --write-tree`), with renames off, so a move out of a
guarded path shows its source; without a clean merge, the merge is
judged against every parent. The blind review of agent-fabric #96 found
the rename case and the `-s ours` fallback; both are closed in the same
pull request.

### Amendment 2026-10-07 — A contributor that merges its own pull request

§5 rule 8 extended. The owner: "we should authorize python-dev to
directly merge their work", approved on these terms: a per-role flag,
python-dev only; its own blind review and gate; arming by the team's
count rule; paths outside its entry supplied by the coordinator onto
its branch; distribution kept by the coordinator, whose key signs it.
The fold through the coordinator cost a round trip per delivery, and
the CI fence already judged contributor commits against the base's
entry, so the merge needs no coordinator in the loop. What CI could not
yet refuse — a pull request opened by a contributor that does not
merge, or from a supply branch — it now does.

### Amendment 2026-10-08 — A role that merges its own work may fold another contributor's supply

python-dev-02's #116 folded devex-tooling's InterWeave configs, as the coordinator had routed them, and CI refused it: only a PR with an owner-role commit could carry a non-merging contributor's supply. A role whose entry merges already opens, reviews and merges its own pull request; it may now fold another contributor's supply as the coordinator does, being the one that merges. Each commit is still held to its own entry by the path check. The guard (tools/fabric/guards/contributors.py pull_request_problem) and its tests change with this rule.
