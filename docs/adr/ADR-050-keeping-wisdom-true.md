# ADR-050 — Keeping wisdom true: judgement where the knowledge lives

**Date:** 2026-10-10
**Status:** Accepted
**Ratified:** owner, 2026-10-13, in the session ("record adr accepted", answering which Proposed records to accept)
**Decision Makers:** the owner (distributed judgement with a central assist); drafted by fabric-coordinator
**Scope:** `tools/fabric/memory_check.py` and `tools/fabric/lint_rules/slices.py`; `tools/fabric/harvest_memory.py` (`parse_memory`), `tools/fabric/assembler/slices.py` (`claim_block`, `remove_sections`), `tools/fabric/assembler/writer.py`, `tools/fabric/assemble.py`, `identities/schemas/claims.schema.json`; `runtime/claude-code/hooks/memory-write-check.py`; `memory/RUBRIC.md`, `memory/README.md`, `identities/prompt/memory.md`; the drain report and the `memory` op of the control plane; `policies/hygiene.json`
**Pillar:** P2

## 1. Context and Problem

The curated corpus (ADR-013) is meant to be wisdom: lessons that stay true
and change what a session does. On 2026-10-10 a verification against main
found 32 of agent-fabric's 69 slices stale: 17 cite a path that no longer
exists, and 19 are records of an event (a PR merged, an issue closed, a
state on a date), not lessons. Four slices are both, so the two counts
overlap and their union is 32. In the same 24 hours `fabric-ctl all
recall` counted 325 sessions and no INDEX or slice read (ADR-049).

Nothing in the pipeline asks, after a section is filed, whether it is
still true. The drain checks form (the rubric, hygiene, collisions); the
*Observed* date says when a section was true, not whether it still is.
`memory_check.py` finds a gone path and nothing else, and nobody is
assigned to act on what it finds. A drain run by fabric-coordinator also
sees only what each agent chose to opt in, so the coordinator is the
least placed reader to judge whether a `solution` section about a
project's code, or a `workflow` section about a role's procedure, still
holds. The agent that holds the role, working in that tree, is.

## 2. Decision

Truth is judged where the knowledge lives.

A `solution` or `workflow` memory may carry **anchors**, the paths and
symbols its claim rests on. A mechanical check, runnable anywhere, sorts
each section as stale-hard, maybe-stale, fresh, unchecked or no-anchor;
only the first two are flags. Each flag reaches the agent that holds the
section's role in one REQUEST, which becomes one job, and that agent checks
the section against the tree and either corrects it with a `merge_target` memory or
confirms it, which re-dates it. A reader's `memory_mark` of `stale` or
`wrong` is routed the same way. For a maybe-stale section the drain may
attach an advisory hint from one model call; the owning role judges and
the drain applies nothing.

The admission bar rises with it: a memory must be a lesson, not a record.
A lesson that can be a test, a lint rule or a hook becomes one and its
section is deleted. Sections are never expired by age; the drain lists
those past a review horizon, and the role's holder confirms, corrects or
retires each, as it does a flag.

## 3. Alternatives Considered

- **Central truth evaluation** (the coordinator or a model judges every
  section against its tree). Rejected by the owner: the judge would be
  the party with the least knowledge of the tree, and a model verdict
  applied to curated wisdom is the unreviewed change the drain exists to
  prevent.
- **Time-based expiry** (delete or archive a section after N days).
  Rejected: wisdom can be rare and decisive; a lesson learnt once in a
  year may be the one that prevents the next incident, and age does not
  say it is wrong. Age only sets a review horizon (rule 8).
- **Auto-merged defrag** (a job rewrites and merges slices that look
  stale or duplicated). Rejected: it changes curated text with no author
  who knows the claim, and a merge is the point a wrong correction becomes
  the corpus.
- **A bitemporal fact store** (valid-time and record-time per claim, so
  superseded knowledge stays queryable). Rejected: superseded knowledge is
  the slice's git history; the corpus serves what is true now.

