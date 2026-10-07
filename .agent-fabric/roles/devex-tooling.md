---
role: devex-tooling
class: remit
project: agent-fabric
description: "What the developer-experience role covers in agent-fabric: the forge tooling and the GZCoord command-line tools, as a contributor."
origin:
  - agent: user
    host: develop-qzapp
---

# devex-tooling — remit in agent-fabric

The charter (`identities/roles/devex-tooling/charter.md`) is the
function. This remit is what that function covers in the control plane.
fabric-coordinator wrote it when the owner made the role a contributor
here (2026-10-03). A role that wants its remit changed proposes it.

**Yours here, as a contributor.** The code your entry in
`policies/authority.json` lists:

- the GitHub toolkit: the shims under `runtime/github/` (pr-gate,
  pr-reply, post-review, pr-review-status, pr-sessions, trial-merge) and
  their Python under `tools/fabric/github/`;
- gzapp's `gh` forwarders and both projects' arm rules, under
  `projects/gzapp/integration/gh/` and `projects/interweave/integration/gh/`
  (an `arm.json` is a project's security boundary in path form: a change
  that narrows one asks that project's architect-cto first);
- the GZCoord command-line tools, `communication/gzcoord/scripts/`, and
  their tests, `communication/gzcoord/tests/`;
- the toolkit's own tests under `tests/`, each named in the entry
  (`test_pr_*`, `test_post_review*`, `test_trial_merge*`,
  `test_commit_class*`, `test_arm_cli`). Not `bin/`, whose commands are other roles'
  (the owner's carve-out is the tools themselves); a new forge command
  that needs a `bin/` entry is asked of fabric-coordinator.

The entry's exclusions are the contributor never-list. You commit on a
branch `develop-qzapp/<login>/for/user/<what>` and open no pull request.
Tell fabric-coordinator by GZCoord when the branch is ready. It folds the
branch unrebased into its own pull request, and the blind review covers
it. A finding on your hunks comes back to you, and fabric-coordinator
merges (ADR-018 §5 rule 8). The hooks refuse anything outside the entry,
and so does CI.

The branch lives in a worktree of its own:
`git worktree add ~/projects/agent-fabric-<what> <branch>`. It never
lives in `~/projects/agent-fabric`, which stays on main. Your launcher,
hooks, prompt and routing run from that checkout, and the launcher
refuses to start from one that is behind origin/main.

**The work.** The tools every session drives a pull request and a
message with. You make the common path one command and the mistakes a
refusal. The first job is `gzcoord-compose`, architect-cto-01's request
01a10026, item 2:

- FROM and ROLE come from `fabric-whoami`;
- PROJECT and REPOSITORY come from the working copy, unless given;
- the id is minted;
- the message is validated as `gzcoord-send` validates it, and written to
  the scratchpad;
- `--send` posts it.

`gzcoord-compose` is built on the Python that `gzcoord-send` and `gzmsg`
become in ADR-040's Wave 7 (python-dev's), so it validates with the
validator `send` uses; it starts when that wave lands. New tooling is
Python, standard library only, on the interpreter the fabric pins.

**The rules that are not style.**

- The GZCoord grammar is frozen (`communication/gzcoord/protocol/`,
  fabric-coordinator's). A tool composes what SPEC.md already allows and
  validates with the same code `gzcoord-send` uses, never a second copy.
- `gzcoord-send` and `gzcoord-inbox` write each agent's journal (ADR-041). A
  send is kept before it is posted, and a page before it is
  acknowledged. A change that moves either step is a finding to
  fabric-coordinator before it is code.
- Run `tests/run.sh` with CI's environment, not the session's: strip
  `AGENT_FABRIC_*`, `GITHUB_*` and `GIT_DIR`. Never run two suites at
  once. A run leaves nothing under `$TMPDIR`.
- Read a command's exit status before anything is chained to it, never
  through a pipe. Run `python3 tools/fabric/lint.py`, clean, before every
  commit.
- A message body goes on stdin, never into argv. No secret value enters a
  message, a test or a log line.

**Not yours here.**

- Everything a role is: `identities/`, `routing/`, `policies/`,
  `communication/gzcoord/protocol/`, `docs/adr/`, `memory/`,
  `.agent-fabric/`.
- `.github/`: CI here runs the authority guards, so its workflows stay
  fabric-coordinator's.
- The guards, the lint, `tests/run.sh`, `tests/static.sh` and
  `tests/leak-check.sh`.
- All of `runtime/claude-code/`.
- The review-brief code (`fabric-review`, `review_brief.py`,
  `review_rounds.py`).
- The journal's modules.

`policies/authority.json` lists each. A rule you find wrong is a finding
to fabric-coordinator, with the case that shows it.
