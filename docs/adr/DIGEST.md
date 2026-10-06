# Decision digest — looked up, never read whole

What is true now, one entry per record. Non-normative: where an entry and
its record disagree, the record wins. Look it up, never read it whole:
`fabric-adr lookup <word>…` answers the entries that mention every word,
`fabric-adr lookup` alone this table.

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
| where knowledge lives; memory classes; the drain; INDEX.md; hygiene | ADR-013 |
| a drain stopped by a collision; supersede, keep-both, drop; merge_target | ADR-014 |
| what a comment is for; stale comments; the stronger executable form | ADR-015 |
| writing a SKILL.md; dates and PR numbers in skills; skill-creator | ADR-016 |
| live checks; read-back; evidence; a prompt change before pushing | ADR-017 |
| who may commit here; Fabric-Role; the hooks; the locale carve-out; what a guard is | ADR-018 |
| opening, counting and arming a PR; pr-gate; Co-authored-by; GitHub settings | ADR-019 |
| the blind review; code-review dispatch; post-review; what counts as coverage | ADR-020 |
| scratch a suite leaves; TMPDIR; containers after a test; cleaning caches | ADR-021 |
| the inbox watch at start; auto mode; plan mode holds the inbox; planning in presence | ADR-022 |
| TO-ROLE; who gets a REQUEST; two holders of one role; claiming an assignment | ADR-023 |
| a message is advisory; working on a request together; OWNER-WORD | ADR-024 |
| branches with no PR; what shares my paths; do two branches combine | ADR-025 |
| measuring progress; supervision; verified result (proposed) | ADR-026 |
| the language-culture role; the locale worker; the prompt in the locale; locale search | ADR-027 |
| dictionaries; the i18n standard; the inbox in the reader's language; GZCOORD_DEFAULT_LOCALE_ONLY | ADR-028 |
| the control agent; fabric-ctl; the control channel; what an account reports; the drain over the relay | ADR-029 |
| is an agent online; HELLO and GOODBYE; send exits 4; --force | ADR-030 |
| which Claude account a login runs on; moving logins; setup-token; usage windows | ADR-031 |
| changing the GZCoord protocol; the grammar freeze; GZCOORD/2 | ADR-032 |
| the relay; the human relay; transports; Telegram; the adapter contract | ADR-033 |
| what a failure may take; single points; degraded modes | ADR-034 |
| working with another organization; portable trust; what may be shared | ADR-035 |
| cost per verified result; spend; shared resources | ADR-036 |
| your job list; fabric-jobs; the next job and a fresh session | ADR-037 |
| an agent's key and secrets; the store; provision; recovery; backup | ADR-038 |
| the agent id; UUIDv7; renaming a login | ADR-039 |
| which language a tool is written in; the bash size limit and allowlist; porting a script; gh.py, git.py | ADR-040 |
| your GZCoord history; the episodic journal; fabric-history | ADR-041 |
| signed store commits; trusted base; trust-base; a refused store | ADR-042 |
| Claude Code mods; managed settings; where the guards live; the fleet's own mods | ADR-043 |

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
- A 2026-09-27 — a source's edit, rename or removal is refused whatever
  the commit's trailers (§5 rule 9).
- A 2026-09-27 — no inline attribution: who decided and when are the
  header's and the history's (§5 rule 10).
- A 2026-09-27 — a record reads current: no date in §2 to §8; §1 may date an
  incident (§5 rule 11).
- A 2026-09-29 — the DIGEST is looked up (`fabric-adr lookup`), never read whole;
  each entry is at most 250 words (§2).
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
- Every read-modify-write holds `agent_lock`, a re-entrant flock, except
  the Node control agent's own files, which only it writes and the
  launcher only consumes (§5 rule 2).
- A binding is per (agent, host); another host's is refused (§5 rule 3).
- A working-copy rename merges history, never overwrites (§5 rule 4); the
  session-start hook stays non-blocking (§5 rule 5).
- A 2026-09-28 — `fabric-fresh` is a second `restart.json` writer, through
  `identity.py`; `fabric-branches` records its sweeps under `agent_lock`.
- A 2026-09-28 — the job list, `jobs.json`, is per-agent state written by
  `update_jobs` (§5 rule 1).
- A 2026-10-05 — `episodic.db` is a second writer class, a self-contained
  transactional store written only by `episodic.py` (§5 rule 1).
- A 2026-10-05 — the GZCoord logs (`journal-bypass.jsonl`, the send ledger)
  are a writer class; the ledger's unlocked trim is a named gap (§5 rule 1).
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
- Today: on plain claude, Sonnet 5.5 for low and medium and Opus 5.5
  for the rest;
  on the broker, DeepSeek V4 Pro for session, high, plan and review, GLM
  for low and medium (§2).
- A 2026-09-29 — `code-low` and `code-medium` on plain claude are
  `claude-sonnet-5-5`, read back live before the change (§2).
- Keywords: model, routing, capability class, alias, provider, OpenRouter,
  broker, review-grade, shim, preset, Opus 5.5, Sonnet 5.5, DeepSeek, GLM, profile.

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
- Today every class and session asks `medium`;
  broker `code-low` is committed at `low` (§2).
- A 2026-09-28 — the session's level is judged on its model like a class's;
  `providers.<p>.session` acknowledges a downgrade.
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
- A 2026-09-28 — `tui` "default" is pinned, so a session's terminal keeps its
  scrollback.
