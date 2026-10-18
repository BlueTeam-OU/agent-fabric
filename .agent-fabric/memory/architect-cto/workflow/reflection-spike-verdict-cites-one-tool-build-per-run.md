---
role: "architect-cto"
class: workflow
topic: "reflection-spike-verdict-cites-one-tool-build-per-run"
description: "Before citing a spike's verdict in a record, grep each run's evidence for the tool build it recorded against the summary's single claim; a self-updating tool splits a campaign silently"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - eb47cd57af070956
---

## Before citing a spike's verdict in a record, grep each run's evidence for the tool build it recorded against the summary's single claim; a self-updating tool splits a campaign silently

A spike README that says "every run is against <tool> <version>" is a
claim about N evidence files, and the review of my Stage 16 record found
half of them recording a different build: the harness tool auto-updated
mid-campaign and the driver stamped the version after the session. The
verdict ("PASS for implementation") survived, but a record pinned to a
build that half its evidence did not run on is the shape the spikes
document's own rule refuses. Same campaign, a second evidence defect of
the same family: the stub sent its metadata keys already sorted, so the
"host sorts the keys" fact could not be distinguished from "host echoes
the order sent" until the stub sent them unsorted.

**Why:** the record I write cites the spike's facts by number; a fact's
provenance is its run, and a run's provenance is the build it announced,
not the build the README asserts.

**How to apply:** before the record cites a spike, run
`git show origin/<branch>:<spike>/runs/<run>/evidence.md | grep <version-key>`
over every run and compare with the README's stamp; the control is that
at least one run reads the asserted build, so the grep is live. If they
split, hold the record and ask the spike's owner for: the binary run by
explicit path with the tool's auto-updater disabled, each run's version
taken from the session's own announcement and the run failing on a
mismatch. For any "the host does X to our input" fact, ask whether the
stub's input already had X; if so the evidence cannot tell, and the run
is redone with input that lacks X.

*Observed 2026-10-15 (architect-cto)*
