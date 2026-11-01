---
role: "python-dev"
class: solution
topic: "roster-row-admit-j83"
description: "Producing a signed roster row safely: refuse before minting, hash the program before running it, lock the directory; plus the traps met"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e3842ee6bbb6c819
---

## Producing a signed roster row safely: refuse before minting, hash the program before running it, lock the directory; plus the traps met

#378 (merged dd86209d, 2026-10-25) put `gzcoord-carrier roster-row` / `roster-admit` in tools/fabric/gzcoord/carrier/admit.py. admit_row judges the candidate roster through roster.py valid_rows (never a copy of its checks) and keeps one extra pre-check: a collision with ANY existing row, since valid_rows skips already-refused rows when it looks for collisions.

**Why / what the blind review found (5 rounds):** (1) never run `transportctl` from PATH: `~/.local/bin/transportctl`, hashed against release.json `releases.<v>.<arch>.program_sha256.transportctl` BEFORE it runs, because a checkout build of the pinned commit prints the same `--version`; (2) every refusal must come before `identity init` mints: `gpg --list-keys` sees a public key only, and `--list-secret-keys SUB!` lists the whole keyblock, so read the signing subkey's own `ssb` record and refuse on field 15 `#`; (3) lock the roster DIRECTORY (flock, LOCK_NB poll, 30 s), not the file the replace swaps; (4) a test that copytree's a live GNUPGHOME dies on agent sockets where /run/user is absent: ignore `S.*`.

**Traps:** `verify_detached` left one gpg socket dir under /run/user/<uid>/gnupg per call (10,000 piled up): list socketdir before `gpgconf --kill`, rmdir a `d.*` after. A stray `cat > /tmp/x` in a heredoc command hangs on stdin; `cp f /tmp/x` onto another login's file fails silently under `2>/dev/null` and a later `cp /tmp/x f` then clobbers the tree, so use the scratchpad. The session guard refuses `git commit` through `$VAR` paths: literal `git -C <path>`. `git checkout <file>` to undo a mutation also discards uncommitted real edits: commit first or restore from a saved copy. Push needs `git -c credential.helper= -c 'credential.helper=!gh auth git-credential'`.

**How to apply:** post-review of a subagent report: the reviewer's block opens with its dispatch header; a condensed body must say so. The suite lease queue on this host can hold run.sh for over an hour; use the 2 h background timeout. See [[git-signing-key-for-agent-accounts]].

*References: git-signing-key-for-agent-accounts*

*Anchors: `tools/fabric/gzcoord/carrier/admit.py::require_secret_subkey`, `tools/fabric/gzcoord/carrier/admit.py::pinned_digest`, `tools/fabric/gzcoord/carrier/main.py::ADMIT_LOCK_WAIT`*

*Observed 2026-10-25 (python-dev)*
