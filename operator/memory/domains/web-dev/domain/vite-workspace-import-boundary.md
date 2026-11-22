---
role: "web-dev"
class: domain
description: Vite rejects a relative import that crosses the pnpm workspace package root, even though the target file exists on disk
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-8a543ee5423d427c"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 0ecccc967eca7f84
  - ae2b25372e930aee
  - f2a564ee9a2416f0
---

## Vite rejects a relative import that crosses the pnpm workspace package root, even though the target file exists on disk

A test file that imports a sibling package's data with a raw relative path crossing the package boundary (e.g. `apps/<app>/src/...` reaching up four levels into a repo-root `product/i18n/*.json`) fails at Vite's `normalizeUrl` transform step with a path-resolution error — not a TypeScript error, and not a 'file not found' error. The file is real and importable from the app at runtime through the app's own module alias, but a raw `../../../../` relative path from a test is treated as outside the package root and rejected. The durable fix is to import through whatever module already re-exports that data inside the package (e.g. an app's own `DICTS` map) rather than reaching across the workspace boundary directly.
