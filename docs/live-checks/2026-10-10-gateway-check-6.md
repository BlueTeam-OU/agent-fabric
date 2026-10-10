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
- **Unexplained:** every run's first request was refused locally
  (`refused`, 401, `local_auth_failed`) before the harness's retry
  succeeded; passed to rust-services-dev-01.
