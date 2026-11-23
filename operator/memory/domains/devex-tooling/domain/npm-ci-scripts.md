---
role: "devex-tooling"
class: domain
description: "npm run --if-present silently no-ops — dangerous for a script that's the only check of something"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-948c9fcd4da94057"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 02a6fc6192ecf06f
  - c9f1fa7d611b7438
  - e0de520143aeafa1
---

## npm run --if-present silently no-ops — dangerous for a script that's the only check of something

`--if-present` exits 0 when the named npm script doesn't exist in `package.json`, which is exactly right for genuinely optional per-app scripts inside a shared CI loop over several sub-apps. It's wrong the moment one app's script is the SOLE check covering some surface — this repo's Cloudflare Worker sub-app has its own `tsconfig.worker.json` reachable only through its `worker:typecheck` script; when the per-app CI loop was consolidated and that call picked up `--if-present` by default, a future rename or deletion of `worker:typecheck` would make the whole CI job report green while every TypeScript error in the worker's source went uncaught. When wiring a shared/looped CI step across sibling apps, decide per-script whether "missing" should mean "skip" (use `--if-present`) or "this is a broken build" (call it unconditionally) — don't apply the flag uniformly just because it made the loop simpler.
