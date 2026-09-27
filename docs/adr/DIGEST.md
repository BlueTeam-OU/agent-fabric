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
- Open gap: `workflow` slices are budgeted as tier 1 and the index banner
  says the hook loads them; it does not (§7).
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
  never older text, a contested heading, or two agents' texts (the owner,
  2026-09-26) (§5 rules 4–6).
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
- Lint refuses only a managed project's name, and not in the dispatch
  skill; the rest is review (§6). pg-probe's bare pointers to a project's
  records are open (§7).
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
  by a session bound to `fabric-coordinator`: `pre-commit` and
  `commit-msg` fence it, `check_agent_fabric_dir_authority.sh` reads the
  `Fabric-Role:` trailer in CI (§5 rules 1–4).
- Every commit carries its account's role as a trailer; a fold-only merge
  passes (§5 rules 2–3). A locale's translations are its holder's to
  commit, alone, and the coordinator's to merge (§5 rule 5).
- A guard is a commit-time check, a CI check on every added commit and a
  planted suite case (§5 rule 6); a proposal is a PR left for the owning
  role (§5 rule 7).
- Open gap: `check_charter_authority.sh` has no CI call site; the fence
  holds charters today (§6).
- Keywords: authority, read-only, fence, tripwire, Fabric-Role, trailer,
  pre-commit, commit-msg, hooksPath, charter, locale carve-out, guard.

### ADR-019 — Work arrives as pull requests: one open PR per agent, 8–16 work commits to arm, the gate read before arming, no machine attribution, repository settings (Accepted)

- Every change reaches `main` through a PR; on agent-fabric since
  2026-09-18, by practice — no ruleset, protection or queue there (§2,
  §5 rule 1, §6).
- One open PR per agent; the next work is another commit while the
  branch is addable; two stated exceptions (§5 rule 2).
- Work commits exclude review fixes (`Answers:` trailer, else the
  subject; `commit-class.sh`): 8–16 arm at the gate, under 8 ask the
  owner, over 16 split before opening (§5 rules 3–4).
- Arm only on `pr-gate.sh`'s `MERGEABLE`, read first, with no open P1/P2;
  on agent-fabric arming is the merge (§5 rules 5–6).
- No `Co-authored-by:`/`Claude-Session:` trailer, footer or session URL
  in commits or PR descriptions (§5 rule 7). GitHub settings: §6.
- Keywords: pull request, PR, arm, merge, band, work commits, Answers,
  pr-gate, MERGEABLE, one open PR, attribution, Co-authored-by, CodeQL,
  repository settings, auto-merge.

### ADR-020 — The review class is the review (Accepted)

- The review class's blind review is the review of every PR: on every
  head, to judge a finding, to re-review a fix range; no automated
  reviewer is assumed (the owner, 2026-09-20) (§2, §5 rule 1).
- Dispatch: `code-review`, `model: fable`, description "review…" or
  "re-review…", no isolation; the guard drops the alias so the agent
  file's routed model decides, within `review-grade.json` (§5 rules 2–3).
- The reviewer writes nothing (`review-bash-guard.sh`); its brief is
  facts from `fabric-review brief`, never conclusions (§5 rules 4–5).
- Posted by `post-review.sh` with the marker; counted only when marked
  and posted by the PR's account or a named poster, or unmarked from a
  trusted account (§5 rules 6–7). Legacy markers until the sunset (§5
  rule 8).
- Keywords: review, blind review, code-review, re-review, brief,
  fabric-review, post-review, pr-review-status, marker, coverage,
  review-grade, substitute.

### ADR-021 — A test run leaves nothing it did not find (Accepted)

- A test run removes, however it ends, the containers, volumes and
  scratch it made; nothing goes into the tree (the owner, 2026-09-19)
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
- Keywords: session, lifecycle, inbox watch, Monitor, gzcoord-inbox,
  --follow, opening prompt, resume, auto mode, defaultMode, plan mode,
  hold, planning, presence.

### ADR-023 — An assignment goes to one login (Accepted)

- A `REQUEST`, or any message with a `REQUEST:`, `ACCEPTANCE:` or
  `DELIVER-TO:` section, is addressed `TO` one login; `TO-ROLE` is for
  `INFO`, `DECISION`, `QUESTION` (the owner, 2026-09-19) (§2, §5 rules
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

### ADR-026 — Progress is measured as supervision per verified result (Proposed)

- Proposed, not binding: P3's progress read as owner supervision events
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
