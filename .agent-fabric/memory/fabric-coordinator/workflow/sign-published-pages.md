---
role: "fabric-coordinator"
class: workflow
topic: "sign-published-pages"
description: "Every page published for the owner carries a signature footer — the agent's host/login, the role held, the date, the revisions it rests on, who was consulted; the owner also likes reports as browser pages"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 73f92d5acc1a834d
---

## Every page published for the owner carries a signature footer — the agent's host/login, the role held, the date, the revisions it rests on, who was consulted; the owner also likes reports as browser pages

The owner, 2026-09-26, after the Pulse research report and proposals were
published as artifacts: "thank for showing it to me in the browser, very
handy" and "one improvement: the signature of the agent that produce the
artifact".

**Why:** a page travels without the conversation that made it; the reader
needs to know which agent (the login, never the directory or session) and
which role produced it, and on what revisions, to judge and to follow up.

**How to apply:** every published page ends with a footer: "Prepared by
<host>/<login>, holding <role>" (from `fabric-whoami --json`), the date, the
revisions (shas) it was built on, and the agents consulted with relay seqs.
For a report the owner will read or act on, prefer a published page over a
long terminal answer. Not yet a fleet rule: ask before putting it in team
guidance (the prompt-template budget is tight).

*Observed 2026-09-26 (fabric-coordinator)*
