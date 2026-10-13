# ADR-054 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-13 — the review engine starts Codex behind the gateway as a session will

§5 rule 7 gains two sentences. The Codex review engine already reaches
ChatGPT through a gateway of its own (ADR-053 rule 3); the owner asked
that it do so "as if we use it as principal harness" — by the session's
launcher path, so a review is also a running check of the route a Codex
session will take — and that the reviewer's gateway-local key stay
different from the main harness's, because "gateway must know in the
long run who is using it". The owner's words, in the coordinator's
session.
