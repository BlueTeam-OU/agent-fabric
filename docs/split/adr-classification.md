# The records, classified for the split (ADR-045 §5 rule 4)

Drafted 2026-11-12 and decided by fabric-coordinator the same day, for the classification
pull request `move-plan.md` §1 puts before step B (the owner's Q1 answer, `move-plan.md`
§5). The pull request that carries this file also carries what it decides: each record's
`**Class:**` header, the amendments, the splits and `docs/adr/reserved.json`. What is
decided is under "Decided" at the end; the table is the evidence it rests on.

**Method.** Each record `docs/adr/ADR-NNN-*.md` was read for its §2 Decision and its §5
Binding Rules. The class rests on what binds, never on the record's history:

- **engine**: every rule holds for anyone who runs the fabric (a mechanism, the protocol,
  a guard, the roots, launch, routing machinery). A rule may *point at* instance data
  (`policies/arming.json`, `runtime/hosts/registry.json`, `routing/policies/`) and stay
  engine, because the data, not the rule, is the organisation's (inventory.md, rule 2).
- **organisational**: what binds is this organisation's own choice (its accounts, hosts,
  people, clients, plans, named repositories, legal position). It moves with its number.
- **mixed**: engine rules beside organisational ones. **amend** where the organisational
  part is a clause, a name or a value the engine can take from configuration; **split**
  where it is a body of its own (a table, a programme, a house style), which becomes an
  operator record citing the number the engine keeps.

Organisational facts that appear only in §1 Context, §6 Consequences, §7 Future
Evolution, §8 Status, References or the amendment history (a crash on the coordinator's
host, a project's PR number, a measured account) do not change the class: they are
narrative evidence, and the engine's publication with a fresh history (ADR-045 §7) is
where they are reworded. "The owner" is the fabric's ratifying authority (ADR-001 §5
rule 2), an engine concept, and does not by itself make a rule organisational.
"stays, reword" marks an engine record whose rule text uses an organisation's name as an
example; an editorial amendment replaces it with the generic term.

**Engine citations** counts the files under `tools/`, `runtime/`, `bin/` and `policies/`
that name `ADR-NNN` (not followed by a digit), with the occurrences in brackets, on
`ab101b34`. The count includes shims and comments: ADR-040's is mostly the port shims.

