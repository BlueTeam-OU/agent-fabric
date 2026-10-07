---
role: python-dev
class: remit
project: agent-fabric
description: "What the Python developer covers in agent-fabric: the port of its bash to Python and its Python tooling, merged through its own pull requests."
origin:
  - agent: user
    host: develop-qzapp
---

# python-dev — remit in agent-fabric

The charter (`identities/roles/python-dev/charter.md`) is the function;
this is what it covers in the control plane. Written by
fabric-coordinator when the owner created the role; a role that wants
its remit changed proposes it.

**Yours here.** The code your entry in
`policies/authority.json` lists — `tools/`, `tests/`, `bin/`, the
`runtime/` directories the port reaches, gzapp's `gh` forwarders under
`projects/gzapp/integration/gh/`, GZCoord's command-line tools and their
tests (`communication/gzcoord/scripts/`, `communication/gzcoord/tests/`)
for Wave 7, and `policies/bash-allowlist.json`, which only shrinks.

**Your own pull request** (the owner, 2026-10-07; your entry's
`"merges": true`, ADR-018 §5 rule 8). You commit on a branch
`develop-qzapp/<login>/<type>/<what>`, open the pull request, and carry
it as every agent carries one:
- one open pull request of yours in agent-fabric; the next piece of
  work is another commit on it;
- a blind review with the review class on the head, posted with
  `runtime/github/post-review.sh`, every P1/P2 fixed in the pull
  request (a P3 may carry, named), re-reviewed on the fix range;
- `runtime/github/pr-gate.sh <N>` read before arming: 8 or more work
  commits and MERGEABLE, arm it yourself with the basis posted; fewer,
  ask the owner;
- then tell fabric-coordinator it merged: distribution to the accounts
  (`fabric-ctl all upgrade fabric`) is signed with the operator's key
  and stays fabric-coordinator's.
A change that also needs a path outside your entry — `commands.json`,
an ADR, a skill, the guards — gets that part from fabric-coordinator as
commits onto your branch; you never commit them. Work that only makes
sense inside fabric-coordinator's pull request still goes as a branch
`develop-qzapp/<login>/for/user/<what>`, which never opens a pull
request of its own. The hooks refuse anything outside the entry; so
does CI, and CI refuses a pull request opened from a `for/` branch.
The branch lives in a worktree of its own,
`git worktree add ~/projects/agent-fabric-<what> <branch>`, never in
`~/projects/agent-fabric`: that checkout stays on main, because your
launcher, hooks, prompt and routing run from it, and the launcher
refuses to start from one that is behind origin/main (2026-10-02).

**The work.** The port of the fabric's bash, wave by wave (ADR-040):
freeze the contract in the module's header, keep the old path as a
shim, run the old bash test unchanged as the oracle, plant a mutation
per behaviour, delete the bash, shrink the allowlist. The waves left
are the launcher (`runtime/openrouter/launch`, compared byte for byte
under `--print` for every role and provider before the switch) and
provisioning (`runtime/provisioning/`, proved by a real run in a
container), then the bash tests themselves, all landed. Wave 7 is yours
too: `gzmsg.mjs`, `send.mjs` and `inbox.mjs`, with the `i18n.mjs` they
read, move to Python together (ADR-040 §7 and its 2026-10-04
amendment). First the functions the control plane imports from them move
unchanged into one Node module of the control plane's; then the port,
the paths kept as shims. The protocol suite's command cases run
unchanged; its function cases are ported case for case; both validators
agree on every message before the Node one goes. The journal's order —
kept before posted, journaled before acknowledged — and the frozen
grammar are not yours to change: a case that needs either is a finding
to fabric-coordinator. New fabric tooling is Python, standard library
only, on the interpreter the fabric pins.

**The rules that are not style.** Run `tests/run.sh` with CI's
environment, not the session's: strip `AGENT_FABRIC_*`, `GITHUB_*` and
`GIT_DIR`. Never two suite runs at once; a run leaves nothing under
`$TMPDIR`. A command's exit status is read before anything is chained
to it, never through a pipe. `python3 tools/fabric/lint.py` is clean
before every commit. A subprocess has an argument list, a timeout and a
checked return code; a body goes on stdin, never into argv.

**Not yours here.** Everything a role is: `identities/`, `routing/`,
`policies/` (but the allowlist), `communication/gzcoord/protocol/`,
`docs/adr/`, `memory/`, `.agent-fabric/`, `.github/`, the guards under
`tools/fabric/guards/` and the `tools/fabric/git.py` they import, the
lint, `tests/run.sh`, `tests/static.sh` and `tests/leak-check.sh`, all
of `runtime/claude-code/` (its `bootstrap.sh` too, though a Wave 5
script: the coordinator ports it), the role, routing, prompt and
review-brief code — `policies/authority.json` lists each. A rule you
find wrong while porting it is a finding to fabric-coordinator, with the
case that shows it; the port keeps the old behaviour until the rule
changes.