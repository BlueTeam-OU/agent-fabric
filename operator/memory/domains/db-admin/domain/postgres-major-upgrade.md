---
role: "db-admin"
class: domain
description: "Postgres major-version bumps are pgdata-incompatible, and PG18+ additionally moved the data-directory mount point"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-8a543ee5423d427c"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 303b402570080e0b
  - 5160aeeb22de39af
  - 67d1aa341cbfb8a8
  - 7972d293350a2203
  - 9e3975efaebdd6e4
  - dd5dad9aeecaa21b
---

## Postgres major-version bumps are pgdata-incompatible, and PG18+ additionally moved the data-directory mount point

Postgres's on-disk data format is not compatible across major versions: pointing an existing named volume at a new major-version image tag (e.g. postgres:16-alpine to 18-alpine) crashes the container on startup rather than upgrading in place — the volume has to be destroyed and the database rebuilt from migrations (or pg_upgrade'd out of band). Starting with the PG18 official image, the layout changed further: data is stored under a major-version subdirectory of /var/lib/postgresql rather than directly at /var/lib/postgresql/data, so a compose file still mounting the volume at the old .../data path fails immediately — even against a freshly emptied volume — with an 'unused mount/volume' error, because the mount target itself has to move up one directory level to match the new image's expectations.

## A stale SELinux MCS category label on a container volume produces a bare 'Permission denied', not an SELinux-labeled error

On a rootless-Podman host with SELinux enforcing, a named volume can retain an MCS category-pair label bound to whichever container context last initialized it. When a differently-labeled container tries to use that same volume — for example after switching Postgres major versions and therefore recreating the container — even root running inside the new container gets a plain 'Permission denied' on mkdir/write, with nothing in the error message pointing at SELinux; it reads exactly like an ownership (uid/gid) bug. Confirm the actual cause with the volume's SELinux label (e.g. via `podman unshare` + `ls -Z`) before chasing uid/gid theories. The fix is `podman unshare chcon -R -l s0 <volume>/_data` to strip the mismatched category pair from the label — this does not require recreating the volume or migrating any data, it only rewrites the label.
