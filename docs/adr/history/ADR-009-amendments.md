# ADR-009 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-28 — A fresh marker is not a resume

Rule 4 said the launcher resumes the stopped session from the restart
marker. Since `fabric-fresh` (ADR-022 rule 10) the marker can say
`fresh`, and then the launcher starts a new session with no `--resume`;
the blind review of that pull request found this rule still describing
only the upgrade case. The upgrade path is unchanged.
