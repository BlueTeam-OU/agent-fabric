# Wave 9 inventory: every tracked bash script in agent-fabric

The inventory behind [ADR-040](../adr/ADR-040-implementation-language-python-above-150-lines.md) §7, Wave 9: each bash file tracked on `origin/main` when the wave was decided, whether it stays shell or is ported, and for a port the batch and the lane. A file is found by `*.sh`, `*.bash`, or a first line naming `bash` or `sh`. *Lines* is the file's line count; *code* is lines that are neither blank nor comments, which is what the forwarder limit of ADR-040 §5 rule 1 counts.

The lane is who may commit the port: `python-dev` is the contributor entry of `policies/authority.json` (its paths `bin/`, `tests/`, `tools/`, `runtime/provisioning/` and the rest, less its `excluding` list); `fabric-coordinator` is the never-list of `CONTRIBUTOR_NEVER` in `tools/fabric/lint.py` (`policies/`, `runtime/claude-code/`, `bin/fabric-role`, `bin/fabric-review`, `tests/run.sh`, `tests/static.sh`, `tests/leak-check.sh`) and every path no contributor entry names (`runtime/langid/`, `projects/gzapp/integration/provisioning/`).

## Batches

A batch is one pull request: the module, the forwarder, the bash test running unchanged against it as the oracle (rule 5), then the bash test replaced by a Python one case for case, and the allowlist entries removed. Batches 1 to 9 are independent; batch 10 is last, because `tests/run.sh` runs the bash suites the others retire.

| batch | what | files | lines | lane |
|---|---|---|---|---|
| 1 | bin/ dispatch and the secrets-sync fixture | 4 | 101 | python-dev |
| 2 | bin/ dispatch of the role and the review | 2 | 85 | fabric-coordinator |
| 3 | policies/ checks and their tests | 3 | 274 | fabric-coordinator |
| 4 | git hooks | 5 | 341 | fabric-coordinator |
| 5 | Claude Code guards and their tests | 6 | 415 | fabric-coordinator |
| 6 | Claude Code session hooks and their tests | 5 | 392 | fabric-coordinator |
| 7 | Claude Code status line and tab title | 3 | 311 | fabric-coordinator |
| 8 | Claude Code installer tests | 2 | 293 | fabric-coordinator |
| 9 | language detector installer and the gzapp host check | 3 | 89 | fabric-coordinator |
| 10 | suite runners and leak check (last) | 4 | 279 | fabric-coordinator |
| | total | 37 | 2580 | |

## Ports

| batch | file | lines | code | lane |
|---|---|---|---|---|
| 1 | `bin/fabric-locale` | 23 | 9 | python-dev |
| 1 | `bin/fabric-pr` | 41 | 24 | python-dev |
| 1 | `runtime/provisioning/secrets/fabric-secrets` | 22 | 10 | python-dev |
| 1 | `tests/fixtures/fake-gh-auth.sh` | 15 | 9 | python-dev |
| 2 | `bin/fabric-review` | 38 | 13 | fabric-coordinator |
| 2 | `bin/fabric-role` | 47 | 23 | fabric-coordinator |
| 3 | `policies/check_repo_settings_carry_no_model_pins.sh` | 102 | 44 | fabric-coordinator |
| 3 | `policies/test_check_agent_fabric_dir_authority.sh` | 131 | 109 | fabric-coordinator |
| 3 | `policies/test_check_repo_settings_carry_no_model_pins.sh` | 41 | 30 | fabric-coordinator |
| 4 | `policies/githooks/commit-msg` | 109 | 60 | fabric-coordinator |
| 4 | `policies/githooks/guarded-change.sh` | 64 | 34 | fabric-coordinator |
| 4 | `policies/githooks/locale-carve-out.sh` | 33 | 21 | fabric-coordinator |
| 4 | `policies/githooks/pre-commit` | 117 | 60 | fabric-coordinator |
| 4 | `policies/githooks/pre-push` | 18 | 3 | fabric-coordinator |
| 5 | `runtime/claude-code/hooks/model-switch-guard.sh` | 65 | 23 | fabric-coordinator |
| 5 | `runtime/claude-code/hooks/pipe-status-guard.sh` | 39 | 13 | fabric-coordinator |
| 5 | `runtime/claude-code/hooks/subagent-clone-guard.sh` | 71 | 22 | fabric-coordinator |
| 5 | `runtime/claude-code/hooks/test_model-switch-guard.sh` | 78 | 54 | fabric-coordinator |
| 5 | `runtime/claude-code/hooks/test_pipe-status-guard.sh` | 68 | 55 | fabric-coordinator |
| 5 | `runtime/claude-code/hooks/test_subagent-clone-guard.sh` | 94 | 65 | fabric-coordinator |
| 6 | `runtime/claude-code/hooks/model-fallback-note.sh` | 78 | 41 | fabric-coordinator |
| 6 | `runtime/claude-code/hooks/plan-hold.sh` | 103 | 43 | fabric-coordinator |
| 6 | `runtime/claude-code/hooks/session-start.sh` | 20 | 7 | fabric-coordinator |
| 6 | `runtime/claude-code/hooks/test_model-fallback-note.sh` | 68 | 50 | fabric-coordinator |
| 6 | `runtime/claude-code/hooks/test_plan-hold.sh` | 123 | 89 | fabric-coordinator |
| 7 | `runtime/claude-code/hooks/statusline.sh` | 108 | 63 | fabric-coordinator |
| 7 | `runtime/claude-code/hooks/tab-title.sh` | 104 | 30 | fabric-coordinator |
| 7 | `runtime/claude-code/hooks/test_statusline.sh` | 99 | 71 | fabric-coordinator |
| 8 | `runtime/claude-code/test_install-agent-files.sh` | 143 | 112 | fabric-coordinator |
| 8 | `runtime/claude-code/test_user-settings.sh` | 150 | 106 | fabric-coordinator |
| 9 | `projects/gzapp/integration/provisioning/host-check.sh` | 19 | 7 | fabric-coordinator |
| 9 | `runtime/langid/install.sh` | 37 | 23 | fabric-coordinator |
| 9 | `runtime/langid/test_install.sh` | 33 | 24 | fabric-coordinator |
| 10 | `tests/leak-check.sh` | 26 | 10 | fabric-coordinator |
| 10 | `tests/run.sh` | 94 | 50 | fabric-coordinator |
| 10 | `tests/static.sh` | 94 | 66 | fabric-coordinator |
| 10 | `tests/test_leak-check.sh` | 65 | 49 | fabric-coordinator |

