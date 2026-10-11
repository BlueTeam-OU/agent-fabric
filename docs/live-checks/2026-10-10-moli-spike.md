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

---

# 2026-10-11 — the second test: @playwright/mcp 0.0.83 over CDP against moli serve --layout

Run by domain-transit (report: GZCoord REPLY 01a12842-2195-7244-91fd-bb70a1e5a860, with a correction, REPLY 01a12842-b858-7c24-84d1-b0f131210bc2, in reply to 01a12826-18ae-7c44-9fd8-d247909d6726), on its own account, 2026-10-11. This is the test the first section's "Not tested" and "What it decides" were waiting for. domain-transit cannot write agent-fabric, so fabric-coordinator committed the report here.

## How it was driven

Three runs per browser; a fresh browser and a fresh MCP server for each run; everything stopped after, and no process left running. A stdio JSON-RPC client spawned the server exactly as the harness does (project `.mcp.json`: `npx -y @playwright/mcp@0.0.83`) and called the tools a session calls. No model was in the loop, so the runs are repeatable. Not done: a model-driven session with the server configured in the harness.

## Versions

- moli v1.1.15, x86_64-unknown-linux-gnu archive, sha256 `f7c9455451bffd4d3a6353431b3596c1d18ad4d9fe6725d8d4033f6fff5fa59d` (re-downloaded and checked against the pin).
- @playwright/mcp 0.0.83, playwright-core 1.64.0-alpha-1790635538000.
- Google Chrome 148.0.7778.167 (the control), Node 22.22.2.

## Exact arguments

- moli: `moli serve --layout --host 127.0.0.1 --port 9222`
- Chrome: `google-chrome --headless=new --remote-debugging-address=127.0.0.1 --remote-debugging-port=9223 --user-data-dir=<fresh temp dir> --no-first-run`
- MCP: `npx -y @playwright/mcp@0.0.83 --cdp-endpoint http://127.0.0.1:9222` (9223 for the Chrome control); no other flags.

## Results, runs 1-3 (pass counts are per run)

| | Chrome over CDP | moli --layout over CDP |
|---|---|---|
| 11 flows | 11/11 x3 | 11/11 x3 |
| navigate + read, 3 pages | 3/3 x3 | 3/3 x3 |
| 24 tools, local test page | 24/24 x3 | 22/24 x3 |
| browser peak PSS | 761-807 MB | 171-183 MB |
| browser idle PSS | 295-318 MB | 9.4-10.0 MB |
| MCP server peak PSS | 201-211 MB | 181-189 MB |
| wall time per run | 93-113 s | 233-238 s |

MB means kB/1000, read from `/proc/<pid>/smaps_rollup` over each process tree every 200 ms. The run is longer than the first spike's (tool sweep, three tabs, three reads), so Chrome's peak is higher than the 502-538 MB reported then. The MCP server, about 190 MB, is now as large as the moli browser. Per session: about 370 MB with moli against about 990 MB with Chrome.

## Tools that fail or behave differently on moli

1. `browser_fill_form` fails 3/3, at the checkbox field. Its textbox and combobox fields work. A plain `browser_click` on the same checkbox fails the same way: a 5000 ms timeout, "waiting for element to be visible, enabled and stable". Its box is 13x13, and buttons on the same page click fine. Cause not determined.
2. `browser_drag` fails 3/3, same timeout. The press on the source succeeds; the timeout comes moving to the drop target, whose box is 122x42. `browser_drop` (synthetic data transfer) passes.
3. `browser_type` with `submit:true` on Wikipedia's Special:Search: Chrome stays on the search results ("Rioni river - Search results"), moli lands on the article ("Rioni - Wikipedia"). Both pass the flow; the form is submitted differently.
4. Slower: the en.wikipedia article takes about 40 s against 15 s, the ka.wikipedia read about 43 s against 8 s. The whole run takes 2.1-2.5x as long.
5. `browser_snapshot` contains extra elements: moli-only words were 21% of matsne.gov.ge/ka (hidden header and search controls Chrome's snapshot omits) and 2% of ka.wikipedia. Recall of Chrome's snapshot words: gzapi.ge 1.000, ka.wikipedia 0.984-0.993, matsne 1.000.
6. Screenshots are larger (gzapi.ge 142 KB against 49 KB PNG); the content is not compared.
7. Unexplained, not reproduced: a trial run before runs 1-3, with a script whose error capture was truncated, failed three flows (two navigates, a screenshot) and 12 tools after `browser_file_upload`. Runs 1-3 did not repeat it. Treat it as possible instability until a longer soak says otherwise.

All other tools behave as on Chrome: navigate, navigate_back, snapshot (with boxes), find, type, select_option, hover, press_key, click + handle_dialog, drop, file_upload, console_messages, network_requests, network_request, evaluate, take_screenshot, emulate_media, resize, wait_for, tabs and close. Not tested: `browser_run_code_unsafe`, which the harness does not expose to sessions.

## Correction: radio buttons

The report's recommendation said to keep Chrome for "checkboxes and radio buttons". Only the checkbox was measured; a radio button was not on the test page, so its failure is an inference. Read it as "checkboxes (radio buttons untested)".

## Recommendation

moli + @playwright/mcp can serve scripted browsing for navigating, reading, clicking links and buttons, typing, select boxes, dialogs, uploads, tabs and screenshots. Keep Chrome for checkboxes (radio buttons untested) through fill_form or click, for drag-and-drop, and for everything the first report excluded: WebGL rendering, video playback, logins, bot-checked sites, Flutter web, and visual judgement. Each login needs its own port: moli's default 9222 on 127.0.0.1 is reachable by every account on the host.

## What it decides

The gate in ADR-051 §2 is met (amendment 2026-10-11). The first section's "Not tested" item on @playwright/mcp is closed by this test; the rest of that list stands.
