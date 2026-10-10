---
role: "fabric-coordinator"
class: threads
topic: "software-factory-gaps-2026-10-09"
description: "Candidate fabric changes from the software-factory article, each with what this fabric showed on 2026-10-09 — open, none adopted; the charter's bar is observed recurrence"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f13f4f591ca0ef3e
---

## Candidate fabric changes from the software-factory article, each with what this fabric showed on 2026-10-09 — open, none adopted; the charter's bar is observed recurrence

From [[software-factory-loops-graphs-harnesses]], held against one day of the fabric
(2026-10-09). None is adopted: a protocol change needs the pattern seen across
independent sessions (charter), and two of these are one day's evidence.

1. A REQUEST names no non-goals. MESSAGE-FORMAT.md §Requesting a supplied piece
   recommends REQUEST/DELIVER-TO/ACCEPTANCE/FACT/BY — no OUT-OF-SCOPE. The article's
   "most valuable learning" is intent with non-goals. Review briefs already have
   out_of_scope. Evidence to watch: a supplier widening a supply. Smallest change:
   a recommended OUT-OF-SCOPE section (prose convention, not grammar — in scope
   under the freeze).
2. Acceptance without a validation tier. My ACCEPTANCE "both cases fail on c6cc64d4"
   (#134, to python-dev-01) was wrong for one case — the code there was already
   right; the honest bar was "fails on the named mutation". The article maps each
   criterion to a tier. Candidate: ACCEPTANCE lines say how each is shown
   (fails-before, mutation, live read-back, suite).
3. A REQUEST that is not a job is not work. python-dev-03 sat idle an hour on three
   REQUESTs (owner caught it; [[request-needs-a-job]]). Enforce over document:
   gzcoord-send could, for a REQUEST TO a login, refuse or warn unless the job is on
   that login's list (or add it through the control plane). This one is a defect
   seen live, not a convention — the strongest candidate.
4. No end-of-session handoff of what went wrong. This session's process failures
   (request without a job; a memory note wrong for a branch checkout; the suite
   failing on a mid-run worktree; gzapp.decks with no arm.json; an unreviewed merge
   resolution left armed) reached memory one by one, by luck of noticing. The
   article's handoff file + a planner that triages it is "the step that compounds".
   fabric-fresh --note is the nearest thing; a structured "went wrong" list fed to
   the next session's jobs is the candidate.
5. Armed state survives a head change. #134 stayed armed after a conflict merge put
   unreviewed code on its head; I disarmed by hand. Candidate guard: wait-merged or
   the gate disarms when the head moves past the reviewed sha.
6. Shift-left critique of my contracts. My REQUESTs and the merge resolution were
   critiqued only after landing on a branch; findings on #134 came from combining
   two sides (re-reviews 2 and 3). A code-plan critic over a REQUEST before it is
   sent is the article's planning loop; cost vs the review class's later catch is
   unmeasured.

Recurrence, 2026-10-09 06:37Z: architect-cto-01, reading the same article on its own
(relay 01a11f61), arrived at gap 2 (each ACCEPTANCE criterion names its validation
tier) and adopts it in its own messages; and proposed MESSAGE-FORMAT say the original
ask of a REQUEST stays verbatim and changes append (the article's summariser drift).
Two independent sessions now: gap 2 meets the charter's bar for a convention. Also its
note: drain more often than weekly while a role is active (the handoff "compounds").
The owner approved gaps 3 and 5 (2026-10-09): guard 5 = .github/workflows/disarm-on-push.yml.

*References: request-needs-a-job, software-factory-loops-graphs-harnesses*

*Observed 2026-10-09 (fabric-coordinator)*