- A 2026-09-28 — the settings writer adds the memory-write check hook (ADR-013 rule 14).
- A 2026-10-01 — the auto-mode classifier's picture of the fleet is
  policies/auto-mode.json, written into every login's user settings; the
  setup wizard is off (§5 rule 7).
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
- A 2026-09-28 — a `fresh` restart marker starts a new session, not a resume
  (rule 4, ADR-022 rule 10).
- A 2026-09-30 — the signing key is in the operator's own store (§6).
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
- A 2026-09-30 — the coordinator keeps its own store and fills each child's, not Doppler (§2, §5 rule 1).
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

- An identity's secrets live per login, in its own store (ADR-038);
  `fabric-secrets sync` applies them and refuses another login's;
  nothing is committed (§2, §5 rules 1–2).
- No tool prints a value; provisioning never passes one through a
  terminal or argv; `provision share` shares an allowlist and refuses
  the identity and the coordinator's credentials (§5 rules 3–4).
- A secret is described by shape and locator, never reproduced (SPEC §17)
  (§5 rule 5).
- A destination and its credential move together, with a check on the
  secret itself; credentials are tested by shape (§5 rules 6–7).
- A 2026-09-30 — the Doppler layout is replaced by each login's own store (§2, §5 rules 1–4, 8).
- Keywords: credentials, secrets, Doppler, token, API key, fabric-secrets,
  provision, enroll, rotation, leak, shape, locator, base URL.

### ADR-013 — The memory model: scopes, kinds of truth, tiers, the drain (Accepted)

- Knowledge is filed by scope (domain here, project in the project's own
  `.agent-fabric/memory/<role>/`, agent, shared) and by one of six kinds
  of truth; `layout.py` alone says where (§2, §5 rule 1). A `solution`
  slice loses to the tree, a `rationale` slice to a record (§2).
- A memory drains only with a `roles_class`; charter, brief, recall and
  index are refused; a bad class or a credential refuses the account's
  whole drain; each agent drains only its own memory, bundles verified
  (§5 rules 2–5).
- Every slice carries provenance and every section its *Observed* date;
  `INDEX.md` is generated and lint fails drift (§5 rules 6–8).
- Hygiene substitutes names and secrets and names each hit; domain-only
  evidence supports only `domain` (§5 rules 9–10). Merge mode, per-store
  watermarks, a wrong slice corrected by a memory (§5 rules 11–13).
- A 2026-09-28 — a session is given the charter, brief, remit and index pointer;
  workflow slices are cued, read before the work they govern (§7).
- A 2026-09-28 — a wrong slice is corrected at its source memory or with
  `merge_target` (rule 12, ADR-014 rule 7).
- A 2026-09-28 — a drain-bound memory is judged when written: a user-scope hook
  says what the drain would refuse or hold (rule 14).
- Keywords: memory, knowledge, slice, drain, harvest, assemble, roles_class,
  domain, solution, rationale, workflow, threads, INDEX, provenance,
  watermark, bundle, hygiene, redacted, tier.

### ADR-014 — The memory assembler's rules: contested claims, same-agent retitle, corrections (Accepted)

- A claim that disagrees with the corpus stops the drain: nothing
  written, exit 1, every pair named with both texts and dates; sections
  compared undated (§2, §5 rule 1).
- A pair is a different text under a held heading, two claims of one
  drain under one heading, or a retitle in a topic whose own files one
  agent wrote — never inferred from the flat or carried file (§5 rule 2).
- The owner decides `supersede`, `keep-both` or `drop` per heading or
  per claim, recorded in the drain report (§5 rule 3).
- An agent's newer text replaces its own older text without a question —
  never older text, a contested heading, or two agents' texts (§5 rules 4–6).
- `merge_target` replaces the named section wherever it lives in the
  class; ambiguous refuses the run, unresolved is reported every drain;
  the correction keeps its own heading (§5 rules 7–8).
- Keywords: collision, SUPERSEDING, supersede, keep-both, drop,
  --collision-decisions, same-agent, retitle, merge_target, correction,
  observed, idempotent, budget part.

### ADR-015 — Code is memory (Accepted)

- Code is memory for the session that comes after yours: a comment keeps
  the *why* a fresh session cannot reconstruct, never narrates the *what*
  (§2, §5 rules 1–2).
- A useful comment is never trimmed to save tokens; a type, assertion or
  test beats a comment, and a cross-module decision goes in a record (§5
  rules 3–4).
- A comment whose assumption a change made false is fixed in that change;
  an intentional oddity says why beside it (§5 rules 5–6).
- The review class grades narration, a missing reason, an unenforced
  invariant and a stale comment (§5 rule 7). Reaches sessions through the
  workspace `CLAUDE.md`, not a project's own (§2).
- Keywords: comment, why, code as memory, self-documenting, stale comment,
  invariant, refactoring, oddity, review, fresh session.

### ADR-016 — Skills carry rules, not history (Accepted)

- A skill states the rule and its reason, generally; never the date, PR
  number, project or login that taught it (§2, §5 rules 1–2).
- Evidence lives in the commit, a live check or the record the skill
  applies; a pointer to a rule's home may stay, named by repository from
  outside it (§5 rules 3–4).
- Load the skill-creator skill before writing or changing a `SKILL.md`
  (§5 rule 5).
