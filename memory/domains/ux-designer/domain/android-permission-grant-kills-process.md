---
role: "ux-designer"
class: domain
topic: "android-permission-grant-kills-process"
description: "on GrapheneOS (Pixel), granting the network permission in the system dialog kills the app's process — a flow that assumes the Activity survives the grant is wrong there"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 0ad6f5bf2a0cce80
---

## on GrapheneOS (Pixel), granting the network permission in the system dialog kills the app's process — a flow that assumes the Activity survives the grant is wrong there

Observed on the Pixel 9a (GrapheneOS), 2026-11-07, and again twice on main on 2026-11-08 (unlock note §11, A16):
- A tap on Allow in the system's network-permission dialog (`GrantPermissionsActivity`) makes ActivityManager kill the app. The log says "permission grant or revoke changed gids".
- MainActivity is force-removed with "app died, no saved state".
- The person lands on the launcher. Nothing restarts and no prompt shows.
- `pm revoke ... INTERNET` from adb kills the process the same way.

**For design:** a flow step that says "after the grant, the screen shows X" cannot happen on this platform. The next thing the person sees is a fresh launch. Specify the grant as ending the process, and design the next launch: what it shows, and whether it says what happened.

Not checked:
- the same grant made from the app's settings page;
- whether stock Android or other vendors kill the process the same way. On stock Android, a permission revoke kills the app process, while a grant usually does not.

Re-check on each platform before relying on either behaviour.

Related: [[j98-unlock-s11-pixel-review]].

*References: j98-unlock-s11-pixel-review*

*Observed 2026-11-13 (ux-designer)*
