---
name: webapp-testing
description: Drive a running browser sub-app of the project you are in with Playwright to verify frontend behaviour a type-check and Vitest run cannot — rendered state, real interaction, console errors, screenshots. Use when a change needs seeing in a browser before it is called done, or when debugging UI behaviour that only appears against a live server.
license: Apache-2.0. Complete terms in LICENSE.txt.
---

# Web Application Testing

> **Vendored and modified.** Upstream is the `webapp-testing` skill from
> `anthropics/skills` (Apache-2.0; `LICENSE.txt` alongside this file is
> upstream's). Changes made for this repo, per Apache-2.0 §4(b):
> `scripts/with_server.py` is **not** vendored and its server-lifecycle
> guidance is replaced by the Makefile rules below, because this repo owns
> server lifecycle and port allocation itself. The three `examples/` are
> upstream's with two substitutions each: `localhost:5173` → the port the
> project's port table gives this clone, and `/mnt/user-data/outputs/` → `/tmp/
> webapp-testing/` (which does not exist on these hosts), plus the
> `os.makedirs` that path needs. The reconnaissance patterns and the
> `networkidle` rule are upstream's, unchanged. Upstream ships no `NOTICE`
> file, so §4(d) does not apply.

## In a managed project, read this first

**Never let a script start a server.** The project's own tooling owns
server lifecycle — one target per app, named in your remit for that
project (`.agent-fabric/roles/web-dev.md`), with a target that brings
the APIs up and one that stops everything. Never a second instance of a
server already listening: host memory is constrained and clones run in
parallel. Upstream's `with_server.py` exists to spawn servers, which is
why it is not vendored. An app with no target is a gap to fix in the
project's tooling, not a reason to hand-roll the dev server.

**Never hardcode a port.** Every local port is a base plus this clone's
offset — a per-login value the project declares under `agent_env` in
`projects/registry.json` and `fabric-secrets sync` exports — so the
upstream `5173` is wrong in every clone and silently wrong in most. Read
the port first, from the command the remit names as authoritative for
THIS clone (a port table target), never from a file you remember.

**Prefer the Playwright MCP server for interactive work.** `.mcp.json`
registers `playwright`, and its `browser_*` tools need no Python, no
dependency install, and no script file. Reach for the Python scripting in
this skill when you want a **repeatable, checked-in** flow — a multi-step
regression you will run again — rather than a one-off look. Whichever route
you take, CLAUDE.md's hygiene rule applies: close the browser after each
non-contiguous block of checks, do not hold it open across implementation
stretches.

**Python Playwright is not installed.** The examples here need it, and this
account does not have it:

```bash
pip install --user playwright && python3 -m playwright install chromium
```

That is a per-account install of a few hundred MB. If you only need a look
at the page, the MCP route above costs nothing — check which you actually
need before installing.

## Decision Tree: Choosing Your Approach

```
Task → Is it static HTML?
    ├─ Yes → Read the HTML file directly to identify selectors
    │         ├─ Success → Write a Playwright script using those selectors
    │         └─ Fails/Incomplete → Treat as dynamic (below)
    │
    └─ No (dynamic webapp) → Is the server already running?
        ├─ No → Start it with the Makefile target for that app, then
        │        the project's port table for its port. Do NOT script the startup.
        │
        └─ Yes → Reconnaissance-then-action:
            1. Navigate and wait for networkidle
            2. Take a screenshot or inspect the DOM
            3. Identify selectors from the rendered state
            4. Execute actions with the discovered selectors
```

## Writing an automation script

Servers are already running and are not this script's business:

```python
import os
from playwright.sync_api import sync_playwright

PORT = int(os.environ["APP_PORT"])  # from the project's port table — never assume, never hardcode across clones

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)  # always headless
    page = browser.new_page()
    page.goto(f'http://localhost:{PORT}')
    page.wait_for_load_state('networkidle')  # CRITICAL: wait for JS to execute
    # ... your automation logic
    browser.close()
```

## Reconnaissance-Then-Action Pattern

1. **Inspect the rendered DOM**:
   ```python
   page.screenshot(path='/tmp/inspect.png', full_page=True)
   content = page.content()
   page.locator('button').all()
   ```

2. **Identify selectors** from the inspection results

3. **Execute actions** using the discovered selectors

## Common Pitfall

❌ **Don't** inspect the DOM before waiting for `networkidle` on dynamic apps
✅ **Do** wait for `page.wait_for_load_state('networkidle')` before inspecting

## Best Practices

- Use `sync_playwright()` for synchronous scripts
- Always close the browser when done — and see the hygiene rule above
- Use descriptive selectors: `text=`, `role=`, CSS selectors, or IDs
- Add appropriate waits: `page.wait_for_selector()` or `page.wait_for_timeout()`
- Screenshots go to a scratchpad path, never into the repo tree

## Reference Files

- **examples/** — upstream's, with the port and output-path substitutions
  noted at the top of this file; they write to `/tmp/webapp-testing/`:
  - `element_discovery.py` — discovering buttons, links, and inputs on a page
  - `static_html_automation.py` — using `file://` URLs for local HTML
  - `console_logging.py` — capturing console logs during automation

`console_logging.py` is the one worth reading first: `packages/web-shared/CLAUDE.md`
records that a green Vitest run is not a quiet one, and console capture in a real
browser is the same question asked of the running app.
