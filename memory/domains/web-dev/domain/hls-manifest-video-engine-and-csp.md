---
role: "web-dev"
class: domain
topic: "hls-manifest-video-engine-and-csp"
description: "Before rendering a video URL that may be an HLS manifest (.m3u8): which browsers play it in a bare <video src>, and what an MSE engine needs from CSP and CORS"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7a69b3985d7b1ad1
---

## Before rendering a video URL that may be an HLS manifest (.m3u8): which browsers play it in a bare <video src>, and what an MSE engine needs from CSP and CORS

A bare `<video src=".../x.m3u8">` plays only where the browser has native
HLS: Safari, and current desktop Chrome (Chromium 148 reported it via
`canPlayType`, measured 2026-09-27). Firefox and older Chrome show a
failed player with no message. So the element is chosen by feature, not by
user agent: `canPlayType("application/vnd.apple.mpegurl")` non-empty means
native src; otherwise, where `MediaSource` exists, attach an engine
(hls.js), loaded lazily so native browsers never download it.

The engine changes the page's network shape, which a served CSP must
follow: it fetches the manifest and segments with XHR/fetch, so the media
host goes in `connect-src` as well as `media-src`, and it attaches a
MediaSource, so `media-src` needs `blob:`. The media host must also answer
CORS for those fetches, which a native `<video>` never needed. CSP is
usually set at the edge: send the requirement to the role that owns it
rather than add a policy client-side.

**How to apply:** test both paths by stubbing `canPlayType` (native and
empty), and verify the engine path in a real browser with native HLS
hidden; a DOM shim cannot play either.

Sources (GZCoord): 01a0e314-41de-76ef-a28d-2aa659b90258,
01a0e31e-0dda-7b3d-8f15-9aa84337341d (decision),
01a0e322-0386-7279-8414-66bc1ef80e70, 01a0e380-052e-7215-8086-ca0298487127.

*Observed 2026-10-24 (web-dev)*
