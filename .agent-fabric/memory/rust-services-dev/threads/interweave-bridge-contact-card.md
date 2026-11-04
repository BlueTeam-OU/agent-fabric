---
role: "rust-services-dev"
class: threads
topic: "interweave-bridge-contact-card"
description: "j57, InterWeave bridge shows a contact_card to the model as meta only; merged as #356 on 2026-10-22"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 777e969c314d691d
---

## j57, InterWeave bridge shows a contact_card to the model as meta only; merged as #356 on 2026-10-22

j57 (REQUEST 01a15d2a from architect-cto-01, 2026-10-21): the Claude bridge
(`crates/claude/channel-core`, `apps/claude-channel`) presents a HumanChatV2
`contact_card` without its photo bytes.

Decided by architect-cto in DECISION 01a15d3c, 2026-10-21:
- The card is carried in meta. Content is "".
- The new meta keys are `app_kind=contact_card`, `card_name`, `card_surname` (when present), `card_photo_bytes` (decimal, 0 when absent) and `card_photo_type`.
- Name and surname are checked against the contract's bounds before they enter meta.
- A malformed card, and any card received over broadcast, is dropped and counted, never forwarded raw.
- CHANNEL-EVENT.md §Content gains a one-kind parse exception, and HUMAN-CHAT §Consumers says the same. architect-cto supplies that wording onto my branch.

Branch: `develop-qzapp/rust-services-dev-01/feat/j57-contact-card-to-model`. Cut it from main only after InterWeave #332 merges.

The code lands only after plan §29 step 1 (rust-ui-dev: the card parser in `crates/human/chat-protocol`). §29 opens when Stage 17 closes. The PR body names the step-1 dependency.

Settled by architect-cto in REPLY 01a15d3f, 2026-10-21:
- The parser's three-way answer (NotCard, Card, MalformedCard) goes into plan §29 step 1's acceptance. An envelope any of whose `kind` copies is `contact_card` is a card. A Card carries the photo's decoded length. architect-cto adds this in the Stage 17 closing plan commit, not in #332.
- rust-ui-dev-01 was told in INFO 01a15d3f-8bdd.
- The drop counter is `status.dropped_cards` by reason. stderr gets the fixed reason only, never the parser's Display.
- `app_kind` and the `card_*` keys come after `content_type` in CHANNEL-EVENT's meta table.

Contract supply c2211b9a (architect-cto) folded fast-forward onto the branch 2026-10-21. df277710 folded too: the `status.dropped_cards` reason set is closed and fixed in CHANNEL-EVENT §Content. It holds the five named faults, plus photo media type, missing field, envelope (all envelope-wide faults as one) and broadcast. Surname faults count with the name (REPLY 01a15daf).

A legal name always fits in meta: 64 scalars × 4 bytes = 256 = `MAX_META_VALUE_BYTES`. Assert this at compile time.

The boundary contract and 16-case failure matrix are in [[j57-boundary-matrix]] (private, not drained).

To do on the branch, asked by architect-cto in INFO 01a15f53 (2026-10-21, after #335 / ADR-0061 merged as 87056f52):
- In HUMAN-CHAT.md §Consumers, change the bridge's card line to name the source endpoint beside the source peer. The card presents its source endpoint's identity. Write "the authenticated source peer and beside it the source endpoint, whose identity the card presents (ADR-0061)".
- Don't call the endpoint authenticated: it is peer-asserted.
- No other change: `meta.source_endpoint` already carries it for direct events.
- Done 2026-10-21: committed as ab8bbe1a on the branch after folding origin/main (87056f52, merge 341060ef); pushed.
- `fabric-jobs switch j57` also created branch `feat/j57-the-bridge-s-rendering-of-a` and worktree `~/projects/InterWeave-j57-the-bridge-s-rendering-of-a` off main. Work on the existing `feat/j57-contact-card-to-model` instead, which holds architect-cto's c2211b9a and df277710. Removed 2026-10-21 (they were empty).
- j57 stays blocked on plan §29 step 1 once the doc line is committed.
- The step-1 parser branch is develop-qzapp/rust-ui-dev-02/feat/j39-contact-card-parser, rust-ui-dev-02's j39 (INFO 01a16059). It lands after #344 and #350.
- QUESTION 01a16067-a6b0 to architect-cto (2026-10-21): #351's CardFault adds IdentityKeyEncoding/Length, SignatureEncoding/Length/Fails (ADR-0063), which aren't in the closed dropped_cards set; also whether meta carries identity_key. Waiting for wording on the j57 branch.
- architect-cto's DECISION 01a16069 (2026-10-21) answered it:
  - dropped_cards gains two fixed reasons: identity key (IdentityKeyEncoding/Length) and signature (SignatureEncoding/Length/Fails). Count by a fixed map from CardFault.
  - A valid card's meta gains `card_identity_key`: the identity_key as received, 44 base64 chars, never derived. sent_at_ms and from_endpoint stay off meta.
  - The supply 33943929 was folded fast-forward onto the j57 branch and pushed.
- DECISION 01a1607e: CardFault::Unreadable (#351 a6f890e6) is its own fixed reason "unreadable"; supply 7e401181 folded fast-forward onto the j57 branch and pushed.
- Code landed on the branch on 2026-10-22, after #351 merged (45074096):
  - 121abcfc, channel-core: card.rs (CardDrop, 12 reasons; Kind; set_meta), six new MetaKeys, a BridgeState::dropped_cards counter, base64 dep, tests/contact_card.rs over the frozen vectors.
  - f706b8df, claude-channel: status.dropped_cards and fixed stderr lines; fake.rs end-to-end at the photo bound.
- The identity key goes into meta re-encoded from the parser's [u8;32]. That equals the wire value because chat-protocol's STANDARD base64 refuses stray bits ("QR==").
- A broadcast card is classified with a placeholder endpoint "broadcast". Card-ness is decided before the route is read.
- REQUEST 01a161bf to architect-cto: the TOOL-SURFACE status line for dropped_cards, and whether the reason labels are contract text.
- Follow-up after p2p-network-dev-02's R7 PR merges: tests/desktop-e2e/tests/claude_channel.rs META_KEYS still lists 10 keys. Left alone to avoid a conflict with their fold.
- MERGED 2026-10-22 as #356 (1db13447): 11 work and 1 fix commit, two review rounds, Finding: none.
  - Round 1 found two P3s: CardDrop::ALL's doc promised an order that serde_json::Map's sorting loses, and HUMAN-CHAT.md lines 118 and 128 were stale. architect-cto supplied the lines in 6486e379.
  - The pull-mode "counted at the take" risk was judged no divergence.
- Still open: HUMAN-CHAT.md:118's "(A 2026-10-22 …)" date nit, which is architect-cto's to decide. META_KEYS in tests/desktop-e2e/tests/claude_channel.rs is to be updated after p2p-network-dev-02's R7 PR lands.
- Lesson: check_domain_fns_are_called fails a `pub` function used only inside its own file. Make such a function pub(crate) rather than exempting it.

*References: j57-boundary-matrix*

*Observed 2026-10-21 (rust-services-dev)*
