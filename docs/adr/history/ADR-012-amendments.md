# ADR-012 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-30 — The Doppler layout is replaced by each login's own store (ADR-038); rules 1-4 and 8 restated, 5-7 stand

Every account reads its own store (ADR-038; the fleet's enrolment is
recorded in docs/live-checks/2026-09-29-fleet-secrets-enrolment.md), so
the Doppler project this record chose is removed: the reader in
`fabric-secrets`, `enroll.sh` and its worker, the migration action, the
Doppler templates of `fabric-accounts`. What `enroll.sh` did for a new
account is `fabric-secrets provision`, which fills a child's store with
the parent's `put`. One rule changed its form: fill-from's denylist of
names never copied became an allowlist of names shared, with the
coordinator's credentials refused even when named — a denylist missed
the provisioning key once. The rules on a secret's shape and locator, a
destination with its credential, and tests by shape stand unchanged.

### Amendment 2026-10-30 — A commit or a push holding a value of the account's own secrets is refused at the keyboard

Rule 1 said no credential is committed, and until now nothing but an
instruction kept it: an auto-mode deny line and the project instruction
files. Pattern scanners (gitleaks, TruffleHog) look for what a key looks
like and miss a key of a shape they do not know; omerta, read on
2026-10-27, searches for the account's actual values instead. Rule 9
borrows its method, not the tool: omerta reads `.env` files at a
repository's root and depends on hyperscan, while an agent's values are
in `~/.config/agent-fabric/secrets.env` and a guard is stdlib (ADR-040).
The same 8-character floor and an ignore list keep ports and counts out.

The check runs in pre-commit (the staged blobs and the names), commit-msg
(the message) and pre-push (every object the push adds, which catches a
commit made with --no-verify, or before the check existed, while it is
still local). A CI leg was planned and is not built: CI holds none of an
account's values, so it would pass by never searching. The `history`
verb is the audit of a repository's reachable objects.
