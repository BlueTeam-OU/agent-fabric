---
role: "python-dev"
class: domain
topic: "git-config-get-reads-beyond-the-repo"
description: "Reading trust state from a repo's .git/config — a plain `git config --get` also reads ~/.gitconfig, system and GIT_CONFIG_* env; use --local"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 325c0222f5064e91
---

## Reading trust state from a repo's .git/config — a plain `git config --get` also reads ~/.gitconfig, system and GIT_CONFIG_* env; use --local

`git -C repo config --get KEY` answers from every scope: system,
~/.gitconfig (or GIT_CONFIG_GLOBAL), the repo, and GIT_CONFIG_COUNT/KEY_n/
VALUE_n from the caller's environment. For state that must be the repo's
own (a trust anchor), read with `--local`: it ignores the env and global
scopes (measured 2026-10-04, git on develop-qzapp: plain get rc=0 with the
env value, --local rc=1).

Case: secret_store.trusted_base (ADR-042's trusted base) used a plain get,
so a base in the env or ~/.gitconfig trusted every store; fixed on
develop-qzapp/python-dev-01/for/user/status-no-base (553e385) with one
reader, `_read_base`, shared by the verifier and `fabric-secrets status`.
A second reader of the same state (ops.mjs hasBase, parsing the file) must
agree with git's semantics: last value wins, key name case-insensitive.

`--local` is not enough: `-C repo` does not beat GIT_DIR. With GIT_DIR (a
git hook runs with one) every `git -C store …` went to that repo — the
--local read returned its base, and a `store set` committed into it (#96
round 1, e97e9ae). Fix at the one subprocess boundary: drop
`git rev-parse --local-env-vars` plus GIT_CONFIG_KEY_n/VALUE_n; keep
GIT_CONFIG_GLOBAL/SYSTEM/NOSYSTEM (account files; tests isolate with them).

**Why:** two readers of one trust state that disagree let status say
"verified" while every verified operation refuses, or the reverse.
**How to apply:** any git config value that gates trust → `--local` (or
`--file`), one reader; test it with a hostile GIT_CONFIG_* caller env.

*Observed 2026-10-04 (python-dev)*
