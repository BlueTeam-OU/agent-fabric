---
name: pg-probe
description: Validate proposed Postgres DDL — a CHECK, an EXCLUDE, a trigger, an ALTER, an index choice — in a throwaway podman container with direct psql probes, before it becomes a migration. Use when reviewing or writing anything under infra/db/migrations/, when a constraint "looks correct" on paper, or when an index-necessity claim needs a real plan rather than an argument.
---

# Probing Postgres DDL

A constraint that reads correctly is not a constraint that holds. Every
finding in the list below was confirmed this way and none of them were
visible in the SQL text. **Probe first, then write the migration.**

Do **not** route a pure schema question through the backend's
Testcontainers suite: it is slower, it applies the whole migration
sequence to ask one question, and its failures are ambiguous between the
DDL and the harness. Testcontainers is for testing the code that uses the
schema. This is for testing the schema.

## Match the major version, or get a wrong answer

Pin the probe to what CI and prod actually run. **Do not trust this
file for the number — grep the project's pin sites**, which have drifted
before: the local compose file's `image:` line, and the integration-test
fixture that builds the database container. Your remit for the project
names both files; the major they agree on is the one to probe with.

This is not a detail. A probe run against 16 once reported that a
driver-keyed predicate on an operator-keyed table had **no index able to
serve it** — true on 16, false on 18, where the planner skip-scans a
non-leading key. The conclusion inverted on the version alone.

## The loop

```bash
podman run -d --rm --name pg-probe -e POSTGRES_HOST_AUTH_METHOD=trust postgres:18-alpine

# Wait for readiness — do not sleep and hope. -h 127.0.0.1 is load-bearing:
# the image's entrypoint runs a TEMPORARY server on the same PGDATA during
# initialisation with listen_addresses='', so a unix-socket pg_isready
# answers "ready" for the init server ~250ms before the real one exists,
# and psql then dies mid-script with "server closed the connection".
for i in $(seq 1 30); do
  podman exec pg-probe pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1 && break; sleep 1
done

podman exec -i pg-probe psql -U postgres <<'SQL'
  ...candidate DDL, then INSERT/UPDATE/DELETE probes...
SQL

# ALWAYS, as soon as the answer is in. The -v is not optional: --rm does
# NOT take the anonymous volume with it, and `podman rm -f` without -v
# leaves a ~40MB orphan per probe. These containers carry no
# org.testcontainers label, so `make prune-testcontainers` never sees them.
podman rm -f -v pg-probe
```

Give it a name you will recognise. Tear it down the moment you have the
answer — CLAUDE.md's process-hygiene rule covers review containers too,
and this host has carried 200+ orphaned volumes before.

Two psql flags worth knowing: `-v ON_ERROR_STOP=1` aborts at the first
error (use it when the DDL must apply as a unit), and the default —
continue past errors — is what you want when you are deliberately probing
several failure shapes in one script, as below.

## Probe the rejection, never the acceptance

**A probe that only inserts a valid row proves nothing.** Every one of
these passed a happy-path test.

### A CHECK over a nullable column passes vacuously

`CHECK (locked_at IS NULL OR anchor = frozen_anchor)` is meant to freeze
`anchor` once the row is locked. With `frozen_anchor` NULL the comparison
is UNKNOWN, and UNKNOWN passes a CHECK exactly like TRUE:

```sql
CREATE TABLE t (id int primary key, locked_at timestamptz, anchor int, frozen_anchor int,
  CONSTRAINT frozen CHECK (locked_at IS NULL OR anchor = frozen_anchor));
INSERT INTO t VALUES (1, now(), 42, NULL);
UPDATE t SET anchor = 999 WHERE id = 1;          -- UPDATE 1. A locked row mutated.
```

The fix is an explicit guard on every column the expression reads:

```sql
CHECK (locked_at IS NULL OR (frozen_anchor IS NOT NULL AND anchor = frozen_anchor))
```

Two things the probe teaches that the reasoning does not. **Set the
compared column to a non-matching non-NULL value and the constraint
rejects correctly** — so a test that varies only the obvious column
reports a constraint that works. And **adding the guarded constraint to a
table that already holds the bad row fails** (`is violated by some row`),
which is the migration you would have shipped: probe the ALTER on dirty
data, not only on an empty table.

