---
role: "python-dev"
class: solution
topic: "j173-client-program-merged-386"
description: "#386 merged - interweave-install installs the client program (current too), read has client.status; arm needed the coordinator's --authorization, classifier refused my own arm"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c7543545af8e7d13
---

## #386 merged - interweave-install installs the client program (current too), read has client.status; arm needed the coordinator's --authorization, classifier refused my own arm

#386 (2 work, 3 fix) made `interweave-install` end with install_client.install for "installed" and "current" (reply `client`: installed|already|failed) and the `interweave` read carry `client.status` ok|absent|differs|unreadable (carrier_install.py `_with_client`, `client_state`). Only a missing path is absent; lstat+open errors are unreadable (lexists/same() fold every OSError).

**Why:** the pinned-release "current" short-circuit meant accounts upgraded earlier never got the program; the coordinator amended ADR-029 rows on my branch (commits onto it).
**How to apply:** an arm under 8 work commits was refused by the auto-mode classifier ("Merge Without Review") even with the coordinator's AUTHORIZES; the owner/coordinator armed it. Do not retry; report and wait. Review rounds: a re-review request must omit previous_findings (read from the last posted review); post-review each round on the head it read. Hook guard refuses commands containing $HOME-like words with commits/publishes: keep `env -i HOME=...` out of commands that also run fabric-pr. See [[arming-minimum-1-and-boundary-authorization]].

*References: arming-minimum-1-and-boundary-authorization*

*Observed 2026-10-26 (python-dev)*
