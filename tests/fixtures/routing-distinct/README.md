# routing-distinct

The routing column and effort file as they stood on 2026-09-24. On that
day every class on plain claude had a different model (Haiku 4.5,
Sonnet 5, Opus 5.5, Fable 5.1, and `claude-opus-5[1m]` for the review
class), and the levels ran from low to xhigh. On 2026-09-25 the owner
moved every class to Opus 5.5 at medium, and on 2026-09-29 the lower
two to Sonnet 5.5. A test of the mechanics needs classes it can tell
apart, so it runs on
this frozen copy: `tests/test_routing.py` (every case built on
`scratch_root`), `tests/test_model_profile.py`,
`tests/test_launch_cli.py`, `tests/test_lint.py` (its `policies/review-grade.json`
only) and the dispatch guard's suite.
`tests/test_routing.py` asserts the committed policy itself.

`profiles.json` and `policies/review-grade.json` are the operator half
(ADR-045 §5 rule 2: the routing overlay and the review grade are
instance data), frozen on 2026-10-08 from the live files with the
profile's roles and agents emptied, so `tests/test_launch_cli.py`
builds its fixture fabric without reading the live ones; so do
`tests/test_routing.py`, `tests/test_model_profile.py` and
`tests/test_fabric_status_cli.py` (`instance_fixtures.write_routing_overlay`).
