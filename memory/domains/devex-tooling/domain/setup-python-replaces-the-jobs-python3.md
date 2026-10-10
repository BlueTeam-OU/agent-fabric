---
role: "devex-tooling"
class: domain
topic: "setup-python-replaces-the-jobs-python3"
description: "actions/setup-python puts its python3 first for every later step; suites needing the runner's modules (PyYAML) break — use update-environment false and a per-suite PATH"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 392f7c03a2054053
---

## actions/setup-python puts its python3 first for every later step; suites needing the runner's modules (PyYAML) break — use update-environment false and a per-suite PATH

In a GitHub Actions job, `actions/setup-python` puts its own `python3`
first on PATH for every step after it. Modules installed into the
runner's python3 earlier in the job (PyYAML, jsonschema, …) are then
missing. InterWeave #204 went red this way in `tool self-tests`
(check_docs_integrity), fixed in d77c2806.

**Why:** one suite needed Python ≥ 3.12.11 (tarfile `data` filter
floor), but ubuntu-24.04's python3 is 3.12.3.

**How to apply:** use `update-environment: false` with an `id`, and
give only the suites that need it `$(dirname
${{ steps.<id>.outputs.python-path }})` first on PATH. Related, from
the same PR: a file bind-mounted elsewhere is restored by writing it
back in place (`cat old > file`), never by `mv`, because the mount
keeps the replaced inode.

*Observed 2026-10-06 (devex-tooling)*
