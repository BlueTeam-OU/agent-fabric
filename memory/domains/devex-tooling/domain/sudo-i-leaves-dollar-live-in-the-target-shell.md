---
role: "devex-tooling"
class: domain
topic: "sudo-i-leaves-dollar-live-in-the-target-shell"
description: "sudo -i with a command re-escapes the argv for the target login shell but leaves $ unescaped, so any \"$1\"/\"$VAR\" in the command expands in that shell (empty) — never pass a $-bearing argument under -i."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 891a2c06cfd929d8
---

## sudo -i with a command re-escapes the argv for the target login shell but leaves $ unescaped, so any "$1"/"$VAR" in the command expands in that shell (empty) — never pass a $-bearing argument under -i.

`sudo -iu <user> <cmd> <args>` does not exec the argv. Per `man sudo`
(1.9.17 on develop-qzapp): "the command and any args are concatenated …
after escaping each character with a backslash except for
alphanumerics, underscores, hyphens, and dollar signs", then handed to
the target's login shell with `-c`. So a `"$1"` or `"$ROLE"` inside a
`bash -c '…'` string reaches that login shell as a live expansion and
becomes empty before the inner bash runs; `~` arrives as `\~`, literal.

**Why:** `docs/host/PROVISIONING.md` §10 (PR #750) first wrote
`sudo -iu "$NEW_USER" bash -c '… bind "$1"' _ "$ROLE"` — which binds
`""`. Caught by a blind re-review, not by reading.

**How to apply:** under `-i`, expand everything in the calling shell and
pass arguments that contain no `$` or `~` — absolute paths built from
`$NEW_HOME`, and `--workspace "$NEW_CLONE"` instead of a `cd`. Verify a
line by applying the escaping rule to the argv and running it under a
bare `bash -c`. `sudo -Hu … bash -c '…' _ args` (no `-i`) passes
positionals verbatim if a login shell is not needed. Related:
[[role-is-bound-with-fabric-role-not-slash-role]].

*References: role-is-bound-with-fabric-role-not-slash-role*

*Observed 2026-09-15 (devex-tooling)*
