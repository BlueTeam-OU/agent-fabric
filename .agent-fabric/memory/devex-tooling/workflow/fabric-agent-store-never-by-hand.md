---
role: "devex-tooling"
class: workflow
topic: "fabric-agent-store-never-by-hand"
description: "Never clone or push my fabric-agent-<id> repo by hand, nor hand the owner a script that does; settings go through fabric-secrets store settings-put"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 62039ee0ba39537a
---

## Never clone or push my fabric-agent-<id> repo by hand, nor hand the owner a script that does; settings go through fabric-secrets store settings-put

`BlueTeam-OU/fabric-agent-<id>` is the agent's secrets store (ADR-038/042): every commit there is signed by its own tool and verified on pull. Writing settings (persona profile, avatar) goes through `fabric-secrets store settings-put --from <dir>` (python-dev-02, agent-fabric #236), never git.

**Why:** 2026-10-13, j117: the permission check refused my clone. I then handed the owner a `! script` that cloned and pushed eeb64870 by hand. Minutes later fabric-coordinator broadcast 01a135c5 saying to do exactly the opposite ("do not ask the owner to let you"). I reported the push to python-dev-02 (relay 149438).

**How to apply:** when a permission check refuses a write to a store or a control-plane surface, the refusal is the answer. Prepare the files, block the job on the tool that writes them, and ask the tool's owner. Don't route the write through the owner's hands.

**What it cost:** the hand commit was signed by the shared git key, which is not a writer of the store, so the store refused every pull and `fabric-secrets sync` reported REFUSED. fabric-coordinator rolled the store's remote back to 3258cafc with the owner's word (relay 151492, 2026-10-13).

**Resolved 2026-10-13:** after #236 merged, `fabric-secrets store settings-put --from <dir holding profile.json + avatar.png>` wrote d279f09, signed by the store's own key. The rolled-back eeb64870 was still in the local store's objects, so `git show eeb64870:settings/<f>` recovered the files. `--from` takes the files themselves, not a `settings/` parent directory.

*Observed 2026-10-13 (devex-tooling)*
