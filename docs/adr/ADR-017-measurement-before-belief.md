# ADR-017 — Measurement before belief: live checks are evidence, prompt changes are read back

**Date:** 2026-09-15
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #52 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** docs/live-checks/; tools/fabric/adr.py (the Evidence field); tools/fabric/lint.py (`harness_source_findings`, `doc_path_findings`); runtime/openrouter/launch (`--print`); tools/fabric/launch_prompt.py (`MAX_CHARS`); tests/test_launch_prompt.py; identities/roles/fabric-coordinator/brief.md; identities/prompt/team.md and identities/prompt/memory.md (verifying before asserting)
**Pillar:** P2
**Evidence:** docs/live-checks/2026-09-15-append-system-prompt.md, docs/live-checks/2026-09-23-opus-5-5.md

## 1. Context and Problem

The fabric sits on things it does not own — a harness that changes with
every build, providers, models, a hypervisor — and several of its
designs were first decided from documentation that turned out wrong or
silent. `--append-system-prompt-file` is hidden from `--help`, and the
harness accepts an unknown flag with exit 0, so a parser check proves
nothing (2026-09-15). Opus 5.5 serves through the launcher, but its
default effort is a level below Opus 5's — a change that would have
shipped with no commit to review (2026-09-23). The first inbox-hold hook
passed its unit test and wrote nothing live, because the test's payload
lacked a field the harness sends (2026-09-16).

The same shape bit the fabric's own changes. On 2026-09-19 a charter
passed lint (its per-file budget) and the suite, was merged, and its
holder could not launch: the rendered prompt was 24.5k characters
against a 23k ceiling that only the launcher checked.

## 2. Decision

**A design decided from documentation is a guess until a live read-back
confirms it** (the coordinator's brief, 2026-09-15). What the fabric
relies on is measured where it runs — live, or read out of the installed
binary — and the measurement is kept as a **live check** under
`docs/live-checks/`: evidence that decision records cite, never rewritten
into a different result. The harness-specific half of this is ADR-008;
the model half is ADR-005's rule that a model enters routing only after a
read-back.

**A change to what a session is born with is read back as a launch.** A
charter, brief, prompt template or locale change is rendered by the
launcher as a holder of each affected role before it is pushed; the
suite renders every catalogue role against the ceiling as well.

**A claim is checked before it is asserted.** A delivery's claim is
verified against the tree before it is acted on; a statement about a
repository is made from the remote ref, not a stale checkout; a guard
added with a fix is proved on the shapes the fix removed.

## 3. Alternatives Considered

- **Trust the vendor's documentation and help text.** Rejected by
  measurement: hidden flags, silent acceptance of unknown flags, defaults
  that differ by model, reminders built from settings no prompt carries.
- **A test in place of the live read-back.** Necessary, not sufficient:
  the inbox hook's test passed on a payload the harness never sends, and
  the launcher does what the suite cannot see (pull, bind, resolve
  models). Both are kept.
- **Record the measurement inside the decision.** Rejected: a decision
  changes by amendment; a measurement is a fact about a build on a date
  and must stay as measured, so a later decision can be weighed against
  it (ADR-001 §5 rule 8).

## 4. Rationale

An organization that retires beliefs needs to know which beliefs rest on
evidence (ADR-000, P2: "a belief with neither evidence nor an owner is a
liability"). A live check dated and tied to a build is exactly the
evidence a later session can re-run when the build moves; a read-back
before a push moves the cost of a broken launch from every holder of a
role to the author of the change.

## 5. Binding Rules

1. A fabric design that depends on how a harness, provider, model or
   platform behaves is read back live, or out of the installed binary,
   before it is relied on; the read-back includes a control where a
   silent failure would look like success (a marker the session must
   quote or answer "NO MARKER", a flag that must be refused).
2. The read-back is recorded as `docs/live-checks/YYYY-MM-DD-<slug>.md`,
   dated by the measurement: what was run, on which host, login and build
   or version, what was measured, and what it decides; what it did not
   establish is said.
3. A live check is evidence. A decision record cites it in `**Evidence:**`,
   and `adr.py check` refuses a path that does not exist; the captured
   harness prompt names its live check as `source:`, and lint refuses one
   that is not an existing live check.
4. A live check's measurement is never rewritten. A later read-back is
   appended as its own dated section; a practice a later decision
   replaced is marked with a one-line banner under the title, followed by
   a blank line, and the measurement stands.
5. After a change to any role's charter or brief, a prompt template under
   `identities/prompt/`, or a locale's translation, the author runs
   `runtime/openrouter/launch --print` as a holder of each affected role
   (for a shared section, the longest prompts) before pushing; the
   launcher renders the prompt and refuses one over `MAX_CHARS`, and
   `tests/test_launch_prompt.py` renders every catalogue role against it.
6. A guard added with a fix is verified by planting each shape the fix
   removed, as the tree contained it, and watching the guard fail.
7. A finding sent to another role states how it was verified, the control
   that shows the measurement was live, and what was not verified
   (`identities/prompt/team.md`); a claim about a repository is made from
   the fetched remote ref (`identities/prompt/memory.md`).

## 6. Consequences

- Twenty-three live checks exist on 2026-09-27. Most end with what they
  decide; three older ones (routing of 2026-09-13, the locale prompt
  replacement of 2026-09-18, the first `upgrade fabric` of 2026-09-26)
  leave that to their prose and to the record that cites them.
- Rules 1, 2, 5, 6 and 7 are practice, held by the author and the review
  class; nothing mechanical checks that a read-back happened. Rule 4 is
  not mechanised either: `adr.py range-check` refuses edits to
  `docs/adr/sources/`, not to live checks, and `doc_path_findings`
  exempts live checks from its citation check because they cite what was
  true when written.
- The ceiling that broke a launch is now tested for every role
  (`MAX_CHARS` 28 000 since 2026-09-20); the launch read-back stays,
  because the launcher does what the suite does not.

## 7. Future Evolution

- ADR-001 §7 names a check that a record's Evidence has not been
  superseded; P2's direction is that a decision whose evidence has gone
  stale is flagged for review.
- A range check that refuses a rewrite of a live check's existing
  sections, if one is ever rewritten.

## 8. Decision Status

Accepted: the brief's rule since 2026-09-15, live checks since
2026-09-13, the prompt read-back since 2026-09-20.

## References

- `docs/live-checks/` — e.g. the Evidence above; the inbox hold
  (`docs/live-checks/2026-09-16-inbox-hold-while-planning.md`), the
  effort registry (`docs/live-checks/2026-09-23-effort-registry.md`).
- `tools/fabric/lint.py` (`harness_source_findings`, `doc_path_findings`),
  `tools/fabric/adr.py`, `tools/fabric/launch_prompt.py`,
  `tests/test_launch_prompt.py`
  (`case_every_catalogue_role_renders_under_the_ceiling`),
  `runtime/openrouter/launch`.
- `identities/roles/fabric-coordinator/brief.md`, `identities/prompt/team.md`,
  `identities/prompt/memory.md`.
- `.agent-fabric/memory/fabric-coordinator/workflow/prompt-change-readback.md`,
  `.agent-fabric/memory/fabric-coordinator/workflow/guard-must-catch-the-shape-it-replaced.md`.
- ADR-000 (P2), ADR-001 (§5 rule 8), ADR-005 (a model after a read-back),
  ADR-008 (harness behaviour).