- A description names when to load the skill (§5 rule 6). Lint checks
  rules 1 and 6 — dates, PR numbers, numbered logins, the occasion; the
  rest is review (§6). pg-probe's bare pointers to a project's records
  are open (§7).
- A 2026-09-28 — lint checks a skill's occasion and description (rule 6).
- Keywords: skill, SKILL.md, skill-creator, history, incident, date, PR
  number, evidence, provenance.

### ADR-017 — Measurement before belief: live checks are evidence, prompt changes are read back (Accepted)

- A design decided from documentation is a guess until read back live,
  with a control where a silent failure would look like success (§2, §5
  rule 1).
- The read-back is a dated live check — what was run, where, on which
  build, what it measured and decides; records cite it as Evidence (§5
  rules 2–3).
- A live check is never rewritten: later read-backs are appended, a
  replaced practice gets a banner (§5 rule 4).
- A charter, brief, template or locale change is read back with
  `launch --print` as each affected holder before pushing; the suite
  renders every role under `MAX_CHARS` (§5 rule 5).
- A guard is proved on the shapes its fix removed; a finding says how it
  was verified (§5 rules 6–7). Mostly practice, not mechanised (§6).
- Keywords: live check, read-back, measurement, evidence, control,
  launch --print, MAX_CHARS, prompt ceiling, verify, guard.

### ADR-018 — Authority: one writer role per surface; a guard is hook + CI + suite; the read-only fence (Accepted)

- Authority attaches to roles and policy files, never to logins or
  directories; holding a role gives nothing over its definition (§2).
- agent-fabric, and `.agent-fabric/` in every project, is committed only
  by a session bound to `fabric-coordinator`: the hooks fence it, CI
  reads the `Fabric-Role:` trailer (§5 rules 1–4).
- Every commit carries its role as a trailer; a clean fold passes
  (§5 rules 2–3). A locale's holder commits its translations (§5 rule 5).
- A contributor role (`authority.json` `contributors`) commits its
  entry's paths on its own `for/` branch (§5 rule 8).
- A guard is a commit-time check, a CI check on every added commit and a
  planted suite case (§5 rule 6); a proposal is a message, or a
  contributor's branch (§5 rule 7).
- The charter tripwire reads the base's `authority.json` (§6).
- A 2026-09-28 — the charter tripwire runs in CI.
- A 2026-09-30 — credentials and the stores are this role's (References).
- A 2026-10-01 — the contributor carve-out; a proposal is a message (§5 rules 7–8).
- A 2026-10-01 — the fence's code is never in an entry (§5 rule 8).
- A 2026-10-01 — CI runs main's guards (§5 rule 4).
- A 2026-10-04 — a merge is judged on its own change (§5 rules 3–4).
- Keywords: authority, read-only, fence, tripwire, Fabric-Role,
  pre-commit, commit-msg, charter, locale carve-out, contributor, guard.

### ADR-019 — Work arrives as pull requests: one open PR per agent, 8 or more work commits to arm, the gate read before arming, no machine attribution, repository settings (Accepted)

- Every change reaches `main` through a PR; on agent-fabric since
  2026-09-18, by practice — no ruleset, protection or queue there (§2,
  §5 rule 1, §6).
- One open PR per agent; the next work is another commit while the
  branch is addable; two stated exceptions (§5 rule 2).
- Work commits exclude review fixes (`Answers:` trailer, else the
  subject; `commit-class.sh`): 8 or more arm at the gate, a security
  boundary too, under 8 ask the owner; 16 is the batch size advised
  (§5 rules 3–4).
- Arm only on `pr-gate.sh`'s `MERGEABLE`, read first, with no open P1/P2;
  on agent-fabric arming is the merge (§5 rules 5–6).
- No `Co-authored-by:`/`Claude-Session:` trailer, footer or session URL
  in commits or PR descriptions (§5 rule 7). GitHub settings: §6.
- A 2026-10-04 — `main` is protected: a ruleset requires a pull request,
  the CI checks and signed commits; auto-merge waits for green (§5 rule 6).
- A 2026-10-05 — the ruleset requires CI's aggregate check `ci-ok` alone
  (§5 rule 6).
- A 2026-10-05 — eight or more work commits arm on the gate alone, a
  security boundary and over sixteen included (§5 rule 4).
- Keywords: pull request, PR, arm, merge, band, work commits, Answers,
  pr-gate, MERGEABLE, one open PR, attribution, Co-authored-by, CodeQL,
  repository settings, auto-merge.

### ADR-020 — The review class is the review (Accepted)

- The review class's blind review is the review of every PR: on every
  head, to judge a finding, to re-review a fix range; no automated
  reviewer is assumed (§2, §5 rule 1).
- Dispatch: `code-review`, `model: fable`, description "review…" or
  "re-review…", no isolation; the guard drops the alias so the agent
  file's routed model decides, within `review-grade.json` (§5 rules 2–3).
- The reviewer writes nothing (`review-bash-guard.sh`); its brief is
  facts from `fabric-review brief`, never conclusions (§5 rules 4–5).
- Posted by `post-review.sh` with the marker; counted only when marked
  and posted by the PR's account or a named poster, or unmarked from a
  trusted account (§5 rules 6–7). Legacy markers until the sunset (§5
  rule 8).
- A 2026-10-05 — the reviewer inherits no secret: every command its fence
  lets through runs with a clean environment (§5 rule 4).
