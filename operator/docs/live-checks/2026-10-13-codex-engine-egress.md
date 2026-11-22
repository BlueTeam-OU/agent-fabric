# 2026-10-13 — the Codex review engine: sandbox proof and egress

Run by python-dev-03 (report: GZCoord REPLY, relay seq 137640, in reply to 01a131bc-9044-74c4-9c91-4a0ff9cc0527), as the login python-dev-03, on its branch `develop-qzapp/python-dev-03/for/user/codex-sandbox-egress` (head a44b2407). python-dev-03 cannot write the decision records, so fabric-coordinator committed the report here.

## What was measured

- **Build:** Codex CLI 0.162.1, the pinned npm vendor tree, installed by `fabric-tools --install codex` (#229).
- **Sandbox proof:** `codex sandbox -P :read-only -C <extract> --` started a real bwrap read-only sandbox and refused a write into the extract.
- **Egress:** `strace` of `codex exec` against a local gateway, 30 seconds each:

| configuration | git executions | non-loopback connects |
|---|---|---|
| the engine's, five features off | 0 | 0 |
| the same build, no `[features]` block | 11 | 7 |

The git executions without the block were `git ls-remote https://github.com/openai/plugins.git HEAD` and `git fetch --depth 1 …`. On an earlier standalone build `plugins = false` alone gave 0 and 0; the engine sets all five (`plugins`, `remote_plugin`, `plugin_sharing`, `apps`, `in_app_updates`) so a later version that moves the fetch behind another feature stays closed.

- **Tests:** seven mutations of `tools/fabric/review_codex.py` (proof call removed, features block removed, `plugins` dropped from the list, `-P :read-only` dropped, the write probe weakened, the returncode check removed, the key blanking removed) each fail `tests/test_review_codex.py`; `tests/run.sh` passes with CI's environment.

## Not verified

- A full review through a real gateway with the features off.
- A run longer than 30 seconds.
- The proof on a host that refuses user namespaces (approximated with `unshare -U -r`, where Codex fails with its own one-line reason).

## What it decides

ADR-053 §5 rules 2 and 3, amended 2026-10-13: the sandbox is proven before every run, and the five features stay off in the engine's configuration.
