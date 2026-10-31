---
role: "fabric-coordinator"
class: rationale
topic: "fabric-ctl-assist-owner-terminal"
description: "Owner 2026-10-22: fabric-ctl gets completion of the first parameter, help per subcommand, and `assist \"<question>\"` on the claude-pzhuy API key — owner's interactive terminal only, grounded on fabric docs"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6d59a1abe2a4cbee
---

## Owner 2026-10-22: fabric-ctl gets completion of the first parameter, help per subcommand, and `assist "<question>"` on the claude-pzhuy API key — owner's interactive terminal only, grounded on fabric docs

Owner, 2026-10-22, asked for three fabric-ctl changes: (1) shell completion of at least the
first parameter (logins, `all`, then the verb); (2) `--help` for each subcommand, where
today `fabric-ctl <login> jobs --help` reprints the whole usage; (3) `fabric-ctl assist
"<question>"` (example: "how can I switch to the claude-pzhuy account?") answered with
the API key kept as `CLAUDE_APIKEY_<SLUG>` for the claude-pzhuy account.

Owner's decisions, the same day: assist runs **only from the owner's interactive terminal**,
and no agent session ever spends the key (this keeps [[api-key-credit-coordinator-only]] and
narrows it further). Each question is sent along with fabric docs as context (fabric-ctl usage,
`fabric-adr lookup` entries, skills), so answers name real commands. The key's promotional
credit expires 2026-10-23; the owner's $20 top-up is what lets requests through.

Owner, later the same day: **defer assist until per-subcommand `--help` has landed**; agents
do not get it (they read the tree themselves). Its main use is when the fabric is stopped —
the fleet's accounts out of credit or another blocker — so assist must work with the fleet
down: no relay, no control agent, no subscription token, only committed files and the key.

**How to apply:** (1)-(2) are python-dev's entry (bin/, tools/); (3) needs a decision record
(a new spend path for an API key) and a refusal test for a non-tty / agent session.
**State 2026-10-22:** per-verb help and completion landed (#355, merged a59d6fd9). ADR-063 (Proposed) is the
record for assist, in #356 (three review rounds, last Finding: none). Next, after the owner accepts ADR-063:
a REQUEST to python-dev with §5 as acceptance (rule-2 refusal tests first, new_agent.py refusing the login
`assist`), and the hosts-schema change of rule 9 by me in the same PR.
Related: [[owner-commands-one-line]].

*References: api-key-credit-coordinator-only, owner-commands-one-line*

*Observed 2026-10-22 (fabric-coordinator)*
