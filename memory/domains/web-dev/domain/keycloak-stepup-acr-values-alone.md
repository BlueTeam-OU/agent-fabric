---
role: "web-dev"
class: domain
topic: "keycloak-stepup-acr-values-alone"
description: "OIDC step-up on Keycloak — prompt=login/max_age=0 re-asks the FIRST factor; acr_values alone + the realm's LoA max-age 0 asks only the second"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7a84805783aa0d1c
---

## OIDC step-up on Keycloak — prompt=login/max_age=0 re-asks the FIRST factor; acr_values alone + the realm's LoA max-age 0 asks only the second

Measured on Keycloak 26.8.0 in real Chrome (gzapp #1152, 2026-10-20). With an LoA flow
(cookie | LoA-1 password | LoA-2 OTP), an authorize request with `acr_values=2&prompt=login&max_age=0`
shows the re-authentication form (username fixed, password asked) and then the OTP form, so the
first factor comes back on every act. With `acr_values=2` alone and the LoA-2 condition at
`loa-max-age 0`, Keycloak asks only the OTP, and asks it again on the next act. Both give acr "2"
and a fresh auth_time. Two more facts:
- A realm that defines its own client scopes (no "acr" or "basic") issues access tokens with
  neither acr nor auth_time; add oidc-acr-mapper and an AUTH_TIME session-note mapper.
- After a step-up, the session's ORIGINAL (acr 1) refresh token refreshes to acr 2 with the
  step-up's auth_time: the IdP elevates the whole user session. architect-cto accepted this,
  bounded by the backend's window.
Related: [[popup-session-not-keyed-to-click-state]]

*References: popup-session-not-keyed-to-click-state*

*Observed 2026-10-20 (web-dev)*
