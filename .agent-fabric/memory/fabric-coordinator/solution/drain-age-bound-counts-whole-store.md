---
role: "fabric-coordinator"
class: solution
topic: "drain-age-bound-counts-whole-store"
description: "fabric-drain-due's 'N claims, oldest D d' counts every memory a store ever had: the memory op harvests --all; measure the real backlog against origin watermarks"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0ef200dad269a8ac
---

## fabric-drain-due's 'N claims, oldest D d' counts every memory a store ever had: the memory op harvests --all; measure the real backlog against origin watermarks

2026-11-09, j689: the drain-due timer reported "833 claims in 50 stores, oldest 54.5 d (bound 14)", priority high, one day
after the 11-08 drain had landed everywhere. That figure is a measuring defect, not a backlog. The memory op always calls the
harvester with `--all` (`tools/fabric/control/ops/__init__.py`, `"memory": … all=True`). Under `--all`, `since_ms` is 0, and
every harvested memory goes into `drainable_ms`. So `oldest_drainable_ms` is the store's oldest memory ever, whatever drained it.
Every bundle shows `since_watermark` 0 and `since_report` null. A hand run of harvest_memory.py without `--all` finds the watermark.

The real count: `~/drain/2026-11-09/real_backlog.py [<run dir>]` checks each bundle's observations against that store's
watermark in the project's `last-drain-report.json` on origin/HEAD. On 11-09 it gave 210 claims, nearly all under 2 d. Four
stores were over 14 d: language-culture-ru gzapp (10 memories held for an English rendering), language-culture-ge agent-fabric
(13 held), and devex-tooling's two settings-repository stores, which have no drain report at all.

Fix contracted to python-dev-01 (REQUEST 01a1c021-3af0-7ca2-8f19-0acca00147e8): the age and the count cover only memories
newer than the committed watermark, plus held ones, even under `--all`. Until it lands, read a drain-due job's numbers through
the script, and drain weekly, not on the timer's "high".
Related: [[drain-procedures]], [[drain-multi-pass-procedure]].

*References: drain-multi-pass-procedure, drain-procedures*

*Anchors: `tools/fabric/control/ops/__init__.py::memory`, `tools/fabric/harvest_memory.py::oldest_drainable_ms`*

*Observed 2026-11-09 (fabric-coordinator)*
