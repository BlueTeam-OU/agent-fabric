A frozen copy of InterWeave's `projects/interweave/integration/gh/arm.json`
(2026-10-09), read by `tests/test_arm_cli.py`. See `../gzapp-gh/README.md`: a
project's integration files are the operator's instance data, and the suites
that test a fabric tool with a project's rules read these copies, so they do
not move when the project edits its rules.
