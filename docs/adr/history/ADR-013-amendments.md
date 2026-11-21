# ADR-013 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-28 — What a session is given at start

§7 recorded a known gap: every generated `INDEX.md` said the
session-start hook gives every `workflow` slice at start, and no hook
did; the record left the choice between loading them and correcting the
banner. The comparison of an external skill-layer plugin with the drain
raised it again, and the owner asked for it in the next PR. Measured on
2026-09-28 across the managed projects: a role's workflow slices are
45–140 KB (architect-cto in gzapp, the largest, about 35k tokens), and
even their index lines reach 23 KB. Loading either at every session
start, on every login, costs more than a missed cue; the banner now says
what the hook gives, and tells the reader to open the matching workflow
slices before the work they govern. The `tier: 1` mark stays as the
larger budget for procedures. Existing indexes carry the old banner
until their next drain regenerates them.

### Amendment 2026-09-28 — A correction replaces a section only at its source or with merge_target

Rule 12 said a wrong slice is corrected by a memory of the same class,
drained like any other. The assembler replaces a stale section only when
the correcting memory carries `merge_target` (ADR-014 rule 7); without it
the correction is filed as a topic of its own beside the stale text.
Measured on 2026-09-28: five correction memories written from that
wording would have landed as five new slices in a gzapp drain, two stale
citations kept; the authors corrected their source memories instead, and
agent-fabric #58 corrected the prompt, CLAUDE.md and memory/README.md.
#58's review found this rule still teaching the old flow.

### Amendment 2026-09-28 — A memory is judged when it is written

The owner chose the external skill-layer plugin comparison's idea 3 for
the fabric: tell an agent about a memory the drain will reject when it
writes it, not weeks later at the drain. The same day's gzapp drain showed
the cost of finding out late: a 16.8 KB thread memory over the slice
budget, and correction memories that would have landed beside their
targets. A PostToolUse hook was read back first
(`docs/live-checks/2026-09-28-posttooluse-memory-feedback.md`): it gets
the written path, and the model reads its `additionalContext`. It runs at
user scope, from the settings writer, because a memory belongs to the
account wherever its session started; a workspace-template hook would ask
every managed project to mirror it. The rules are imported from the
harvester and lint, not copied. A usage measurement of slices and skills,
the comparison's idea 1, is kept for later.

### Amendment 2026-10-10 — Truth is judged where it lives: anchors, flags, horizons

ADR-050 makes the holder of a role the judge of whether its slices are
still true. Four rules here change to carry it: rule 11's drain report
lists flags, helpful marks, applied corrections, same-agent retitles and
the sections past a review horizon; rule 12 asks a correction into a
`shared/` slice to name `shared_with` and its author to retire the memory
it replaces and the applied correction; rule 14's write-time check gains
the event-shaped description warning and the anchors hint; rule 15 is the
routing itself. Evidence: on 2026-10-10, 32 of agent-fabric's 69 slices
were stale (17 citing a gone path, 19 records of an event) and 325
sessions in 24 hours read no slice; the same day's drain also left applied
corrections standing beside the text they replaced. The owner chose
distributed judgement with a central assist over central evaluation.
None of the four rules' new behaviour is built yet; each says so in its
text and what happens until it is, and ADR-050 section 6 names the
builder of each.

### Amendment 2026-11-21 — A hygiene entry may hold in its own project only

The owner ruled on 2026-11-19, in the gzapi.brand half of the drain of
2026-11-17: gzapp is the app and must be valid wherever it runs, so its
corpus names no city or country; another project's memory may be about
a situation in a real place. The one scope there was, `"others"`, does
the reverse (the name is the listing project's to say, withheld
everywhere else), and an unscoped entry in gzapp's list redacted a
gzapi.brand rationale slice that cites that project's own decision
record, which names the city. `"scope": "own"` is the new value: the
entry holds in the listing project's slices and is left out of every
other project's set and of agent-fabric's. Without a project the set is
the strictest, which is what the fabric's domain slices are held to:
they are read in every project, so an own name stays out of them. Built
by python-dev-02 (j173); the scope goes on gzapp's entries only after
the fleet runs the code, since older code refuses an unknown scope.
