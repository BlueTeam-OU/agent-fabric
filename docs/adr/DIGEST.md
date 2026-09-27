# Decision digest — read first

What is true now, one entry per record. Non-normative: where an entry and
its record disagree, the record wins. `tools/fabric/adr.py lookup <word>`
searches it.

| Looking for | Record |
|---|---|
| what the fabric is for, the pillars | ADR-000 |
| how a decision is recorded, amended, accepted | ADR-001 |
| who an agent is; role binding; the launch prompt | ADR-002 |
| writing per-agent state; binding.json; rename a working copy | ADR-003 |
| adding a role or a project; the order of the commits | ADR-004 |

### ADR-000 — The enduring organization (Accepted)

- agent-fabric is infrastructure for **enduring organizations** of people
  and agents; the promise is turning temporarily available intelligence
  into lasting collective capability (§2).
- The principle: separate what must endure from what must be able to
  change — identity ≠ model, expertise ≠ session, collaboration ≠
  orchestrator, a project's knowledge ≠ the infrastructure (§2).
- Seven pillars, each with a Today and a Direction: P1 Outlives its tools
  · P2 Learns, not merely remembers · P3 Autonomy with verifiable
  commitments · P4 Diversity of expertise · P5 Autonomy from
  infrastructure · P6 Federation · P7 Sustainable operation (§5 rule 1).
- A decision that ties what must endure to what will change must justify
  it (§5 rule 3). The record changes only by the owner's amendment (§5
  rule 4).
- Keywords: vision, purpose, pillars, principle, endure, direction.

### ADR-001 — Decision records (Accepted)

- Decisions live in `docs/adr/` on gzapp's engine: numbered records,
  amendment in place with a history note, supersession with a point map;
  the index is generated (§2).
- fabric-coordinator writes; the owner accepts, and `Accepted` needs a
  `Ratified:` line naming where the owner's word is; merging ratifies
  already-practised records, and a new record only when the PR says arming
  ratifies it and the owner arms it so (§5 rules 1–2).
- An ADR body edit needs an Amendments row or an `ADR-Editorial:` trailer
  (§5 rule 4); from outside, cite "agent-fabric ADR-NNN" (§5 rule 6).
- Live checks are immutable evidence (§5 rule 8); `sources/` keeps the
  verbatim texts a record paraphrases, never edited (§5 rule 9).
- Keywords: ADR, amendment, supersede, ratify, index, digest, rationale.

### ADR-002 — Role, login and model are kept apart (Accepted)

- The Linux login is the agent; directory, repository, branch, project and
  session are context. Agent, role, project, working copy, host, session
  and capability/model are kept apart — the canonical table is §2 (§5
  rules 1–2).
- A role is bound from a login shell only (`fabric-role bind`), refused
  inside a session; a different role is a relaunch (§5 rule 3).
- The role rides in the system prompt (`--append-system-prompt-file`):
  header, charter, brief, team, memory — byte-stable, no project; the
  project remit arrives from the SessionStart hook (§5 rules 4–5).
- Drift is printed by `fabric-status`; a binding is per (agent, host)
  (§5 rules 6–7). Brief is identifier-free, the remit anchored (§5 rule 8).
- Keywords: identity, login, whoami, role, bind, launch prompt, charter,
  brief, remit, drift, binding, dimensions.

### ADR-003 — Per-agent state is one layer (Accepted)

- Every write under `agents/<login>/` goes through `runtime/identity.py`:
  `atomic_write`, `update_binding`, `append_history`; no caller opens a
  state file for writing (§5 rule 1).
- Every read-modify-write holds `agent_lock`, a re-entrant flock (§5 rule 2).
- A binding is per (agent, host); another host's is refused (§5 rule 3).
- A working-copy rename merges history, never overwrites (§5 rule 4); the
  session-start hook stays non-blocking (§5 rule 5).
- Keywords: state, binding, atomic write, lock, flock, rename, history,
  host, XDG_STATE_HOME.

### ADR-004 — Adding a role without breaking anyone's CI (Accepted)

- A role is added in four steps, in order: the role here; the binding PR
  in the project; the drain, both sides; the account (`new-agent.sh`)
  (§2, §5 rule 1).
- No generic file names the project; the remit does (§5 rule 2).
- In the drain the project side is committed first and the fabric commit
  pushed before the project's checks run (§5 rule 4); a colliding claim
  waits for the owner (§5 rule 5).
- A failing intermediate state is fixed by landing the missing half,
  never by loosening the lint (§5 rule 6).
- Keywords: new role, onboarding, catalog, taxonomy, remit, INDEX, drain,
  new-agent, merge queue, CI.
