# `runtime/interweave/` — the InterWeave carrier's runtime files

What ADR-064 (GZCoord carried over InterWeave: one host, beside the relay)
needs on a host beyond the carrier's code, which is
`tools/fabric/gzcoord/carrier/`:

- `roster.json` — every login's PeerId, endpoint and port, keyed by agent
  id; a row counts only when signed by its login and countersigned by the
  coordinator (§5 rule 2). The coordinator writes it; it is outside the
  python-dev entry for that reason.
- the roster's schema, the renderer's inputs for each profile's
  `config.yaml` (§5 rule 2), and the client unit's program (§5 rule 5):
  python-dev's, under `policies/authority.json`.

The names, the framing, the receipt and the adapter channel are
`communication/gzcoord/docs/CARRIER-CONTRACT.md`.
