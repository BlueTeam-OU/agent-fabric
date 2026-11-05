---
role: "fabric-coordinator"
class: threads
topic: "j510-session-seal-managed"
description: "j510 2026-11-03: ADR-038 r9 seal split into session-seal.py, managed SessionStart via hook_entry; workspace copy never stands down (managed CLAUDE_ENV_FILE unmeasured)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b1531ca42ab788b1
---

## j510 2026-11-03: ADR-038 r9 seal split into session-seal.py, managed SessionStart via hook_entry; workspace copy never stands down (managed CLAUDE_ENV_FILE unmeasured)

j510 (branch develop-qzapp/user/feat/j510-adr-038-r9-seal-as-a). The ADR-038 rule 9 shell seal moves out of
runtime/claude-code/hooks/session-start.py into runtime/claude-code/hooks/session-seal.py. It runs as a managed
`SessionStart` hook ("session-seal" in hook_entry.py GUARDS, event None, exec'd like plan-hold) and also as an
UNGATED workspace entry.

**Why ungated:** the 2.1.316 read-back (docs/live-checks/2026-10-31-managed-settings-2-1-316.md) exercised
PreToolUse hooks only. Whether a managed SessionStart hook gets CLAUDE_ENV_FILE is unmeasured. The seal writes once
per file, so two copies cost nothing, and a stand-down could leave it running nowhere.

**LANDED 2026-11-03:** #464 merged 5581daa2 on the owner's "arm 464" (5 work, 4 fix, 4 review rounds), distributed 30/30. The live check passed on 2.1.286 and 2.1.316: a managed SessionStart hook gets its own CLAUDE_ENV_FILE, its unset reaches Bash, and a login's disableAllHooks does not stop it. The record is docs/live-checks/2026-11-03-managed-sessionstart-env-file.md, and the probe scripts are in scratchpad rb/. The final shape: the workspace copy is session-start.py calling session-seal.py by path, not a settings entry ([[new-settings-entry-needs-bootstrap]]). The host's /etc file is from 1b90ade8 and names no session-seal, so it reads managed DRIFTED until the owner reinstalls. The owner reinstalled at 5581daa2 the same day, and check reads in force. Read-back: `claude -p` from /tmp, where no workspace settings apply, wrote one env file, sessionstart-hook-0.sh, holding the seal, and Bash saw no GH_TOKEN. So the real installed hook_entry seal works. Not yet in a live-checks record. Follow-up: j572 (local_settings.py drift).

**How to apply (historical):** the ADR amendments are commit 3a5b68a7 (ADR-038 r9 bullet, ADR-043 r2 list + r9 sentence). The
code went to a code-high worker. A live read-back of managed SessionStart + CLAUDE_ENV_FILE needs root, through
`sudo unshare -m` as in j509. That is the owner's to approve again. Until it is done, the workspace copy is the one
known to run. Related: [[adr-043-managed-settings-option-1]].

*References: adr-043-managed-settings-option-1, new-settings-entry-needs-bootstrap*

*Observed 2026-11-03 (fabric-coordinator)*
