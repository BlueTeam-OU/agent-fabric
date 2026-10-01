---
role: shared
class: workflow
topic: "guard-must-catch-the-shape-it-replaced"
description: A guard added alongside a fix is verified by planting the exact shape the fix removed — not the shape you had in mind when you wrote the pattern
tier: 1
knowledge_scope: full
shared_with:
  - "fabric-coordinator"
  - "python-dev"
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0c8e876312607fd5
---

## A guard added alongside a fix is verified by planting the exact shape the fix removed — not the shape you had in mind when you wrote the pattern

When a fix removes a bad idiom and you add a guard so it cannot return,
plant the removed shape and watch the guard fail. Planting *a* violation
is not enough: write down the spellings the tree actually contained, and
test each one.

Concretely (agent-fabric PR #28): the defect was a module URL handed to
the filesystem as `.pathname`. It appeared two ways — inline,
`new URL('./x', import.meta.url).pathname`, and bound first,
`const file = new URL('./x', import.meta.url); … file.pathname`. The
guard I wrote grepped for `import.meta.url).pathname` and I verified it
by planting the inline form, which passed. A blind review found it
matched neither of the three sites the same commit had just converted —
all of them the bound form. A guard that misses the case it exists for
is worse than none: it reports clean and the reader stops looking. The
replacement is a binding pass (collect identifiers bound from a module
URL per file, then flag their `.pathname` uses), verified against three
shapes including a legitimate `new URL(req.url, …).pathname` that must
still pass.

Two related traps from the same branch: a lint check that read a pattern
from a schema but fell back to a hard-coded copy on failure — the
fixture never had the schema, so every case ran the fallback and the read
path shipped untested; and a dead-key guard scoped to one file, which
would have called twenty-six keys in another file dead.

The same shape, twice more on that branch and not about guards at all:
hardening an unguarded dictionary read in one module while adding an
unguarded copy of the identical idiom to a second in the same commit;
and fixing a suite that was green on CI and red on holders by making it
green on holders and red on CI — the new fixture took the role from the
running login's binding, and CI's login has none. Both were caught by
review, and the second by the PR's own CI, red on one commit and green
on the next.

**Why:** a fix is verified against the case you were thinking about, not
against the case that made it necessary. The diagnostic question was
already asked and answered for the defect — "what does CI's login
actually have?", "where else does this idiom appear?" — and simply not
re-asked of the fix. A guard written in the same sitting as the fix is
the special case where nothing else will ever exercise it.

**How to apply:** re-ask the diagnostic question about the fix itself
before committing it, out loud: the defect was *X depends on Y* — does
the fix still depend on Y, or on something equally variable? Then,
before committing a guard, `git grep` the pre-fix
commit for what it is meant to catch, enumerate the distinct spellings,
plant each one, and confirm both that it fires and that a legitimate
neighbour still passes. See [[blind-review-loop]] and
[[local-grep-is-ugrep]] — the same branch also confirmed the guard must
be checked with `/usr/bin/grep`, not the local ugrep.

Again on #69 (2026-09-30): self-kill-guard's prefix fix regressed twice in
review — a merged option set, then an outer-prefix-only set — each fixing
the reported spelling and opening another. What ended it was walking the
structure (each prefix switches its own option set) and keeping every
earlier round's spellings as refused cases. Before committing a fix to a
parser-like guard, run the previous version against the new cases AND the
new version against every old case, nested forms included.

And the rule behind #70's fourth round: model the tool, not the text. pkill
takes ONE pattern, its first non-option argument; taking the last let
every trailing thing (comment, redirect, fd) displace it. Prove a guard
change by loading every prior version (git show) and comparing decisions
over a corpus of every command any review named — zero "denied before,
not now" — and pick probe words that do not occur in the cmdline fixture
(the fixture said "inbox watch", so a misread "watch" matched by luck).

*References: blind-review-loop, local-grep-is-ugrep*

*Observed 2026-10-01 (fabric-coordinator)*
