# agent-fabric-coord — the plan (for the owner's review)

GZCoord in its own repository: the protocol, its decision records, a written contract
and its validations, organised as a product rather than a directory of the control
plane. Asked by the owner on 2026-10-19, beside the rule that GZCoord never enters
InterWeave, which stays a general-purpose transport for people too. Proposed by
fabric-coordinator; nothing moves until the owner has answered [the questions](#the-owners-questions).

**Read from**, on 2026-10-22, `origin/main` at `a59d6fd9`: `git ls-files`, the import
graph of `tools/fabric/gzcoord/` (each module's non-stdlib imports), the decision records
that name GZCoord more than three times, and every file that cites the protocol's path.

## What GZCoord is in agent-fabric today

| Piece | Where | Size | Leans on the fabric for |
|---|---|---|---|
| The wire contract: SPEC, MESSAGE-FORMAT, SEMANTICS, CONFORMANCE, examples | `communication/gzcoord/protocol/` | 1,100 lines | nothing |
| Transport documents: adapter contract, human relay; retired transports | `communication/gzcoord/{docs,history}/` | — | nothing |
| The reference implementation: validator, compose, send, inbox, intake, bypass, i18n | `tools/fabric/gzcoord/`, `bin/gz*` | 4,750 lines | `identity` (who sends), `jobs` (intake queues a REQUEST, ADR-037), `episodic` (the journal, ADR-041), `roots`, `launch_locale`, `hidden_unicode`, `httpsafe`, the role catalogue |
| The relay: unit, catch-up, the client side | `communication/gzcoord/runtime/`, `tools/fabric/relay*.py`, `inbox_parts/relay.py` | — | the operator account, its store's token (ADR-033 §5 rules 5–6) |
| The session wiring: watch at launch, held while planning, drain at start, stop guard | `runtime/claude-code/hooks/{session-start,inbox-watch,watch-on-stop,self-kill-guard,job-copy-guard}.py`, `plan_hold.py` | — | the harness lifecycle (ADR-022) |
| The validations | `tests/test_gzcoord_*.py`, `communication/gzcoord/tests/parity/corpus.jsonl`, `tests/fixtures/gzcoord-operator/` | 6,460 lines | both: wire-level cases and implementation cases mixed in one file |
| The decision records | ADR-032 (the contract), ADR-033 (transports), ADR-030 (presence); GZCoord parts of ADR-023, ADR-024, ADR-028, ADR-041 | — | — |

The reverse direction matters as much: **the control plane rides GZCoord's relay**.
Every account's agentd answers signed actions on `fabric:control` over the same relay
(ADR-029), and 19 fabric modules import `gzcoord` directly (27 reach it by import or
path) — the launcher, the job list, presence, `fabric-ctl`, the arm. GZCoord is not a leaf of agent-fabric; it is woven
through it.

## The cut

One rule decides every file: **what a second, independent implementation would need
goes to agent-fabric-coord; what makes the fabric's own agents speak it stays.**

**Moves.** The four normative files and their examples; the adapter contract and the
human-relay document; the transport history; the GZCOORD/1 decision records, re-issued
in the new repository's own series; the conformance suite (below); the GZCoord-over-
InterWeave mapping and the carrier's record, which have no home yet and were promised
this one (InterWeave ADR-0055 keeps only what any machine client gets).

**Stays, as a consumer.** The implementation, the relay unit, the hooks, the journal,
intake into the job list, the i18n catalogue the implementation renders from, and the
control plane's use of the relay. They are agent-fabric runtime: they import identity,
jobs and state, and they reach every account through `fabric-ctl all upgrade fabric`
today. Moving them would add a second repository to every account's bootstrap and
upgrade path for no reader that exists yet.

**Phase 2, only on a trigger.** The implementation moves when a second consumer
appears (a carrier written outside agent-fabric, a person's client, another
organisation under ADR-035) — and then as a library the fabric pins, after its
`identity`, `jobs` and `episodic` imports have become parameters. Not planned now.

## The contract

`CONTRACT.md` at the new repository's root, the one page an implementer reads first:

- **What it defines**: GZCOORD/1, the message as text — grammar (SPEC §6), types,
  required and optional metadata, semantics of REPLY-EXPECTED, assignment and
  cooperation as message rules.
- **What it does not**: identity (an address is `<host>/<login>`, and who a login is
  stays the operating system's), transport, storage, jobs, sessions.
- **The compatibility rule**, moved from ADR-032 unchanged: within /1 the accepted set
  only narrows; a disagreement between old and new readers is GZCOORD/2.
- **Conformance**: an implementation conforms when it gives the corpus's verdict on
  every case; the version of the corpus it was measured against is named.
- **Who changes it**: fabric-coordinator alone, every change with an amendment of the
  contract's record, as today.

## The validations

The corpus is the contract's executable form; tests that exercise the fabric stay.

1. **Classify** every case in `tests/test_gzcoord_*.py`: *wire* (a message in, accept or
   reject with a reason out, nothing else consulted) or *implementation* (a send, a
   watch, a lock, the journal, a job). A python-dev REQUEST, with a mutation control per
   class: a planted grammar defect must fail a wire case, a planted lock defect must
   not.
2. **Extract** the wire cases into `conformance/corpus.jsonl` beside the examples, the
   existing parity corpus folded in; one reason code per rejection, defined in
   CONFORMANCE.md.
3. **Split the validator.** `gzmsg.py` mixes the grammar with fabric checks (a role in
   the catalogue, an address on a registered host, localized messages). The grammar part
   becomes `conformance/validate.py`, standard library only (ADR-040), the reference
   validator; the fabric's checks stay in `gzmsg.py`, which calls the same grammar
   rules.
4. **Pin.** agent-fabric records the coord commit it conforms to (a pin file, read
   like the Claude Code pin), and its CI checks that commit out and runs the corpus
   against its own validator. A bump is a pull request on agent-fabric that the
   corpus passes.

## The seams, one by one

| Seam | Today | After |
|---|---|---|
| Hooks (watch, hold, drain, stop guard) | fabric | fabric; they cite the coord contract for what a message is |
| Inbox and send | fabric | fabric, conforming at the pin |
| Journal (ADR-041) | fabric state | fabric state; the record keeps "the carrier is provenance" and cites coord for MESSAGE-ID |
| Relay hosting (ADR-033 §5 rules 5–6, the unit) | fabric | fabric: it is the operator's service and the control plane's channel. The adapter contract and the human relay move; which relay runs is an operational choice |
| The InterWeave carrier | nowhere | its mapping and record in coord; where its code lives is that record's question |
| ADR numbering | agent-fabric ADR-NNN | coord's own series, cited "agent-fabric-coord ADR-NNN", as the gateway's are; agent-fabric keeps each moved record's file as a stub naming its successor, so the 22 files that cite ADR-032 or ADR-033 still resolve, and `fabric-adr lookup` follows the stub |
| Authority | the repository-wide trailer fence (`policies/AUTHORITY.md` row `communication/gzcoord/protocol/*`) | the coord repository's taxonomy gives its protocol and records to fabric-coordinator; the same commit hooks and CI check, installed as for any managed repository; the agent-fabric row retires with the directory |
| i18n | the catalogue renders protocol words for the reader (ADR-028) | the catalogue stays (runtime); which words are protocol vocabulary is the contract's |

## The order

| Step | What | Who |
|---|---|---|
| 0 | This plan; the owner's answers | fabric-coordinator, the owner |
| 1 | Create `BlueTeam-OU/agent-fabric-coord`, Apache-2.0, registered in `projects/registry.json` with taxonomy and remits (the `repo-lifecycle` skill) | the owner creates; fabric-coordinator registers |
| 2 | Move the protocol, documents and history with their history (`git subtree split`), amend ADR-032 ("moved, unchanged") in the same agent-fabric PR that removes them | fabric-coordinator |
| 3 | Re-issue the records in coord's series; stubs and DIGEST rows in agent-fabric; `fabric-adr lookup` follows a stub | fabric-coordinator; the lookup change to python-dev |
| 4 | `CONTRACT.md`; classify, extract, split the validator, pin | fabric-coordinator writes the contract; python-dev the rest, one REQUEST |
| 5 | Sweep every restatement: this role's charter ("amendment of agent-fabric ADR-032"), `AUTHORITY.md`, the gzcoord skills, each project's `integration/gzcoord/CLAUDE.md`, the remits, the slices | fabric-coordinator |
| 6 | The carrier record, in coord | fabric-coordinator, with architect-cto-01's transport facts |

Steps 2 and 3 land together: a protocol moved without its record would leave the
amendment rule pointing at nothing. The grammar freeze is untouched — a move changes
where the text lives, never what a reader accepts.

## The owner's questions

1. **Scope.** Protocol, records, contract and conformance now, the implementation
   staying as a consumer until a second one exists (recommended) — or everything at
   once, adding the coord repository to every account's bootstrap?
2. **History.** Carry the protocol's git history across with `git subtree split`
   (recommended, keeps blame for every MUST) — or start the repository fresh with a
   pointer back?
3. **Visibility.** Public, as agent-fabric is and as a protocol meant for other
   implementations should be (recommended) — or private for now?
4. **Moved records.** A stub in agent-fabric for each moved record (recommended, every
   existing citation keeps working) — or rewrite every citation to the new series?
