---
role: "web-dev"
class: domain
topic: "token-expiry-burst-hits-retired-map"
description: "One expired tile token = a burst of 401 error events from the outgoing map after the first one triggered renewal; a one-renewal cap reads the rest as fatal"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "web-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 90f7747d872b2597
---

## One expired tile token = a burst of 401 error events from the outgoing map after the first one triggered renewal; a one-renewal cap reads the rest as fatal

When the tile token expires on a painted map, every tile in view is refused at once. The first 401 triggers the renewal (`tile.renew()` + remount), but the rest of the burst still reaches `onError` from the same outgoing map instance before React commits the rebuild. A one-renewal cap (`authRenewalsRef < 1`) then reads each later 401 as "renewal spent", so a correctly renewing map flashed map-unavailable for about 0.4 s and focus jumped to "Try again".

Seen in Chromium on gzapp #1250 (2026-11-11), admin MapView. web-shared MapCanvas had the same shape. The fix: a `WeakSet` of map instances (`event.target`) retired at renewal; their errors are only logged. Under react-map-gl 8, `event.target` on `onError` is the map instance, the same object across the burst.

To trigger it in a harness without moving focus: revoke the token on the fake service, then press `-` on the focused canvas or resize the viewport, so MapLibre requests new tiles.

*Observed 2026-11-11 (web-dev)*
