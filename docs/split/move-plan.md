# The move plan: instance data into the operator repository (ADR-045)

What leaves agent-fabric for the operator repository, `BlueTeam-OU/blueteam-fabric`
(private, created by the owner on 2026-11-10, empty), and in what order. The list is
`tools/fabric/roots.py`'s instance data, the paths the seam already routes through
`operator_root()`. Each path keeps its relative path in the operator repository, so a
reader that asks `roots` needs no change: the move is the files plus one default.
`inventory.md` classes every top-level path. This plan covers the part that moves first,
at the extraction stage (the inventory's stage 4, ADR-045 §7's third).

Counts are tracked files on main at 6fa97620 (2026-11-11).

## 1. The move list

| Path | Files | `roots` helper | Reader outside the seam that needs a shim (§3 step B) |
|---|---|---|---|
| `identities/roles/` (catalogue, charters, briefs, locales) | 78 | `role_catalog`, `roles_dir`, `role_dir`, `locale_dir` | CI's signing step (`git archive … identities/roles`) |
| `identities/personas/` | 3 | `personas` | none |
| `identities/keys/`, `identities/agents/README.md` | 32 | `keys_dir` | CI's signing step (`identities/keys`); the key-trust anchor, §4 |
| `identities/recovery.asc` | 1 | `recovery_key` | none |
| `projects/registry.json`, `projects/clients.json`, `projects/<id>/` | 62 | `projects_registry`, `clients_registry`, `projects_dir`, `project_integration` | `runtime/claude-code/hooks/session-start.py`; CI's signing step |
| `runtime/hosts/registry.json` | 1 | `hosts_registry` | `runtime/provisioning/platform/qubes/ssh-operator.sh` (honours `AGENT_FABRIC_HOSTS_REGISTRY`) |
| `policies/` instance files: `arming`, `authority`, `auto-mode`, `host-load`, `hygiene`, `signing` (`.json`) | 6 | `policy` | CI's signing step (`policies`) |
| `routing/profiles.json` | 1 | `routing_profiles` | `runtime/claude-code/hooks/model-switch-guard.py`, `tools/fabric/launcher/routing.py` |
| `routing/policies/` (`account-switch`, `availability`, `review-grade`) | 3 | `routing_policy` | none |
| `memory/domains/`, `memory/shared/`, `memory/agents/` | 618 | `memory_dir` | `runtime/claude-code/hooks/memory-write-check.py`, `tools/fabric/assembler/intake.py` |
| `docs/live-checks/` | 79 | `live_checks_dir` | `session-start.py`, `launcher/routing.py` (both name a record in prose) |

884 files, and `docs/legal/`'s 3 with them in step B. `memory/README.md` and `memory/RUBRIC.md` stay: they say how a corpus
works, not what this one knows.

### What `roots.py`'s list names that does not move

- **`policies/*.json` is not all instance.** Nine of the fifteen are the engine's own
  exception lists, naming engine modules a checker admits: `bash-allowlist`,
  `command-names`, `context-reads`, `evidence-caps`, `mechanisms`, `process-spawns`,
  `state-writers`, `transport-calls`, `work-writes`. They change with the code they judge,
  so they stay with it. Step A moves them out of `policies/` beside their checkers, as
  `tools/fabric/roots_bypass.json` already is. That leaves `policies/*.json` meaning
  instance data, which is what rule 2 says. `bash-allowlist.json` was classed instance in
  the inventory. It lists tracked engine bash files, so it is engine.
- **`docs/adr/` is classified, record by record** (the owner, 2026-11-11, Q1). A purely
  organisational record moves to the operator's `docs/adr/` and keeps its number. Rule 4
  forbids a renumbering, not a move. An engine record stays. A mixed record stays too, and its organisation's rules
  leave it either by amendment or, where it serves, by splitting the record (the owner, the
  same day): the engine's part keeps the number, and the organisation's part becomes a new
  operator record that cites it.
  The engine's `index.json` keeps every moved number as reserved ("moved to the operator"),
  so no new record reuses one, and the public engine names no private content.
  `fabric-adr lookup` reads both trees: `adr_dir()` for the operator's records, and an
  engine lookup for the engine's. The classification is its own pull request, before step B.

### Instance data outside this move, each with its own later step

These paths are not in `roots.py` because no engine reader resolves them through an
operator tree. Each one needs a design before it moves:

- `.agent-fabric/` (961 files): this repository's own remits, taxonomy and project
  memory. The session-start hook reads them from the working copy, so they live wherever
  the engine's working copy is. They leave when the engine is published with a fresh
  history (ADR-045 §7, last stage), or earlier only once the resolver can serve a project's
  remit from the operator's tree.
- `docs/legal/`: the company's legal opinions. No reader exists. The files move by
  `git mv` in step B with the rest; they are listed here because `roots` does not name them.
- The mixed files (`identities/prompt/team.md`, `policies/AUTHORITY.md`,
  `code-as-memory.md`, `AGENTS.md`, `CLAUDE.md`, `README.md`, the role library): each is
  split by amendment (`inventory.md`), not moved.

## 2. Preconditions (each its own job, before step B)

1. **The stripped suite is clean.** `tests/stripped_skip.txt` names 4 files that still read
   the live instance tree: `test_gateway_plan.py` (j62), `test_repo_settings_cli.py`
   (j63), `test_session_start.py` and `test_subagent_ledger.py` (j64), all python-dev-03.
   Rule 3 requires it to be empty, because step B is where a live-tree read stops finding
   its file.
