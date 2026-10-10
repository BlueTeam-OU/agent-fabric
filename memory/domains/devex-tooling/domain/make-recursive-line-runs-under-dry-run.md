---
role: "devex-tooling"
class: domain
topic: "make-recursive-line-runs-under-dry-run"
description: "a recipe line that references $(MAKE) RUNS under make -n — a callback string carrying $(MAKE) made `make -n tiles-publish` publish a real vintage"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 2dc725fcf13005f3
---

## a recipe line that references $(MAKE) RUNS under make -n — a callback string carrying $(MAKE) made `make -n tiles-publish` publish a real vintage

GNU make executes any recipe line that references the MAKE variable even
under `-n` (it treats it as a recursive make). On 2026-10-08 a
`--record-cmd "$(MAKE) … tiles-record"` argument passed to publish.py made
`make -s -n tiles-publish CITY=[redacted]` run the whole publish (12 MB into
infra/local/tileserver/published/); only the sub-make, which inherited -n,
was dry.

Fix used in gzapp (branch feat/tile-vintage-publish, 1205fcb31): a callback
handed to a script is spelled `make -s --no-print-directory -C $(CURDIR)`,
never $(MAKE); test_make_data_prechecks asserts `make -n` publishes nothing
and the $(MAKE) spelling fails it.

Same day, same branch, measured: `podman compose run` (podman-compose
provider) prints the container id on stdout before the command's output,
and `run --build` prints the whole build log on stdout too — build in its
own step with `>&2`, and strip only leading 64-hex lines when parsing.
And two containers bind-mounting the same directory with `:Z` deny each
other (the private label is per container; the second start relabels) —
use `:z` on both. See [[podman-volume-prune-on-a-stopped-stack]].

*References: podman-volume-prune-on-a-stopped-stack*

*Observed 2026-10-08 (devex-tooling)*
