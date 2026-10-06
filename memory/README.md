# Memory

Decisions: agent-fabric ADR-013, ADR-014 (docs/adr/)

Durable knowledge agents can retrieve, filed by **scope** and by **kind of
truth**, with provenance that says who learned it, where, and when.

```text
memory/                          (this repository — field knowledge)
├── domains/<domain>/            reusable knowledge about a field
├── agents/<login>/              knowledge genuinely tied to one agent (rare)
├── shared/                      field knowledge two or more roles own
└── RUBRIC.md                    what earns a place here, and what does not

<working copy>/.agent-fabric/    (each managed project's own repository)
└── memory/
    ├── <role>/                  filed per role: what that role learned here
    │   ├── INDEX.md             generated map of everything the role knows
    │   ├── crossref.json        artifact → where it was learned and landed
    │   ├── solution/ intersection/ rationale/ workflow/ threads/
    ├── shared/                  project knowledge two or more roles own
    └── last-drain-report.json   the last drain's record (every bundle of its stamp) and watermarks
```

**Project knowledge lives in the project's repository.** A `solution`
slice describes the tree as of a date and loses to the tree; keeping it
beside the tree is what lets a change that moves the architecture update
the slice in the same commit series, and lets a checkout at any commit
carry the knowledge that was true then. It also keeps a project's
confidential knowledge under the project's own license and access.
`.agent-fabric/` is written by the **fabric-coordinator role** — the
drain writes it, every other role reads it; the git hooks refuse a
commit under it unless the session's binding holds the role, and CI
checks the `Fabric-Role:` trailer they write (`policies/AUTHORITY.md`). Index links inside it are
relative to the working copy; a fabric-side slice is linked as
`../agent-fabric/<path>`, the sibling-checkout layout.

The reusable definition of a role — its charter, its brief (how it works,
in any project; in every launch prompt), its recall guide, its skills — is
**not** memory. It lives under `identities/roles/<role>/`.
Where a role applies inside a repository is a project binding under
the project's `.agent-fabric/taxonomy.json`. This directory holds only what was
learned.

## Why this exists

Sessions accumulate knowledge that the repository never records. Decision
records say what was decided and why; the code says what is; a project's
`CLAUDE.md` says what the rules are. None of them hold the things that were
learned the hard way — that a green test suite can be testing nothing, that
a queued branch refuses a push, that a bare permission error from a
container is really a stale security label. That knowledge lived only in a
memory buffer organised by session rather than by subject.

So it gets drained: mined, judged against a fixed bar (`RUBRIC.md`), filed
by scope and by kind of truth, and committed. Memory is the **input
buffer**; this corpus is the **durable knowledge**.

## Four scopes

| scope | what belongs | default for |
|---|---|---|
| `domains/<domain>/` | true of the field regardless of any project | technical knowledge that transfers |
| `<working copy>/.agent-fabric/memory/<role>/` (in the project's own repository, never here) | what one system implements, decided, does, and still owes | most of what a session learns |
| `agents/<login>/` | genuinely specific to one agent and to nothing else | almost nothing — a fact is not agent-scoped merely because that agent discovered it |
| `shared/` | field knowledge owned by two or more roles, stored once | the assembler's multi-owner route |

Domain ids currently equal role ids: the corpus was extracted with domain
knowledge filed per role, and renaming domains was not part of the
extraction. `tools/fabric/layout.py` is the one place that knows where each
class lives, so a domain can be split or renamed later without touching
the tools.

## Six kinds of truth

Slices are filed by **epistemic class**, not by topic, because the classes
decay and verify differently and mixing them is how a knowledge base starts
lying:

| class | scope | what it is | how it is checked | how fast it rots |
|---|---|---|---|---|
| `domain` | domains | true of the field regardless of us | against the discipline | slowly |
| `solution` | projects | what the system implements today | against the tree | every merge |
| `intersection` | projects | where we follow or depart, and why | against the decisions | when a decision changes |
| `rationale` | projects | reasoning not yet in a decision record | against the record | until promoted |
| `workflow` | projects | how work is actually done there | by doing it | when tooling changes |
| `threads` | projects | known loose ends | by closing them | continuously |

Two consequences worth stating plainly. **`solution` carries an as-of
date** and where it conflicts with the tree, the tree is the fact and the
drift is worth recording — project truth always overrides stale distilled
knowledge. **`rationale` is a staging area, not an authority**: where it
disagrees with an active decision record, the record wins and the
disagreement is a finding. Entries there that prove durable get promoted
into an actual decision record and deleted here.

Some evidence comes from sibling projects. It can teach how a platform
behaves but says nothing about what a given system implements, so it is
marked `knowledge_scope: domain-only` and may support `domain` claims and
nothing else. The sibling project is never named.

## Two tiers, and why

A session is born with tier 1 only: the role's charter and brief, in the
system prompt the launcher renders (`tools/fabric/launch_prompt.py`), and
the project's remit for the role plus the pointer to its `INDEX.md`, from
the session-start hook. Everything else waits for a cue.

The index is the mechanism. Each slice's frontmatter carries a one-line
description written as a retrieval cue, and the index is **generated** from
those lines — never hand-maintained, because a hand-written index drifts
from the files it points at and then quietly lies. Its paths are relative
to the working copy — a fabric-side slice through `../agent-fabric/` —
because a role's knowledge lives in three places (its identity, its
domain, the project). A session reads the index,
recognises that knowledge exists, and opens the one slice that matches.
`tools/fabric/lint.py` fails when an index and its slices disagree.

