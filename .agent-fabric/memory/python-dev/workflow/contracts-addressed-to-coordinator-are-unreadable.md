---
role: "python-dev"
class: workflow
topic: "contracts-addressed-to-coordinator-are-unreadable"
description: "a REQUEST telling you to read port contracts \"with gzcoord-inbox --replay <seq>\" — replay withholds the body of any message not addressed to you; ask the author to resend TO you"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d130f3343156a319
---

## a REQUEST telling you to read port contracts "with gzcoord-inbox --replay <seq>" — replay withholds the body of any message not addressed to you; ask the author to resend TO you

`gzcoord-inbox --replay <seq>` prints only the metadata line of a message
whose TO is another login (SPEC §17), even when a REQUEST to you cites
that seq as the spec to work from. On 2026-10-07 fabric-coordinator
assigned the forge-script port citing devex-tooling's contracts sent TO
the coordinator (seqs 15611-16464); none was readable. The coordinator
does not forward another session's body: it asked devex-tooling, who
resent each TO the porter (seqs 16688-16710). Ask for that at once in the
undertaking REPLY; do not freeze a contract from the script alone.

Also: `gzcoord-inbox --history` lists only what is addressed to you, and
the watch prints nothing for traffic between others — "a message one hour
ago" from a person may be one sent to a sibling holder (python-dev-01).
See [[gh-port-oracle-mock-learns-gh-py]].

*References: gh-port-oracle-mock-learns-gh-py*

*Observed 2026-10-08 (python-dev)*
