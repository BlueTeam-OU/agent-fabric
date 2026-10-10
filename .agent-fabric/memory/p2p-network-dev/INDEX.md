---
role: "p2p-network-dev"
class: index
description: "What p2p-network-dev knows and where it lives."
tier: 1
distilled_at: "2026-10-10"
---

# p2p-network-dev — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/p2p-network-dev/charter.md`](identities/roles/p2p-network-dev/charter.md) — The fleet's peer-to-peer networking developer in Rust: transports, discovery, peer routing, NAT traversal and the admission discipline around them, on libp2p, proven over real sockets.

## brief

- [`identities/roles/p2p-network-dev/brief.md`](identities/roles/p2p-network-dev/brief.md) — How p2p-network-dev works day to day, in any project: start from the end-to-end network behaviour, design from stated invariants, prove between real peers, deliver evidence by level.

## domain

- [`memory/domains/p2p-network-dev/domain/a-select-guard-is-read-only-when-the-loop-wakes.md`](memory/domains/p2p-network-dev/domain/a-select-guard-is-read-only-when-the-loop-wakes.md) — A tokio::select! branch guard (`if lane.capacity() > 0`) is evaluated only when the loop wakes; waiting on another task to free room stalls forever on a connection with no timer. #151 had it twice
- [`memory/domains/p2p-network-dev/domain/a-version-gate-has-two-sides.md`](memory/domains/p2p-network-dev/domain/a-version-gate-has-two-sides.md) — An additive-minor rule gates emission AND acceptance; put the version in the decoder's signature so no reader can skip it
- [`memory/domains/p2p-network-dev/domain/apostrophe-breaks-quoted-python.md`](memory/domains/p2p-network-dev/domain/apostrophe-breaks-quoted-python.md) — An apostrophe in a comment inside a shell script's single-quoted python block silently ends the quote; bash -n passes and the failure surfaces as a runtime syntax error far from the edit
- [`memory/domains/p2p-network-dev/domain/autonat-client-crate-facts.md`](memory/domains/p2p-network-dev/domain/autonat-client-crate-facts.md) — What libp2p-autonat 0.15.0's v2 CLIENT actually does — measured, and contradicting several accepted documents
- [`memory/domains/p2p-network-dev/domain/cancel-a-future-after-one-poll.md`](memory/domains/p2p-network-dev/domain/cancel-a-future-after-one-poll.md) — To test "a caller that gave up after its command was sent", poll once with Waker::noop on a current-thread runtime; tokio::time::timeout(Duration::ZERO) does NOT cancel after one poll
- [`memory/domains/p2p-network-dev/domain/cargo-metadata-does-not-typecheck.md`](memory/domains/p2p-network-dev/domain/cargo-metadata-does-not-typecheck.md) — a guard built on `cargo metadata --locked` cannot see a pin whose source does not compile against it — only `cargo check --locked` can
- [`memory/domains/p2p-network-dev/domain/claude-code-channel-facts-2-1-285.md`](memory/domains/p2p-network-dev/domain/claude-code-channel-facts-2-1-285.md) — Measured Claude Code 2.1.285 channel behaviour (SPIKE-001, PR #172): handshake, enabling, rendering, escaping, tools, shutdown, crash; and how to drive a nested Claude session as evidence
- [`memory/domains/p2p-network-dev/domain/error-text-matching-pins-the-public-type.md`](memory/domains/p2p-network-dev/domain/error-text-matching-pins-the-public-type.md) — when a dependency's error is unexported and matched by its Display text, pin the text on the TYPE THE CALLER RECEIVES and feed the classifier a real event — the AutoNAT client's public Error wraps DialBackError and displays that, so a…
- [`memory/domains/p2p-network-dev/domain/libp2p-facts-from-the-hop-gate-and-keepalive.md`](memory/domains/p2p-network-dev/domain/libp2p-facts-from-the-hop-gate-and-keepalive.md) — libp2p 0.57 facts that bit building the relay hop gate, close-on-removal and the relay keepalive (#129) — outbound local IP, ping's give-up, relay's per-connection ReservationClosed, pub(crate) handler events
- [`memory/domains/p2p-network-dev/domain/libp2p-relay-022-release-frees-the-connection.md`](memory/domains/p2p-network-dev/domain/libp2p-relay-022-release-frees-the-connection.md) — libp2p-relay 0.22.0's client resets a reservation when its listener closes, so a released reservation's connection idles out; 0.21.1 held and renewed it for up to an hour
- [`memory/domains/p2p-network-dev/domain/libp2p-relay-client-listener-semantics.md`](memory/domains/p2p-network-dev/domain/libp2p-relay-client-listener-semantics.md) — What libp2p-relay 0.21.1's client actually reports for a reservation -- addresses are the relay's external ones, one NewListenAddr each, re-emitted on renewal; every failure and a release alike end in ListenerClosed
- [`memory/domains/p2p-network-dev/domain/libp2p-tcp-dials-the-last-host-of-a-stacked-multiaddr.md`](memory/domains/p2p-network-dev/domain/libp2p-tcp-dials-the-last-host-of-a-stacked-multiaddr.md) — An address-class predicate that reads only the first /ip4|/ip6 pair is bypassed by stacking a second host behind a public literal; judge the whole multiaddr shape
- [`memory/domains/p2p-network-dev/domain/never-share-a-target-dir-across-worktrees.md`](memory/domains/p2p-network-dev/domain/never-share-a-target-dir-across-worktrees.md) — A worktree of main built with the repo's CARGO_TARGET_DIR overwrote workspace-member artifacts; the branch's next full CI failed to compile on a constant main lacked
- [`memory/domains/p2p-network-dev/domain/per-arch-constants-come-from-libc.md`](memory/domains/p2p-network-dev/domain/per-arch-constants-come-from-libc.md) — Never hand-type an open(2) flag per architecture; take it from libc — CI runs x86_64 only, so no test catches a wrong arm
- [`memory/domains/p2p-network-dev/domain/race-tests-need-the-current-thread-runtime.md`](memory/domains/p2p-network-dev/domain/race-tests-need-the-current-thread-runtime.md) — A select! race between a finished task's join and a signal another task sets is invisible on tokio's multi-thread runtime (LIFO slot); reproduce it on current_thread
- [`memory/domains/p2p-network-dev/domain/reach-the-last-slot-of-a-bounded-channel-by-parity.md`](memory/domains/p2p-network-dev/domain/reach-the-last-slot-of-a-bounded-channel-by-parity.md) — Testing "a command took the channel's last slot and its follow-up found it full" -- overfilling makes the test vacuous; alternate two sends and run padded 0 and 1 so one run is odd
- [`memory/domains/p2p-network-dev/domain/replacing-a-libp2p-behaviour-leaks-its-tasks.md`](memory/domains/p2p-network-dev/domain/replacing-a-libp2p-behaviour-leaks-its-tasks.md) — before swapping a libp2p behaviour at runtime, check what its Drop stops — tokio JoinHandles detach, so spawned tasks outlive it
- [`memory/domains/p2p-network-dev/domain/state-is-never-refused-by-an-input-queue.md`](memory/domains/p2p-network-dev/domain/state-is-never-refused-by-an-input-queue.md) — A bounded input queue mixing presses with STATE (edits, focus): refuse only presses, coalesce state in place, hold nothing aside; three #170 rounds came from violating this
- [`memory/domains/p2p-network-dev/domain/tokio-signal-handler-outlives-its-stream.md`](memory/domains/p2p-network-dev/domain/tokio-signal-handler-outlives-its-stream.md) — tokio::signal::unix::signal installs a process-wide OS handler that stays after the Signal stream is dropped; a mutation that drops the stream removes nothing
- [`memory/domains/p2p-network-dev/domain/yamux-silent-downgrade.md`](memory/domains/p2p-network-dev/domain/yamux-silent-downgrade.md) — Tuning libp2p yamux via any setter silently swaps the muxer to vulnerable yamux 0.12.1, and cargo-deny cannot see that advisory
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## recall

- [`identities/roles/p2p-network-dev/recall.md`](identities/roles/p2p-network-dev/recall.md) — Where p2p-network-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
