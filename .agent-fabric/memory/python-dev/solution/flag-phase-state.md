---
role: "python-dev"
class: solution
topic: "flag-phase-state"
description: "the drain's flag phase (#209, #213): where it lives, its decisions, and what a live dry run found that fixtures could not"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bbd69ba68a38358c
---

## the drain's flag phase (#209, #213): where it lives, its decisions, and what a live dry run found that fixtures could not

The flag phase of ADR-050 (rules 3, 5, 6) is tools/fabric/memory_flagrun.py: `assemble.py --flags [--send]` and `fabric-memory-check --flags [--project ID] [--send]`, merged in #209 (j94) and hardened in #213 (j95). Dry run is the default; `--send` sends one REQUEST per owning login, attaches memory_hint's guess, and appends one line per flag to `<agent state dir>/memory-flags.jsonl`.

Decisions it carries: an account that did not answer presence or jobs is unknown, its flags are held and listed; a REQUEST under 7 days old with no open job counts as standing (fabric-ctl lists open jobs only); no ledger lock, one runner.

**Why:** the first live dry run crashed on an account whose `jobs` list held strings: every fixture had only well-formed rows, and the fleet's answers come from other accounts.
**How to apply:** anything that reads another account's JSON (fabric-ctl rows) checks types before use and treats a malformed row as unknown (`job_objects`, the role check in `read_fleet`); a fixture for such a reader carries malformed shapes AND the shapes real data has (a control that rejects them all must fail).

*Anchors: `tools/fabric/memory_flagrun.py::read_fleet`, `tools/fabric/memory_flagrun.py::job_objects`*

*Observed 2026-10-11 (python-dev)*
