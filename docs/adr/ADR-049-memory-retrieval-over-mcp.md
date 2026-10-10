# ADR-049 — Memory is retrieved through an MCP server, the curated corpus unchanged

**Date:** 2026-10-10
**Status:** Proposed
**Decision Makers:** the owner (curated slices stay; retrieval by an MCP server); drafted by fabric-coordinator
**Scope:** a `fabric-memory` MCP server over the corpus (`memory/`, a working copy's `.agent-fabric/memory/`); its registration in each login's `~/.claude.json`; the session-start hook's INDEX line, the launch prompt's memory section (`identities/prompt/memory.md`) and agent-fabric's `CLAUDE.md` "Knowledge you retrieve"; how retrieval is measured
**Pillar:** P2

## 1. Context and Problem

The corpus (ADR-013) is curated knowledge: drained from agents' memories,
judged against a rubric, filed by scope and kind, each section dated. It
reaches a session only by pull. The launch prompt carries the charter, the
brief and the shared sections; the session-start hook carries the
project's remit and one line pointing at the role's INDEX.md; a slice is
read only if the agent opens the file. On 2026-10-10 `fabric-ctl all
recall` counted 325 sessions in 24 hours with no INDEX read and no slice
read. The same day a verification against main found 32 of agent-fabric's
69 slices stale. The pipeline ends where push stops and pull begins.

The owner weighed automatic capture (claude-mem: hooks record every tool
use and inject at session start) and declined it: the fabric keeps
processed, token-efficient slices, not raw observations. What is missing
is retrieval a session will actually use.

## 2. Decision

A local MCP server, `fabric-memory`, retrieves from the curated corpus.
Its tools answer cheaply first and in full only on request: cue lines and
section ids, then one section. The corpus, the drain and the rubric are
unchanged.

## 3. Alternatives Considered

- **Automatic capture (claude-mem or similar).** Declined by the owner: it
  stores what happened, not what was learnt, and costs a model call per
  observation; the fabric's value is the processing.
- **Inject cue-matched slices at session start from the hook.** Pushes
  tokens into every session whether the work needs them or not, and the
  hook cannot know the task. Kept as a possible later layer (§7).
- **Fold the knowledge into the briefs.** Briefs are paid by every
  session, every turn; they hold what the role always needs, not what one
  task might.
- **Embeddings.** A vector index needs a model or a dependency (ADR-040
  rule 1: the standard library), and BM25 over short, cue-headed sections
  is enough for a corpus of a few hundred sections.

## 4. Rationale

A tool in the session's tool list is discoverable in a way a path in a
hook line is not; a ranked list of cue lines costs tens of tokens, and the
full section is fetched only when it matches. The curated corpus stays the
one source of truth, so the drain's judgement and provenance keep their
meaning.

## 5. Binding Rules

1. `fabric-memory` is a stdio MCP server in Python's standard library, on
   the pinned interpreter (ADR-040), started by Claude Code, one per
   session, running as the session's own login. It opens no network
   connection, writes nothing under the corpus, and calls no model. It is
   registered the way `runtime/mcp/websearch-locale/install.py` registers
   its server: `runtime/mcp/fabric-memory/install.py` merges an entry
   named "fabric-memory" into the login's `~/.claude.json` (user-scope MCP
   servers live there, not in `settings.json`). The entry runs the command
   `fabric-memory-mcp` by name on PATH, the `~/.local/bin` link every
   `bin/` command has (ADR-040 rule 7), never a `bin/` path; the installer
   recognises its own entry by the name "fabric-memory" and that command.
   `tools/fabric/install_agent_files.py` calls it for every login
   (`runtime/claude-code/install-agent-files.sh` is only a shim to it);
   its contract header and both parity tests
   (`runtime/claude-code/test_install-agent-files.sh`,
   `tests/test_install_agent_files.py`) change with the new call.
2. It reads only the corpus the login already has: the fabric's
   `memory/` (through `tools/fabric/roots.py`) and the session's working
   copy's `.agent-fabric/memory/`.