### numrange() will not take double precision

float8→numeric is an assignment cast, not an implicit one, so it does not
participate in function-overload resolution:

```sql
EXCLUDE USING gist (numrange(d - 1, d + 1) WITH &&)
-- ERROR: function numrange(double precision, double precision) does not exist
EXCLUDE USING gist (numrange((d - 1)::numeric, (d + 1)::numeric) WITH &&)   -- correct
```

This aborts at DDL time, so it stops every environment at that migration
rather than failing quietly — but only if someone ran it. Any range or
EXCLUDE built over a measurement column (metres, seconds) needs the casts.

### The append-only trigger blocks your own backfill

On a table already carrying `reject_update_delete()`, the natural
two-step column addition does not work — the migration's own backfill is
application traffic as far as the trigger is concerned:

| what you write | what happens |
|---|---|
| `ADD COLUMN k text;` then `UPDATE … SET k = 'legacy'` | `ERROR: ev is append-only` |
| `ADD COLUMN k text NOT NULL` | `ERROR: column "k" … contains null values` |
| `ADD COLUMN k text NOT NULL DEFAULT 'legacy'` | works |

Only the third survives — but **not** for the reason it looks like.
`ALTER TABLE` never fires row-level triggers, rewrite or no rewrite: a
volatile default (`DEFAULT clock_timestamp()::text`) forces a full rewrite,
leaves `atthasmissing` false, and still succeeds on a guarded table, as
does `ALTER COLUMN … TYPE`. Fast-default is why row three is *cheap*, not
why it is *allowed*. Do not design around a barrier that is not there —
what the trigger blocks is a statement-level `UPDATE`/`DELETE`, which is
what row one is.

Row two is not about the trigger at all: `ADD COLUMN … NOT NULL` with no
default fails on any table that already has rows, guarded or not.

Where old rows need a value the new default does not describe, add the
column nullable with no default and **INSERT a new versioned row** carrying
the real values — corrections append here, they do not mutate (ADR-018).

### A shared trigger function must report TG_TABLE_NAME

`reject_update_delete()` is attached to 15+ tables. Probe it on a
**second** table, not the one you wrote it for — a hardcoded name in the
`RAISE` is invisible on the first:

```sql
CREATE FUNCTION reject_update_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME; END $$;
```

Before migration 0039 the message said `runtime_events` on all 15, and an
operator debugging a rejected write investigated the wrong table.

## Index questions need a plan, not an opinion

Load enough rows that the planner will not seq-scan out of triviality
(a few thousand), `ANALYZE`, then `EXPLAIN (ANALYZE, BUFFERS)`. Assert on
what the plan *costs*, not on the node name: "not a Seq Scan" is a brittle
assertion on 18, where a skip scan can serve a predicate that had no
usable index on 16. Index choices here are reviewed per query
(ADR-022 §5 rule 9) — the probe is how that review gets evidence.

## Before it becomes a migration

Once the DDL is settled, the migration itself still owes:

- **A free numeric prefix.** Parallel branches take the same slot and
  merge clean; `bash tools/checks/scan_semantic_collisions.sh` is the
  check, and the filename is restated in the file's own header comment,
  so a `git mv` means editing that comment too.
- **Append-only enforcement in the SAME migration as the table.** Both
  tables added since the baseline do this — `0024_stopping_mode_policy.sql`
  (table :44, trigger :76) and `0038_transit_search_profiles.sql`
  (:81, :278). A two-step "ship it commented out, activate later" pattern
  existed once, for one table, and its migration was folded into the
  baseline at the next re-baseline; nothing has used it since. Attach the
  guard with the table.
- **`ON CONFLICT (<natural key>) DO NOTHING`** on any seed row. Not because
  the file gets re-run — `MigrationRunner` records applied filenames in
  `schema_migrations` and refuses to re-apply. Because of **re-baselining**:
  a seed folded into `0001` while still present in a later migration
  collides on a fresh database, and this baseline has been re-folded three
  times (`infra/db/migrations/README.md`).
