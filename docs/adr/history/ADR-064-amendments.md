# ADR-064 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-24 — the carrier's codec is zlib, a receipt also answers a message not addressed here, and the carrier contract is written

What changed: §5 rule 8's codec, `;ce=br` (brotli, the content-encoding
of InterWeave's human facade), becomes zlib under the carrier's own media
type, `;ce=deflate`. §5 rule 7, and §2's delivery bullet, add that the
receiving carrier also answers with a receipt when it decides a message
is not addressed to its agent. Rule 8 names the carrier contract,
`communication/gzcoord/docs/CARRIER-CONTRACT.md`, as where the names,
the framing, the receipt and the adapter channel are fixed.

Why, the codec: the build found it unbuildable as written. The fleet's
pinned Python (3.13) has neither brotli nor zstd, and ADR-040 holds the
fabric's tooling to the standard library; a brotli module would be an
unpinned dependency diverging between accounts. The codec is between two
carriers only: the daemon never decompresses and no human client
receives these payloads, so InterWeave's choice for its human facade
does not bind it. Why, the receipt: rule 6 sends a `TO-ROLE` or a
broadcast to every roster member, and each filters as its inbox does;
a member that filters a message out would never append it, so under the
old text its sender retried it for ever.

Raised by python-dev-02 building the carrier (j89, its QUESTIONs of
2026-10-24); the contract is its draft, reviewed and changed by the
coordinator. Accepted by the owner, 2026-10-24 ("adr 64 accepted", in the
coordinator's session).

### Amendment 2026-10-25 — an InterWeave install or update is a control-plane action, checked after the restart

What changed: §5 gains rule 14. Installing or updating the InterWeave
programs is a control-plane action. It restarts the units that were
running, checks them through the control plane (the daemon and the
carrier active, the pinned version reported, the carrier answering
`status`), and reports done only after that check. A failed check puts
back the previous programs and says so. The same check is the control
plane's read of each account's InterWeave state after any restart.

Why: the archive's `install.sh` replaces the programs and enables
nothing, so a running daemon and carrier keep the old binaries until
they are restarted, and the restart takes the account's InterWeave
channel down. If the restart goes wrong, the agent is unreachable on
that channel and nobody is told. The control plane stays on the relay
(rule 12), so it can still reach the account while that channel is
down. It is therefore the one place that can confirm the account came
back.

Raised and accepted by the owner, 2026-10-25, in the coordinator's
session: "when an install/update of interweave happens the
channel/communication become unavailable, if things go wrong agent
become 'invisible' so a control plane check after the restart should
be required".
