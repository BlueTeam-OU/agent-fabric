# ADR-042 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-04 — Where writers are read; how a base is set

python-dev-01, implementing the record, found three cases its text did
not settle (messages 01a10630-bba3-7d5c-a195-9797d3339342 and
01a10641-dee8-7314-9033-9634b53ef5f2), and fabric-coordinator ruled on
each.

Rule 2 now says where the writers are read: the account's fabric
checkout at `origin/main`, by `git show`, never its working tree, where
an uncommitted edit would name a writer.

Rule 4 said the base is set "once, by the migration". Read literally,
every enrolment broke: a new account's first commit is signed by a key
that reaches main only when its keys pull request merges, after the
enrolment has run. And an implicit migration, "a store with no base
takes its local head", would also fire on a mirror deleted and re-cloned
from its remote, trusting the remote whole. So:
- the base is explicit, `fabric-secrets store trust-base`, run once per
  account by bootstrap for the stores it then holds;
- a store born later is based at first contact from the enrolment bundle
  the host executor carries, never from a fetch;
- a store with no base refuses and names the command.

Enrolment mirrors are made and moved only through `secret_store.py`,
never a raw `git clone` or `git pull`.

The record also still read Proposed after the merge that accepted it
(#91); it now reads Accepted.

### Amendment 2026-10-07 — A commit verification could not judge is a stop, not a refusal

§5 rule 5 narrowed for one case. python-dev-01 found that a correctly
signed store commit was recorded as refused "not signed" when gpg or git
could not run (an unusable temporary directory, no gpg): verify-commit
is silent then as for an unsigned commit, and a standing refusal reads
as forgery. The coordinator ruled that a commit gpg could not judge
stops the operation without a record. The blind review of the change
(#112) found that "a signature header and no verdict" alone let anyone
with push access to a store's remote switch the refusal off (junk in
PGP SIGNATURE armour, a header of the other object format, a header in no
signature format), so the stop needs all three: no status line, the
header git verifies for the store's format, and PGP SIGNATURE armour in it.

### Amendment 2026-10-17 — Holder addenda (ADR-060)

ADR-060 §5 rule 3: the verification of incoming commits never sees the agent's own local commits, so the launcher checks the last commit on settings/roles/<role>/ itself, with the parent's public key alone, and renders only the files of that commit's tree.

### Amendment 2026-10-18 — A base a rebase orphaned

On 2026-10-17 two accounts, architect-cto-01 and brand-comms-01, could not launch: ADR-060's addenda.load refused because each store's HEAD did not descend from its trusted base, and in both the base named a commit no ref held any more. python-dev-02 found the writer that does it (reproduced, #293's follow-up): `entries._before_write` rebases the store's unpushed commits onto the verified remote tip, and a base on one of those commits (init's first commit, or a `trust-base` run at an unpushed head, as the bootstrap migration does) was left on the pre-rebase commit, while rule 4 let the base only move forward. A refused push is how such a commit stays unpushed. The base now moves back after that rebase, only when HEAD descended from it before: to the commit they still share, or to the verified tip when they share none. A base HEAD was already off stays a refusal, which now names the base, HEAD and the remedy: the owner checks HEAD against the remote and records it with `trust-base --replace-orphaned`, which replaces no base HEAD descends from. Both moves trust less of the past, never more. Which of the two incidents took this path is not verified; the owner set both bases to the verified HEAD by hand on 2026-10-18.
