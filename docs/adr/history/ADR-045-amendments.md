# ADR-045 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-08 — The engine root honours AGENT_FABRIC_ROOT until stage 4

Rule 1 said `engine_root()` is the code's own location. The seam's first
implementation (python-dev-03, #119) kept honouring `AGENT_FABRIC_ROOT`
when it is set: every wrapper and test fixture sets it, and in production
it names the code's own location anyway, so dropping it would have
rewritten every fixture for no change in behaviour. It is accepted as a
transition until stage 4, when the operator's data moves out and the
variable stops meaning both trees. Meanwhile a fixture that stands in
for instance data sets `AGENT_FABRIC_OPERATOR`, so the double meaning the
record ends is not extended.

### Amendment 2026-11-11 — The operator repository is named, and the move has a plan

The owner created the operator repository on 2026-11-10 as
`BlueTeam-OU/blueteam-fabric`, private and empty. `docs/split/inventory.md`
had named it `gzapi-org/blueteam-fabric` and is corrected. It is not one of
the settings repositories (`BlueTeam-OU/agent-fabric-settings`, and the
one gzapi-org has): each of those holds one organisation's arming policy
for `fabric-pr arm`, stays its own repository and takes nothing from this
move.

The extraction's order is written in `docs/split/move-plan.md`. The list
comes from `tools/fabric/roots.py`. The files move inside this repository
first, behind a changed fallback, with the git-object readers moved
before them and symlink shims for readers of the working tree only. Only
then do they cross into the operator repository. The owner chose on 2026-11-11 to classify
`docs/adr/` record by record. An organisational record moves with its
number, and the engine keeps that number reserved. Rule 4 forbids
renumbering, not moving. A mixed record may also be split: the
engine's part keeps the number, and the organisation's part becomes an
operator record that cites it. Engine CI reads the operator's main for the
signing check through a read-only deploy key (the owner, the same day).

The Scope line, rule 1 and §8 named a `runtime/control/roots.mjs`. It
was deleted with the Node control plane on 2026-10-10 (a20b4159), and
those mentions are struck.

### Amendment 2026-11-11 — Rule 2's list matches the tree

Rule 2's list did not match the tree it describes. The review of #557
found the gap, and `tools/fabric/roots.py` is the source of the
corrected list. `identities/personas/` and the clients registry are
instance data, and `roots` already resolved both under the operator's
tree. `routing/policies/` (account switching, availability, the review
grade) is instance data too: it records how this fleet chooses, and
`roots.routing_policy` resolves it there. The inventory had classed it
with the routing defaults. Nine of the fifteen `policies/*.json` files
are the guards' exception lists: each one names engine modules that a
checker admits, and it changes with that code. Rule 2 therefore keeps
them with the guards in the engine, and `docs/split/move-plan.md` step A
moves them out of `policies/`.

### Amendment 2026-11-22 — Step B: the operator falls back to operator/, and the forge keys move with signing.json

Step B of `docs/split/move-plan.md` moves the instance data into
`operator/` inside this repository. Rule 1 said the operator root falls
back to the engine root when `AGENT_FABRIC_OPERATOR` is unset; from step B
it falls back to `operator/` under the engine root, whether the engine
tree came from the environment or from an `engine=` argument, and step D
replaces that with the account's operator clone. python-dev-02's j175
changed `roots.operator_root()` and `operator_prefix()` to match.

The plan's precondition 5 left one question open: `policies/forge-keys/`
was not on the move list, yet `ban_unsigned_commits.py` and the signing
lint read it beside `signing.json`, through the operator's tree. The two
options were to move the keys with `signing.json` or to have both readers
ask the engine for them. The owner chose on 2026-11-22 to move them: the
`forge_keys` list and the key files it names are one trust decision, so
they live in one repository, and a change to either is reviewed where the
other is. The keys are GitHub's and the same for every operator, which was
the case for the engine; it lost because the list would then sit in one
repository and its files in another. Rule 2 names the folder, `roots`
lists it among the paths that move, and CI's signing step archives it
under main's operator prefix.

### Amendment 2026-11-27 — After step D the authority guards read the operator's main, or refuse

`docs/split/move-plan.md` precondition 6 named the one failure of the
move that would pass instead of fail. Two guards read
`policies/authority.json` at the base: `agent_fabric_dir_authority` and
`charter_authority`. `agent_fabric_dir_authority` decided whether a
repository is agent-fabric itself by whether that file was present.
After step D the engine keeps no such file. The guard would then take
agent-fabric for a managed project and check only `.agent-fabric/**`,
and every other commit would pass unchecked, without a word.

Rule 7 closes it in three parts. First, the engine is recognised by its
own code at the base, `tools/fabric/roots.py`, and a branch cannot move
that by adding or deleting an operator tree, nor a managed project's
branch by adding that file. Second, the file is read where the base
keeps it: in the repository while the base has `operator/` or the old
path, and from step D in the operator repository's committed `main`.
In CI that is a checkout of `main` alone at depth 1 through the deploy
key, which the authority step names to the two guards alone
(`AGENT_FABRIC_OPERATOR_GIT`, at the commit checked out) and deletes
before any of the branch's code runs: the operator repository is
private, and this repository's CI logs are public. On an account it is
the login's own clone (`roots.operator_clone`), found from the password
database, never `$HOME`; the documented variables choose another.
Third, past step D a read of the
operator's file that fails is a refusal, exit 4, naming what could not
be read. A git read at the base that cannot run is a refusal too, exit 2,
as is every other refusal. While the base still holds the tree, a file
it lacks is read as before: the default role, no contributors, a
charter refusal.

CI's probe step fails the run when main has neither tree and the
`OPERATOR_DEPLOY_KEY` secret is empty. Once main lacks the operator's
paths, the authority step archives only the paths main has. The
suites' own run of the guards (`tests/run.py`'s bash section, in both
CI jobs) is handed no operator, so past step D the guards refuse there;
CI sets `AGENT_FABRIC_AUTHORITY_GATED_ELSEWHERE=1`, and with it an exit 4
from one of the two guards is a NOT ENFORCED line, the authority step
being the gate. The status is the guard's own word for why it refused;
any other status of those guards, exit 2 included, still counts. A
run without the variable, as on an account, still fails on it. The
key's other use, the signing step's archive of the keys, holders and
registry, is still the key-trust hazard in the plan's §4 (job j1119):
that step will fetch its own copy the same way, before any of the
branch's code runs. Step D cannot pass until the key exists.
Dependabot runs read only Dependabot secrets, so the owner adds the key
under both.