- Keywords: review, blind review, code-review, re-review, brief,
  fabric-review, post-review, pr-review-status, marker, coverage,
  review-grade, substitute.

### ADR-021 — A test run leaves nothing it did not find (Accepted)

- A test run removes, however it ends, the containers, volumes and
  scratch it made; nothing goes into the tree
  (§2, §5 rule 1).
- `tests/run.sh` owns a fresh `TMPDIR` per run and fails naming every
  entry left in it (§5 rule 2).
- Node suites use `scratch()` (`tests/scratch.mjs`); `static.sh` refuses
  inline `mkdtempSync`; a leftover is fixed in the suite that made it
  (§5 rules 3–4).
- A dependency-graph change cleans its build target; large caches go;
  measure first and say what was removed (§5 rule 5).
- Keywords: test, suite, leak, scratch, TMPDIR, temporary directory,
  container, volume, cache, clean up, disk.

### ADR-022 — The session lifecycle: auto mode, the watch armed at launch, the inbox held while planning and visible to senders (Accepted)

- Every session watches its inbox from first turn to last, one watch per
  session; the launcher's opening prompt arms it, and the start hook says
  `NO INBOX WATCH` on start, resume or compaction without one (§2, §5
  rules 1–3).
- Every login's user settings start sessions in auto mode (§5 rule 4).
- While a session plans, `plan-hold.sh` marks the account held and the
  watch polls nothing; the planning span arrives together after
  approval; sending, the start drain and `--wait` are not held (§5 rules
  5–7).
- Presence reports `planning`; `fabric-ctl presence` shows it;
  `gzcoord-send` tells the sender, without refusing (§5 rule 8).
- A clone-started session is held only if its project wires the hooks
  (§5 rule 9, §7).
- A 2026-09-28 — a finished job ends its session with `fabric-fresh` (§5 rule 10).
- A 2026-09-28 — `fabric-branches --sweep` weekly (§5 rule 11).
- A 2026-09-28 — the next job decides whether the session continues: `fabric-jobs
  next`, then `fabric-fresh --job` into the job's working copy (§5 rule 12).
- A 2026-09-30 — the opening prompt names no command (§5 rule 1).
- Keywords: session, lifecycle, inbox watch, Monitor, gzcoord-inbox,
  --follow, opening prompt, resume, auto mode, defaultMode, plan mode,
  hold, planning, presence.

### ADR-023 — An assignment goes to one login (Accepted)

- A `REQUEST`, or any message with a `REQUEST:`, `ACCEPTANCE:` or
  `DELIVER-TO:` section, is addressed `TO` one login; `TO-ROLE` is for
  `INFO`, `DECISION`, `QUESTION` (§2, §5 rules
  1, 3).
- The validator refuses the role-addressed shape and `send.mjs` does not
  post it (§5 rule 2).
- Not knowing the holder: the one on the path, else one running now,
  else the lowest-numbered — and say which rule chose (§5 rule 4).
- One that reached a role anyway is claimed by the first `REPLY`; the
  others stand down silently (§5 rule 5).
- A 2026-09-27 — a receiver stands down on a sibling's pushed branch, PR or
  not, found by the in-flight query (§5 rule 5).
- Keywords: assignment, REQUEST, TO-ROLE, TO, holder, role address,
  duplicate work, claim, REPLY, SPEC §13.

### ADR-024 — Cooperating on requests; a decision is advisory until it reaches an artifact (Accepted)

- A GZCoord message is advisory: it authorises nothing and never stands
  in for a commit, PR, review or record; claims are verified against the
  repository, and an undo states its defect (§2, §5 rules 1–3).
- A request says what done looks like and looks for the job in flight;
  receipt is not acceptance — the `REPLY` says what is undertaken (§5
  rules 4–5).
- Renegotiate only where the agreement changes, `TO` each login; silence
  is neither consent nor release (§5 rule 6).
- A delivery names its sha or PR and what was checked; the agreement
  lives in the PR body, commits and `threads` memory (§5 rules 7–8).
- The owner's word travels verbatim under `OWNER-WORD:` (§5 rule 9).
- Keywords: GZCoord, advisory, request, undertake, dependency,
  renegotiate, delivery, agreement, HANDOFF, OWNER-WORD, artifact.

### ADR-025 — The in-flight view and the trial merge (Accepted)

- `pr-gate.sh --in-flight` lists every branch on origin not merged, PR or
  not, owner from the branch prefix, with the paths it changes;
  `--overlap` and `--path` narrow it; it reserves nothing (§2, §5 rules
  1–3).
- `trial-merge.sh` merges named refs onto the base in a throwaway
  worktree: combines, conflicts or could not merge, for the shas printed;
  the caller's clone is untouched (§5 rules 4–5).
- `--check` runs the project's declared check (`trial.json`); a verdict
  line wins over the exit code; unavailable is never a pass (§5 rule 6).
- Exit 0 combines/passed, 1 conflicts/failed, 2 could not try or
  unavailable (§5 rule 7).
- Keywords: in flight, branch, no PR, overlap, shared paths, trial merge,
  combine, conflict, worktree, trial-check, dependency.

### ADR-026 — Progress is measured as supervision per verified result (Accepted)

- P3's progress read as owner supervision events
  per verified result, as a trend beside the verified-result rate, never
  a target (§2, §5 rules 1, 4).
- A verified result: a merged PR, reviewed and green at its head, not
  reverted or fixed within a window (fourteen days proposed) (§2).
