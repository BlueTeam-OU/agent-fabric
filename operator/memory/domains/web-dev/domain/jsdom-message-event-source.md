---
role: "web-dev"
class: domain
topic: "jsdom-message-event-source"
description: "testing postMessage source checks under jsdom — construct the MessageEvent, then defineProperty its source to the stand-in window"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 936575bd9beb8bca
---

## testing postMessage source checks under jsdom — construct the MessageEvent, then defineProperty its source to the stand-in window

jsdom has no window.open, and MessageEvent's init rejects a non-Window `source`. To test an
opener that trusts `event.source === popup`, create `new MessageEvent("message", {data, origin})`,
then `Object.defineProperty(event, "source", { value: fakePopup })`, then
`window.dispatchEvent(event)`. Used in packages/web-shared/src/auth/stepUp.test.ts (gzapp #1152).
For a static public/ script, import it with `?raw` (vite/client types): admin_web's tsconfig has
no node types, and under jsdom import.meta.url is not a file URL.

*Observed 2026-10-20 (web-dev)*
