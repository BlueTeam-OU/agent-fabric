---
role: "devex-tooling"
class: domain
description: Postgres 18+ images moved the data directory under a version subdirectory
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-8a543ee5423d427c"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 5198900503d5e970
  - d54a4c2f00d91067
---

## Postgres 18+ images moved the data directory under a version subdirectory

postgres:18-alpine (and later) no longer stores its cluster directly at `/var/lib/postgresql/data`; the data lives under a major-version subdirectory of `/var/lib/postgresql` (a docker-library/postgres image change). A compose volume still mounted at the old `.../data` path fails at startup, and on a volume previously initialized under the old layout, the volume directory's ownership can end up split — part owned by the container's mapped subuid, part by the in-container postgres uid — producing a `mkdir: can't create directory` permission error rather than a clear "wrong path" message. Mount at `/var/lib/postgresql` (not `.../data`) for any new 18+ service, and treat a mixed-ownership volume as a sign the mount path changed under an already-initialized volume.