- A supervision event: an `OWNER-WORD`, an arming only the owner could
  make, an owner's correction recorded in a commit or PR, a drain
  collision the owner decided; direction-setting and machine checks are
  not (§2).
- Read only from artifacts — never message bodies beyond the
  `OWNER-WORD` marker, transcripts or memory (§5 rule 3). No counter
  exists (§6). Waits on the owner's acceptance (§8).
- Keywords: progress, supervision, verified result, measure, metric,
  owner, OWNER-WORD, autonomy, mandate, proposed.

### ADR-027 — Language-and-culture specialists shape the work, not only translate it; the bridge (Accepted)

- The role owns the words and what a market's culture changes, stated so
  the surface's owner decides; it says when a language cannot carry a
  meaning; findings in another's surface are `OBSERVATION`s with the
  correction (§2, §5 rule 2).
- One holder per locale, `language-culture-<suffix>`; the tag is
  `locale.json`'s, never inferred (`ge` is `ka-GE`) (§5 rule 1).
- Two-pass review, target first, every finding naming its pass; requests
  translated in, answers composed once in the locale and rendered; the
  fleet gets English (§5 rules 3–4). Notes in the locale, counted by
  `fabric-ctl <login> script`, counts only (§5 rule 5).
- The bridge: `locale-worker`, one inert tool (`TaskStop`), installed only
  on a holder's login; the guard wants a model and no isolation; a Latin
  paragraph in its input is a leak (§5 rules 6–8).
- The prompt in the locale: per-piece translations with a source digest;
  `harness.md` present replaces the whole prompt, absent is the kill
  switch; lint keeps the identifiers; a lag warns and is served; only the
  holder translates (§5 rules 9–11).
- Memory rendered under `## English` by its holder, else
  `needs_rendering`; locale search through `websearch-locale`, SerpAPI
  then Brave, the harness's `WebSearch` removed (§5 rules 12–13).
- Keywords: language-culture, locale, translation, culture, bridge,
  locale-worker, worker, Georgian, Russian, ka-GE, ru-RU, harness.md,
  system-prompt-file, notes, script, needs_rendering, web search, SerpAPI,
  Brave, carve-out.

### ADR-028 — The house i18n standard; GZCoord speaks the reader's language (Accepted)

- A fabric dictionary is the house standard: one flat JSON per locale
  named by its BCP-47 tag, dotted-slug keys, non-empty values, `{name}`,
  `en-US` mandatory; the managed projects are read before any new format
  (§2, §5 rule 1).
- An active locale's dictionary lives in its locale directory, where its
  holder commits it; lint refuses one that is incomplete, loses an
  identifier, or is not in the locale (§5 rules 2–3).
- Every line the GZCoord tools print around a message — the validator's
  diagnostics included — is in the reader's language; the message, its
  metadata keys and type names never are (§5 rule 4).
- The login's suffix and bound role find the dictionary, `locale.json`
  its tag; a missing key or unreadable file falls back to `en-US` — a
  key-level fallback the house standard forbids its clients, kept for the
  session start and named (§4, §5 rule 5).
- `GZCOORD_DEFAULT_LOCALE_ONLY=1` pins English for suites; a new key
  reaches every active locale in the same change (§5 rules 7–8).
- Keywords: i18n, dictionary, locale, BCP-47, en-US, ru-RU, ka-GE,
  translation, inbox, validator, fallback, i18n.mjs, house standard,
  GZCOORD_DEFAULT_LOCALE_ONLY, reminder.

### ADR-029 — The control plane: a control agent per account answers signed actions over the relay (Accepted)

- Every account runs `agentd.mjs` under a lingering user unit, session or
  not, answering on the relay's `fabric:control` channel; no cursor, so a
  request made while it is down is lost (§2, §5 rules 1–2).
- A closed op set, no request field reaches a shell; actions need the
  operator's Ed25519 signature, fresh and strictly newer than the last
  (§5 rules 3–5).
- Every reply arrives, gaps named, no secret; `fabric-ctl` exits 1 on
  silence or a failed action; the drain files only verified bundles
  (§5 rules 6–9). Reads are fenced, not proved, until replies are signed (§6).
- A 2026-09-27 — actions run beside the read loop, one of a kind per
  account; a second is `busy` (§5 rule 12).
- A 2026-09-27 — each operation's answer budget (§5 rule 12).
- A 2026-09-28 — `jobs` and `jobs-add` carry the job list (§5 rule 13).
- A 2026-09-29 — `secrets-migrate` moves an account from Doppler to its
  store, verified by sha256 (§5 rule 14).
- A 2026-09-30 — rule 14 withdrawn with Doppler; the signing key is in the
  operator's store (§5 rules 5, 14).
- A 2026-10-06 — `local` reads, `local-prune` cleans each account's settings.local.json (§5 rule 15).
- Keywords: control plane, agentd, fabric-ctl, control channel,
  fabric:control, relay, ops, status, ping, keys, usage, recall, tokens,
  drain, memory, signed, operator_key, keygen, linger, persist.
### ADR-030 — Presence replaces HELLO and GOODBYE (Accepted)

- Whether a session runs is the control agent's answer from its process
  table and binding — since when, role, project, planning; unreadable is
  unknown, never offline (§2, §5 rule 1). `presence` is the one public op
  (§5 rule 2).