| No. | Title (short) | Class | Action | Organisational parts | Engine citations | Reason |
|---|---|---|---|---|---|---|
| 000 | The enduring organization | engine | stays | none binding; the pillars' *Today* paragraphs narrate this fleet | 1 (6) | §5 rule 1: the pillar table `tools/fabric/adr.py` reads; rules 2-4 govern any record set |
| 001 | Decision records | engine | stays | §1-§4 history of gzapp's record engine | 4 (9) | §5 rules 1-12 are how records are written, accepted and numbered, the engine's own process |
| 002 | Role, login and model kept apart | engine | stays | none | 1 (1) | §5 rules 1-9: identity from `id -un`, binding and the launch prompt's order |
| 003 | Per-agent state is one layer | engine | stays | none | 24 (48) | §5 rules 1-5: `agent_lock`, the state writers, `read_binding` |
| 004 | Adding a role without breaking CI | engine | stays | none | 0 | §5 rules 1-6: the ordered steps for any role and project; rule 2 forbids naming the project |
| 005 | Models routed by capability class | engine | stays | rule 6 names who chooses the review model (architect-cto, the owner), a role of the library | 4 (4) | §5 rules 1-10: classes, the dispatch guard, shims, the review-grade check |
| 006 | Effort is routed | engine | stays | none | 7 (8) | §5 rules 1-7: `routing/effort.json` and the launcher's refusals |
| 007 | A flagged request is contagious | engine | stays, reword | rule 5 cites `projects/gzapp/integration/gzcoord/INSTALL.md` | 1 (1) | §5 rules 1-5: the fallback hook and the writer's rule; rule 5's path is an example of a project's wiring |
| 008 | Harness pinned by measurement | engine | stays | none | 2 (2) | §5 rules 1-7: user settings keys, the harness pin and capture |
| 009 | Fleet operations are signed actions | engine | stays | none | 6 (6) | §5 rules 1-9: signed actions, `upgrade`, distribution after a merge |
| 010 | Hosts, provisioning, resources | engine | stays | §1 and §7 name the coordinator's host and the second host | 18 (28) | §5 rules 1-12: hostexec, the registry's shape, leases; rule 8 (Qubes) is a platform adapter; rule 11 leaves the targets to each project |
| 011 | Managed projects at a pinned ref | engine | stays | §1 and References: gzapp#854, #857 | 1 (3) | §5 rules 1-5: `fabric-ref` and the drain's landing order, for any managed project |
| 012 | Credentials | engine | stays | none | 7 (9) | §5 rules 1-9: never committed, shapes in tests, the secret-value hooks |
| 013 | The memory model | engine | stays | none (the corpus and `policies/hygiene.json` are instance data) | 4 (4) | §5 rules 1-15: layout, the drain's opt-in, provenance; how any corpus works |
| 014 | The memory assembler's rules | engine | stays | none | 3 (5) | §5 rules 1-10: the collision pre-pass, `merge_target`, retitles |
| 015 | Code is memory | engine | stays | none | 2 (5) | §5 rules 1-8: comment discipline the review class grades |
| 016 | Skills carry rules, not history | engine | stays | §7 cites gzapp's records as the case | 1 (5) | §5 rules 1-6: what a shipped `SKILL.md` may hold |
| 017 | Measurement before belief | engine | stays | none (`docs/live-checks/` is instance data, ADR-045 rule 2) | 0 | §5 rules 1-7: a read-back is evidence, never rewritten |
| 018 | Authority and the read-only fence | engine | stays | none (the holders are `policies/authority.json`, instance) | 7 (16) | §5 rules 1-8: the hooks, the carve-outs, the fence; who holds a role is data |
| 019 | Work arrives as pull requests | mixed | amend | rule 1's "Declared today for brand-comms on blueteam.ee, gzapi.ge, gzapp.decks and gzapi.brand"; rule 4's eight and sixteen as this fleet's numbers (they are `policies/arming.json` values); rule 6's "the one GitHub account every session uses"; §6's `access` row (one collaborator, the owner) | 16 (30) | §5 rules 1-3, 5 and 7 are the PR mechanism every operator runs; rule 1 names this organisation's direct projects and rule 4 restates its policy's values, which `arming.json`'s own description says are the policy's |
| 020 | The review class is the review | engine | stays, reword | rule 9's tail "the gzapp and InterWeave cards are to follow" | 20 (35) | §5 rules 1-11: dispatch shape, briefs, coverage, the card from the base |
| 021 | A test run leaves nothing | engine | stays | References: the host crash live check | 1 (1) | §5 rules 1-5: cleanup of any run |
| 022 | The session lifecycle | engine | stays | §7 lists which of this organisation's projects wire the hold | 7 (10) | §5 rules 1-12: auto mode, the watch, the plan hold, `fabric-fresh` |
| 023 | An assignment goes to one login | engine | stays | none | 0 | §5 rules 1-6: GZCoord addressing, held by the validator |
| 024 | Cooperating on requests | engine | stays | none | 0 | §5 rules 1-9: messages advisory, `OWNER-WORD:` carriage |
| 025 | In-flight view and trial merge | engine | stays | §6, §7: gzapp's first run and PR #943 | 0 | §5 rules 1-7: `--in-flight`, `trial-merge`; a project declares its own check |
| 026 | Supervision per verified result | engine | stays | none | 2 (6) | §5 rules 1-4: definitions and use of the measure |
| 027 | Language-and-culture, the bridge | engine | stays, reword | rule 11 names `language-culture-ge`, `legal-expert-ge`, `legal-expert-ee-eu` as examples | 13 (16) | §5 rules 1-13: locale directories, the worker, the dispatch guard, lint of translations; the locales held are data |
| 028 | The house i18n standard | engine | stays | §1, §4, §6: gzapp's ADR-024 as origin; the projects' dictionaries | 1 (1) | §5 rules 1-9: the dictionary format, lint and GZCoord's rendering |
| 029 | The control plane | engine | stays | none binding (the channel is `runtime/control/config.json`) | 23 (27) | §5 rules 1-19: agentd, the closed op set, signed actions; rule 11 is the Qubes adapter, rule 18 a carrier |
| 030 | Presence replaces HELLO/GOODBYE | engine | stays | none | 4 (4) | §5 rules 1-8: the `presence` op and GZCOORD/1's retirement |
| 031 | Claude accounts by signed action | engine | stays | none (the templates are store entries) | 17 (24) | §5 rules 1-9: templates, `assign`, `secrets-sync`, fingerprints, for any set of accounts |
| 032 | GZCOORD/1 is a normative contract | engine | stays | none | 1 (1) | §5 rules 1-8: the protocol's change process |
| 033 | GZCoord's transports | engine | stays, reword | §2 and §6 name the channel `gzapp:gzcoord` (now a client's `channel` in `projects/clients.json`) | 1 (1) | §5 rules 1-8: the adapter contract, the relay unit, the human relay |
| 034 | Decentralization as a direction | mixed | split | §1's inventory table (this deployment's one host, sixteen logins, the relay's Proton Drive copy, one observer login) and rule 1, which keeps that table | 11 (16), all to §7 | the criterion and rules 2-5 hold for any deployment; §1's table is one organisation's dependencies, kept current by rule 1; §7 (the relay backup, the scheduled drain) is what the engine cites and stays |
| 035 | Federation between organizations | engine | stays | none | 0 | §5 rules 1-6: what may cross between any two organisations |
| 036 | Cost per verified result | engine | stays | §1: the host crashes | 2 (4) | §5 rules 1-6: the measure and the lease rule |
| 037 | Each agent keeps a job list | engine | stays | none | 43 (90) | §5 rules 1-14: `jobs.json`, states, pools, holds |
| 038 | Each agent owns its key and secrets | mixed | amend | Scope and §2 name the stores as `BlueTeam-OU/fabric-agent-<id>`; §8 names the two company stores | 46 (70) | §5 rules 1-10 are the key and store mechanism, rule 10's company store included; only the GitHub organisation that hosts the stores is this organisation's |
| 039 | Agent id is a UUIDv7 | mixed | amend | rule 4: "`BlueTeam-OU/fabric-agent-<id>`" | 13 (20) | rules 1-3 and 5-8 are the id and lineage; rule 4 fixes the store's owner organisation, which becomes the operator's configured organisation |
| 040 | Python above 150 lines | mixed | split | rule 10 (Wave 10, the managed projects' Node scripts, "the owner asked for it") and §7's Wave 10 inventory rows (gzapp, gzapp.decks, blueteam.ee, gzapi.ge, herdr) | 192 (299) | rules 1-8 bind the fabric's own code and are what the shims cite (`ADR-040 §7` in engine files names waves 1-9); rule 10 is this organisation's porting programme for its projects |
| 041 | Agent-local episodic history | engine | stays | none | 15 (29) | §5 rules 1-10: the journal |
| 042 | Store commits signed and verified | engine | stays | none | 12 (50) | §5 rules 1-5: writer keys from lineage, trusted base |
| 043 | Claude Code mods: managed only | engine | stays | §8: the pin's read-back on the coordinator's host | 16 (26) | §5 rules 1-9: managed settings, the marketplace, `fabric-managed`; rule 9's Qubes clause is a platform adapter |
| 044 | Identity kinds: agent and human | engine | stays | §1: the Fleet Deck fork | 17 (51) | §5 rules 1-6: `kinds`, what `all` means |
| 045 | Engine, operator and clients | engine | stays | §8 names `BlueTeam-OU/blueteam-fabric` and the two settings repositories | 18 (33) | §5 rules 1-6 are the split itself: roots, instance data, numbering, client resolution |
| 046 | Fleet views read on demand | engine | stays | none (the herdr fork is the engine's Fleet Deck, `docs/fleet-deck/`) | 2 (2) | §5 rules 1-7: one reader, cost classes, read-only views |
| 047 | Plans kept by the coordinator | engine | stays | none | 4 (7) | §5 rules 1-5: plan and step shape |
| 048 | Operator reaches accounts over ssh | mixed | amend | rule 1's "`fabric-h2` the first" and "develop-qzapp's address" | 17 (29) | rules 2-8 are the ssh mechanism and the Qubes adapter; rule 1's exception names this deployment's hosts where "a host reached over ssh" and "the coordinator's host" suffice |
| 049 | Memory retrieved over MCP | engine | stays | none | 16 (26) | §5 rules 1-8: the server, ranking, no secrets |
| 050 | Keeping wisdom true | engine | stays | none | 19 (51) | §5 rules 1-14: anchors, flags, the owning role judges |
| 051 | moli is the fleet's web reader | engine | stays | none (the pin lives in `projects/registry.json`, an inventory question) | 4 (6) | §5 rules 1-7: a pinned tool the engine installs and its skill |
| 052 | Account-switch policy | engine | stays | rule 10's starting values (data in `routing/policies/account-switch.json`) | 13 (18) | §5 rules 1-13: the controller's algorithm; the pool and numbers are configuration |
| 053 | A second review engine: Codex | engine | stays | none binding (rule 6: "Which engines is policy data, never this record") | 30 (52) | §5 rules 1-8: the engine's brief, gateway, structured answer, token distribution |
| 054 | Codex as a session harness | engine | stays | none | 1 (2) | §5 rules 1-10: harness adapters, instruction file, credential path |
| 055 | Model availability rediscovered | mixed | amend | rule 7's last sentence ("OpenAI today, against Anthropic's two seats and three review models"); rule 8's statement of what `policies/arming.json` lists today | 4 (4) | rules 1-6 and rule 8's principle (an additional engine never blocks) are engine; the fleet's seats and its policy's current lists are data |
| 056 | Agent personas | mixed | split | rule 3 (the surnames are deceased scientists, the weapons test, the owner judges); rule 5 (a name from the surname's culture); rule 7 (the house style, brand-comms draws, the avatars' path) | 11 (23) | rules 1, 2, 4, 6 and 8 are the persona mechanism and the "AI" marking ADR-033 §5 rule 3 needs; the naming theme and the house style are this organisation's brand |
| 057 | Each agent signs its own commits | engine | stays | none (formats are `policies/signing.json`, instance) | 16 (28) | §5 rules 1-8: the signing program, timestamps, the checker |
| 058 | Reflection pass | engine | stays | none | 10 (15) | §5 rules 1-5 |
| 059 | Third-party data out of the Max plan | organisational | move | the whole record | 0 (one comment in `tools/fabric/adr.py` uses "ADR-059" as an example of another project's number, not a citation) | §5 rules 1-4 bind this company's Claude plan and the blueteam.ee privacy notice, from a legal opinion in `docs/legal/` (instance) |
| 060 | Holder addenda | engine | stays | §1, §6: the legal-expert jurisdictions as the case | 18 (44) | §5 rules 1-11: the addenda store, render order, limits, `holder.json` |
| 061 | Errors per actor | engine | stays | none | 4 (9) | §5 rules 1-8 |
| 062 | Hidden Unicode refused | engine | stays | none | 0 | §5 rules 1-5 |
| 063 | fabric-ctl assist | mixed | amend | the title and rule 1's key `CLAUDE_APIKEY_CLAUDE_PZHUY_8ALIAS_COM` (the account; its slug is a constant in the assist module) | 0 by number; `tools/fabric/control/accounts.py` names the account as an example | rules 2-9 (the operator's terminal only, advice never action, spend recorded) hold for any operator; which key is this organisation's account |
| 064 | GZCoord over InterWeave | mixed | amend | rule 1's second-host paragraph (`fabric-h2`, the Proxmox node s13337, develop-qzapp's address, the owner's waivers for it) | 41 (72) | rules 2-14 and rule 1's first milestone are the carrier; the named second host and its waivers are this deployment's, read from `runtime/hosts/registry.json` |
| 065 | Reviewer reads through pinned tools | engine | stays | §1: the sandbox read back on the coordinator's host | 26 (53) | §5 rules 1-7 |
| 066 | Review class measured as a classifier | engine | stays | none binding; see the uncertain list for rule 3's ledger | 3 (11) | §5 rules 1-11: labels, halves, seeded defects, intervals |
| 067 | One owning module per mechanism | engine | stays | none | 23 (49) | §5 rules 1-5: the catalogue and its lint |
| 068 | One `fabric <noun> <verb>` command | engine | stays | none | 16 (23) | §5 rules 1-10 |

## Totals

| Class | Records | Of which |
|---|---|---|
| engine | 58 | 54 stay as they are; 4 stay with an editorial reword of an example name (007, 020, 027, 033) |
| mixed | 10 | amend 7 (019, 038, 039, 048, 055, 063, 064); split 3 (034, 040, 056) |
| organisational | 1 | moves with its number (059) |
| **all** | **69** | ADR-000 to ADR-068 |

No moved record is cited by the engine: ADR-059 has no citation under `tools/`,
`runtime/`, `bin/` or `policies/`. Of the split records, the engine's citations land on
the part that stays: ADR-034's sixteen all name §7 (the relay backup and the scheduled
drain); ADR-040's name rules 1-8 or the engine's own waves in §7; ADR-056's name the
persona mechanism. ADR-019 rule 4 is cited by `policies/arming.json` (instance data) and
by `policies/fabric-decisions/SKILL.md`; after the amendment the skill's citation still
holds, since rule 4's mechanism stays.

## Uncertain at the draft, and why

- **ADR-019 §6 and rules 6, 8.** The table describes agent-fabric's own GitHub settings.
  Agent-fabric stays as the engine, so the settings could be the engine repository's;
  but "one collaborator, the owner" and "the one GitHub account every session uses" are
  this organisation's hosting. Amending those two clauses is proposed; moving rule 8 and
  §6 whole into an operator record is the alternative, if the published engine will be
  administered by someone other than this organisation.
- **ADR-063, amend or split.** The record exists for one account's key, and its title
  names it. The mechanism (rules 2-9) is general, so amending the key into the operator's
  configuration (and retitling) is proposed. Whether a retitle is an amendment or needs a
  new record is fabric-coordinator's to judge under ADR-001 §5 rules 3-4.
- **ADR-056, split or keep.** The scientist surnames, the weapons test and the house style
  could be read as the engine's default persona policy that another operator replaces.
  Proposed as a split because `identities/personas/` is instance data (ADR-045 rule 2)
  and the style is owned by this organisation's brand-comms.
- **ADR-034, split or amend.** Rule 1 binds the inventory to the record, so the table
  cannot leave by a light amendment; a split keeps the engine's criterion and rules
  2-5. The alternative: an amendment that makes rule 1 point at "the operator's
  inventory" kept outside the record.
- **ADR-040 rule 9.** It advises managed projects and names this library's roles
  (devex-tooling, architect-cto); classed engine with rules 1-8. Only rule 10 and the
  Wave 10 rows are taken as organisational.
- **ADR-066 rule 3.** The labels ledger `docs/review-calibration/labels.jsonl` holds this
  organisation's PR coordinates and labeller. The rule is engine, but the path it fixes is
  instance data that `inventory.md` does not list; the inventory should gain the row, and
  rule 3 may need the path read through `roots`.
- **ADR-000.** The pillars are the fabric's stated purpose and the record any other
  operator inherits; classed engine. Its *Today* paragraphs, though required by rule 2,
  narrate this fleet's history, so the published engine may need them restated.
- **Tool pins in instance files (051, 053, 064).** moli's, Codex's and InterWeave's pins
  sit in `projects/registry.json` or `runtime/interweave/`, instance data, while the
  records are engine. That is an inventory question for step B, not a record's class.
- **Context-only names.** Records 000, 001, 010, 011, 016, 021, 022, 025, 028, 034, 036,
  043, 044, 045, 060 and 065 name this organisation's hosts, projects or PRs in §1, §6,
  §7, §8 or References. They are classed by their rules here; ADR-045 §2 says the public
  engine names no private content, so the publication stage owes them a reword.

## Decided (fabric-coordinator, 2026-11-12)

Every record leaves this pull request either `engine` or `organisational`: "mixed" is the
state the classification found, not one a record keeps.

- **The split's operator parts take the next numbers.** One number space serves both
  trees, so a number names one record wherever it lives: ADR-034's inventory becomes
  ADR-069, ADR-040's porting programme ADR-070, ADR-056's naming theme and house style
  ADR-071. Each is `organisational` and cites the engine record it came from. The engine
  record keeps its number and every rule the engine cites.
- **Moved at step B:** ADR-059, ADR-069, ADR-070, ADR-071, the records whose `Class` is
  `organisational` (`adr.py list --class organisational`). Step B's commit moves them and
  adds their numbers to the engine's `docs/adr/reserved.json`, so no new engine record
  takes one.
- **ADR-019:** amended. Rule 1's named projects become "the projects `policies/arming.json`
  declares direct"; rule 4 keeps its mechanism and points at `arming.json` for the
  numbers; rule 6's "the one GitHub account" and §6's access row name the operator's
  account and the repository's administrators. Rule 8 stays: it is the engine
  repository's own settings, and whoever publishes it administers them.
- **ADR-063:** amended, title included. The mechanism is general and the record is
  Proposed, so the account's key becomes the operator's configured assist key; a new
  record would only renumber the same decision.
- **ADR-034:** split, as the table proposes; rule 1 then points at the operator's
  inventory, ADR-069.
- **ADR-056:** split, but no rule leaves the engine whole. Rules 3, 5 and 7 are cited by
  engine code for what it runs (the list file, sex then a first name from the entry's
  `from`, the candidates' folder and rejections), so they keep that under their numbers;
  ADR-071 takes the taste beside it: the scientist theme and its weapons test, a
  language-culture agent's own culture and the famous-name bar, the house style.
- **ADR-040 rule 9:** engine, with rules 1-8; rule 10 and the Wave 10 rows go to ADR-070.
- **ADR-066 rule 3:** engine. The labels ledger is instance data: `inventory.md` gains
  its row, and step B reads it through `roots`.
- **ADR-000, the tool pins, the context-only names:** engine, unchanged here. The *Today*
  paragraphs and the narrative names are reworded at publication (ADR-045 §7); the pins
  are step B's inventory rows.
