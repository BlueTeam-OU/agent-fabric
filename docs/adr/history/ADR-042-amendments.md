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
