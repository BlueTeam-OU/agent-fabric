# ADR-013 — The memory model: scopes, kinds of truth, tiers, the drain

**Date:** 2026-09-13
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #52 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** memory/ (README.md, RUBRIC.md, domains/, shared/, agents/); every managed project's .agent-fabric/memory/; tools/fabric/layout.py, tools/fabric/harvest_memory.py, tools/fabric/assemble.py, runtime/claude-code/hooks/memory-write-check.py, tools/fabric/lint.py, fabric-query; identities/schemas/claims.schema.json; identities/prompt/memory.md; policies/hygiene.json; runtime/control/ctl.mjs (the `memory` op); bin/fabric-status (the undrained count)
**Pillar:** P2

## 1. Context and Problem

Sessions learn things the repository never records: that a green suite
can be testing nothing, that a queued branch refuses a push, that a bare
permission error from a container is a stale security label. Before the
fabric, that knowledge lived in a memory buffer organised by session
rather than by subject, and in the first managed project's own tree
beside the code it described (`clone_id`-keyed, under a directory the
control plane owned).

Three failures made a model necessary. Knowledge about one system sat in
the control plane, under the control plane's licence and access, and
drifted from the tree it described because nothing moved them together.
Knowledge of different kinds — what the field is, what one system does
today, why a decision was made, what is still open — was filed together,
so a claim that rots with every merge sat beside one that holds for
years, and nothing said which was which. And an index maintained by hand
drifted from the files it pointed at, then quietly lied.

On 2026-09-13 project knowledge moved into each project's own repository
(`<working copy>/.agent-fabric/memory/`); on the following days the
drain was rebuilt around each agent's own Claude memory, a stated
cadence, a cross-host bundle and hygiene by substitution.

## 2. Decision

Durable knowledge is filed by **scope** and by **kind of truth**, with
provenance, generated into an index a session reads before it opens
anything, and fed by a **drain** from each agent's own memory.

**Four scopes** (`tools/fabric/layout.py` is the one module that says
where each lives):

