# 2026-10-01 — auto mode's classifier configuration, read back on 2.1.282

The owner asked for the auto-mode classifier's configuration to be set
centrally for every agent, after one login's `/auto-mode-setup` proposed
one. ADR-008 asks that a harness behaviour a fabric rule depends on be
measured, so this records what Claude Code 2.1.282 does with `autoMode`,
on develop-qzapp as user.

## Where the classifier reads it

The harness's documentation (code.claude.com/docs/en/auto-mode-config)
says the classifier reads `autoMode` from user settings, managed
settings and `--settings`, and not from a project's `.claude/settings.json`
or `.claude/settings.local.json`. Each list is prose, and `"$defaults"`
splices in the built-in entries; a list without it replaces them. The
review of #74 confirmed the scope rule in the 2.1.282 binary: project and
local `autoMode` is ignored.

## The built-in lists

`claude auto-mode defaults` printed one JSON object: 21 `environment`
entries, each `**<slot>**: <text>`, 17 `allow`, 70 `soft_deny` and 1
`hard_deny`. Most environment slots read "None configured"; the ones
with guidance of their own are Repository visibility, Host containment
(metadata credentials are never task credentials; the classifier sees
commands, not their output), Trusted repo, Source control, Sensitive
data locations (the [named+specifics] bar), Sensitive remote targets and
Protected IaC scopes.

## The fleet's configuration, composed and read back

`user-settings.py` replaced the policy's 10 slots in place, kept the
other 11 as worded, and added the policy's one soft and one hard block
after `"$defaults"`. `claude auto-mode config`, run with
`CLAUDE_CONFIG_DIR` pointing at a scratch directory holding only that
`autoMode`, read back 21 environment entries, 17 allow, 71 soft_deny and
2 hard_deny: the composition as written. `claude auto-mode critique` on
the same directory answered "No critique was generated" twice.

## What the accounts carried before

Read through the host executor as each login, `autoMode` and the wizard
override only. Seven accounts had the same `environment` of 15 entries
and nothing else: user, backend-dev-01, backend-dev-02, flutter-dev-01,
web-dev-01, db-admin, devex-tooling. It was a wizard's output saved
without `"$defaults"`, so it replaced the built-in list. It had
- eleven of the built-in slots, most reading "None configured";
- two stray headings, "### Org-wide" and "### User-specific";
- one leaked wizard line, `no "routine under <user>/ prefix" qualifiers
  found`.

It dropped the built-in Trusted repo, Source control, Repository
visibility, Host containment, Secrets management and Sensitive data
entries: those seven classifiers had no guidance on which repositories
were trusted or where sensitive data lives. The other nine accounts had
no `autoMode`, and ran on the built-in defaults. No account had an
allow, soft_deny or hard_deny entry of its own.

## What it decides

- The fleet's configuration lives in user scope, written by
  `user-settings.py` from `policies/auto-mode.json` (ADR-008 §5 rule 7).
- A replaced slot carries its built-in safeguard over, since replacing
  drops it.
- The environment follows the pinned harness: a claude upgrade reruns
  `user-settings.py`.
- Nothing the accounts carried was worth keeping; the first bootstrap
  after the merge replaces it.
