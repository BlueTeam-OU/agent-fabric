# gzcoord-operator

An operator tree for `tests/test_gzcoord_protocol.py` and
`runtime/control/tests/gzcoord.test.mjs` (ADR-045 §5 rule 3:
tests read instance fixtures, never this checkout's live instance
files): the role catalogue cut to the roles the suites and the protocol's
examples name, ids and titles as the catalogue had them on 2026-10-08
(all gzmsg reads), plus `fixture-only-role`, which no live catalogue
holds: a case names it, so a reader that took the live catalogue fails.
And gzapp's GZCoord integration. A case or an example that
comes to name another role fails until it is added here. Also read by
`tests/test_arm_cli.py` (a waiver by `architect-cto`, checked against the
catalogue) and `tests/control_parity.py` (`python-dev`, `web-dev`,
`fabric-coordinator`, for `pool-add`): trim the catalogue only after them.
