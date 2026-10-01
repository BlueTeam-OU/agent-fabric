---
role: "fabric-coordinator"
class: solution
topic: "fleet-upgrade-concurrency"
description: "fabric-ctl all upgrade claude run on 13 accounts of one host at once: 9 installs failed; one at a time every one succeeded — serialize installs per host (fabric-lease), keep the error's LAST line, exit 1 on any failure"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 6c77578f79fd718b
  - 97d8b90083da6f7f
---

## fabric-ctl all upgrade claude run on 13 accounts of one host at once: 9 installs failed; one at a time every one succeeded — serialize installs per host (fabric-lease), keep the error's LAST line, exit 1 on any failure

First real signed `fabric-ctl all upgrade claude` (2026-09-25, 2.1.281 → 2.1.282,
develop-qzapp, fleet idle): the request to "*" makes every daemon run `claude
install` at the same moment; 4 of 13 succeeded, 9 answered `claude install
2.1.282: Command failed: …` — the reason cut to execFile's FIRST line, so the
cause never showed. The same install by hand, or `fabric-ctl <login> upgrade
claude` for one login, succeeded every time (backend-dev-01 and seven more).

Also: fabric-ctl exited 0 with nine failed rows.

Fix belongs in runtime/control/upgrade.mjs: run the install under the host
lease (`bin/fabric-lease`, agent-fabric ADR-010 (docs/adr/ADR-010-hosts-provisioning-host-execution-and-resources.md)) so one account installs at a time
per host; report the error's LAST non-empty line; ctl exits 1 when any upgrade
row is failed. Until then: upgrade `all` only for a no-op check, and one login
at a time for real installs. Signing, ledger and verify all worked live.

*Observed 2026-09-25 (fabric-coordinator)*