## Provenance

Every distilled slice carries frontmatter the assembler writes:

```yaml
origin:
  - agent: backend-dev-02        # who learned it: the Linux login
    host: develop-qzapp          # where it ran
    project: gzapp               # what it applies to
    working_copy: backend-dev-02 # the checkout, as a label
derived_from:                    # observation content hashes
  - 42bc0c9685ab878c
distilled_at: "2026-09-05"       # when
topic: release                   # the memory this file is (not on a flat <class>.md)
```

`topic` is what tells a budget part from a memory named like one: part
two of `release` is `release-2.md`, and so is a memory named `release-2`
(a drain's blind review, 2026-09-26). A slice written before the field
existed is read as a part when `release.md` exists and neither the drain
nor the role's crossref names `release-2` as a topic.

Agent, host, project and working copy are four separate facts. Slices
written before the identity migration carry `clone_id` instead of `agent`;
they are preserved verbatim, and
the label is kept as it is — a record of where the slice was learned, not
resolved to a login. An observation that resolves to no agent is reported
**provisional**, never guessed, and the tally lands in
`last-drain-report.json` and on stderr at assembly. The runs of one
stamp — one per bundle — merge into that report: each bundle's harvest
record is kept under `harvest_sources` (by agent@host), and `files`
lists what the tree holds after the last run, not a file a later run
of the stamp retired.

## The drain cycle

The input is each agent's own Claude memory
(`~/.claude/projects/<launch-dir-slug>/memory/`), written deliberately,
one fact per file. A memory reaches this corpus only if it opts in with a
`roles_class` in its `metadata:` block; nothing is inferred from `type`. A
memory with no `roles_class` is skipped **and named** in the report.
`charter`, `brief` and `recall` are refused as targets — they are authored
identity, not derived knowledge. A fact other roles own too names them
on one line, `shared_with: web-dev, backend-dev`, in the same block: the
drain carries the co-owners and the assembler files the claim once,
under `shared/` (a `domain` claim here, a project claim in the project's
own `shared/`), with every owner's index pointing at it.

A holder that writes its memory in another language (language-culture,
in the language it answers for) drains through the **English rendering**
each drain-ready memory carries under a `## English` heading: the claim
is the rendering, the original stays in the holder's home, the
observation records the language. Its cue is English too: a description
in another script travels under `description_en: "…"` in the `metadata:`
block, because the index line and the heading are what every holder of
the role reads first. A non-Latin memory without either is
named under `needs_rendering` in the report and yields no claim — so a
drain of such a login is two steps: the coordinator's dry run, whose
`needs_rendering` names go to the holder as a `REQUEST` on the relay;
the holder — the fleet's translator — renders them and answers with the
count; then the drain. Nothing translates a memory but its holder.

```sh
tools/fabric/harvest_memory.py --role architect-cto --out /tmp/drain --dry-run
tools/fabric/harvest_memory.py --role architect-cto --out /tmp/drain
tools/fabric/assemble.py --claims /tmp/drain/claims --drain /tmp/drain \
    --project <project> --working-copy ~/projects/<working-copy> --stamp $(date +%F)
tools/fabric/lint.py --working-copy ~/projects/<working-copy>
```

Across accounts the drain is a **bundle**: one tar with a manifest naming
who harvested and the digest of every file, written by the agent on its
own account and verified by the coordinator before anything is read —
only the agent reads its memory; the coordinator receives the result.
It travels over the control plane (`docs/adr/ADR-029-the-control-plane-a-control-agent-per-account.md`): each
account's own daemon answers `memory` by running the harvester on every
memory directory the harness keeps for it, and `fabric-ctl` reassembles
and verifies what came back — no sudo, no read of another home.

```sh
bin/fabric-ctl all memory --out ~/drain               # <login>/<working copy>.tar per account (0700/0600), plus each report
bin/fabric-ctl all memory --out ~/drain --json         # the same, with every name the table only counts
tools/fabric/assemble.py --bundle ~/drain/<login>/<wc>.tar --project <project> --working-copy ~/projects/<wc> --stamp $(date +%F)
```

The run is also the dry run: each row carries the harvest report —
the claim count, how many memories need rendering, how many were
skipped — beside the bundle's status, and `--json` carries the names,
so the `needs_rendering` list for the holder comes from the same run
that fetched the bundles. The op always harvests every memory (`--all`);
the watermark below governs the sudo fallback. A memory carrying a
credential by shape refuses that account's whole drain at the
harvester, named in the row. A bundle whose parts are short, whose
digest is wrong or whose manifest names another agent is refused with a
status and no file.
`bin/fabric-host <host> drain <login> > drain.tar` remains only as the
sudo fallback for a host whose daemons are down.

**Holding a slice back.** `assemble.py --hold FILE` (a JSON list of
`<role>/<class>:<topic>` or `shared/<class>:<topic>`) keeps those slices
out of this drain — knowledge waiting on a ruling, say — and the report
lists them under `held_back`. A key naming no slice refuses the run. A
hold defers, it does not drop: the store's watermark is kept below the
oldest memory a held claim stands on (or not moved, when one has no
recorded time), so the next drain without the hold writes the slice.
Under a hold the report's `watermarks` for that store is therefore lower
than its harvest's own `next_watermark`; the former is what the next
harvest reads.

One `assemble.py --bundle` run per bundle, all with the drain's one
`--stamp`, build one drain report: a run finding a report of the same
stamp merges into it — roles and shared topics unioned, decisions (one
per key, the later), moves, files and findings appended without
repeats, telemetry kept per agent@host so a re-run bundle replaces its
counts — and a report of another stamp is replaced. Watermarks carry
across both: a run replaces the mark of each store (agent@host) it
harvested with that harvest's own — lower too, when the harvester held
it below a memory awaiting its rendering — and a run that harvested
nothing changes none. Every path in the report is
relative to the working copy, or to the fabric root for a fabric file.

`harvest_memory.py` stamps the agent from `runtime/identity.py`, the
project from the working copy's remote, and the working copy as a label.
It reads only memories newer than the **watermark** the project's last
report recorded for this agent's store (`last-drain-report.json`,
`watermarks`, keyed `agent@host` — every account on a host has its own
store; the projects root's memory is a second store of the account,
keyed `agent@host#projects-root`, with a bundle of its own; a harvest
report names only its own store; `--all` ignores it), and writes `harvest-report.json` with the next one,
which `assemble.py` commits — so each drain starts where the last one
stopped, and `bin/fabric-status` can say how much is undrained.
Each agent drains **its own** memories; nothing reads another account's
home directory. `assemble.py` writes the project-scoped classes into the
working copy's `.agent-fabric/memory/` (`--working-copy`; the agent's
binding supplies it when omitted) and the domain classes into this
repository — so a drain lands as a branch in the project's repository,
opened by a fabric-coordinator holder under that project's contribution
rules, plus a commit here.

