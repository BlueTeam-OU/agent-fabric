---
role: "brand-comms"
class: domain
description: "Porting a Node script to Python (ADR-040 Wave 10): where the two runtimes differ silently, and how to run the old script as an oracle without touching the clone."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: gzapi.ge
    working_copy: gzapi.ge
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: gzapp.decks
    working_copy: gzapp.decks
derived_from:
  - 2c19408741a668f3
  - 5b867442edfb0953
  - 6845bcbd59e8cbea
  - 82563842f5be1487
---

## What GITA ([redacted]'s Innovation and Technology Agency) offers startups as verified on 2026-09-17 — programme names, amounts, co-financing, windows — for the GITA deck in gzapp.decks/gita/.

Verified 2026-09-17 from gita.gov.ge, grants.gov.ge and 500.co (fetched pages,
not search snippets):

- **Innovative Startup Acceleration Program (INAP_2027)** — grants.gov.ge
  call 275: fully GITA-funded, 50,000 GEL at Phase II + 150,000 GEL at
  Phase III (200,000 GEL/startup), run through accelerators (Plug and
  Play, Startupbootcamp since Jan 2026; 500 Global and Founder Institute
  from July 2026); call listed open to 31 Dec 2026. The 500 Global
  "[redacted] Startup Academy" is one track: 12 months (6 Jul 2026 – 25 Jun
  2027), Stage 1 founder-market fit (≤40), Stage 2 MVP (≤20, 50k GEL),
  Stage 3 market entry (≤10, 150k GEL); needs a Georgian legal entity
  (or plan for one); for MVP-stage, NOT early-revenue/VC-seeking;
  applications closed 31 Jul 2026, reopen October 2026.
- **Startup Matching Grants** — grants.gov.ge call 271: up to 150,000 GEL,
  ≤90% of a nine-month project budget, ≥10% applicant cash co-financing
  (private, not public grants); NAPR-registered business entity; last
  call closed 5 Sep 2023 — watch for a new call.
- **Innovation Grants for Regions** — up to 25,000 GEL, regional
  ecosystem (Samegrelo winners reported; Imereti/[redacted] eligibility to
  confirm with GITA: +995 32 2 00 44 82, info@gita.gov.ge).
- Historical: 100,000 GEL and 650,000 GEL matching-grant competitions.

The GITA deck (`gzapp.decks/gita/deck.md`, v0.1.0, uncommitted) keeps the
programme, amounts, co-financing and dates as [PLACEHOLDERS] — the owner's
facts.

## The three instruments a national innovation agency offers startups — staged accelerator grants, matching grants, regional grants — with the figures verified 2026-09-17 for the one this company applies to.

A national innovation agency's startup support comes in three shapes, and
knowing which one a deck is written for decides what the deck must say.
Read a programme from the agency's own pages and the state grants portal,
never from a search snippet; record the call number, the ceiling, the
co-financing share, the eligibility and the window, because all five move.
The figures below are the agency this company applies to (GITA), verified
2026-09-17:

- **Innovative Startup Acceleration Program (INAP_2027)** — grants.gov.ge
  call 275: fully GITA-funded, 50,000 GEL at Phase II + 150,000 GEL at
  Phase III (200,000 GEL/startup), run through named accelerators
  (four of them, joining through 2026); call listed open to 31 Dec 2026.
  One accelerator's track: 12 months (6 Jul 2026 – 25 Jun
  2027), Stage 1 founder-market fit (≤40), Stage 2 MVP (≤20, 50k GEL),
  Stage 3 market entry (≤10, 150k GEL); needs a legal entity registered in the
  country (or a plan for one); for MVP-stage, NOT early-revenue or
  VC-seeking;
  applications closed 31 Jul 2026, reopen October 2026.
