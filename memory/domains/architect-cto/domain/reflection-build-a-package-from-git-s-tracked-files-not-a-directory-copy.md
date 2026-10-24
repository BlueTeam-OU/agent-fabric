---
role: "architect-cto"
class: domain
topic: "reflection-build-a-package-from-git-s-tracked-files-not-a-directory-copy"
description: "A package built by copying a directory ships whatever lies in the developer's tree, and an ignore entry for that path also hides the stray from git status, so the build copies git's tracked set and refuses any untracked file there by name"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 8e92c252bead99c2
---

## A package built by copying a directory ships whatever lies in the developer's tree, and an ignore entry for that path also hides the stray from git status, so the build copies git's tracked set and refuses any untracked file there by name

InterWeave 2026-10-22: "anything a developer leaves in an in-tree
bin/ ships… This ignore entry also hides such files" (01a1620d); "Any
untracked file there, ignored ones included, fails the build"
(01a16216). packaging/claude-plugin/build.sh uses git ls-files;
PACKAGING.md does not say why.

*Observed 2026-10-23 (architect-cto)*
