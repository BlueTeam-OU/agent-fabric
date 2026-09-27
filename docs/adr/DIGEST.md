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
| which model a class runs on; review-grade; shims; fabric-model | ADR-005 |
| how hard a class thinks; effort levels; CLAUDE_CODE_EFFORT_LEVEL | ADR-006 |
| a safeguard flag; model fallback; "Switched to" | ADR-007 |
| Claude Code settings on every account; attribution; auto-update; the harness prompt | ADR-008 |
| upgrading the fleet; distributing after a merge; fabric commands without approval | ADR-009 |
| hosts and placement; hostexec; provisioning an account; fabric-lease and host memory | ADR-010 |
| fabric-ref; a project's CI red from a fabric push; landing a drain | ADR-011 |
| secrets, keys, tokens; Doppler; reporting a leaked secret | ADR-012 |

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
- A 2026-09-27 — the coordinator's proposals, P7 among them, adopted
  by the owner; the body no longer marks them.
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
  header, charter, brief, team, memory — byte-stable, no project; a
  language-culture login with a locale harness translation replaces the
  prompt instead (`--system-prompt-file`, the translation last). The
  project remit arrives from the SessionStart hook (§5 rules 4–5).
- Drift is printed by `fabric-status`; a binding is per (agent, host)
  (§5 rules 6–7). Brief is identifier-free, the remit anchored (§5 rule 8).
- Keywords: identity, login, whoami, role, bind, launch prompt, charter,
  brief, remit, drift, binding, dimensions.

### ADR-003 — Per-agent state is one layer (Accepted)

- Every write under `agents/<login>/` goes through `runtime/identity.py`:
  `atomic_write`, `update_binding`, `append_history`; no caller opens a
  state file for writing. The Node control agent, which cannot import it,
  writes by temporary and rename (§5 rule 1).
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

### ADR-005 — Models are routed by capability class (Accepted)

- A task names one of five classes (`code-low`, `code-medium`,
  `code-high`, `code-plan`, `code-review`); `routing/capabilities.json`
  and the per-provider profile layers decide the model (§2, §5 rules 1, 4).
- A dispatch's `model` is its class's tier alias, checked by the dispatch
  guard; writing classes run in a worktree (§5 rules 1–3).
- The review class's model reaches its agent file, never an export, and
  is gated by `routing/policies/review-grade.json` (§5 rules 5–6).
- No settings scope pins a model; shims are live-tested per family; a
  model enters routing only after a read-back (§5 rules 7–10).
- Today: every class on plain claude is Opus 5.5 (the owner, 2026-09-25);
  on the broker, DeepSeek V4 Pro for session, high, plan and review, GLM
  for low and medium (the owner, 2026-09-19) (§2).
- Keywords: model, routing, capability class, alias, provider, OpenRouter,
  broker, review-grade, shim, preset, Opus 5.5, DeepSeek, GLM, profile.

### ADR-006 — Effort is routed (Accepted)

- Each class's reasoning effort is routed beside its model, in
  `routing/effort.json`, one seven-level ordinal vocabulary (§2, §5 rule 1).
- The fabric fits a level to what the model admits before the request
  leaves — the vendor's mapping, else down, and up to the model's floor;
  a lost, raised or inexpressible level is a committed override with a
  note, or `routing.py check` fails (§5 rules 2–3).
- A class's level reaches its subagent via the agent file's `effort:`
  line; the session's via `--effort`, stamped (§5 rules 4–5).
- `CLAUDE_CODE_EFFORT_LEVEL` is refused in any value; committed settings
  carry no effort keys; never set per dispatch (§5 rules 6–7).
- Today every class and session asks `medium` (the owner, 2026-09-25);
  broker `code-low` is committed at `low` (§2).
- Keywords: effort, reasoning, thinking, level, clamp, medium, high,
  --effort, agent file, CLAUDE_EFFORT, Opus 5.5 default.

### ADR-007 — A flagged request is contagious (Accepted)

- A session whose request a model's safeguards flagged holds text that
  flags every session it reaches; the fabric tells it at the switch (§2).
- `model-fallback-note.sh` on `PostModelSwitch` (`source: "auto"`) names
  the models, the category and the stickiness; a per-pid marker makes
  `send.mjs` repeat the reminder; `fabric-status` shows it as drift (§5
  rules 1–3).
- After a flag a finding travels by locator and class, never content;
  a delivery that flags you is answered by locator (§5 rule 4).
