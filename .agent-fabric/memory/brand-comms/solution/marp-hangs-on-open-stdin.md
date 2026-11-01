---
role: "brand-comms"
class: solution
topic: "marp-hangs-on-open-stdin"
description: "gzapp.decks builds and new-deck releases since #32 (1187f2ed): no < /dev/null, no opening hand commit; release --dry-run first"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 72643b82778e06a1
---

## gzapp.decks builds and new-deck releases since #32 (1187f2ed): no < /dev/null, no opening hand commit; release --dry-run first

Marp used to inherit an open stdin and hang, and release.py used to skip a
deck folder that git did not track yet. Both are fixed on main since #32
(1187f2ed, 2026-10-27).

- Deck builds no longer need `< /dev/null`.
- A new deck needs no opening direct commit. Run
  `npm run release -- <deck> <kind> -m "..." --dry-run` first. For a new
  folder, the plan lists every file it would stage, so a stray file shows up
  before it is committed.
- A deck git already tracks still leaves untracked files out. A new file
  inside it needs its own `git add`.

*Anchors: `gzapp.decks:scripts/build.py::stdin=subprocess.DEVNULL`, `gzapp.decks:scripts/release.py::git add`*

*Observed 2026-10-27 (brand-comms)*
