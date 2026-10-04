# ADR-019 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-04 — `main` is protected

Rule 6 said agent-fabric had auto-merge off and no ruleset, so arming a
pull request meant merging it, and `gh pr merge --auto` merged at once
while CI was still running: the session's own discipline was the only
thing between a red build and `main`. An external review of the fabric
named that as the next hardening step, and the owner approved a minimal
ruleset modelled on gzapp's: a pull request, the CI checks and signed
commits required; deletion and force-pushes refused; merge commits
only; no approval count, since every session merges from one account;
no merge queue, so arming stays one command. Auto-merge is on, so
`gh pr merge --auto` now waits for green. The ruleset is committed as
`tools/fabric/github-ruleset-main.json` and applied by
`tools/fabric/github-repo-settings.sh`, which used to force auto-merge
off. The authority guards still decide who may merge; GitHub now
refuses what is not a green pull request.