## 4. Rationale

A claim about code is cheapest to check next to the code. Anchors turn
"is this still true" from a reading task into a mechanical question with a
short list of suspects, so the judge's work is the part only it can do:
reading a few lines of a section against the tree. Routing the flag to the
role's holder gives the check an owner and a place in the job list
(ADR-037); a flag nobody is assigned is the state `memory_check.py`
already left the corpus in. A reader who meets a wrong section is the best
sensor the fabric has, and ADR-049 decides a `memory_mark` for it; this
record gives the mark somewhere to go once ADR-049's server and harvest
carry it.

The rubric gains the test the stale count points at: 19 of 69 slices were
events, which the tree, git, the PR or the job list already record. Of the
rest, a lesson a test or a hook can enforce is better enforced there than
read (ADR-015, the stronger executable form).

The corrections from the drain that found the stale count are rules here
because each cost a measured defect: a `merge_target` into a `shared/` slice that reached no
one; applied correction memories left standing beside the text they
replaced; a same-agent retitle that retired sections the new claim did not
name; and addresses and home paths that the hygiene patterns did not catch.

## 5. Binding Rules

Where a rule says "not yet built", the behaviour is not in the
tree; the words after it say what happens until it is.

1. **Anchors.** A memory whose
   `roles_class` is `solution` or `workflow` may carry
   `anchors: [<path>::<symbol or literal>]` in its `metadata:` block: a
   repository path, and after `::` a symbol name or a literal string that
   path must contain. `harvest_memory.parse_memory` carries them to the
   claim, `identities/schemas/claims.schema.json` admits them,
   `slices.claim_block` renders them into the section's provenance line,
   and `memory-write-check.py` asks for them on a `solution` or `workflow`
   memory that has none, reading them as `parse_memory` does. A memory of any other class that
   carries `anchors` keeps its claim: the harvest drops the anchors with a
   warning, so the schema never sees them and a drain is never refused for
   them.
2. **Mechanical detection.** `tools/fabric/memory_check.py` sorts every section as exactly one of
   five outcomes, and a slice it cannot read is reported `unreadable`,
   never routed. `stale-hard`: an anchor's path is gone, an anchor's
   symbol or literal is no longer in its file, or a path the section cites
   is gone. `maybe-stale`: an anchor's file changed after the section's
   *Observed* date; the finding names the commit that changed it, and it
   needs that file's git history. `fresh`: every anchor and cited path
   holds and no anchor's file changed since *Observed*. `unchecked`: the
   origin project's checkout is absent, or the history is shallow or
   missing, so the section cannot be judged; unknown, never stale, never
   routed. `no-anchor`: the section has no anchors and cites no path; not
   checked, never routed. Only `stale-hard` and `maybe-stale` are flags.
   The check runs anywhere there is a checkout, needs no network and no
   model, and is also a lint warning from `lint_rules/slices.py`, never an
   error.
3. **A flag is routed to one agent** (`tools/fabric/memory_flags.py` decides
   and renders, `memory_flagrun.py` sends). The routing key is per section: the agent that last wrote the
   section, which the drain keeps per section in its own state beside
   `memory-drain-reads.json` (a slice's provenance names the role, never
   the login, as it travels into every repository), if it
   still holds the section's role; else the role's running holder; else its
   lowest-numbered holder. The assembler records the writer per section
   (`section_writers` in the drain report, one agent per section, the last
   to write it), and the flag run routes by it as above; a section with no
   recorded writer, or whose writer no longer holds the role, goes to the
   running holder, else the lowest-numbered one. A `shared/`
   section is routed by its section's role as recorded in *Observed*; if
   that names several roles, by the first. The drain sends one REQUEST per
   agent listing its flags, each with the slice, the heading, the anchor
   and the reason; the REQUEST becomes one job on that agent's list by
   intake (ADR-037 rule 11), so the drain adds no job per flag and needs no
   signed `jobs-add`. A flag already listed in an open job of that agent is
   not sent again; the drain report lists it as still open. The drain
   report lists every flag and the agent it went to.
