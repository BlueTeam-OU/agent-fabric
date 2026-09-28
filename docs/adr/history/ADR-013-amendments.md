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