- `send.mjs` asks before a `TO` or `TO-ROLE` leaves: no session, silence
  or an unplaced address exits 4 unless `--force`; a role passes when any
  holder runs; planning is a note, never a refusal (§5 rules 3–4).
- The launcher and `fabric-role` announce nothing; the inbox acknowledges
  an old HELLO/GOODBYE and never delivers it; GZCOORD/1 has retired both
  and a parser rejects them (§5 rules 5–7).
- A request whose addressee's session ended is re-sent, with what
  changed, when presence shows a session (§5 rule 8).
- A 2026-09-27 — HELLO and GOODBYE are retired from GZCOORD/1; a parser rejects
  them (§5 rule 7).
- Keywords: presence, online, HELLO, GOODBYE, announcement, process table,
  send, --force, exit 4, fabric-ctl presence, planning, re-send.

### ADR-031 — Claude accounts: which account a login runs on is assigned, applied and proved by signed action (Accepted)

- Working sessions run on a template's setup-token: an entry of the
  coordinator's store per Claude account, its token put into each
  login's store; the launcher refuses a plain-claude session without one
  (§2, §5 rules 1–3).
- `fabric-accounts assign` writes the token into each login's store, then the
  signed `secrets-sync` action has each account sync, prove the
  template's fingerprint, and resume its session on it; any row not
  `synced` exits 1 (§5 rules 4–5).
- Sign-ins are named by fingerprint everywhere; `fabric-accounts
  templates` maps them (§5 rule 6).
- An observer on the coordinator's login keeps one `/login` per account,
  read every four hours by the harness's own `/usage` — never a
  hand-made refresh (§5 rule 7, §3).
- A 2026-09-27 — `--no-sync` sends no action; the login applies the move at its
  next sync (§5 rule 4).
- A 2026-09-29 — on the coordinator's store, a template is its entry and an
  assignment writes the token into the login's store (§5 rules 1–2).
- A 2026-09-30 — Doppler retired: the store entry and the store write are the only ones (§5 rules 1, 2, 4).
- Keywords: Claude account, subscription, setup-token, /login, template,
  claude-accounts, CLAUDE_CODE_OAUTH_TOKEN, fabric-accounts, assign,
  secrets-sync, fingerprint, usage windows, observer, /usage.

### ADR-032 — GZCOORD/1 is a normative contract: the grammar frozen until a transport exercises it, GZCOORD/2 for a breaking change, adoption by observation (Accepted)

- SPEC, MESSAGE-FORMAT, SEMANTICS and CONFORMANCE are GZCOORD/1's
  normative text; `gzmsg.mjs` is the reference validator and every example
  validates (§2, §5 rule 1). Only fabric-coordinator changes them (§5
  rule 2).
- The grammar (SPEC §6) is frozen until an automated transport exercises
  it; prose, conventions, tightened MUSTs and optional fields stay in
  scope; a new type waits (§5 rule 3).
- Within /1 the accepted set only narrows; a disagreement between old and
  new readers, or a widened §6, is `GZCOORD/2` — a narrowing never is
  (§5 rules 4–5).
- A change is adopted by observation: recurring, a real interoperability
  failure, the smallest fix (§5 rule 6).
- Every change to the four files lands with an amendment of ADR-032 in the
  same PR; examples and validator move with the text (§5 rules 7–8).
- A 2026-09-27 — HELLO and GOODBYE retired: a narrowing under rule 4.
- A 2026-09-28 — SPEC is Normative and names this record; CAPABILITIES and
  SPECIALTIES are optional metadata on any message.
- A 2026-10-04 — WAIVES, an optional common field (SPEC §7.5): a waiver
  role's word that one pull request, at one head, may arm.
- Keywords: GZCoord, GZCOORD/1, GZCOORD/2, protocol, SPEC, grammar,
  freeze, frozen, compatibility, narrowing, conformance, validator,
  extension, X-, protocol change, WAIVES, waiver.

### ADR-033 — GZCoord's transports: the human relay, the adapter contract, Telegram retired; the relay is central today (Accepted)

- A transport carries GZCOORD/1 unchanged, satisfies the adapter contract,
  and never makes a native field a protocol field (§2, §5 rules 1–2).
- No transport gives an agent a human-style identity — why Telegram's
  workaround was refused; a candidate is validated with two instances
  (§5 rules 3–4).
- The transport is the Claude-Bridge relay: one user unit on the
  operator's account, loopback, one database, one channel for every
  project, the control plane beside it; the token from the account's own
  store (§2, §5 rules 5–6).
- The human relay is the fallback: validate, fenced block, 72 columns,
  minted id; normalise and check the addressee before the body (§5 rules
  7–8).
- The relay is a single point of failure, authenticates no sender and
  filters nothing — the inbox does (§6).
- A 2026-09-30 — the relay token comes from the account's own store (§5 rule 6).
- A 2026-10-04 — cccc recorded among the refused alternatives (§3).
- Keywords: transport, relay, Claude-Bridge, claude-bridge,
  gzcoord-relay, human relay, fallback, Telegram, adapter contract,
  channel, gzapp:gzcoord, bridge token, central, single point of failure.

### ADR-034 — Decentralization as a direction: a failure may reduce capacity, never take identity, knowledge or continuity (Accepted)

- Decentralize only where a failure would take
  identity, knowledge or the ability to go on working; reduced capacity
  is acceptable (§2).
