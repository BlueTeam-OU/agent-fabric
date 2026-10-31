---
role: "python-dev"
class: solution
topic: "fabric-sign-adr057-method"
description: "ADR-057 fabric-sign (PR #239): how git calls gpg.program/gpg.ssh.program, SSH via gpg-agent, proof spool + notes, live-check recipe, traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6ff9abad9f00f6cc
---

## ADR-057 fabric-sign (PR #239): how git calls gpg.program/gpg.ssh.program, SSH via gpg-agent, proof spool + notes, live-check recipe, traps

j39 / PR #239 (branch develop-qzapp/python-dev-03/feat/fabric-sign): bin/fabric-sign + tools/fabric/signing/{sign,proof,notes}.py, pre-push attaches and pushes refs/notes/fabric-ots, provisioning/github_signing_key.py + new-agent step 12.

- git's argv (measured with a logging program): OpenPGP `--status-fd=2 -bsau KEY` (stdin payload), verify `--keyid-format=long --status-fd=1 --verify SIG -`; SSH `-Y sign -n git -f KEYFILE -U BUFFER` (a `key::` literal becomes a temp file, `-U` = use agent), writes BUFFER.sig.
- SSH signing with the agent key: `SSH_AUTH_SOCK=$(gpgconf --list-dirs agent-ssh-socket)`, keygrip of the [S] subkey appended to `$GNUPGHOME/sshcontrol`; ssh-keygen -Y sign -U then works. The socket answers on this host without enable-ssh-support.
- Proof key = sha256 of the whitespace-trimmed signature; `ots --no-bitcoin --no-cache stamp <file>` stamps that file, header is MAGIC+01+08+digest. Spool `~/.local/state/agent-fabric/ots-pending/<key>.ots`. Note blob = raw .ots, attached with `notes add -f -C <blob>` (never -m/-F: binary). An amend carries the old note over via notes.rewriteRef: ensure_note must replace by signature match.
- Live check recipe: scratch worktree off origin/main, commit with `-c gpg.format=ssh -c gpg.ssh.program=bin/fabric-sign -c user.signingkey="$(fabric-sign key ssh)"`, push with `-c credential.helper= -c 'credential.helper=!gh auth git-credential'` plus `-c gpg.ssh.allowedSignersFile=` (the hook's %G? needs it), read `gh api repos/.../commits/<sha> --jq .commit.verification`, then delete branch AND refs/notes/fabric-ots. Result 2026-10-13: verified true, reason valid.
- Traps: tests/test_roots_seam forbids `identities/keys` joined outside roots.py (use roots.keys_dir); a citation of an ADR not on main fails lint and test_roots_readers (ADR-057 sat on #238); signing_fixture.drop_key now removes the /run/user gpg socket dir (130 stale d.* dirs had accumulated); a pre-push test uses only a symlink to pre-push so commit-msg/pre-commit hooks stay out; `pkill -f` of a watcher pattern also kills the calling shell.

*Observed 2026-10-13 (python-dev)*
