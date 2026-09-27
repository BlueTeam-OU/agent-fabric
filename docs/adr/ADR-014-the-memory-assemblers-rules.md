# ADR-014 — The memory assembler's rules: contested claims, same-agent retitle, corrections

**Date:** 2026-09-20
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #52 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** tools/fabric/assemble.py (the collision pre-pass, `--collision-decisions`, `merge_target` resolution, the write phase, the drain report's `collision_decisions` and `merge_target_unresolved`); tools/fabric/harvest_memory.py (`observed_at`, `merge_target`); tests/test_assemble.py; memory/README.md §"The drain cycle"
**Pillar:** P2

## 1. Context and Problem

The assembler files each drained claim under its topic and heading
(ADR-013). Until 2026-09-20 a claim arriving under a heading the slice
already carried, with different text, was written beside it as "X (2)"
and reported as a collision nobody read. Such a pair is a potential
supersession — a workflow that changed, or a memory that is wrong — and
the assembler cannot tell which. Nothing dated a section either, so two
divergent sections could not even be read in time order.

The drains of 2026-09-25 and 2026-09-26 found the rest of the shape. A
memory's topic is its file name and its heading is its description, so
an agent rewriting a tracker ("#851 OPEN" → "#851 MERGED") brought a new
heading into its own topic and the stale section stood beside it, both
cues in the index. A correction memory naming the stale section in
`merge_target` is a memory of its own, with its own file name, so it
landed as a new slice beside the one it corrected. And once the owner
was asked about every same-agent pair, 34 of 34 were the author's later
version, all superseded (the owner, 2026-09-26).

## 2. Decision

**A claim that disagrees with the corpus stops the drain** (the owner,
2026-09-20). Before anything is written, a pre-pass finds every such
pair; if any stands undecided, the run writes nothing, exits 1 and names
each: the section in the corpus with its date, the incoming one with its
agent and date, both texts. The coordinator brings the pairs to the
owner, and the re-run carries the owner's word in `--collision-decisions
FILE` — `supersede` (the incoming text replaces the section and retires
its kept-both siblings), `keep-both` (both stand, side by side, dated),
or `drop` (the incoming claim is wrong). Every applied decision is
recorded in the drain report under `collision_decisions`. Every section
is dated (*Observed YYYY-MM-DD (role)*), so a kept pair reads in time
order.

**An agent's newer text replaces its own older text without a question**
(the owner, 2026-09-26). Where every section the claim would replace
came from the claim's own agent, the assembler supersedes, prints
`SUPERSEDED, same agent`, and records the decision with `"rule":
"same-agent"`. The rule covers the retitle — a new heading in a topic
whose own files one agent wrote — and a new text under a heading that
agent wrote. It is bounded: an older text, a heading two claims of one
drain disagree under, and two agents' texts still stop the run; an
owner's decision still wins.

**An author who knows its older text is wrong says so**, in the memory's
`metadata:` block, `merge_target: "<the section's heading>"`; the
harvest carries it to the claim, and the assembler replaces that section
without asking, wherever it lives in the role's class, under the
correcting memory's own heading.

## 3. Alternatives Considered

- **Append and report** (before 2026-09-20). Rejected: the report went
  unread, the index showed both cues, and a reader could not tell which
  was current.
- **Newest wins, always.** Rejected: a newer memory can be the wrong
  one, and a replayed or delayed bundle carries old text with a new
  arrival; which of two agents is right is not the assembler's call.
- **Ask the owner about every pair, same agent included** (2026-09-25
  to 2026-09-26). Rejected by the owner after 34 of 34 same-agent pairs
  were answered `supersede`: asking had become a formality that cost the
  owner's attention and taught nothing.
- **Infer a retitle from any file one agent wrote.** Rejected
  (2026-09-26): the flat class file holds every memory of its class until
  the class splits, so one agent's second memory there read as a retitle
  of its first, and the rule deleted the first.

## 4. Rationale

The corpus is curated, not accumulated (ADR-000, P2): a belief is retired
by a decision someone can point at, not by whichever text arrived last.
Stopping the whole drain, rather than writing what is clear and
reporting the rest, keeps every drain a reviewable diff with no half-
applied state to revert. The same-agent rule removes the owner from the
one case the evidence showed was never in doubt, and keeps them in every
case where it could be — two authors, a contested heading, an older text.

## 5. Binding Rules

1. The collision pre-pass runs before any write. If any pair stands
   undecided, the run writes nothing and exits 1, naming each pair with
   both texts and dates. Sections are compared **undated**: the same
   text again, whatever its date, is never a collision, and a text
   already standing as a kept-both sibling "X (n)" is not asked again.
2. A pair is: an incoming claim under a heading its topic's files hold
   with a different text; two claims of one drain under one heading with
   different texts, whether or not the corpus holds the heading; or a
   **retitle** — a new heading in a topic whose own files'
   (`<class>/<topic>.md` and its budget parts, or the shared
   `<class>-<topic>.md` and its parts) every origin names one agent, the
   claim's own. A retitle is never inferred from the flat `<class>.md` or
   a carried `<class>-carried-<stamp>.md`, which hold several memories.
3. A decision is `supersede`, `keep-both` or `drop`, keyed by the heading
   (`<role>/<class>:<topic>#<heading>`, for every pair under it) or by
   the claim (`…#<heading>@<first evidence hash>`), the claim's key
   winning. `supersede` on a retitle retires every section of the topic
   and puts the new heading in the first one's place. Every applied
   decision is recorded under `collision_decisions` in the drain report.
