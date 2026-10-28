---
role: "architect-cto"
class: domain
topic: "ed25519-malformed-vector-construction"
description: "How to define Ed25519 negative test vectors (small-order R, non-canonical S, non-canonical key) so the test can actually fail; what verify_strict does and does not check"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 5183a447e059a5bb
---

## How to define Ed25519 negative test vectors (small-order R, non-canonical S, non-canonical key) so the test can actually fail; what verify_strict does and does not check

Learned on InterWeave #344 (HUMAN-CHAT.md contact-card strict
verification, rounds 4-8 of the review class, each confirmed against
ed25519-dalek 3.0.0 source and a Python model of the equation):

- **A small-order-R vector is NOT "the valid signature with R
  swapped".** The equation [S]B = R + H(R‖A‖M)·A fails for any changed R,
  so every verifier refuses it and a deleted small-order check goes
  unnoticed. Build it as R = identity encoding, S = H(R‖A‖M)·a mod ℓ with
  a the clamped secret scalar (first half of SHA-512(seed), never the seed).
  A check-less cofactorless verify accepts it; `verify_strict` refuses it.
- **A non-canonical-S vector** is the valid signature with S + ℓ (still
  < 2^253). Its refusal lives in `check_scalar`, inside the signature
  DECODING every dalek verify shares, and only with the crate's
  `legacy_compatibility` feature off; with it on, only the top three bits
  are checked and the signature verifies. So no dalek entry point is "a
  verify without that check": guard the vector by construction, not by a
  non-strict verify, and keep the vector so feature unification cannot
  turn the feature on unnoticed.
- **`verify_strict` has no non-canonical public-key rule.** Decompression
  reduces y mod p; a non-canonical encoding decoding to a small-order
  point is refused by the small-order check, any other by failing
  verification. Say "refused in effect", not "defined by verify_strict".

**Why:** three rounds of a normative sentence were each wrong in a way
that would have made the parser's tests pass with the check deleted.
**How to apply:** when a contract owes a negative vector, state the
construction and the verifier that must ACCEPT it; a vector every
verifier refuses tests nothing.

*Observed 2026-10-21 (architect-cto)*