- §1 inventories what depends on one thing today — one host, one relay
  and its database, one signing key, one observer, two
  providers, undrained memory, the owner — with each degraded mode or
  "none" (§1, §5 rule 1).
- Data that exists nowhere else gets a copy first; a degraded mode counts
  only with a live check; identity never depends on a central service
  (§5 rules 2–4).
- First step: a copy of the relay's database and a restore read back
  (§7). Waits on the owner's acceptance (§8).
- A 2026-09-30 — the inventory's key and secrets rows name the stores; Doppler is gone (§1, §5 rule 4).
- Keywords: decentralization, resilience, single point of failure,
  degraded mode, relay, host, crash, backup, autonomy, P5, proposed.

### ADR-035 — Federation between organizations: expertise transfers, confidential information does not; portable trust first (Accepted)

- What crosses between organizations is expertise
  and results; a project's code and knowledge, private memory,
  credentials and channel traffic never do (§2, §5 rules 1–2).
- No shared credential; no exchange before identity, action and
  provenance are verifiable by the other side from a published record
  (§5 rules 3–4).
- A request between organizations is advisory; no organization's key
  orders the other's accounts (§5 rule 5).
- Today every trust mechanism — addresses, signed actions, the role
  trailer, slice provenance — is checkable only inside one installation
  (§1).
- First step: a published organization record of operator keys, and a
  second installation verifying a signed action against it (§7). Waits
  on the owner's acceptance (§8).
- Keywords: federation, organization, portable trust, identity,
  signature, provenance, confidential, licence, expertise, P6, proposed.

### ADR-036 — Sustainable operation: shared resources, and cost per verified result beside supervision per verified result (Accepted)

- Cost per verified result — spend attributable to
  a period's verified results over their number, ADR-026's denominator —
  read as a trend beside supervision per verified result, never a target
  or per agent (§2, §5 rules 1–2, 4).
- Direct-path spend in input-token equivalents from the logins' own
  records, broker spend from the provider per key, never converted into
  each other (§5 rule 3).
- Growth is argued by its effect on cost per verified result; a shared
  resource is taken for a stated job and released (§5 rules 5–6).
- Today's pieces are cited, not restated: leases, clean test runs, prompt
  budgets, usage windows, `tokens` (§1). Nothing links spend to a result
  yet (§6).
- First step: a report of input-token equivalents per merged PR (§7).
  Waits on the owner's acceptance (§8).
- Keywords: sustainable, cost, spend, tokens, usage windows, budget,
  lease, verified result, capability per spend, P7, proposed.

### ADR-037 — Each agent keeps a job list (Accepted)

- One list per login, `agents/<login>/jobs.json`, written only through
  `runtime/identity.py`; states queued, active (one at a time), blocked,
  delivered, done, dropped (§5 rules 1–2).
- At a job's end `fabric-jobs next` compares the next job's project,
  working copy and topic: the same continues here, a difference is
  `fabric-fresh --job <id>`, a fresh session in the job's working copy
  with the job in its opening prompt (§5 rule 3).
- Jobs come from the agent and from the owner (`fabric-ctl <login>
  jobs-add`); a GZCoord request becomes a job only when its receiver adds
  it — the automatic intake is built and inactive (§5 rules 4–5).
- The owner reads every list with `fabric-ctl <login|all> jobs` (§5
  rule 6). Waits on the owner's acceptance (§8).
- Keywords: job, to-do, jobs.json, fabric-jobs, next, topic, fresh
  session, restart, fabric-fresh --job, working copy, intake, P3, proposed.

### ADR-038 — Each agent owns its key and its secrets (Accepted)

- One key per login, made in the account, a subkey per use. Its private
  half leaves only as a recovery copy encrypted to the owner's recovery
  key, backed up to Proton Drive (§5 rules 1, 6; §6).
- A key is an agent's when committed at `identities/keys/<id>.asc` and
  certified by its parent recorded in `lineage.json`; lint refuses one
  without (§5 rule 2).
- Each agent's secrets are a private pass(1)-format repository,
  `agent-fabric-secrets-<id>`, encrypted to that key alone: the parent
  writes (`fabric-secrets put`) and never reads (§5 rule 3).
- No step relies on a shared host (§5 rules 4–5). `sync` reads the store
  alone (§5 rules 7–8).
- A 2026-09-29 — recovery copies and backups go to Proton Drive.
- A 2026-09-29 — recovery copies are encrypted to the owner's recovery key.
- A 2026-09-29 — keys, lineage and repositories are named by the agent id (ADR-039).
- A 2026-09-29 — one identity key with a subkey per use (§5 rule 1, §7).
- A 2026-09-30 — Doppler removed from the code; `provision` fills a child's store (§5 rules 3, 7–8; §7).
- A 2026-10-01 — a new account's store travels as a bundle (§5 rule 5).
- A 2026-10-06 — no shell holds a secret; env.sh holds plain values (§5 rule 9).
- Keywords: secrets, key, GPG, pass, paperkey, backup, env.sh, bashrc,
  identity, lineage, parent, custody, recovery, Doppler, migration,
  provision, placement, P1.
### ADR-039 — The agent id is a UUIDv7 minted at birth (Accepted)

- Each agent has an id, a UUIDv7 whose time is its birth: an existing
  account's home creation time, a new one's enrolment. It is minted once
  by the parent and never replaced (§5 rule 1).
