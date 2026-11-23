# 2026-10-20 — what GitHub signs inside a branch

Run by fabric-coordinator, as the login user (job j186, from the review of
#247). The question: which commits that GitHub itself makes can appear in
the range ADR-057 §5 rule 5 judges (the commits a pull request adds), how
they are signed, and whether they carry anything of their own.

## What was measured

GitHub's commit-signing keys, from `gh api users/web-flow/gpg_keys`:
`4AEE18F83AFDEB23` (expired 2024-01-16) and
`968479A1AFF927E37D1A566BB5690EEEBB952194` (since 2024-01-16, no expiry).
Imported into a scratch keyring, nothing else in it.

Every commit on agent-fabric's `origin/main` whose committer is `GitHub`
(366) and whose subject is not "Merge pull request #…": six. Each verified
with `git -c gpg.program=gpg log --format='%G? %GF'` against that keyring,
and each merge's tree compared with `git merge-tree --write-tree` of its
two parents.

| commit | what | parents | signature | own change |
|---|---|---|---|---|
| 0bd4b7ae | "Merge branch 'main' into …/ge-native-pass" (Update branch) | 2 | U, 968479A1…B5690EEEBB952194 | none: tree = clean merge |
| 5877c757 | "Merge branch 'main' into …/ge-brief" (Update branch) | 2 | U, same key | none |
| a5fa4fd6 | "Merge #4: locale/ge …" (API merge) | 2 | U, same key | none |
| b22d3454, e59d0ba0 | squash merges of #31, #30 | 1 | U, same key | the whole PR |

(`U`: a good signature from a key the scratch keyring does not trust; the
checker reads `G` and `U` alike and judges validity itself.) All six are
authored by the shared account, carry no `Fabric-Role:` trailer and have
no note under `refs/notes/fabric-ots`. No commit authored by
`dependabot[bot]` is on main yet.

On a push to main, `ban_unsigned_commits.py` resolves its range from
`origin/main` to `HEAD`, the same commit, so a pull request's own merge
commit is never judged; only what a branch carries is.

## What it decides

- Rule 5 as it stood would refuse every Update-branch merge: no agent's
  key, no trailer, no proof. The first one after a `since` would leave a
  pull request no agent can turn green without a force-push.
- A forge merge with no change of its own is identifiable from the
  commit alone (its tree against its parents' clean merge), and a
  forge signature is identifiable by a pinned fingerprint. ADR-057 §5
  rule 8 admits exactly that, and Dependabot's workflows-only commits.
- The squash merges are what a forge-signed commit with content looks
  like; on main today they come only from before the ruleset's
  merge-commit-only rule, and rule 8 refuses their kind inside a branch.

## Not verified

- A Dependabot commit's signature: GitHub documents that it signs
  Dependabot's commits with web-flow's key; none was here to read.
- A conflict resolved in GitHub's web editor: expected to be a
  forge-signed merge whose tree differs from the clean merge, and so
  refused; not produced.