| scope | what belongs |
|---|---|
| `memory/domains/<domain>/` (here) | true of the field regardless of any project |
| `<working copy>/.agent-fabric/memory/<role>/` (the project's repository) | what one system implements, decided, does and still owes |
| `memory/agents/<login>/` (here) | genuinely specific to one agent — almost nothing |
| `memory/shared/` here, or the project's own `shared/` | a claim two or more roles own, stored once |

Domain ids equal role ids today, an artefact of the extraction;
`layout.py` is where a later split or rename happens.

**Six kinds of truth**, filed by epistemic class because they decay and
verify differently: `domain` (checked against the discipline, rots
slowly), `solution` (what the system implements today, checked against
the tree, rots with every merge), `intersection` (where the system
follows or departs from the field, and why), `rationale` (reasoning not
yet in a decision record — a staging area), `workflow` (how work is
actually done there) and `threads` (known loose ends). A `solution`
slice loses to the tree; a `rationale` slice loses to a decision record
and is promoted into one when it proves durable (ADR-001 §5 rule 7).
Sibling-project evidence is `knowledge_scope: domain-only` and may
support a `domain` claim and nothing else.

A role's charter, brief and recall are **not memory**: they are authored
identity under `identities/roles/<role>/` (ADR-002). The project's remit
for a role is authored too, in the project's `.agent-fabric/roles/`.

**Two tiers.** A session is born with the role's charter and brief and
the team and memory sections, in the launch prompt (ADR-002), and the
project's remit for the role plus one line pointing at its `INDEX.md`,
from the session-start hook. Everything else waits for a cue: the
index, **generated** by the assembler from each slice's one-line
description, lists every slice the role can reach — its identity files,
its domain, the project's slices, the shared ones — and the session
opens the one whose cue matches.

**The drain.** The input is each agent's own Claude memory, one fact per
file. A memory reaches the corpus only if it opts in with a
`roles_class` in its `metadata:` block; `harvest_memory.py` stamps the
agent (from `runtime/identity.py`), host, project and working-copy label,
and emits claims; `assemble.py` files them, writes provenance, regenerates
every index and the citation graph (`crossref.json`), and commits a drain
report (`last-drain-report.json`) with the per-store watermark the next
harvest starts from. Across accounts a drain is a bundle — one tar with a
manifest and the digest of every file — produced by each account's own
control agent (`fabric-ctl all memory`) and verified before it is read;
only the agent reads its memory. `.agent-fabric/` and the domain corpus
are written by a fabric-coordinator holder, who assembles and commits;
landing a drain across repositories is ADR-011's order. How the
assembler decides between a claim and the text already in the corpus is
the next record's subject.

**Cadence.** An agent harvests after a change to how
its role works has landed, and at least weekly while it is active.

**Hygiene.** English always. A person is named by role, never by name;
a secret of any shape is never knowledge. The assembler
**substitutes, it does not refuse**: a hit on `policies/hygiene.json`,
the credential shapes in `layout.py` or a project's own
`.agent-fabric/hygiene.json` becomes the entry's `refer_as` or
`[redacted]`, in title, description, body and file name, and is named in
the report. A language or script name is not a place name, and a path
is not matched.

## 3. Alternatives Considered

- **Project knowledge in the control plane** (the earlier
  layout, `memory/projects/`). Rejected: a `solution` slice can only stay
  honest if it is versioned with the tree it describes, so one change can
  move both; and a project's confidential knowledge belongs under the
  project's own licence and access. The runtime branch that still read
  the old path is removed; lint refuses the directory.
- **Filing by topic.** Rejected: topics mix claims that decay at
  different rates and verify against different things; mixing them is how
  a knowledge base starts lying.
- **Inferring the class from the memory's `type`** (the first harvester).
  Rejected: four memory types cannot carry six classes — measured on the
  first five memories, the mapping mis-filed two of three — and it needed
  a mapping table, a special case and a refusal to answer one question.
- **Transcripts or a session-memory plugin as input.** Both retired: a
  memory file is one fact written deliberately with its why, already the
  shape of a claim, needing no model pass and no scraping.
- **A hand-maintained index, or a database.** Rejected: a hand-written
  index drifts; committed JSON keeps a drain reviewable as a diff. A
  generated SQLite edge cache is the step if multi-hop queries become
  routine — derived, never authoritative.
- **Refusing a claim that carries a name** (the first hygiene).
  Rejected: the knowledge is lost with the name; substitution
  keeps the fact and names the fix.

## 4. Rationale

Each separation here is ADR-000's principle applied to knowledge: the
field outlives any project, a project's knowledge belongs to the project,
and what one session learnt must outlive the session. Filing by kind of
truth is what lets a reader weigh a slice — a `solution` slice is a claim
about the tree as of a date, and the tree wins — so the corpus can be
curated rather than accumulated. Opt-in by the author, provenance on
every slice and a generated index trade volume for trust: fewer claims
arrive, and each can be traced to who learnt it, where and when.

## 5. Binding Rules

1. Where each class lives is decided only by `tools/fabric/layout.py`;
   the harvester, assembler, linter and query tool import it. Project
   classes (`solution`, `intersection`, `rationale`, `workflow`,
   `threads`) live in the project's working copy under
   `.agent-fabric/memory/<role>/`, never in this repository; the domain
   class under `memory/domains/<domain>/`; a claim with two or more
   owners under the matching `shared/`.
2. `charter`, `brief` and `recall` are authored identity: the harvester
   refuses them as a `roles_class` (`HAND_AUTHORED_CLASSES`), and lint
   refuses a slice of those classes anywhere under `memory/`. `index` is
   generated and refused as a class too.
3. A memory is drained only if it carries `roles_class`; one without it
   is skipped and **named** in the harvest report. A memory whose class
   is hand-authored, generated or unknown, whose `shared_with` names a
   non-slug, or whose body carries a credential by shape refuses the
   **whole** drain of that account, with the file named.
4. A memory written in another language drains through the English
   rendering under its `## English` heading, and a non-Latin description
   through `description_en`; one without them is named under
   `needs_rendering`, yields no claim, and holds the watermark below
   itself so the next drain names it again. Nothing renders a memory but
   its holder.
5. Each agent drains only its own memory; nothing reads another account's
   home. A bundle is refused, by name, when a file is missing or its
   digest differs from the manifest, when the tar holds a file the
   manifest does not name, when manifest and harvest report disagree on
   agent, host, role or project, or when its manifest names another
   agent than the login it came from (`wrong-agent` in `fabric-ctl`).
6. Every slice carries provenance written by the assembler: `origin`
   (agent, host, project, working copy — four facts), `derived_from`
   (observation hashes), `distilled_at`, and `topic` on a slice of the
   directory shape or under `shared/`. Lint refuses a non-identity slice
   with no `derived_from`. A row that resolves to no agent is reported
   provisional, never guessed; `clone_id` records from before the
   identity migration are kept verbatim.
7. Every section ends with *Observed YYYY-MM-DD (role)*, from the
   memory's own `modified` stamp or else its mtime — the role, never the
   login.
8. Every `INDEX.md` is generated by the assembler from slice
   frontmatter; lint fails when an index misses a slice, links one that
   does not exist, or carries a description other than the slice's.
   Index links are relative to the working copy; a fabric-side slice is
   linked as `../agent-fabric/<path>`.
9. Evidence from a sibling project is `knowledge_scope: domain-only`;
   the assembler refuses such a claim, before writing anything, on any
   class but `domain`. The sibling project is not named: a project's own
   hygiene list carries the names the assembler substitutes.
10. Hygiene substitutes: a banned hit becomes its `refer_as` or
    `[redacted]` in title, description, body and topic, and is named in
    the report; a claim whose body still reads as non-English is rejected
    and named. Lint refuses a committed slice or payload file that still
    carries a hit.
11. The drain report merges every run of one stamp (one per bundle):
    each bundle's harvest under `harvest_sources`, telemetry per
    agent@host, `files` as the tree holds them after the last run.
    Watermarks are per store (`agent@host`, or `agent@host#<store>` for
    an account's second store, the projects root's): a run replaces the mark of
    each store it harvested with that harvest's own — lower included,
    since the harvester holds a mark below a memory still awaiting its
    rendering — and a run that harvested nothing changes none.
12. A slice an agent believes wrong is corrected at the memory it was
    drained from, or by a memory of the same class carrying `merge_target`
    with the stale section's heading (ADR-014 rule 7); a correction
    without it is filed beside the stale text, not in its place. No
    session edits a slice in place (`identities/prompt/memory.md` tells
    every session so) (A 2026-09-28).
13. Merge mode is the default: a drain reads the existing slices and
    folds new claims into them; regenerating from scratch is never done
    implicitly, an empty delta is a correct outcome, and the same claims
    twice give a byte-identical tree.
14. A memory that opts into the drain is judged when it is written: a
    user-scope PostToolUse hook (`runtime/claude-code/hooks/memory-write-check.py`,
    written by the settings writer) runs the harvester's and lint's own
    rules on that one file and tells the session, one line per problem,
    what the drain would refuse or hold; it is silent otherwise, never
    blocks, and names a credential by its kind only (A 2026-09-28).

## 6. Consequences

- A project's checkout at any commit carries the knowledge that was true
  then, and a change that moves the architecture can move its slice in the
  same series. The cost is a drain that lands in two repositories, in
  ADR-011's order.
- The corpus holds only what an author chose to share; what nobody opts
  in is visibly missing (named), not silently filed wrong.
  `bin/fabric-status` counts each agent's drainable and private memories
  since the last watermark.
- `memory/RUBRIC.md` states the admission bar (durable, not already
  recorded, evidenced, actionable, classifiable). No tool applies it: the
  harvester admits every memory that opts in, so the bar is the author's
  at writing time and the coordinator's at review.
- Recall is deliberate — a session consults the index. Involuntary recall
  (knowledge arriving when matching code is touched) is not built; a
  pre-tool hook or nested skill directories are the documented routes.

## 7. Future Evolution

- What tier 1 holds was a known gap, closed by the banner (A 2026-09-28):
  a session is given the charter and brief, the remit and the index
  pointer; `workflow` slices are cued like every other section, read
  before the work they govern. Their `tier: 1` mark keeps only the larger
  budget (3000 tokens), for procedures. Loading them at start stays
  possible only with a measured budget — they were 45–140 KB per role.
- A domain split or rename is a `layout.py` change.
- A generated edge cache if the citation graph outgrows `jq`.

## 8. Decision Status

Accepted and in force: project knowledge in the project; the opt-in
drain and cadence; bundles and hygiene by substitution; rendering; the
per-store watermark and merged drain report. `memory/README.md` stays
the manual.

## References

- `memory/README.md` (the manual), `memory/RUBRIC.md`,
  `identities/prompt/memory.md`.
- `tools/fabric/layout.py`, `tools/fabric/harvest_memory.py`,
  `tools/fabric/assemble.py`, `tools/fabric/lint.py` (`lint_slices`, the
  index and shared checks), `fabric-query`,
  `identities/schemas/claims.schema.json`.
- `tests/test_harvest_memory.py`, `tests/test_assemble.py`,
  `tests/test_lint.py`.
- `runtime/control/ctl.mjs` (the `memory` op, `wrong-agent`),
  `runtime/claude-code/hooks/session-start.py` (the project layer),
  `bin/fabric-status`.
- ADR-000 (P2), ADR-001 (promotion of a rationale slice), ADR-002 (the
  role's authored files), ADR-011 (landing a drain).

## Amendments

The body above reads current; each change's full note is in [history/ADR-013-amendments.md](history/ADR-013-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-09-28 | What a session is given at start | §7: the known gap closed — the INDEX banner no longer claims the hook gives workflow slices |
| 2026-09-28 | A correction replaces a section only at its source or with merge_target | §5 rule 12: the two ways, per ADR-014 rule 7 |
| 2026-09-28 | A memory is judged when it is written | §5 rule 14: the write-time check, at user scope |