**When a drain runs** (stated 2026-09-15; there was no cadence before,
and the roles' own accounts of their work named facts "reconstructed
from transcripts more than once"): an agent harvests after a change to
how its role works has landed — a merged pull request that changed a
workflow, or a `solution` fact that cost a day — and at least weekly
while it is active; a fabric-coordinator holder assembles and commits
what arrived, with the agent's name in each slice's `origin`. A slice an
agent finds wrong is not raised by hand: the agent corrects the memory
the slice was drained from, or writes the correction as a memory of the
same class carrying `merge_target: "<the stale section's heading>"`, and
the next drain puts it in the stale section's place
(`identities/prompt/memory.md` tells every session so). A correction
without `merge_target` is filed as a topic of its own beside the stale
text, which stays. `bin/fabric-status` counts what an agent has written
and not yet drained.

**Landing a drain, in this order** (2026-09-18, after three gzapp
reds in one day from the fabric moving under its check). The domain
slices commit and push here first — a project index that lists a slice
not yet on fabric main is the same drift finding, so the order is
forced. Then, on each project's drain branch,
`.agent-fabric/fabric-ref` is written with that commit
(`git -C agent-fabric rev-parse origin/main >
<wc>/.agent-fabric/fabric-ref`; one line, the full id — lint checks
the shape) and the project pull requests are opened and armed at once.
A project whose CI runs the fabric's guards checks out the commit that
file names, never the fabric's default branch: a fabric change reaches
the project's check only when the ref moves, in the pull request that
carries the matching indexes, and a fabric defect stops the fabric's
CI rather than the project's. Between the fabric push and the project
merges the window is still open on a project whose CI has not yet
pinned the ref — kept to minutes by arming the PRs in the same breath
as the push, and said on the relay when a queue holds one for longer.

**Merge mode is the default from cycle two onward.** New claims fold into
existing slices; the existing file is the calibration anchor for what
counts as good enough; **an empty delta is a correct outcome.** Never
regenerate from scratch — that discards accumulated curation. Same claims
in, byte-identical tree out, which is what makes a drain reviewable as a
content diff.

**A claim that disagrees with the corpus stops the drain** (the owner,
2026-09-20). A new claim under a heading the slice already carries, with
different text — a workflow that changed, or a memory that is wrong —
is a potential supersession, and the assembler cannot tell which. It
used to write both as "X" and "X (2)" and report a collision nobody
read. Now `assemble.py` finds every such pair in a pre-pass, writes
nothing, and exits 1 naming each: the section in the corpus with its
date, the incoming one with its agent and date, both texts. The
coordinator brings the pairs to the owner, and the re-run carries the
owner's word in `--collision-decisions FILE`, one entry per pair —
`supersede` (the incoming text replaces the section and retires its
siblings: `merge_target`, the author's instrument, applied on the
owner's decision), `keep-both` (both stand, side by side, dated), or
`drop` (the incoming claim is wrong). Every applied decision is
recorded in the drain report under `collision_decisions`. Two claims of
one drain under one heading collide the same way. So does a **retitled
memory**: a memory's topic is its file name and its heading its
description, so a claim bringing a new heading into a topic whose every
section one agent wrote — that agent's own — is the same memory
rewritten (a tracker's "OPEN" become "MERGED"), not a second fact.
Only the topic's own file answers that — `<class>/<topic>.md` and its
budget parts, or the shared `<class>-<topic>.md` and its parts: the
flat `<class>.md` holds every memory of its class until the class
splits, and a carried file every memory it moved with, so a claim
landing there is never a retitle (a drain's blind review, 2026-09-26:
one agent's second memory in a flat file deleted its first); a new
text under a heading one agent wrote there still falls under the rule
below, which replaces that one section and touches no other memory.
**An agent's newer text replaces its own older text without a
question** (the owner, 2026-09-26, after 34 such pairs asked and all 34
superseded): a retitle, or a new text under a heading of that agent's
own topic, supersedes — the old sections are retired and the new one
takes their place — and it is printed (`SUPERSEDED, same agent`) and
recorded in `collision_decisions` with `"rule": "same-agent"`. An
owner's decision in `--collision-decisions` still wins. Two agents'
texts under one heading, and two claims of one drain under one heading
with different texts — whether or not the corpus holds that heading
too — still stop the run. A topic several agents wrote appends a new heading as before, and
a memory whose `merge_target` names the old section is not asked about. An author who knows
the older text is superseded says so in the memory itself — in its
`metadata:` block, `merge_target: "<the section's heading>"` — and no
question is asked: the harvest carries the field to the claim and the
assembler replaces the section and retires its siblings; the section
then carries the correcting memory's own heading, not the stale one —
also when the stale section sat in another budget part of the topic
and was retired there. The heading is
found wherever it lives in the role's class (or the shared class), not
only in the correcting memory's own topic — a correction is a memory of
its own, so its file name is never the stale slice's. A heading held by
two topics refuses the run (`MERGE TARGET AMBIGUOUS`, nothing written);
a heading held by none is written as its own topic and named on stderr
and under `merge_target_unresolved` in the report — on every drain that
brings the memory, not only the first. The tree cannot tell a target
that never matched from one an earlier drain already replaced, so the
author reads the line and either retargets the memory, if a stale section
remains, or drops the `merge_target`, if it was applied.

**Every section is dated.** A claim carries `observed_at` — the
memory's own `modified` stamp, else the file's mtime — and the section
rendered from it ends with *Observed YYYY-MM-DD (role)*, so where the
owner keeps both, a reader sees which describes the later state. The
role, never the login: a slice travels into every repository.

## Tools

```text
tools/fabric/layout.py            where each class lives — the one source
tools/fabric/harvest_memory.py    drain this agent's memory into claims
tools/fabric/assemble.py          claims → slices, indexes, citation graph
tools/fabric/lint.py              guard the committed corpus (CI)
tools/fabric/query.sh             ask the citation graph
tools/fabric/role.py              bin/fabric-role — bind a role to this agent, from a login shell
tools/fabric/launch_prompt.py     the system prompt a session is born with: charter, brief, team and memory sections
```

`query.sh` answers the questions the citation graph exists for:

```text
tools/fabric/query.sh adr ADR-054        # who learned from it, where it landed
tools/fabric/query.sh migration 0007
tools/fabric/query.sh obs <content-hash> # what a single observation taught
tools/fabric/query.sh roles              # sizes, per project and role
```

The graph stays in committed JSON rather than a database. It is small
enough that `jq` answers in milliseconds, and keeping it in files preserves
the property that matters most: a drain is reviewable as a diff. If
multi-hop queries ever become routine, the next step is a *generated*
SQLite edge cache — derived, never authoritative.

## Language, and who is named

English, always, whatever the source was in. Translate rather than quote;
mark a translated quote as translated. `lint.py` flags a slice that reads
as non-English.

**A person is named by role, never by name.** The CEO, the owner, a
reviewer, an agent by its login (`architect-cto-01`): a slice travels
into every project's repository and outlives the session that wrote
it, so a person's name in it is a privacy matter, not a style one
(decided 2026-09-16). The same holds for the memory an agent writes for
itself, since a drain carries it verbatim; and for a secret of any
shape — a password, an API key, a token, key material — which is never
knowledge. `policies/hygiene.json` (people) and the credential shapes
in `tools/fabric/layout.py` are the fence, together with each project's
`.agent-fabric/hygiene.json` for its own names — its city, its country,
the sibling projects. **The assembler substitutes, it does not refuse:**
a hit becomes what the entry says instead (`refer_as`: a person becomes
"the CEO") or `[redacted]`, in the title, the description, the body and
the file name alike, and every substitution is named in the drain
report so the memory's owner fixes the source. Lint refuses a committed
slice that still carries a hit, so nothing reaches `main` unsubstituted.

A project's own entry may carry `"scope": "others"`: the name is that
project's to say in its own slices (its `.agent-fabric/memory/`), and is
withheld everywhere else — the fabric's corpus and every other project.
The fabric's own list may not use the scope, and a list that cannot be
read, or carries a key or flag it does not know, stops the drain and is
a lint finding: nothing is judged clean against a broken list. A
substitution note names the entry's label and the place, never the text
it withheld.

**Where the rule stops** (three roles asked on the first fleet drain,
2026-09-18): the lists ban a deployment's *place names* — its city, its
country, a sibling project — as words in prose. A **language or script
name is not banned**: "the Georgian script", "a Georgian interface",
`ka-GE` name the locale's language, which is the fact itself for a
locale rule, and hiding it would make the knowledge unreadable ("a
[redacted] interface"). Say what the place is to the fact — the
deployment, the market, the deployment's country — and name the
language where the language is the point. A **path or identifier is
not matched**: the patterns stop at word boundaries, so
`tools/gtfs_<city>/…` passes as it is, and a `solution` slice cites
the system's paths as the system spells them — project truth, kept in
the project's own repository. Every substitution is a memory to fix at
the source; a hit inside a path would be a name to change in the
system, which is not the drain's call.

## What is not here yet

Recall is deliberate: a session consults the index, or a skill surfaces
through description matching. What is missing is *involuntary* recall —
knowledge arriving unbidden the moment matching code is touched. Nested
skill directories or a pre-tool hook matching path patterns are the two
documented routes; neither is built. The absence is a design choice, not
an oversight.
