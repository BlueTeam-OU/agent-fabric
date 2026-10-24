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
