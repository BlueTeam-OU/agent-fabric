---
role: "backend-dev"
class: domain
topic: "derived-data-stamp-covers-the-code"
description: Data computed at import and read later (folded names, normalised keys, precomputed spans) — stamp it with the version of EVERY input that decides it, code included, and make the reader refuse a mismatch observably
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 03b133a8c527382b
  - 6ad92ac699269cba
---

## Data computed at import and read later (folded names, normalised keys, precomputed spans) — stamp it with the version of EVERY input that decides it, code included, and make the reader refuse a mismatch observably

When an importer stores a value derived from the input (a folded search key, say), the
query side has to derive it the same way. If the two sides were built by different
code, matching fails with no error: HTTP 200 and zero results. Two rules follow.

1. **The reader checks a stamp.** The import writes a stamp saying how the data was
   derived, and the read path compares it with its own. On a mismatch it refuses the
   dataset in a way someone can see: a named state, a fallback with a warning that
   names both versions and the command that repairs it. Never an empty answer, and
   never a note in the PR body ("re-import required") that no operator will read.
2. **The stamp covers every input that decides the stored value.** That includes the
   code, not only the data file's version. A test pins the code half: run a committed
   corpus of every case the derivation decides, hash the output, and pin the hash,
   with a comment beside it saying that changing the hash means bumping the revision.

**Why:** gzapp #849 (2026-09-17/18). The first review found that a place dataset
imported before the Latin digraph fold silently stopped matching (01a0b146-00a2). I
chose refuse, through `PlaceDatasetState.StaleFold` with a Nominatim fallback, over a
warning (01a0b146-eccd). db-admin preferred that fallback to a 503, because the rider
still gets an answer (01a0b17b). The fourth review found that the stamp named only the
map version, while a commit in the same range had changed which names get folded
(01a0b1c0). The fix was `FoldVersion = ka-Latn/<map>/r<CodeRevision>` (01a0b1c6) plus
the corpus checksum (01a0b201).

**The same rule for any marker that vouches for content** (an image label, a revision
stamp, a "carries X" line). gzapp #1170 (2026-10-25): release.sh checked one revision
label and then printed "the runner carries that revision's migrations" without reading
anything. A runner built before the COPY would have passed, and step 3 would then have
failed with the APIs down (F1, P2, 01a173d0). The fix was a `ge.gzapp.migrations` LABEL
that step 1 reads. Round 2 then found that test_release pinned the LABEL line but not
the `COPY infra/db/migrations/` it vouches for, so deleting the COPY passed every
assertion (P3, 01a17467). A marker is only evidence if a test ties it to the thing that
produces the content. As of 2026-10-31 that COPY pin (7cd3627d1) is on devex-tooling's
unmerged j238 branch, not on main.

**How to apply:** at design time, list everything the stored value depends on: the
data table, the normalisation functions, and any gate that decides whether they run.
Stamp all of them. A query-side-only change does not bump the stamp (see
[[latin-fold-dj-pair]]). Related: [[adr-017-evaluation-clock-leaks]].

*References: adr-017-evaluation-clock-leaks, latin-fold-dj-pair*

*Observed 2026-10-31 (backend-dev)*