- **Startup Matching Grants** — grants.gov.ge call 271: up to 150,000 GEL,
  ≤90% of a nine-month project budget, ≥10% applicant cash co-financing
  (private, not public grants); a business entity on the national registry;
  last call closed 5 Sep 2023 — watch for a new call.
- **Innovation Grants for Regions** — up to 25,000 GEL for the regional
  ecosystem; winners reported in one region, so eligibility for the
  company's own region is confirmed with the agency by phone before a
  deck names it.
- Historical: 100,000 GEL and 650,000 GEL matching-grant competitions.

The grant deck keeps the programme, amounts, co-financing and dates as
[PLACEHOLDERS] until the owner fills them: which instrument is being
applied for is a company fact, and a deck that guesses it is wrong in a
way a reviewer at the agency will see.

*Observed 2026-09-18 (brand-comms)*

## A Marp slide that is too tall does not clip — vertical centring spends its margins first, so "it fits" by eye can be an overflow; measure section scrollHeight, per language

Marp centres a slide's content vertically. A slide whose content is taller
than the frame does not visibly clip: the title rises toward the top edge
and the last line runs down into the credit or footer. By eye that reads
as "fits, a bit tight".

Measured on gita-pitch v2.4.1 (2026-10-30, the deck-review trial, PR
gzapi-org/gzapp.decks#33): in the Georgian deck, pages 5 and 9 have
`section.scrollHeight > clientHeight`. On page 5 the title sits about 90px
from the top, against 200px in English, and the privacy line is about
20px above the photo credit. The v2.4.0 commit f54a9bf had called page 5
fitting.

**How to apply:** after any change that lengthens copy, and always for
Georgian, compare each slide's title height from the top across languages,
or measure overflow on Marp's HTML output (the `deck-review` skill's
assessment B). Never call a translated slide fitting from the render alone.
Related: [[deck-review-ledger-before-blind-findings]].

*References: deck-review-ledger-before-blind-findings*

*Observed 2026-10-30 (brand-comms)*

## Porting a Node script to Python (ADR-040 Wave 10): where the two runtimes differ silently, and how to run the old script as an oracle without touching the clone.

Differences that read alike and are not, each of which broke the
gzapp.decks port:
- `spawnSync` of a missing binary returns `status: null`, which callers
  treat as a failure and move on from. `subprocess.run` raises. Route
  every external command through one wrapper that returns a failed result.
- JavaScript truthiness: `{}` and `[]` are truthy, while Python's `not {}`
  is True. Compare with `is None`.
- `path.join` joins an absolute part and resolves `../`. `os.path.join`
  drops what precedes an absolute part and resolves nothing. Use
  `normpath("/".join(parts))`.
- `readdirSync` is sorted byte-wise (libuv), so `sorted()` matches it.
  `localeCompare` is ICU order: `_` before `-`, then digits, then letters,
  lower case before upper.
- `Number()` accepts `0x`, `0o`, `0b` and `Infinity`, and reads `""` as 0.
  `float()` accepts `inf` and `1_0`. A huge hex literal is Infinity, not
  an OverflowError.
- `RegExp.test(x)` coerces a non-string with `String()`. Python crashes
  on it.
- `\p{Script=…}` has no stdlib equivalent. The `unicodedata` name
  approximates it and misreads about 750 code points.
- `open(p, "w")` truncates before a read in the same expression, so read
  first, then write.
- Text mode turns `\r\n` into `\n`. Use `newline=""` for byte parity.
- Importing a sibling module writes `__pycache__/`, which dirties the
  tree. Set `sys.dont_write_bytecode = True`.

**How to apply:** build the oracle as a fresh `git worktree` per run,
with the old script restored from the base commit, and a stub for any
renderer. Pass excludes through `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0=core.excludesFile`
in the run's environment, never through `info/exclude`: every worktree
shares that file, and writing to it hid my new files from git in my own
clone. Tags made in a worktree are the clone's own, so delete any a test
creates.

*Observed 2026-10-19 (brand-comms)*
