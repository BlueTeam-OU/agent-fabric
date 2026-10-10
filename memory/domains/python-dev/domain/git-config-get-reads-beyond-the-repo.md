---
role: "python-dev"
class: domain
topic: "git-config-get-reads-beyond-the-repo"
description: "Reading trust state from a repo's .git/config — a plain `git config --get` also reads ~/.gitconfig, system and GIT_CONFIG_* env; use --local"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2011f3eaf0a85be4
  - 325c0222f5064e91
---

## Reading trust state from a repo's .git/config — a plain `git config --get` also reads ~/.gitconfig, system and GIT_CONFIG_* env; use --local, and keep every other reader of the state in agreement

`git -C repo config --get KEY` answers from every scope: system, ~/.gitconfig (or GIT_CONFIG_GLOBAL), the repo, and
GIT_CONFIG_COUNT/KEY_n/VALUE_n from the caller's environment. For state that must be the repo's own (a trust anchor),
read with `--local`: it ignores the env and global scopes (measured: plain get rc=0 with the env value, --local rc=1).

Case: the trusted base (ADR-042) was read by a plain get, so a base in the env or ~/.gitconfig trusted every store. Now one
reader, `_read_base` in tools/fabric/secretstore/trust.py (`git config --local --get`), is shared by the verifier and
`fabric-secrets status`. **Every other reader of the same state must agree with git's semantics, so name the readers when
you fix one**: the second is `hasBase` in runtime/control/ops/keys.mjs, which parses the file and must follow the same
rules (the key name in any case, the last value wins, the value 40 lowercase hex), or the keys probe says "verified" for a
store every verified operation refuses.

`--local` is not enough: `-C repo` does not beat GIT_DIR. With GIT_DIR (a git hook runs with one) every `git -C store …`
went to that repo — the --local read returned its base, and a `store set` committed into it. Fix at the one subprocess
boundary: `_git_scrubbed` in tools/fabric/secretstore/core.py drops the `git rev-parse --local-env-vars` names plus
GIT_CONFIG_KEY_n/VALUE_n and keeps GIT_CONFIG_GLOBAL/SYSTEM/NOSYSTEM (account files; tests isolate with them).

*Observed 2026-10-10 (python-dev)*
