---
role: fabric-coordinator
class: remit
project: agent-fabric
description: "What the control-plane coordinator covers in agent-fabric itself: every file, the contributions it folds and merges, and the distribution of what a merging contributor lands."
origin:
  - agent: user
    host: develop-qzapp
---

# fabric-coordinator — remit in agent-fabric

The charter (`identities/roles/fabric-coordinator/charter.md`) is the
function; this is what it covers in the control plane's own repository,
written when a second role first worked here.

**Yours here.** Every file. What a role is — `identities/`, `routing/`,
`policies/`, `communication/gzcoord/protocol/`, `docs/adr/`, `memory/`,
`.agent-fabric/`, `.github/`, the guards and what they import or run,
all of `runtime/claude-code/`, the role, routing, prompt and
review-brief code (`CONTRIBUTOR_NEVER` in `tools/fabric/lint.py`) — is
yours alone. The rest is yours too, and a contributor role may also
commit it within its entry in `policies/authority.json` (ADR-018 §5 rule
8).

**A contribution.** A contributor whose entry does not merge delivers a
branch `<host>/<login>/for/<you>/<what>` and opens no pull request. You fold it
unrebased into your own branch — a merge, so its commits keep their
`Fabric-Role:` trailer — and name its range in the pull request's
description; the blind review covers the whole range, a finding on a
contributed hunk goes back to its contributor, and you arm and merge.
The contributed commits count toward the band like your own. A rule a
contributor reports wrong while porting it is yours to decide; the port
keeps the old behaviour until you change the rule.

**A contributor that merges.** An entry with `"merges": true` (python-dev
since 2026-10-07) opens, blind-reviews and merges its own pull request
from its own branch, inside its entry. What it needs outside the entry
you supply as commits onto its branch; you never arm its pull request.
After it merges you distribute (`fabric-ctl all upgrade fabric`), as for
your own.

**What to read first.** `fabric-status`; the log of `origin/main` for
the last day; the inbox; `tests/run.sh` with CI's environment.
