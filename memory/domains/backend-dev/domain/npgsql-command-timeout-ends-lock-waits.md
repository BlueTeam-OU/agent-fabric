---
role: "backend-dev"
class: domain
topic: "npgsql-command-timeout-ends-lock-waits"
description: "Setting or documenting a statement bound next to a lock bound (Npgsql Command Timeout, lock_timeout) — the client-side timeout cancels a lock wait too, so the wait ends at the lower of the two with a different error; the factory bakes 30…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - fca387ddfb7fe11d
---

## Setting or documenting a statement bound next to a lock bound (Npgsql Command Timeout, lock_timeout) — the client-side timeout cancels a lock wait too, so the wait ends at the lower of the two with a different error; the factory bakes 30 s into every connection

Npgsql's `Command Timeout` runs on the client. When it expires, Npgsql cancels
the command, and that includes a command that is still waiting on a lock.
Postgres's `lock_timeout` runs on the server and only bounds lock waits. With
both set, a lock wait ends at whichever is lower, and the error tells you which
one ended it: 55P03 lock_not_available means lock_timeout, and a cancelled
statement means Command Timeout. Docs that say "a lock wait fails at 30 s
whatever the bound" are wrong whenever the bound is below 30 s.

Three related facts I measured on Postgres 18:
- `SET LOCAL` sent as the transaction's first command lands inside the
  transaction, because Npgsql sends BEGIN together with that command. It is gone
  at commit, so the next user of the pooled connection sees the default.
- `client_connection_check_interval` lets the server end an orphaned statement
  once the client's socket closes. A SIGTERM'd runner's backend was gone 0.31 s
  later. A client whose host vanished without closing its socket is not caught.
- To show that a bound does not cut a statement short, run it against a real
  long statement (`pg_sleep(3)`). An instant `SELECT 1` passes under any bound.

**Why:** gzapp #1182 (2026-10-26). gzapp's NpgsqlConnectionFactory writes
`Command Timeout` = 30 s into the connection string by default, so every
migration statement had a cap that no operator setting could lift (01a175ce).
architect-cto ruled that migrations run under no statement bound and that the
lock wait is bounded instead (01a175d1). I fixed Program.cs's wording to
min(30 s, bound) (review F2). Then the re-review found that devex-tooling's
RELEASE.md row still said "30 s whatever" (F4, 01a17637). They fixed it in all
three places that said it (01a17638).

**How to apply:** when you add any `Command Timeout` or `CommandTimeout`, ask
which lock waits it also cuts short. State both bounds and both errors together.
Code that has to run longer than 30 s builds its connection with an explicit
timeout. It never relies on the factory default. Related:
[[podman-compose-requires-reruns-one-shot]] (the #1182 build), [[a-change-sweeps-the-prose-that-states-the-old-fact]].

*References: a-change-sweeps-the-prose-that-states-the-old-fact, podman-compose-requires-reruns-one-shot*

*Observed 2026-10-31 (backend-dev)*