Notes on the ports:

- `bin/fabric-pr` (verb table), `bin/fabric-locale` (two verbs) and `runtime/provisioning/secrets/fabric-secrets` (four verbs) move their dispatch into the module; `bin/fabric-role` (the refusal inside a harness session, the help text) and `bin/fabric-review` (verb dispatch) likewise. What is left in each is a forwarder.
- `policies/githooks/pre-commit`, `commit-msg`, `guarded-change.sh` and `locale-carve-out.sh` become one Python module on the pin; the two hooks stay as forwarders because git runs a file by path. `pre-push` is a forwarder already, to the host's `python3`; it moves to the pin. `tests/test_githooks_cli.py` and `tests/test_githooks_prepush.py` are the oracle.
- `policies/test_check_agent_fabric_dir_authority.sh` has a Python twin, `tests/test_agent_fabric_dir_authority.py`; the batch compares the two and deletes the bash one when the twin holds every case.
- `runtime/claude-code/hooks/session-start.sh` keeps its path as a forwarder; the `CLAUDE_ENV_FILE` export it does moves into `session-start.py`.
- `tests/run.sh` and `tests/static.sh` become `tests/run.py` and `tests/static.py`; the two `.sh` paths stay as forwarders that exec the host's `python3` (the interpreter CI's matrix sets, rule 4), not the pin.
- `runtime/langid/install.sh` makes a venv with the host's `python3`; the port keeps that interpreter for the venv, as bootstrap does (rule 4).
- `projects/gzapp/integration/provisioning/host-check.sh` is gzapp's file, tracked here; the worker runs it by path, so the port changes the call in `tools/fabric/provisioning/worker.py` and is told to gzapp's devex-tooling.

## Stays

### Pre-Python installation path

