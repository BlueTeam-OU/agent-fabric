---
role: "db-admin"
class: domain
description: "Keycloak self-migrates its backing database across intermediate minor versions on restart, unlike Postgres across majors"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-8a543ee5423d427c"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 398cc2e5a11e47e3
  - 577ffa5ac96b46ab
---

## Keycloak self-migrates its backing database across intermediate minor versions on restart, unlike Postgres across majors

Bumping the Keycloak image several minor versions at once (observed: 24.0 straight to 26.7.0) does not require destroying the keycloak-postgres volume or running an explicit migration step the way a Postgres major-version bump does. Keycloak steps its own backing schema through each intermediate minor version sequentially and automatically on container startup (26.1.0 → 26.2.0 → ... → 26.7.0 in one boot, against the existing volume, with no errors). It also re-runs its bundled realm-JSON import on every startup but treats it as idempotent — realms that already exist in the database are skipped rather than overwritten, so a version bump doesn't clobber realm configuration that has diverged from the checked-in export.
