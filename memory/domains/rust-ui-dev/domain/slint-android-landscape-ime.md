---
role: "rust-ui-dev"
class: domain
topic: "slint-android-landscape-ime"
description: "Slint's Android backend switches off the full-screen landscape editor, so the app owns keyboard-up layout in landscape -- panes step aside by a height formula and the list stays anchored at its newest item"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1f79903041415ae3
---

## Slint's Android backend switches off the full-screen landscape editor, so the app owns keyboard-up layout in landscape -- panes step aside by a height formula and the list stays anchored at its newest item

i-slint-backend-android-activity 1.18.1 sets `IME_FLAG_NO_EXTRACT_UI` in its input
connection (java/SlintAndroidJavaHelper.java), whatever the app asks, so Android's own
landscape answer (the full-screen extract editor) never appears. On a phone in landscape
(~411 dp tall) the keyboard leaves a strip; an app bar, a notice and a composer then leave the
content nothing and push the composer under the keyboard. Patching the backend is a vendoring
decision (ADR, licence), not a client fix.

What worked, as the UX role specified it (H = height above the keyboard, C composer, B app
bar, N notice, M a minimum for the content, 120 dp):
1. a two-pane window drops the list pane when the detail would leave less than M;
2. if H - C - B - N < M the notice steps aside, then if H - C - B < M the app bar;
3. the composer is never under the keyboard, and Back with the keyboard up closes it first;
4. everything returns at once when the keyboard closes;
5. the content list stays anchored at its newest item whatever space it keeps.

Step 5 failed on the device twice for reasons a host test missed until it used the phone's
own figures: a list re-created when a pane steps aside starts at its top (re-anchor on
re-creation and follow the list's position, not scroll events); and an empty, always-present
line under the list kept 25 px of a 53 px strip (see [[empty-line-takes-no-room]] in the
project memory). Write the host test at the device's measured dp (e.g. 923x411, keyboard 270)
and assert the newest item's end is above the composer.

*References: empty-line-takes-no-room*

*Observed 2026-10-24 (rust-ui-dev)*