- The id identifies the agent across renames; the login is its current
  name. What is stored is named by the id; commands take a login (or an
  id) and resolve it first; a repository's description gives both
  (§2, §5 rule 5).
- A rename changes the entry's `login` and the description, and nothing
  stored moves (§5 rule 6).
- `lineage.json` is keyed by id (`login`, `born`, `fingerprint`, parent id);
  keys are `identities/keys/<id>.asc`, their user id `<id>@agents.agent-fabric`,
  certified there by the parent (§5 rules 2–3).
- Secrets repositories are `agent-fabric-secrets-<id>`, and so are mirrors,
  bundles and recovery copies (§5 rule 4).
- A reused login is a new agent with a new id (§5 rule 7).
- Keywords: agent id, UUIDv7, birth, rename, identity, lineage, key,
  secrets repository, P1.

### ADR-040 — Implementation language: Python above 150 lines (Accepted)

- New fabric tooling is Python, standard library only, valid on 3.12+
  and run on the pinned `fabric-python` (`runtime/python.json`); bash stays
  for shims, forwarders, hook entry points, the suite runners and
  sudo/ssh/installer step-runners (§5 rule 1).
- Lint refuses a tracked bash script over 150 lines not named in
  `policies/bash-allowlist.json`; each entry names its wave, and the
  list only shrinks (§5 rule 2).
- A port freezes the contract (argv, environment, stdout/stderr, exit
  codes, help) in the module's header, keeps the path as a shim, runs the
  old bash test unchanged as the oracle, and removes the entry (§5 rules
  3–5).
- GitHub and git go through `gh.py` and `git.py`: bodies on stdin or a
  file, bounded calls named in their errors, JSON in Python (§5 rule 6).
- A 2026-10-01 — the oracle's assertions stay; its gh mock may learn
  gh.py's transport (still passing the bash original), and a case
  reading the source reads the module.
- A 2026-10-01 — one pinned Python, 3.13, as fabric-python per host; shims run it (§5 rules 1, 4).
- A 2026-10-01 — a fixture may copy the modules of the scripts it copies; no assertion changes (§5 rule 5).
- A 2026-10-04 — Wave 7: send, inbox and gzmsg to Python together; the control plane's imports split out first (§7).
- Keywords: Python, bash, shell, port, allowlist, lint, shim, wave, gh,
  git, 150 lines, P1.

### ADR-041 — Agent-local episodic history: exact messages kept above the transport (Accepted)

- Each agent keeps its own journal, `<state>/agents/<login>/episodic.db`,
  0700/0600, owned by its agent id; a reused login is refused (§5 rule 1).
- Only GZCoord messages it sent or was addressed; never control, presence
  or others' traffic (§5 rule 2).
- Written at the crossing: pending before the post, before the ack; a
  failure refuses the send or withholds the ack (§5 rules 3–4).
- One row per source, direction, MESSAGE-ID; outbound reuse refused,
  inbound reuse set aside; the carrier is provenance (§5 rules 5–6).
- Evidence, not truth; never auto-injected or auto-promoted; each agent
  imports its own past (§5 rules 7–9).
- A 2026-10-05 — `GZCOORD_JOURNAL=off` is a recorded break-glass: each
  bypassed crossing appends an audit line first, or is refused (§5 rule 10).
- A 2026-10-06 — a bypassed send's second line records its outcome (§5 rule 10).
- Keywords: episodic, history, journal, GZCoord, carrier, transport,
  relay, InterWeave, fabric-history, backfill.

### ADR-042 — Store commits are signed by their writer and verified before they are applied (Accepted)

- Every store commit is signed by its writer's own key: the agent's for
  `set`, the parent's for `put` and `seed-child` (§5 rule 1).
- Only the agent's and its parent's keys may write a store: a signing
  subkey of a primary key `lineage.json` records, read from the committed
  `identities/keys/<id>.asc`; the root writes alone (§5 rule 2).
- `pull`, `take-bundle`, the fast-forward before a push and `sync` verify
  every commit past the trusted base; one failure refuses the operation,
  named, nothing applied (§5 rules 3–4).
- A refusal is a security event, said by `fabric-secrets status` and
  `fabric-ctl keys` until repaired (§5 rule 5).
- A 2026-10-04 — writers read at origin/main; the trusted base explicit:
  bootstrap's once-only migration, or first contact through the
  enrolment bundle; a store with no base refuses (§5 rules 2, 4).
- Keywords: store, signing, signature, verify, forged entry, lineage,
  pass, bundle, take-bundle, writer, trust-base, trusted base.

### ADR-043 — Claude Code mods: managed only, the guards in managed settings, the fleet's mods from a root-owned marketplace (Accepted)

- User-installed mods, and mods Claude writes in a session, never load on a
  fleet host: managed settings set the built-in guard's
  `allowManagedModsOnly` and `disableSideloadFlags` (§5 rule 1).
- The guards move into managed settings, where they run before any mod and
  their block is final, each running a root-owned copy of its script
  (§5 rule 2).
- The fleet's own mods load first from a root-owned marketplace; the first
  one redacts the login's secret values from tool results, failing closed
  (§5 rules 3–4).
- The Claude Code pin moves to 2.1.287 or later only after every host reports
  rules 1 and 2 in force (§5 rule 6).
- Keywords: mods, plugin, managed settings, allowManagedModsOnly,
  disableSideloadFlags, prependPlugins, sec-default, guard, redaction.
