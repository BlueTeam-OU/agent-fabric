---
role: "rust-services-dev"
class: index
description: "What rust-services-dev knows and where it lives."
tier: 1
distilled_at: "2026-10-31"
---

# rust-services-dev — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/rust-services-dev/charter.md`](identities/roles/rust-services-dev/charter.md) — The fleet's network-services developer in Rust: proxies, gateways and API servers — streaming, cancellation, retry and failover, TLS and credential boundaries — proven over real sockets.

## brief

- [`identities/roles/rust-services-dev/brief.md`](identities/roles/rust-services-dev/brief.md) — How rust-services-dev works day to day, in any project: the service boundary written as a contract first, a failure matrix before done, wire behaviour proved over real sockets, and credentials kept inside the process.

## domain

- [`memory/domains/rust-services-dev/domain/adapter-composed-text-indistinguishable.md`](memory/domains/rust-services-dev/domain/adapter-composed-text-indistinguishable.md) — An adapter feeding an LLM host never composes its own text into the content body; facts it derives go in structured metadata, because unescaped content is indistinguishable from peer text
- [`memory/domains/rust-services-dev/domain/assert-only-what-transport-promises.md`](memory/domains/rust-services-dev/domain/assert-only-what-transport-promises.md) — A load test asserts only what the transport's contract promises (exactly-once, bounds); order and drop counts it does not promise are reported as measurements, and a request asking for more is answered before code
- [`memory/domains/rust-services-dev/domain/backpressure-blocks-keepalive.md`](memory/domains/rust-services-dev/domain/backpressure-blocks-keepalive.md) — A consumer that applies backpressure by not reading its single stream also stops answering liveness probes on it, so a paused consumer is closed as wedged and accepted messages are lost
- [`memory/domains/rust-services-dev/domain/cargo-exports-ssl-cert-env.md`](memory/domains/rust-services-dev/domain/cargo-exports-ssl-cert-env.md) — cargo sets SSL_CERT_FILE/SSL_CERT_DIR for every child; rustls-native-certs then reads them instead of the host store
- [`memory/domains/rust-services-dev/domain/cargo-machete-silent-pass.md`](memory/domains/rust-services-dev/domain/cargo-machete-silent-pass.md) — cargo-machete 0.9.2 default mode skips dev-deps; --with-metadata reports unreadable crates clean with exit 0
- [`memory/domains/rust-services-dev/domain/claude-code-print-session-channel-facts.md`](memory/domains/rust-services-dev/domain/claude-code-print-session-channel-facts.md) — Claude Code 2.1.286 -p sessions with a channel: mid-turn events queue, closed stdin still answers, manual mode denies MCP tools, plugin configure needs --values-stdin
- [`memory/domains/rust-services-dev/domain/credential-companion-resolved-together.md`](memory/domains/rust-services-dev/domain/credential-companion-resolved-together.md) — A value that must match the backend credential (account id, org id) has to be resolved with the credential, per attempt; a static header diverges on an account switch
- [`memory/domains/rust-services-dev/domain/credential-coupled-value-one-read.md`](memory/domains/rust-services-dev/domain/credential-coupled-value-one-read.md) — A value that must stay consistent with a rotating credential (a per-account pseudonym key) is read in the same atomic read as the credential, never from a second source
- [`memory/domains/rust-services-dev/domain/eprintln-panics-on-closed-stderr.md`](memory/domains/rust-services-dev/domain/eprintln-panics-on-closed-stderr.md) — In a stdio child of a host that may die, never eprintln!; it panics on EPIPE (exit 101)
- [`memory/domains/rust-services-dev/domain/git-commit-stamp-watches-per-ref-backend.md`](memory/domains/rust-services-dev/domain/git-commit-stamp-watches-per-ref-backend.md) — A cargo build script that stamps the git commit goes stale unless it watches what each ref backend actually writes
- [`memory/domains/rust-services-dev/domain/guarded-kind-classifier-fails-toward-guard.md`](memory/domains/rust-services-dev/domain/guarded-kind-classifier-fails-toward-guard.md) — When a classifier decides whether a payload takes a protective path, a malformed or unreadable instance of the guarded kind must classify as that kind (three-way answer), never fall through to the forward-raw path
- [`memory/domains/rust-services-dev/domain/hyper-cancellation-and-head-deadline.md`](memory/domains/rust-services-dev/domain/hyper-cancellation-and-head-deadline.md) — What hyper 1.x itself does on body drop and idle connections, and how gateway tests separate it from the gateway's own guards
- [`memory/domains/rust-services-dev/domain/hyper-client-closes-finished-sized-body.md`](memory/domains/rust-services-dev/domain/hyper-client-closes-finished-sized-body.md) — A test proving the gateway closed an upstream connection must leave that response's body unfinished — hyper's client closes a fully-received sized body itself
- [`memory/domains/rust-services-dev/domain/json-line-bound-encoded-size.md`](memory/domains/rust-services-dev/domain/json-line-bound-encoded-size.md) — A byte bound on a JSON line must measure the encoded form: control chars cost 6 bytes escaped, 7 when re-embedded in a JSON string
- [`memory/domains/rust-services-dev/domain/leak-test-failure-messages.md`](memory/domains/rust-services-dev/domain/leak-test-failure-messages.md) — A secret-leak test reports a hit by name and offset, never the bytes; a drop's log line names its class, never the error's Display
- [`memory/domains/rust-services-dev/domain/loss-counter-at-the-drop-site.md`](memory/domains/rust-services-dev/domain/loss-counter-at-the-drop-site.md) — Count dropped messages where the drop happens, never from the event the drop emits
- [`memory/domains/rust-services-dev/domain/loss-counter-is-a-session-read.md`](memory/domains/rust-services-dev/domain/loss-counter-is-a-session-read.md) — Expose loss counts as a pull read scoped to the session with its open instant, not as a pushed field or a cross-session sum
- [`memory/domains/rust-services-dev/domain/managed-settings-linux-path.md`](memory/domains/rust-services-dev/domain/managed-settings-linux-path.md) — Where Claude Code 2.1.286 reads an organisation's managed settings on Linux, and how to present them without root
- [`memory/domains/rust-services-dev/domain/mcp-refused-start.md`](memory/domains/rust-services-dev/domain/mcp-refused-start.md) — Claude Code does not restart a stdio MCP server that exited; a start that cannot work serves a refusing server instead of exiting
- [`memory/domains/rust-services-dev/domain/measurement-claim-scoped-to-runs.md`](memory/domains/rust-services-dev/domain/measurement-claim-scoped-to-runs.md) — Reporting a spike or live measurement: one run is that run's outcome, not a rule; an unreproduced cause is inferred; 'no log line' means none among the patterns searched; unrecorded conditions are named
- [`memory/domains/rust-services-dev/domain/mutation-restore-mtime-stale-build.md`](memory/domains/rust-services-dev/domain/mutation-restore-mtime-stale-build.md) — restoring a file from a backup after a mutation test leaves cargo's mutated build in place; touch the file before the next run
- [`memory/domains/rust-services-dev/domain/nofollow-directory-symlink-enotdir.md`](memory/domains/rust-services-dev/domain/nofollow-directory-symlink-enotdir.md) — openat(O_DIRECTORY|O_NOFOLLOW) on a symlink fails ENOTDIR on Linux, not ELOOP; classify with fstatat
- [`memory/domains/rust-services-dev/domain/package-from-tracked-files.md`](memory/domains/rust-services-dev/domain/package-from-tracked-files.md) — Assemble a release package from the files git tracks, and refuse any untracked or ignored file; cp -R ships strays that .gitignore hides
- [`memory/domains/rust-services-dev/domain/pipefail-head-sigpipe.md`](memory/domains/rust-services-dev/domain/pipefail-head-sigpipe.md) — `cmd | head -1` under `set -euo pipefail` can end a shell script silently; quit inside the producer instead
- [`memory/domains/rust-services-dev/domain/proxy-time-bounds-are-separate-clocks.md`](memory/domains/rust-services-dev/domain/proxy-time-bounds-are-separate-clocks.md) — A streaming proxy's time bounds are three separate clocks (commit deadline, upstream idle, hard ceiling); what each one counts, and the race when a timeout fires
- [`memory/domains/rust-services-dev/domain/refusal-test-proves-its-cause.md`](memory/domains/rust-services-dev/domain/refusal-test-proves-its-cause.md) — A test that a network path is refused must assert why it failed (elapsed time against the timeout, a counter on the intended drop rule), or a missing route or a RST passes it
- [`memory/domains/rust-services-dev/domain/response-commitment-point.md`](memory/domains/rust-services-dev/domain/response-commitment-point.md) — Where a proxied response commits, and what a proxy may and may not do on each side of that point (retry, failover, its own error, an upstream failure)
- [`memory/domains/rust-services-dev/domain/s19-driver-shape.md`](memory/domains/rust-services-dev/domain/s19-driver-shape.md) — Driving a nested claude TUI through a pty: match menu text with spaces squeezed out, and redact ~/ paths
- [`memory/domains/rust-services-dev/domain/serde-derive-accepts-arrays.md`](memory/domains/rust-services-dev/domain/serde-derive-accepts-arrays.md) — A derived serde struct also deserializes from a JSON array; a field probe that must only accept objects needs a map-only visitor
- [`memory/domains/rust-services-dev/domain/serde-tagged-unit-variant-ignores-unknown.md`](memory/domains/rust-services-dev/domain/serde-tagged-unit-variant-ignores-unknown.md) — serde internally tagged enum unit variant accepts unknown keys despite deny_unknown_fields; use an empty struct variant
- [`memory/domains/rust-services-dev/domain/spike-fact-is-its-configuration.md`](memory/domains/rust-services-dev/domain/spike-fact-is-its-configuration.md) — a spike's wire observation describes the client configuration it ran; check it in the configuration the gateway serves and commit it to the record before a contract relies on it
- [`memory/domains/rust-services-dev/domain/tracing-optional-field-omitted.md`](memory/domains/rust-services-dev/domain/tracing-optional-field-omitted.md) — How to make a tracing log field appear only when a value is recorded (absent, not "None"), and validating an HTTP header's shape before logging it
- [`memory/domains/rust-services-dev/domain/tracing-set-default-misses-events.md`](memory/domains/rust-services-dev/domain/tracing-set-default-misses-events.md) — a thread-scoped tracing subscriber in a unit test misses events when other tests hit the same callsite; log tests need their own binary
- [`memory/domains/rust-services-dev/domain/validator-shares-runtime-construction.md`](memory/domains/rust-services-dev/domain/validator-shares-runtime-construction.md) — a validator that copies the runtime's acceptance rule as a pattern drifts both ways; validate by calling the constructor the runtime uses