4. **The owning role judges.** The agent given a flag checks the section
   against the tree and does one of two things: it writes a memory with
   `merge_target` naming the section's heading that corrects it (ADR-014
   rule 7), or, if the section is true, it confirms it by a memory with
   the same `merge_target` and an unchanged claim, whose *Observed* date
   re-dates the section. Re-dating a confirmed section exists: it is the
   assembler's same-claim rule (`writer.py`; `tests/test_assemble.py`
   `test_the_same_claim_again_is_never_a_collision_whatever_its_date`). The
   drain never edits a flagged section itself.
5. **The reader's judgement** (`memory_flags.py` routes the marks; the drain
   report carries them as `memory_marks` and `memory_helpful`). A
   `memory_mark` of `stale` or `wrong` (ADR-049 rule 3) is carried in the
   harvest bundle, from each login's own `memory-marks.jsonl`, through
   `fabric-ctl <login> memory`, and is routed as rule 3 routes a flag, by
   the section the mark names. `helpful` marks are counted per section id
   in the drain report.
6. **The central assist is advisory** (`tools/fabric/memory_hint.py`). For a `maybe-stale` section the drain may
   attach a hint: one model call per flagged section, through the harness
   CLI on the coordinator's account, given the section and the diff of its
   anchors since *Observed*, asked which sentence looks wrong. The hint is
   text in the flag's REQUEST, marked as a model's guess; no flag, section
   or slice changes because of it, and a drain with no model available
   runs the same without it.
7. **A lesson, not a record.** The rubric has test 6, "a lesson, not a record".
   `memory-write-check.py` warns on a description shaped like an event,
   matched exactly and case-sensitively: it starts with `FIXED`, `MERGED`,
   `CLOSED` or `DONE` in capitals followed by `:` or a space, or with
   `#<digits>` or `PR <digits>`, or with a date `YYYY-MM-DD` followed by
   `:`. The promote verdict: a lesson that can be a test, a lint rule or a
   hook is made one and its section is deleted (ADR-015); a `workflow`
   lesson replaces one-off values with parameters. The assembler retires a
   section when a `merge_target` memory names its heading and has no body
   (`slices.remove_sections`); the retired section leaves the corpus, and
   its text stays in git. The retire path is built:
   `claims.schema.json` admits a retire claim whose body is empty,
   `parse_memory` produces it, and `writer.py` removes the section.
8. **Review horizons, listed, never expired** (built in the drain
   report). The drain report lists each
   `solution` section older than 30 days and each `workflow` section older
   than 90 days whose *Observed* date no confirmation has re-dated, and
   each section no `memory_read` returned in the last 8 weeks. The horizon
   counts reads, not finds: the ids a read returned, which ADR-049 rule 7
   decides the harvest bundle carries. ADR-049's server and the
   bundle's read ids exist, so the drain counts them now (`ids_read`,
   `memory_horizons.record_reads`); the unread list stays empty for a
   section until the drain has watched it for 8 weeks, since before that
   the answer is unknown, not "unread". The drain keeps the per-section
   last-read date in its own state file, `memory-drain-reads.json`, in the
   drain's agent state directory (`agents/<login>/`, beside
   `memory-calls.jsonl`), and writes it on every drain. Nothing is
   deleted, archived or demoted by age. A listed section is routed as rule
   3 routes a flag, to its owning role, whose holder confirms it
   (re-dating), corrects it or retires it; the owner is not asked per
   section.
9. **A `merge_target` into a shared slice names `shared_with`.**
   `memory-write-check.py` warns when a memory's `merge_target` names no
   heading in the role's own slices of its class and the memory has no
   `shared_with`; slices it cannot read, it says nothing of.
10. **A correction's author retires what it replaces.** The author of a
    correction memory retires the memory it replaces, in its own Claude
    memory, when the correction is written. After a drain applies a
    `merge_target` correction, the author retires the correction memory
    too, until the harvest drops applied corrections itself. The drain
    report lists every applied correction (`applied_corrections`).