4. **Same agent.** Absent an owner's decision, a pair supersedes without
   a question when the claim's agent is the only agent in the origin of
   (a) the topic's own files, for a retitle, or (b) every file the
   pre-pass reads the topic from — the flat class file included, when it
   holds the topic — for a new text under an existing heading — the same-heading supersede replaces one
   section and touches no other memory. It is printed (`SUPERSEDED, same
   agent`) and recorded with `"rule": "same-agent"`.
5. The same-agent rule never applies when the incoming claim is dated
   before any section it would retire (the heading and its "X (n)"
   siblings; for a retitle, the whole topic) — an undated side does not
   block it — nor when two claims of this drain disagree under the
   heading, nor when another agent's origin is in the files.
6. A claim repeating the text of the first claim of a contested heading
   leaves the drain: the decision on the first governs it, and its
   evidence is folded into the first claim's, so every agent that
   asserted the text stays in the slice's provenance.
7. `merge_target` is the author's instrument: a claim naming a section
   present in its topic replaces it without a question and retires its
   siblings. A target absent from the claim's topic is looked for in
   every topic of the role's class (or the shared class); one holder
   takes the claim. A heading two topics hold refuses the whole run
   (`MERGE TARGET AMBIGUOUS`, nothing written). A heading held by none is
   written as the claim's own topic and named on stderr and under
   `merge_target_unresolved` on every drain that brings the memory.
8. A corrected section carries the correcting memory's own heading, also
   when the stale section sat in another budget part and was retired
   there.
9. A claim body's own headings of level two or deeper are demoted one
   level at render time, so a body never opens a section and the same
   claims twice give a byte-identical tree.
10. A slice of the directory shape or under `shared/` names its `topic`
    in its frontmatter; that field, not the file name, decides whether a
    `<topic>-<n>.md` is a budget part or a memory of its own. Part one of
    a split topic is always `<topic>.md`.

## 6. Consequences

- A drain that meets a real disagreement costs a round trip to the owner
  and a re-run; one that meets only an author's own updates does not.
- The author holds the cheapest path: a memory that names its
  `merge_target` is applied without anyone being asked. The price is that
  the tree cannot tell a target that never matched from one an earlier
  drain already applied, so the author reads the unresolved line and
  either retargets the memory or drops the field.
- Sections accumulate dates, not duplicates; a kept pair is visible as
  such.

## 7. Future Evolution

- `memory/README.md` said a claim in the flat class file "never falls
  under" the same-agent rule. That holds for the retitle only; the
  same-heading supersede applies in a flat file (rule 4(b), since the
  re-review of 2026-09-26). The manual is corrected in the same commit as
  this record.
- A decision file the coordinator writes by hand is the one manual step
  left; a generated skeleton from the refused run's output is a
  candidate.

## 8. Decision Status

Accepted: the stop and the dated sections since 2026-09-20; the retitle
as a collision since 2026-09-25; the same-agent rule, bounded to newer
text and to uncontested headings, since 2026-09-26 (the owner's word,
recorded in the commit that applied it).

## References

- `tools/fabric/assemble.py` (the pre-pass: `sole_author`,
  `is_budget_part`, the collision loop; the write phase),
  `tools/fabric/harvest_memory.py` (`observed_at`, `merge_target`).
- `tests/test_assemble.py`: `test_a_collision_stops_the_drain_until_the_owner_decides`,
  `test_a_retitled_memory_replaces_its_own_old_section`,
  `test_one_agent_s_memories_in_a_flat_class_file_are_not_one_retitled_memory`,
  `test_an_agents_new_text_under_its_own_heading_in_a_flat_file_supersedes`,
  `test_the_same_agent_rule_never_replaces_newer_text`,
  `test_a_correction_naming_another_topic_s_section_replaces_it_there`,
  `test_an_unresolved_merge_target_is_reported_on_every_drain`,
  `test_a_claim_body_s_own_headings_never_open_a_section`.
- Commits 2383b44 (the stop), 5ffd21f (the retitle), 04f4b1c (the
  owner's same-agent rule), e995f18 and 3845255 (newer text only),
  14f85cd and 94461ce (the topic's own files; the same-heading supersede
  in a flat file), 3571e91, b6dcc66 and 9e172af (corrections), cac5a04
  (body headings).
- `memory/README.md` §"The drain cycle", the manual.
- ADR-013 (the memory model this assembles).
