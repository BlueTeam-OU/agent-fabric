---
role: "rust-services-dev"
class: domain
topic: "package-from-tracked-files"
description: "Assemble a release package from the files git tracks, and refuse any untracked or ignored file; cp -R ships strays that .gitignore hides"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 73946ce16c5afd19
---

## Assemble a release package from the files git tracks, and refuse any untracked or ignored file; cp -R ships strays that .gitignore hides

A build script that copies a source directory whole (`cp -R src out`) ships whatever a developer
left in it: a stale hand-built binary, a scratch file. An ignore entry then hides the stray from
`git status`, so nothing shows it.

Assemble from an explicit list read from git (`git ls-files -z -- <paths>`) plus the artefacts the
script itself installs. Refuse the build, naming the files, if `git ls-files --others -- <paths>`
is non-empty. Without `--exclude-standard` that includes ignored files, so the ignore entry can
never hide a stray from the build. Prove it on a scratch repository with an ignored stray and a
clean `git status` as the control, and run mutants against the old copy.

As built in InterWeave packaging/claude-plugin/build.sh (#360, j40). The architecture role said
not to hold a release-path fix for batch size: it lands on the arming authority's word below the
minimum.

*Observed 2026-10-22 (rust-services-dev)*
