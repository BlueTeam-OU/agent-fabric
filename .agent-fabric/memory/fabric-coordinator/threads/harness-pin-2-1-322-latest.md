---
role: "fabric-coordinator"
class: threads
topic: "harness-pin-2-1-322-latest"
description: "owner 2026-11-10: Claude Code pin 2.1.311 -> 2.1.322 (npm latest, not stable); the pin PR also brings architect-cto-01 back to Fable 5.2 (j749)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1a51c6ff80094e08
---

## owner 2026-11-10: Claude Code pin 2.1.311 -> 2.1.322 (npm latest, not stable); the pin PR also brings architect-cto-01 back to Fable 5.2 (j749)

The owner decided on 2026-11-10 to move the fleet's Claude Code pin (`runtime/claude-code/harness.json`) from 2.1.311 to npm `latest`. That day `latest` was 2.1.322 and `stable` was still 2.1.311. The owner first said 2.1.321, the first build that knows `claude-fable-5-2`, then chose 2.1.322 when asked. This departs from the 2026-11-03 rule of "npm stable" (ADR-043 amendment). Say that in the amendment.

Why move: 2.1.311 does not know Fable 5.2, and 2.1.316+ makes background-subagent progress summaries about 99% cheaper (ClaudeDevs, 2026-11-04). 2.1.316 also adds `CLAUDE_CODE_SUBAGENT_EFFORT`, which needs the same launcher fence as `CLAUDE_CODE_EFFORT_LEVEL` (ADR-006).

How to apply (job j749; its title still says 2.1.321):
- Read back the claims in docs/live-checks/2026-11-03-claude-code-2-1-311-readback.md on 2.1.322, and recapture harness/en.md.
- Amend ADR-043 and move the pin.
- In the same PR, as its own ADR-005 amendment, restore the Fable 5.2 agent layer for architect-cto-01. #548 (j748) removed it, and the owner wants it back with the pin.
- After the merge: `sudo fabric-managed install --sha <main>` (by the owner), then `upgrade fabric`, then `upgrade claude`.

j748 itself landed as BlueTeam-OU/agent-fabric#548, armed 2026-11-10 at minimum 1.

Owed when #548 merges (j748 is delivered, not done): `fabric-ctl all upgrade fabric`; relaunch architect-cto-01 and read its `fabric-status` session line, which should be claude-opus-5-5 (the review's risk: a local model-profile could still pin Fable); then `fabric-jobs done j748 BlueTeam-OU/agent-fabric#548`. After that, open j750 (moli 1.1.23 for devex-tooling, REQUEST 01a1c620; the REPLY promised a REPLY naming the PR and the moli-web empty-dump line). Doing j749 and j750 in one PR is fine.

Read-back trial without restarting the session: install 2.1.322 into the scratchpad (`npm install --prefix`) and run `claude -p` children on that binary. The 11-03 trial instead upgraded the account itself, which SIGTERMs and resumes the session.

Progress 2026-11-10 ~17:45Z (session 9b4e5145): j748 closed (fleet upgraded to b8716d09; architect-cto-01 read `[2.1.311 · Opus 5.5 · medium]`). On j749's branch: a0dc8c62 the live check docs/live-checks/2026-11-10-claude-code-2-1-322-readback.md (every claim holds; F1: 2.1.322 knows fable-5-2), 26edb413 the pin + ADR-043 A 11-10, b42b65b4 ADR-006 A 11-10 + model_pins.py names CLAUDE_CODE_SUBAGENT_EFFORT, 268c4d2a the architect layer back + ADR-005 A 11-10. The launcher refusal is python-dev-01's j225 (REQUEST 01a1c63c): ADR-006 rule 6 says the launcher refuses it, so the PR does not merge before j225 does. en.md recapture waits until this account runs 2.1.322. After the merge: owner `sudo ~/projects/agent-fabric/bin/fabric-managed install --sha <main>`, `upgrade fabric`, `upgrade claude` (architect-cto-01 must get both in one pass, or it launches Fable 5.2 on 2.1.311).

Landed 2026-11-10: BlueTeam-OU/agent-fabric#549 merged as 80e612ff (5 work, 3 fix; three blind-review rounds; armed on the owner's word under minimum 8, with j225 to land after, the owner's choice). Review rounds found: the new-agent install path had no managed gate (fixed in tools/fabric/provisioning: claude_install_refusal, asked only where a build would install). The owner ran the reinstall at 80e612ff; fabric upgraded on all 30, managed in force on all 30; trial claude upgrade on legal-expert-ch took 2.1.322 from the native installer and resumed. Then `fabric-ctl all upgrade claude` (skips user). Still owed: upgrade this account (restarts the session), en.md recapture from a 2.1.322 session, architect-cto-01's status line reading Fable 5.2, then `fabric-jobs done j749 BlueTeam-OU/agent-fabric#549`. python-dev-01 has j225/j226.

2026-11-10 ~19:45Z: 29 of 30 accounts on 2.1.322 (9 failed the first all-run on the claude-install lease after 900 s, re-run serially, all upgraded). architect-cto-01 reads [2.1.322 · Fable 5.2 · medium]. Last: `fabric-ctl user upgrade claude` (stops this session; the launcher resumes it on 2.1.322). Next in the resumed session: confirm `fabric-status` claude 2.1.322; recapture runtime/claude-code/harness/en.md from this session (method: docs/live-checks/2026-11-07-claude-code-harness-prompt.md, scripted one-occurrence replacements, model in the header) as a new PR; then `fabric-jobs done j749 BlueTeam-OU/agent-fabric#549`, start+done j753 (reply 01a1c6eb), next j755 (fold legal-expert-ee-eu j20 branch at 8506690d) — both en.md and j755 can ride one PR.

*Observed 2026-11-10 (fabric-coordinator)*