11. **A retitle replaces only the section it names** (built: the
    assembler's half and the report's, #252).
    The same-agent retitle (ADR-014 rule 4(a)) replaces a section
    only when the claim names it by `merge_target` or shares its cue; a
    claim that shares nothing with the topic's sections is a new topic.
    The assembler does this (`slices.shares_cue`, `collisions.py`). The
    drain report lists every same-agent retitle it applies, in its
    `retitles` list (`assembler/report.py`), beside the line printed as
    `SUPERSEDED, same agent`.
12. **Hygiene patterns.** `policies/hygiene.json` has patterns for
    private-network addresses and for `/home/<login>/` paths, applied in
    every project as ADR-013 rule 10 applies the existing ones.
13. **The drain runs per project.** The assembler has no domain-only mode;
    a drain is one run per project, and a run that lacks a project's
    working copy writes nothing for it.
14. **Nothing crosses hosts by a local read.** Everything the drain needs
    from another agent (memories, marks, call counts, confirmations)
    travels in that agent's harvest bundle through `fabric-ctl`, or as
    REQUESTs over the relay. No step reads another account's state, or
    another host's disk, directly (ADR-013 rule 5).

## 6. Consequences

- Built: rules 1 to 10, 12, 13 and 14, and the assembler's half of rule 11.
  The anchors are `parse_memory`, the claims schema and `claim_block`; the
  checker is `memory_check.py` with its lint warning; the flags are routed
  by `memory_flags.py` and `memory_flagrun.py` from the assembler's
  `section_writers`; the model hint is `memory_hint.py`; the drain report
  carries the marks, the horizons and the applied corrections; the retire
  path is the schema's empty body, `parse_memory` and `writer.py`. The
  rubric has test 6 and the promote verdict, and the hook
  (`memory-write-check.py`) warns on rules 1, 7 and 9. The report of
  rule 11 is built too: its `retitles` list (#252).
- fabric-coordinator's drain gains work (routing, the report's lists) and
  loses the work it could not do well: judging a section it cannot see
  the code of.
- Each role's holders gain jobs. The cost is bounded by one REQUEST per
  agent per drain, no flag already open is sent again, and the flag count
  falls as stale sections are corrected or retired.
- Section counts will fall: records are retired, and lessons that became
  tests leave the corpus. That is the aim, not a loss.
- A section without anchors is checked for a gone path only; the quality
  of detection follows the quality of anchors, which the write-time hint
  asks for and nothing forces.
- ADR-013 rules 11, 12, 14 and 15 and ADR-014 rules 4 and 7 are amended
  with this record; ADR-049 §7's "anchors, to come with the record that
  makes them" is this record.

## 7. Future Evolution

- Require anchors on a `solution` memory at write time, once the share of
  sections carrying them is measured.
- Have the harvest drop applied corrections itself, which retires the
  second half of rule 10.
- Move the retitle change (rule 11) into the assembler's pre-pass, which
  retires the report listing.
- Weigh the call counts against the horizons: a section never read and
  never flagged is a candidate for its role's decision, not for automatic
  action.

## 8. Decision Status

Accepted (the header names the owner's word).

## References

- ADR-013 (the memory model; §5 rules 11, 12, 14 and 15 amended), ADR-014 (the
  assembler's rules; §5 rules 4 and 7 amended), ADR-015 (code is memory;
  the stronger executable form), ADR-037 (jobs), ADR-049 (retrieval; marks
  and call counts), ADR-029 (the `memory` op)
- `memory/README.md`, `memory/RUBRIC.md`
- `tools/fabric/memory_check.py`, `tools/fabric/assembler/slices.py`
  (`remove_sections`, `claim_block`), `tools/fabric/assembler/writer.py`,
  `tools/fabric/harvest_memory.py`,
  `runtime/claude-code/hooks/memory-write-check.py`
