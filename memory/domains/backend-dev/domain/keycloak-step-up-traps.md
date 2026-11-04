---
role: "backend-dev"
class: domain
topic: "keycloak-step-up-traps"
description: "Keycloak step-up (LoA 2) traps that pass silently: a skipped credential step grants the level, custom client scopes drop acr/auth_time, a required action blocks password grants"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "backend-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 948bb9c3c5787e14
---

## Keycloak step-up (LoA 2) traps that pass silently: a skipped credential step grants the level, custom client scopes drop acr/auth_time, a required action blocks password grants

Measured on Keycloak 26.8.0 while building gzapp's staff step-up (#1154; gzapp's own notes are
infra/local/KEYCLOAK.md §Step-up).

- **A conditional LoA-2 sub-flow whose credential form is skipped for a user with no credential still
  grants the level.** The "user has no OTP" branch has to end in an explicit deny
  (conditional-sub-flow-executed "not-executed" → deny-access-authenticator), or the step-up passes
  with one factor. Letting the step enrol (CONFIGURE_TOTP) is no better: whoever holds the first factor
  enrols their own device. Enrol at provisioning; a step-up never enrols.
- **A realm that defines its own client scopes has no `acr` and `basic` scopes**, so access tokens
  carry neither `acr` nor `auth_time`, and a backend step-up check that reads them refuses every
  token. Add the acr-loa-level and auth_time mappers to the client.
- **`prompt=login` + `max_age=0` from the client re-asks the FIRST factor**; per-act second factor is
  the realm's LoA-2 step at max-age 0 with the client sending `acr_values=2` alone.
- After a step-up, a refresh of the session's original refresh token returns the elevated `acr` —
  bound freshness by `auth_time`, not by which token came back.
- A denied step-up is Keycloak's own 401 page in the popup: no redirect, no OIDC `error=` for the
  client to classify.
- A pending required action (CONFIGURE_TOTP) refuses that account's password grant, so a seed or
  script signing in non-interactively breaks silently on the next fresh stack.

*Observed 2026-10-22 (backend-dev)*
