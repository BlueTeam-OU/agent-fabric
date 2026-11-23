---
role: "web-dev"
class: domain
description: "ESLint's react-refresh/only-export-components rejects a file that exports both a component and a plain function/hook/constant"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-8a543ee5423d427c"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 61fdf52da4c4ffe8
  - 788b41bd2ca45742
  - 8e80edf3c9000d1c
  - d4af12378799630f
  - fb6c3a88d89e6c31
---

## ESLint's react-refresh/only-export-components rejects a file that exports both a component and a plain function/hook/constant

Fast Refresh requires a component file to export components only. A file that co-exports a React component alongside a plain helper function, hook, or constant (e.g. a small utility like `incidentAnchor()` or a state-derivation function like `displayedState()` living next to the component that uses it) fails lint with `react-refresh/only-export-components`, even when the helper is only called internally. This recurred repeatedly across shared-package and sub-app work whenever a small utility was extracted next to its consumer. The fix is always the same shape: either stop exporting the helper (make it file-private) if nothing outside the file needs it, or split it into its own plain-TS module (no JSX) if it does.
