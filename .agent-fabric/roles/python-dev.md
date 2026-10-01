---
role: python-dev
class: remit
project: agent-fabric
description: "What the Python developer covers in agent-fabric: the port of its bash to Python and its Python tooling, as a contributor."
origin:
  - agent: user
    host: develop-qzapp
---

# python-dev — remit in agent-fabric

The charter (`identities/roles/python-dev/charter.md`) is the function;
this is what it covers in the control plane. Written by
fabric-coordinator when the owner created the role; a role that wants
its remit changed proposes it.

**Yours here, as a contributor.** The code your entry in
`policies/authority.json` lists — `tools/`, `tests/`, `bin/`, the
`runtime/` directories the port reaches, gzapp's `gh` forwarders under
`projects/gzapp/integration/gh/`, and `policies/bash-allowlist.json`,
which only shrinks. You commit on a branch
`develop-qzapp/<login>/for/user/<what>`, open no pull request, and tell
fabric-coordinator by GZCoord when it is ready; it folds the branch
unrebased into its own pull request, the blind review covers it, a
finding on your hunks comes back to you, and it merges (ADR-018 §5
rule 8). The hooks refuse anything outside the entry; so does CI.

**The work.** The port of the fabric's bash, wave by wave (ADR-040):
freeze the contract in the module's header, keep the old path as a
shim, run the old bash test unchanged as the oracle, plant a mutation
per behaviour, delete the bash, shrink the allowlist. The waves left
are the launcher (`runtime/openrouter/launch`, compared byte for byte
under `--print` for every role and provider before the switch) and
provisioning (`runtime/provisioning/`, proved by a real run in a
container), then the bash tests themselves. New fabric tooling is
Python, standard library only, on the interpreter the fabric pins.

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