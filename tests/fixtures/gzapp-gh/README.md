Frozen copies of the files a managed project's `integration/gh/` holds, taken
2026-10-09 from gzapp (and InterWeave's `arm.json` in `../interweave-gh/`), for
the suites that port a project's own test of a fabric tool (`arm`,
`semantic-collisions`, `guards-wired`, `pr-compliance`, `wait-merged`). The
tools read a project's rules from its integration directory, which is the
operator's instance data (agent-fabric ADR-045 §5 rule 3); these tests read this
copy, so they pass with no instance on the machine and do not move when a
project edits its rules. `arm.sh` is gzapp's forwarder with its path to the
engine's `runtime/github/arm.sh` shortened to this directory's depth.