## solution

- [`.agent-fabric/memory/rust-services-dev/solution/gateway-body-user-id-passthrough.md`](.agent-fabric/memory/rust-services-dev/solution/gateway-body-user-id-passthrough.md) — what end-user identifiers Claude Code and Codex send through the gateway, and the decided forward/drop/hash rule for metadata.user_id (ADR-003 rule 17)
- [`.agent-fabric/memory/rust-services-dev/solution/interweave-bridge-host-line-ceiling.md`](.agent-fabric/memory/rust-services-dev/solution/interweave-bridge-host-line-ceiling.md) — InterWeave claude-channel bounds each host stdin line at 1 MiB before UTF-8/JSON; over-ceiling lines dropped unanswered (PR #330)
- [`.agent-fabric/memory/rust-services-dev/solution/interweave-bridge-size-load-figures.md`](.agent-fabric/memory/rust-services-dev/solution/interweave-bridge-size-load-figures.md) — InterWeave Claude bridge size limits and load behaviour, measured in tests/desktop-e2e (#375, #379; 2026-10-22); the host-line bound and its two-form measure
- [`.agent-fabric/memory/rust-services-dev/solution/plugin-marketplace-strict.md`](.agent-fabric/memory/rust-services-dev/solution/plugin-marketplace-strict.md) — Claude Code 2.1.286 `plugin validate --strict` fails a marketplace.json without metadata.description

## workflow

- [`.agent-fabric/memory/rust-services-dev/workflow/agent-repo-commit.md`](.agent-fabric/memory/rust-services-dev/workflow/agent-repo-commit.md) — how my persona/settings reach my own fabric-agent-<id> repository — never by hand
- [`.agent-fabric/memory/rust-services-dev/workflow/awaiting-supply-user-is-coordinator.md`](.agent-fabric/memory/rust-services-dev/workflow/awaiting-supply-user-is-coordinator.md) — AWAITING-SUPPLY names a login; `user` is the login holding fabric-coordinator, not the owner
- [`.agent-fabric/memory/rust-services-dev/workflow/boundary-arm-authorization.md`](.agent-fabric/memory/rust-services-dev/workflow/boundary-arm-authorization.md) — Arming a PR under the work-commit minimum or on the security boundary: who gives the word per repository, that it must be an AUTHORIZES header for the exact head, and that the count comes from the dry-run, not a CLAUDE.md
- [`.agent-fabric/memory/rust-services-dev/workflow/classifier-session-driver.md`](.agent-fabric/memory/rust-services-dev/workflow/classifier-session-driver.md) — Auto mode refuses a script that launches claude sessions with dev-channel flags, even after the owner says yes in chat; it needs allow rules
- [`.agent-fabric/memory/rust-services-dev/workflow/disk-hygiene.md`](.agent-fabric/memory/rust-services-dev/workflow/disk-hygiene.md) — clean a finished job's worktree target/ when the job ends; the fleet's disks fill up
- [`.agent-fabric/memory/rust-services-dev/workflow/housekeeping-is-not-a-job.md`](.agent-fabric/memory/rust-services-dev/workflow/housekeeping-is-not-a-job.md) — an asked-for cleanup with no PR, commit or reply goes in the active job's note, never as its own job
- [`.agent-fabric/memory/rust-services-dev/workflow/interweave-ci-target-size.md`](.agent-fabric/memory/rust-services-dev/workflow/interweave-ci-target-size.md) — one InterWeave `cargo xtask ci` grows target/ to ~64G on the shared /home; clean it when the run ends
- [`.agent-fabric/memory/rust-services-dev/workflow/interweave-pr-merge-order-repin.md`](.agent-fabric/memory/rust-services-dev/workflow/interweave-pr-merge-order-repin.md) — When two open InterWeave PRs interact through a test that pins behaviour the other changes, agree up front that whichever lands second re-pins, and expect the merge queue to catch it
- [`.agent-fabric/memory/rust-services-dev/workflow/interweave-suite-crate-partition.md`](.agent-fabric/memory/rust-services-dev/workflow/interweave-suite-crate-partition.md) — InterWeave root test suites (tests/<suite>/) are partitioned by file between open PRs, not by crate; library and app crates stay one open PR per crate
- [`.agent-fabric/memory/rust-services-dev/workflow/one-taken-reply-after-job-add.md`](.agent-fabric/memory/rust-services-dev/workflow/one-taken-reply-after-job-add.md) — Taking a REQUEST: create the job first, read its branch from fabric-jobs show, then send one 'taken' REPLY; later facts go in a delivery, not a second 'taken'
- [`.agent-fabric/memory/rust-services-dev/workflow/operator-reason-labels-are-contract.md`](.agent-fabric/memory/rust-services-dev/workflow/operator-reason-labels-are-contract.md) — A drop or refusal counter's reason labels are a closed set the contract states by name; every key is reported with zero; distinct attacker shapes get distinct reasons; a list the contract enumerates is held to its table by a test
- [`.agent-fabric/memory/rust-services-dev/workflow/qualifier-travels-with-restatement.md`](.agent-fabric/memory/rust-services-dev/workflow/qualifier-travels-with-restatement.md) — A fact read (not measured) keeps 'read from the binary, not measured' and its conditions in every restatement, supplied text included
- [`.agent-fabric/memory/rust-services-dev/workflow/rustup-pin.md`](.agent-fabric/memory/rust-services-dev/workflow/rustup-pin.md) — Which cargo runs on this account, and why a rust-toolchain.toml pin was ignored before 2026-10-19
- [`.agent-fabric/memory/rust-services-dev/workflow/rustup-pinned-toolchain.md`](.agent-fabric/memory/rust-services-dev/workflow/rustup-pinned-toolchain.md) — which cargo/rustc this account builds the gateway with, and since when the rust-toolchain.toml pin is honoured
- [`.agent-fabric/memory/rust-services-dev/workflow/shape-only-capture.md`](.agent-fabric/memory/rust-services-dev/workflow/shape-only-capture.md) — how to measure what identifiers a harness sends without recording any value; reading a login's real Claude config is refused

## threads

- [`.agent-fabric/memory/rust-services-dev/threads/interweave-bridge-contact-card.md`](.agent-fabric/memory/rust-services-dev/threads/interweave-bridge-contact-card.md) — j57, InterWeave bridge shows a contact_card to the model as meta only; merged as #356 on 2026-10-22
- [`.agent-fabric/memory/rust-services-dev/threads/interweave-c05-bridge-r7.md`](.agent-fabric/memory/rust-services-dev/threads/interweave-c05-bridge-r7.md) — j58 InterWeave SECURITY-MATRIX C-05 run R7 bridge side — branch, split with p2p-network-dev-02, host-line ceiling already on main

## recall

- [`identities/roles/rust-services-dev/recall.md`](identities/roles/rust-services-dev/recall.md) — Where rust-services-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
