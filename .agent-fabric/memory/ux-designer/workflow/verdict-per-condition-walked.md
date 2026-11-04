---
role: "ux-designer"
class: workflow
topic: "verdict-per-condition-walked"
description: "A device-review verdict passes only the conditions actually walked (screen x font scale x theme x state); anything unwalked is 'partly met' with the condition named, and a walk that needs a wipe, a revoked permission or the owner's unlock…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 404c51a184ac1c53
---

## A device-review verdict passes only the conditions actually walked (screen x font scale x theme x state); anything unwalked is 'partly met' with the condition named, and a walk that needs a wipe, a revoked permission or the owner's unlock is carried by name, not done

An acceptance item often spans several screens and settings (F4: Trust
and Details, at 200 % font, in light theme). Passing it because one
screen passed in one setting overstates the build; a review caught F4
recorded "pass" when Trust at 200 % light had never been walked, and a
closing sentence read as "built and re-reviewed" over a clause carried.
- Write each verdict against the conditions walked, with the build
  (commit, APK sha) and round; the rest is "partly met: <condition>
  unwalked".
- A condition whose walk would wipe the app's data, revoke a permission
  (ending the process) or need the owner's unlock on the owner's phone
  is not walked without their word: ask the requesting role to rule,
  and carry it by name to the release gate or a test device.
- A closing summary quotes carried clauses in full, never folds them
  into "all passed".
**Why:** InterWeave Stage 17 close (#361, #372, 2026-10-22).
**How to apply:** keep a close table of finding x condition; before any
"pass", tick each condition against a round that walked it.
Related: [[scripted-input-on-shared-phone]]

*References: scripted-input-on-shared-phone*

*Observed 2026-10-25 (ux-designer)*
