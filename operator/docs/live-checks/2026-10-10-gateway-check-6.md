# 2026-10-10 — gateway live check 6: an account switch inside an unfinished tool-use loop

Run by the owner on develop-qzapp, from agent-fabric-gateway at
`v0.1.0-17-g2c6c7e37` (main after #34), harness 2.1.285 (the pin), model
claude-sonnet-5-5, accounts A = andrea-benetton-blueteam-ge (token
fingerprint 183a68e97389) and B = claude-pzhuy-8alias-com (26f5543797ba),
token files made by `$XDG_RUNTIME_DIR/check6/run` (never printed, removed on
exit). Command: `spikes/live-account-switch/check-6.sh --token-a … --token-b …`.

A first run failed before any tool call (upstream 401 on both runs): the
helper line handed to the owner cut each token's last byte (`head -c -1` on an
entry with no trailing newline). Corrected and re-run; the result below is the
second run.

## Result

Requests are numbered as the gateway logs them: request 1 is the
harness's keyless `HEAD /api/hello` probe, which the gateway refuses by
design (`local_auth_failed`), so the first tool-use turn is request 2 and
the turn after the first tool result is request 3.

| run | harness exit | turns | upstream statuses | swap | first request after the swap |
|---|---|---|---|---|---|
| control | 0 | 4 (tool_use ×3, text) | 200 ×4 | none | — |
| switch | 0 | 4 (tool_use ×3, text) | 200 ×4 | `credential.replaced` (generation 2) after the first tool result | request 3, 200 |

- **Proven:** a token swap by write-then-rename between tool results is
  picked up on the next request; that request and the rest of the loop are
  served (200) on account B with the same harness and gateway, no restart.
- **Observed:** the first turn on B wrote the whole prompt cache again
  (cache_read 0, cache_creation 34,616): a switch costs one cold cache.
- **Not measured** (`measured: false`): `thinking_before_hook` was false in
  both runs, so no signed thinking block from A was handed back to B. The
  case the check exists for is still open.
- **Expected:** every run's request 1 is refused locally (401,
  `local_auth_failed`): the harness's keyless probe, refused by the
  gateway's operation-inventory decision (rust-services-dev-01, pinned by
  tests/anthropic-passthrough/tests/operations.rs); nothing is retried.
- **Next:** check-6 now defaults to claude-sonnet-4-5, whose turns return
  signed thinking (gateway #36); the owner reruns it once #36 merges.