3. Four tools, cheapest first:
   - `memory_find(query, role?, project?, limit?, max_tokens?)` — ranked
     section hits, each as one line: slice id, section heading (the cue),
     kind, *Observed* date, scope, the section's size in tokens and its
     score; no body; the reply stays within its token budget, shows one
     best section per slice, and adds the count of hits in other scopes.
     A query with no hit answers with the index's closest cue terms
     ("try: …"), never an empty reply.
   - `memory_read(ids, max_tokens?)` — one or more sections by id, each
     with its provenance line and the cue lines of its related slices,
     cut at `max_tokens`; a slice id alone lists its sections.
   - `memory_index(role?, project?)` — the INDEX cue lines for that role
     and project.
   - `memory_mark(id, verdict, note?)` — `verdict` is `helpful`, `wrong`
     or `stale`. It appends one line to the login's own state,
     `agents/<login>/memory-marks.jsonl` (mode 0600: time, id, verdict,
     the note cut at 300 characters), and refuses an id that
     `memory_find`, `memory_read` or `memory_index` has not returned in the
     session. The server still writes nothing under
     the corpus; a mark is evidence for the drain, not an edit.
4. Ranking is BM25 with separate weights for the cue, the slice's title
   and the body, tokenising identifiers (paths, `snake_case`, `--flags`)
   as words, built at server start (or on a corpus change) in memory; the
   session's role and project rank first, other scopes are counted, and
   near-duplicate cues are shown once. Each hit is labelled `strong`,
   `weak` or `none` from its BM25 score and its coverage of the query's
   idf weight; a list whose best hit is not strong opens with "weak
   match: read only if the cue fits". The index is a library,
   `tools/fabric/memory_index.py`, which the server imports and a later
   hook reuses. No embeddings, no model call.
5. Decay is shown, not hidden: a `solution` hit carries its *Observed*
   date and "verify against the tree"; a section a `merge_target`
   correction replaced is never returned.
6. The server never returns a secret: it serves only what lint has
   already admitted to the corpus (`policies/hygiene.json`), and refuses
   a path outside rule 2's roots. That holds for the fabric's `memory/`
   and for a working copy's committed corpus: the server reads git's
   committed tree (`git show HEAD:<path>`), not the working tree, so an
   uncommitted slice, which no lint has seen, is refused, not served.
7. Each call is recorded in the login's own state
   (`agents/<login>/memory-calls.jsonl`: time, tool, hit count, the ids
   returned and whether a find was followed by a read; never the query's
   text), so the zero-hit rate, the read-through rate and the slices never
   retrieved can be computed; an offline set of expected hits is kept with
   the tests. The harvest bundle carries the call log's counts (calls per
   tool, zero-hit finds, finds followed by a read, the corpus ids read;
   never query text) and the marks, through `fabric-ctl <login> memory`,
   and the drain report lists them per login and per section id. Agents
   may live on different hosts, so nothing here is read from another
   account's state directly. This amends three contracts: the bundle
   gains `marks.jsonl` and the call-log counts, which the manifest names
   (ADR-013 §5 rule 5 refuses a file it does not); the drain report gains
   a retrieval section per login (ADR-013 §5 rule 11); and the `memory`
   op of ADR-029 §5 rule 9 harvests them with the memories. A mark's
   note is free text and crosses the relay, so the harvester applies its
   credential check (`harvest_memory.credential_hits`) to each note
   before the bundle leaves the account: a note with a credential by
   shape travels empty, the mark kept and the withheld notes counted;
   the rest of the call log travels as counts only (ADR-029 §5 rule 6).
8. The session-start hook's INDEX line names the tools ("ask
   `memory_find` before changing …") instead of a file path. The hook
   is `runtime/claude-code/hooks/session-start.py`, and
   `tests/test_session_start.py` changes with it. The two other texts
   that teach the pull-by-path flow change with it: the retrieval line
   of `identities/prompt/memory.md` and agent-fabric's `CLAUDE.md`
   "Knowledge you retrieve".

## 6. Consequences

- Retrieval becomes measurable per login, and the drain's work can be
  judged by whether it is used.
- Stale slices are served with their dates; verification and correction
  (merge_target) stay necessary and matter more once slices are read.
- One more process per session, small and local.

## 7. Future Evolution

- Aliases on a slice, written by the drain, indexed as their own field.
- Anchors on a `solution` section, "verify: path::symbol", to come with
  the record that makes them.
- An action-time recall hook, after a week of measured use.
- An embedding or model re-rank, only if the counts show misses that
  better cues cannot close.

## 8. Decision Status

Proposed. The owner chose curated slices with MCP retrieval, in the
coordinator's session; acceptance is theirs.

## References

- ADR-013 (the memory model; §5 rules 5 and 11 amended by rule 7),
  ADR-029 (§5 rules 6 and 9: the `memory` op and what a reply carries),
  ADR-040 (Python, the standard library,
  the wire freeze), ADR-045 (roots, the operator tree)
- `memory/README.md`, `memory/RUBRIC.md`
- `tools/fabric/control/ops/activity.py` (the recall operation)
