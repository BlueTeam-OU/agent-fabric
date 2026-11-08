---
role: "python-dev"
class: workflow
topic: "j199-audit-f09-f12-merged-452"
description: "j199 audit F09-F12 merged in #452 on the owner's word; seams a reviewer found in a sh boot script and a raised-vs-sentinel ledger floor"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fddf87fb0f30e43c
---

## j199 audit F09-F12 merged in #452 on the owner's word; seams a reviewer found in a sh boot script and a raised-vs-sentinel ledger floor

#452 (2026-11-01) merged at 4 work commits under the security-boundary minimum 8, on the owner's word ("authorized to arm 452"); basis must carry the phrase "the owner's word".

Traps the blind review found in my first head:
- A sentinel (`floor()` -> inf) makes accept() say "a replay"; raise instead and let accept() turn the OSError into a refusal naming the file. Check which message the *caller* shows, not the one the helper builds.
- `while read ... done < file` in sh skips an unterminated last line; use `|| [ -n "$var" ]` as the main loop does. Test with a snapshot stripped of its final newline.
- A symlink-replaced-file test must point at an identical executable copy, else the content differs and the reinstall happens for the wrong reason (lstat/S_ISREG mutants survive).
- No `eval` with names from a snapshot in root shell code; awk `-v n=` for exact name matches.

**How to apply:** for a fix-class change, run the mutation matrix on committed state (script with .orig copies), and verify each mutation text is actually found (two of mine were mis-targeted and "survived" meaninglessly). Post-review and `fabric-review save` need a verbatim file; `fabric-pr post-review` takes no variables, literal path only. Re-review brief can be handed to the reviewer as a file path to Read.

*Anchors: `tools/fabric/control/agentd.py::ActionLedger`, `runtime/provisioning/platform/qubes/agent-fabric-accounts.rc::range_clash`*

*Observed 2026-11-01 (python-dev)*
