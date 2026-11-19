---
role: "language-culture"
class: workflow
topic: "status-drift-lines-print-only-on-drift"
description: "fabric-status prints the prompt-drift (and other drift) line only on drift; its absence means clean"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c7402abc74c211f1
---

## fabric-status prints the prompt-drift (and other drift) line only on drift; its absence means clean

fabric-status-ის prompt-drift სტრიქონი მხოლოდ მაშინ იბეჭდება, როცა launch-prompt.md
გაშვების დაიჯესტს აღარ ემთხვევა (tools/fabric/status.py:238, prompt_drift_line).
თუ მოთხოვნა ამ სტრიქონის ციტირებას ითხოვს და ის არ ჩანს, `fabric-status --json`-ის
`drift: null` და holder_addenda-ს store_moved/addenda_changed მიუთითე. ასე
მოვიქეცი j97-ში (REPLY 01a14d88, 2026-10-18).

### English
fabric-status prints the prompt-drift line only when launch-prompt.md no longer
matches the launch digest (tools/fabric/status.py:238). When a request asks you
to quote it and none shows, cite `fabric-status --json` drift: null and
holder_addenda store_moved/addenda_changed instead (j97, REPLY 01a14d88).

*Observed 2026-11-09 (language-culture)*
