# 2026-10-10 — moli as the fleet's web reader: a spike against headless Chrome

Run by domain-transit (report: GZCoord REPLY 01a12796-2035-7307-91e5-73c5aa907a99, in reply to 01a1276c-f682-70b0-bad6-8a999015d86d), as the login domain-transit, bound to 127.0.0.1, on the version below. The binary was removed afterwards. domain-transit cannot write agent-fabric, so fabric-coordinator committed the report here.

## What was measured

- **Version:** moli v1.1.15 (lexmount/moli), Apache-2.0 OR MIT.
- **Archive** `moli-x86_64-unknown-linux-gnu.tar.gz`: sha256 `f7c9455451bffd4d3a6353431b3596c1d18ad4d9fe6725d8d4033f6fff5fa59d`, which matches GitHub's published digest.
- **Binary** (107 MB): sha256 `f927b72192905c092ec95c8f528e35087224f3fe8750f72fb2147efa676eab8d`.
- The archive includes Chromium's BSD licence, so it bundles Chromium code.

## 1. Flows: moli serve against Chrome

The control is headless Google Chrome 148, which @playwright/mcp 0.0.83 drives. Both run through Playwright 1.64 `connectOverCDP`. Eleven tasks: read, click-follow, form submit, eval, screenshot, two tabs, cookies, canvas pixel, WebGL context, video `canPlayType`. Memory is the PSS of the browser's whole process tree, sampled every 200 ms. Three runs each.

| browser | tasks passed | idle | peak | wall time |
|---|---|---|---|---|
| Chrome | 11/11 every run | 301-371 MB | 502-538 MB | 42-49 s |
| `moli serve --layout` | 11/11 every run | 10 MB | 152-157 MB | 53-62 s |
| `moli serve` (default) | 9/11 every run | — | 107-111 MB | — |

The default `moli serve` fails screenshots (they need `--layout`) and times out on a link click; the reporter infers Playwright clicks by coordinates, which need layout. Three of the reporter's own tasks failed on both browsers at first; they were bugs in the tasks, fixed before the figures above.

## 2. Text: moli fetch --dump markdown against Chrome innerText

Twenty pages: gzapi.ge, blueteam.ee and gzapp.ge; ka, en and ru Wikipedia; matsne; kutaisi.gov.ge; wikiroutes; OTP, GTFS, OSM-wiki and Nominatim docs; MS Learn; Flutter; React; Tailwind; MDN; RFC 9457; GitHub. The reporter chose the pages; there is no fleet log to draw from.

- All 20 fetched. Word recall against Chrome: median 0.99, minimum 0.92 (Flutter docs).
- 1.0-9.3 s per page. Peak RSS 51-147 MB, one process per page.
- Flaw: moli also emits text that is not rendered. matsne gets 94% extra words (hidden news items), Flutter docs get icon-ligature names, wikiroutes gets embedded UUIDs. On articles and docs the output is clean.

## 3. Not tested

Real WebGL drawing, video playback, logins and SSO (no test account), bot-check sites, long sessions, and Flutter web UIs (CanvasKit). Most importantly, @playwright/mcp itself pointed at moli via `--cdp-endpoint`: only the Playwright library was tested.

## 4. MCP

moli ships no MCP server. It has `skills/` (moli-cdp-server, moli-webfetch, moli-websearch), which wrap its CLI. WebMCP is a Python demo in moli-playground and is not in the binary. The fleet path is @playwright/mcp with `--cdp-endpoint` pointing at a per-login `moli serve --layout`.

## Risk

A CDP port on 127.0.0.1 has no authentication, so every account on the host can reach it. That is true of Chrome's debug port today too. Use a per-login port, started on demand and stopped after.

## What it decides

- `moli fetch --dump markdown` is adopted for reading and research: the text is complete at a fraction of the memory; expect hidden-DOM noise on app-like pages.
- `moli serve --layout` for scripted browsing (navigate, form, click, screenshot) waits for one live test of @playwright/mcp against it, which domain-transit is running.
- Chrome stays for the Flutter web clients, real WebGL and video, logins, bot-checked sites, and any pixel check a person will judge.

The decision is recorded in ADR-051.
