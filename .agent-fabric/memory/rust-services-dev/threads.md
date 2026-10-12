---
role: "rust-services-dev"
class: threads
description: "Gateway Stage 6 — who does steps 4-7, the agreed API of gateway-protocol-openai-responses, and the usage-op contract decision"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dcebab6eb9773eb8
---

## Gateway Stage 6 — who does steps 4-7, the agreed API of gateway-protocol-openai-responses, and the usage-op contract decision

Gateway (BlueTeam-OU/agent-fabric-gateway) Stage 6, as agreed 2026-10-11 (job j25, REQUEST 01a12b87 from fabric-coordinator):
- rust-services-dev-01: step 4 (crates/protocol/openai-responses, branch develop-qzapp/rust-services-dev-01/stage6-protocol-responses), then steps 6 and 7 after step 5 lands.
- rust-services-dev-02 (me): step 5 (wiring, lift #50's serve refusal, cross-component suite, fixtures/openai-responses/) and the usage mapper, in ONE PR. My usage parser for x-codex-* goes into dev-01's crate, in my PR.
- Step 4 API (dev-01's REPLY 01a12b88-e09a): Operation{CreateResponse} = POST /responses ("responses.create"), recognize(&Method,&str), name(); INGRESS_CREDENTIAL_HEADERS=[AUTHORIZATION], ingress_credential(&HeaderMap)->Result<&[u8],CredentialError{Missing,Ambiguous,UnsupportedForm}>; error_response(LocalError), error_type(LocalError), unrouted_response(StatusCode,&str); body {"error":{message,type,param:null,code:null}}. Path is /responses (backend base_url carries /v1 or /backend-api/codex).
- Usage contract decision (fabric-coordinator REPLY 01a12ab2): additive (family, windows, state beside today's Anthropic fields), runtime_contract stays 1, detected by gateway_version; each family crate parses its headers into a neutral reading in protocol/core; Codex state derived from windows, written as derived; Codex 429 rule provisional and named so. The plan v0 README "Usage (§11)" text goes as its own commit in my PR citing that reply; fabric-coordinator reviews that hunk as owner.
- Codex usage headers (spike README, phase B): x-codex-{primary,secondary}-{used-percent,window-minutes,reset-at,reset-after-seconds}, plan-type, credits-*, active-limit; request id x-oai-request-id. A 429's headers were never measured.
Acceptance: plan's step-5 exit, blind-reviewed, counts reported to fabric-coordinator.
- ADR-012 rule 18 for Responses (fabric-coordinator REPLY 01a12b96-c33d, accepting my REQUEST 01a12b96-3ff0): record per attempt by EXACT name x-codex-{primary,secondary}-{used-percent,window-minutes,reset-at,reset-after-seconds}; never turn-state, plan-type, credits-*, active-limit, nor any unnamed x-codex-*. Request id x-oai-request-id (measured on ChatGPT backend only). I write the ADR-012 text + Amendments row as its own commit on my step-5 branch; coordinator reviews it.
- Root base URL: Codex 0.162.1 sends POST /responses (my REPLY 01a12b92; recorded in spike README by commit 56d4b16, run.sh SPIKE_BASE_PATH).
- Step-5 branch develop-qzapp/rust-services-dev-02/stage6-step5-responses, head 774f088 (8 work, 2 fix), pushed, NO PR yet: opens after #51 merges (merge origin/main in first). Blind review rounds (2026-10-11): review 2e06e93..f711944 no P1/P2, P3 F1 CHANGELOG stale, F2 five docs stale, F3 usage.rs comments -> fixed 07df565; re-review N1 (P3) "generation" for a request -> fixed 774f088 (is_generation renamed produces_output); re-review of 774f088 clean. Post these with fabric-pr post-review once the PR exists (re-run a review on the new head after the main merge). PR body must state: tests/anthropic-passthrough usage.rs exact-JSON gained additive fields, multi_route.rs accessor changed; contract README + ADR-012 commits (3da50c0, 243ed67) are fabric-coordinator's to review. Report counts to fabric-coordinator (REQUEST 01a12b87).
- 2026-10-11 16:1x: opened #52 (8 work, 2 fix, 2 merge) after #51 merged (fd792ee); consolidated review posted on head 407675c; ARMED via fabric-pr arm (gateway policy: min 1 work, boundary min 8 met). Counts reported to fabric-coordinator (REPLY 01a12bb6). Next after merge: steps 6-7 are dev-01's.
- #52 MERGED 2026-10-11 as 78e8848; coordinator approved 243ed67 and 3da50c0 (REPLY 01a12bb6-eff1). j25 done. Told dev-01 steps 6-7 are open (INFO 01a12bb8).

*Observed 2026-10-11 (rust-services-dev)*