2. **Every admitted bypass is judged against the move.** `tools/fabric/roots_bypass.json`
   admits 16 modules. Those named in the table above read an instance path the shim must
   keep resolving until the module is moved onto a root it is handed. The rest find a
   tree, not an instance path, and are unaffected. The hooks (`runtime/claude-code/`) and `runtime/identity.py` lie
   outside every contributor's entry, so their fix is fabric-coordinator's.
3. **The second checkout is provisioned** (ADR-045 §6). Bootstrap, the upgrade, the
   launcher's pull, the control agent's unit, moveto and new-agent learn
   `<home>/projects/blueteam-fabric` beside the engine, and the operator pins the engine's
   version. Needed before step D, not step B.
4. **The operator repository is a managed project.** It needs an entry in
   `projects/registry.json` (client `blueteam`), a `.agent-fabric/taxonomy.json`, a
   `policies/signing.json` row and an arming policy in `BlueTeam-OU/agent-fabric-settings`.
   Needed before step C.

## 3. The steps

Each step is one pull request on agent-fabric unless it says otherwise. Each is read back on
one account before the fleet takes it (`fabric-ctl <login> upgrade fabric`, then
`fabric-status` and a launch).

**Step A: separate what stays from what moves, inside the engine.** `git mv` the nine
exception lists to `tools/fabric/<checker>.json` (for example `policies/mechanisms.json` →
`tools/fabric/mechanisms.json`), with their readers and the lint's tables. `roots` gains an
engine ADR lookup beside `adr_dir()`, and the DIGEST readers read both. Correct `roots.py`'s docstring list to this plan.
No file leaves the repository, and behaviour does not change.

**Step B: the move, inside one repository.** Every path in §1's list is moved with
`git mv` into `operator/<same path>`. One `roots` default changes: `operator_root()` falls
back to `<engine root>/operator` instead of the engine root. A shim is left at each old
top-level path, as a relative symlink (`identities/roles` → `../operator/identities/roles`).
The shims serve only the readers in §1's last column, and the commit lists each shim with
the reader it serves. With `AGENT_FABRIC_OPERATOR` set, the suite reads the fixtures it
always read. Unset, it reads `operator/`. Both pass, or step B is not done. Reverting the
step is one commit. This is the change of one root that ADR-045 §4 asks to be read back
before anything crosses a repository boundary.

```sh
mkdir -p operator/identities operator/projects operator/runtime/hosts operator/policies operator/routing operator/memory operator/docs
git mv identities/roles identities/personas identities/keys identities/agents identities/recovery.asc operator/identities/
git mv projects/registry.json projects/clients.json operator/projects/   # then each projects/<id>/ but schemas/
git mv runtime/hosts/registry.json operator/runtime/hosts/
git mv policies/{arming,authority,auto-mode,host-load,hygiene,signing}.json operator/policies/
git mv routing/profiles.json routing/policies operator/routing/
git mv memory/domains memory/shared memory/agents operator/memory/
git mv docs/live-checks docs/legal operator/docs/
git mv docs/adr/ADR-NNN-*.md operator/docs/adr/   # each record the classification moves
```

**Step C: the operator repository takes its history.** In a fresh clone of agent-fabric
at step B's merge, `git filter-repo` keeps each §1 path (the old path and its `operator/`
path) and renames `operator/` to the root. The result is pushed as `main` of
`BlueTeam-OU/blueteam-fabric`, signed and armed like any managed repository. Each file
keeps its history, and agent-fabric is not touched.

**Step D: the engine lets go.** `git rm -r operator/` and the shims. `operator_root()`
falls back to the account's operator clone, `roots.operator_clone(home)` =
`<home>/projects/blueteam-fabric`, beside `account_clone`. Rule 1's transition ends here as
the record says: `engine_root()` stops honouring `AGENT_FABRIC_ROOT`. Whether that lands in
step D or in a pull request right after it is the owner's choice. Engine CI reads its
instance data from the operator's `main` (§4).

**Step E: distribution.** One account first: pull both checkouts, relaunch, run
`fabric-status`, `fabric-adr lookup`, a dispatch and a commit (signing reads the moved
keys). Then `fabric-ctl all upgrade fabric`. An account that has not pulled the operator
repository still resolves its operator to a missing tree, and that is reported, never
silently replaced by the engine's tree (`roots`: "a missing root is a path that does not
exist").

## 4. Hazards

- **The key-trust anchor moves** (ADR-045 §6). CI's signing step judges a branch by
  main's keys, holders and registry (`git archive origin/main … identities/keys …`), so
  that a branch cannot admit its own key. After step D those are the operator's `main`.
  Engine CI reads the operator's `main` through a read-only deploy key on
  `blueteam-fabric`, held as an agent-fabric CI secret (§5, Q2). Until that key exists, step D
  cannot pass.
- **A path a reader joins by hand is found only when it breaks.** The bypass lint sees
  Python. Bash, the systemd units, CI and the skills' prose are found by the text search
  this plan's table came from. Step B's shims are what keep those readers working, and a
  shim no reader needs is removed in the same pull request that removes its reader.
- **Memory drains write into `memory/`.** A drain that runs between steps B and D writes
  through the shim. One that runs after step D must target the operator clone. Drains are
  held from step C until step E is read back.

## 5. The owner's answers (2026-11-11)

- **Q1, the records:** classify them and move the organisational ones; a mixed record may
  be split (§1). That is not the
  plan's first proposal, which was to keep every record in the engine.
- **Q2, CI's signing check:** a read-only deploy key on `blueteam-fabric`, held as an
  agent-fabric CI secret. The check stays where the commits are.
