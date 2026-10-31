---
role: "backend-dev"
class: domain
topic: "media-urls-meet-the-browser-element"
description: "Before shaping a media read, check how the client's element will load the URL: an <img>/<video> src sends no Authorization header, so a 302 from a bearer-only route never reaches it; and an HLS manifest plays natively only in Safari."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "backend-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - cf18000f163e557b
---

## Before shaping a media read, check how the client's element will load the URL: an <img>/<video> src sends no Authorization header, so a 302 from a bearer-only route never reaches it; and an HLS manifest plays natively only in Safari.

Two contract shapes for the admin creative read (#953) were ruled, built,
and then found unusable by the web client. Neither problem was in the
backend code. Both were in how a browser element fetches a URL.

1. **An element src carries no header** (01a0df45-cf6b, decided
   01a0df46-a039). The ruling was "302 to the composed provider URL".
   But admin_web authenticates every call with `Authorization: Bearer`
   and `credentials: "omit"`, and AdminApi accepts only JWT bearer. An
   `<img src>` or `<video src>` sends no header, so the request is
   refused before any redirect happens. The other routes fail too.
   `fetch()` with the header follows the redirect cross-origin, so the
   bytes come through the page and CORS decides. `redirect: "manual"`
   gives an opaque response whose Location cannot be read. The fix kept
   the rule that no bytes pass through our host: the route answers
   200 JSON `{ url, kind, expires_at? }` and the client sets the URL as
   the element's src. Rejected alternatives: a cookie scheme added for
   one read, and a credential in the query string.
2. **An HLS manifest is not a playable src everywhere** (01a0e314-41de,
   decided 01a0e31e-0903). Cloudflare Stream's composed URL is a signed
   `.m3u8`. Safari plays it in a bare `<video src>`; Chrome desktop and
   Firefox do not. The wire stayed as it was. Playback became the
   client's rendering concern: a bundled HLS engine (hls.js) where the
   browser has no native HLS. That also needs the media host in CSP
   `connect-src` beside `media-src`, and CORS on the manifest host.

**Why:** a URL on the wire is only correct if the consuming element can
load it with the credentials and codecs it actually has. A contract
test cannot see that, and neither can a backend test.

**How to apply:** when a response carries a URL for a browser to load,
ask web-dev before freezing the shape, or read
`packages/web-shared/src/api/client.ts` yourself. Questions to answer:
which element loads it; does the route need a header the element cannot
send; what format the provider serves and which browsers play it
natively; what CSP and CORS the fetch needs. Record anything unverified
(a real signed URL in three browsers) as unverified.

*Observed 2026-10-15 (backend-dev)*