| file | lines | code | why no interpreter is available |
|---|---|---|---|
| `runtime/provisioning/moveto/completion.bash` | 50 | 33 | sourced by an interactive shell |
| `runtime/provisioning/moveto/enter` | 19 | 3 | login-shell stub (#!/bin/bash -l): the login is the point |
| `runtime/provisioning/moveto/enter-ssh` | 56 | 17 | sshd forced command; works in an account before the interpreter is there |
| `runtime/provisioning/moveto/install.sh` | 18 | 4 | root installs moveto before the pin; falls back to the host's python3 |
| `runtime/provisioning/platform/debian-qubes.sh` | 13 | 5 | sourced profile: the host's shell is all there is when it is read (the CI smoke job installs the host contract from it before any Python) |
| `runtime/provisioning/platform/debian.sh` | 18 | 14 | sourced profile: the host's shell is all there is when it is read (the CI smoke job installs the host contract from it before any Python) |
| `runtime/provisioning/platform/detect.sh` | 36 | 26 | sourced profile: the host's shell is all there is when it is read (the CI smoke job installs the host contract from it before any Python) |
| `runtime/provisioning/platform/fedora-qubes.sh` | 17 | 5 | sourced profile: the host's shell is all there is when it is read (the CI smoke job installs the host contract from it before any Python) |
| `runtime/provisioning/platform/fedora.sh` | 16 | 14 | sourced profile: the host's shell is all there is when it is read (the CI smoke job installs the host contract from it before any Python) |
| `runtime/provisioning/platform/packages.sh` | 12 | 5 | sourced profile: the host's shell is all there is when it is read (the CI smoke job installs the host contract from it before any Python) |
| `runtime/provisioning/platform/qubes/agent-fabric-accounts.rc` | 101 | 60 | every-boot re-creation of the accounts, from /rw, before any user manager |
| `runtime/provisioning/platform/qubes/ssh-operator.sh` | 149 | 96 | first provisioning of an AppVM, by hand, as root; stages the boot-time restore |
| `runtime/provisioning/platform/qubes/ssh-restore.sh` | 65 | 40 | every-boot restore of sshd from /rw staging; must come up when nothing else does |
| `runtime/provisioning/platform/qubes/ssh-template.sh` | 30 | 18 | runs in a TemplateVM, where the pin is not installed |

### Forwarders

Each is at most 12 lines of code, has no `case` or loop, and does one thing: find its Python module, check the pin and print the install command if it is absent, exec. Two fail closed instead, `agent-dispatch-guard.sh` (asks) and `review-bash-guard.sh` (denies), because the harness reads a hook that fails as no objection. `fabric-secret-run` and `moveto` also pass on which signals were ignored, which Python's start-up would erase.

| file | lines | code |
|---|---|---|
| `bin/fabric-accounts` | 23 | 6 |
| `bin/fabric-branches` | 18 | 7 |
| `bin/fabric-ctl` | 39 | 6 |
| `bin/fabric-fleet` | 9 | 4 |
| `bin/fabric-fresh` | 13 | 4 |
| `bin/fabric-genimage` | 16 | 7 |
| `bin/fabric-history` | 17 | 9 |
| `bin/fabric-host` | 14 | 3 |
| `bin/fabric-jobs` | 20 | 6 |
| `bin/fabric-lease` | 22 | 8 |
| `bin/fabric-memory-check` | 10 | 4 |
| `bin/fabric-memory-mcp` | 9 | 3 |
| `bin/fabric-model` | 22 | 6 |
| `bin/fabric-pause` | 16 | 6 |
| `bin/fabric-plan` | 20 | 6 |
| `bin/fabric-query` | 16 | 6 |
| `bin/fabric-repo-settings` | 18 | 6 |
| `bin/fabric-resume` | 11 | 4 |
| `bin/fabric-secret-run` | 24 | 11 |
| `bin/fabric-secrets` | 5 | 1 |
| `bin/fabric-ssh-hosts` | 15 | 6 |
| `bin/fabric-status` | 24 | 9 |
| `bin/fabric-tools` | 11 | 4 |
| `bin/fabric-usage` | 12 | 4 |
| `bin/fabric-watch` | 11 | 5 |
| `bin/fabric-websearch-locale` | 10 | 3 |
| `bin/fabric-whoami` | 9 | 3 |
| `bin/gzcoord-compose` | 16 | 7 |
| `policies/ban_generated_by_attribution.sh` | 14 | 4 |
| `policies/check_adr_amendment.sh` | 14 | 6 |
| `policies/check_agent_fabric_dir_authority.sh` | 13 | 4 |
| `policies/check_charter_authority.sh` | 15 | 4 |
| `policies/run_suite.sh` | 10 | 4 |
| `runtime/claude-code/bootstrap.sh` | 17 | 3 |
| `runtime/claude-code/hooks/agent-dispatch-guard.sh` | 30 | 12 |
| `runtime/claude-code/hooks/review-bash-guard.sh` | 23 | 9 |
| `runtime/claude-code/install-agent-files.sh` | 16 | 3 |
| `runtime/hostexec/hostexec` | 17 | 3 |
| `runtime/hostexec/worker` | 14 | 3 |
| `runtime/openrouter/launch` | 18 | 3 |
| `runtime/openrouter/model-audit.sh` | 13 | 3 |
| `runtime/provisioning/moveto/moveto` | 24 | 8 |
| `runtime/provisioning/new-agent-worker.sh` | 21 | 5 |
| `runtime/provisioning/new-agent.sh` | 15 | 3 |
| `runtime/provisioning/secrets/store-enroll.sh` | 15 | 3 |
| `tests/fixtures/gzapp-gh/arm.sh` | 18 | 7 |

Totals: 97 files, 3937 lines; ports 37 files, 2580 lines; pre-Python 14 files, 600 lines; forwarders 46 files, 757 lines.
