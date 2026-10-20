# ADR-057 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-20 — A commit the forge makes

Decided by fabric-coordinator in job j186, before any repository is given
a `since`: the review of #247 named the risk that rule 5, read as written,
refuses every commit GitHub itself makes inside a branch, and the first
one would leave a pull request that no agent can turn green.

What GitHub makes inside a branch, measured on agent-fabric's history
(docs/live-checks/2026-10-20-forge-made-commits.md): two "Update branch"
merges (0bd4b7ae, 5877c757, 2026-09-18) and an API merge (a5fa4fd6), each
signed by web-flow's key 968479A1AFF927E37D1A566BB5690EEEBB952194, each
authored by the shared account, each with no trailer and no proof, and
each a tree equal to the clean merge of its parents. Dependabot's
action-pin commits are signed by the same key; none has landed here
yet. A pull request's merge commit on main is never judged: on a push to
main the checker's range is empty.

The choice was between refusing every forge commit (the fleet then must
never press "Update branch" and Dependabot's pull requests can never pass)
and admitting a forge signature as such. Neither: anyone pushing through
the shared GitHub account can have the forge sign a commit of any
content, so a forge signature says only that GitHub made the commit, never
who asked. Rule 8 admits what that signature cannot misuse: a merge with
no change of its own adds nothing that is not judged in its parents; a
Dependabot commit is held to the same path fence, SHA-pin check and
review as under the trailer guard, and is said to be a tripwire there
too. Everything else made on the forge is re-made in a working copy.

The forge key is pinned by fingerprint in the policy, not trusted by
name: GitHub rotated it once (4AEE18F83AFDEB23, expired 2024-01-16), and a
new one is admitted by a policy change, failing closed until then.