- Each project's `.claude/settings.json` wires the hook (§5 rule 5).
- Keywords: safeguards, flagged, fallback, contagion, PostModelSwitch,
  classifier, locator, broadcast.

### ADR-008 — Harness behaviour is pinned by measurement (Accepted)

- A harness behaviour the fabric relies on is read back live or out of the
  binary, with build and date, in a live check (§2, §5 rule 1).
- The fabric's keys go into user scope via `user-settings.py`:
  attribution off, `DISABLE_AUTOUPDATER`, thinking summaries and verbose,
  fabric-command allow rules, `defaultMode` auto (§2, §5 rule 2).
- Attribution off plus the commit-msg guard (§5 rule 3); the version moves
  only through `harness.json` and `upgrade claude` (§5 rule 4).
- `harness/en.md` is the captured harness prompt, verbatim, refreshed on a
  new build (§5 rule 5).
- Keywords: Claude Code, harness, settings.json, attribution, Co-Authored-By,
  auto-update, DISABLE_AUTOUPDATER, verbose, auto mode, system prompt, build.

### ADR-009 — Fleet operations are signed control-plane actions (Accepted)

- An operation on accounts is a signed action each account's daemon
  verifies, performs and answers; never a hostexec/sudo loop per login
  (§2, §5 rules 1–2).
- `upgrade claude`: the pinned version, installs queued on a host lease
  before any stop, SIGTERM only, the session resumed (§5 rules 3–4).
- `upgrade fabric`: origin/main's sha, fast-forward or nothing, bootstrap
  every time, no session stopped; run by the coordinator after every
  merge (§5 rules 5–6). Any failed row exits 1 (§5 rule 7).
- Fabric commands run by name from `commands.json`, linked into
  `~/.local/bin` with narrow allow rules; wrappers still ask (§5 rules 8–9).
- Keywords: fabric-ctl, upgrade, distribution, signed, control plane,
  agentd, hostexec, harness.json, commands.json, approval, allow rule.

### ADR-010 — Hosts, provisioning, host execution and resources (Accepted)

- `runtime/hosts/registry.json` holds hosts and placements; `hostexec`
  runs one command on a host — local or over ssh, the same worker (§2).
- Nothing touches an account's host but through `hostexec`; placement is
  not identity; the host reports itself; secrets on stdin (§5 rules 1–5).
- `new-agent.sh` provisions idempotently; GitHub host keys from the
  published set; nothing about accounts in the Qubes TemplateVM (§5 rules
  6–8).
- Every memory-heavy job takes the host lease `heavy` (`fabric-lease`,
  `--need-mem`); refusals end with a `reason=` line; call sites are the
  project's (§5 rules 9–11). Quota and fleet lease are not built (§2).
- Deferred by the owner (2026-09-26): a shared Android SDK/Gradle cache,
  until a second Flutter login needs it (§7).
- Keywords: host, placement, hostexec, fabric-host, ssh, provisioning,
  new-agent, Qubes, persist-accounts, moveto, lease, heavy, memory, crash, OOM.

### ADR-011 — Managed projects consume the fabric at a pinned ref (Accepted)

- A managed project's `.agent-fabric/fabric-ref` names the fabric commit
  its indexes match; its CI checks that commit out, never the fabric's
  default branch (§2, §5 rules 1–2).
- A drain lands fabric first, then `fabric-ref` written and the project
  PRs armed at once; the ref moves only with matching indexes (§5 rules
  3–4).
- Until a project's pin is live, a fabric push that changes its index
  waits for an empty queue and goes out with the index PR (§5 rule 5).
- Keywords: fabric-ref, pin, cross-repo, lint window, drain, merge queue,
  CI, project checkout.

### ADR-012 — Credentials (Accepted)

- An identity's secrets live in Doppler, project `agent-fabric`, one
  config per login; the account holds one read-only token and
  `fabric-secrets sync` applies the rest; nothing is committed (§2, §5
  rules 1–2).
- No tool prints a value; enrolment never passes one through a terminal
  or argv; `fill-from` never copies identity or coordinator credentials
  (§5 rules 3–4).
- A secret is described by shape and locator, never reproduced (SPEC §17)
  (§5 rule 5).
- A destination and its credential move together, with a check on the
  secret itself; credentials are tested by shape (§5 rules 6–7).
- Keywords: credentials, secrets, Doppler, token, API key, fabric-secrets,
  enroll, rotation, leak, shape, locator, base URL.
