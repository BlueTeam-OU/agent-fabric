---
role: "rust-ui-dev"
class: index
description: "What rust-ui-dev knows and where it lives."
tier: 1
distilled_at: "2026-10-18"
---

# rust-ui-dev — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/rust-ui-dev/charter.md`](identities/roles/rust-ui-dev/charter.md) — The fleet's native-client developer in Rust: the user interface on Slint across desktop and mobile, its accessibility, the client's local store and its privacy posture, and the acceptance tests a person's use of it must pass.

## brief

- [`identities/roles/rust-ui-dev/brief.md`](identities/roles/rust-ui-dev/brief.md) — How rust-ui-dev works day to day, in any project: a change begins from the person's journey, is designed as well as built, rests on agreed contracts, and is verified in the rendered client on every platform before it is called done.

## domain

- [`memory/domains/rust-ui-dev/domain/android-ndk-context-and-dns.md`](memory/domains/rust-ui-dev/domain/android-ndk-context-and-dns.md) — Rust networking crates on Android -- system resolver config needs ndk_context (panics outside an Activity process); feed DNS from the platform's per-network view instead
- [`memory/domains/rust-ui-dev/domain/android-no-hard-links.md`](memory/domains/rust-ui-dev/domain/android-no-hard-links.md) — Android app processes cannot link(2) in their data dir (SELinux untrusted_app), so any create-via-hard-link persistence fails with EACCES on a phone and passes on the host
- [`memory/domains/rust-ui-dev/domain/android-private-dir-ancestors.md`](memory/domains/rust-ui-dev/domain/android-private-dir-ancestors.md) — Owner-only directory checks on Android -- /data is 0771 system and files/ is 0771 app-gid, so the ancestor walk needs a platform trust boundary
- [`memory/domains/rust-ui-dev/domain/android-settings-observe-live.md`](memory/domains/rust-ui-dev/domain/android-settings-observe-live.md) — Android settings a UI follows (accessibility timeouts, animator scale, 12/24-hour) change while the app is in front -- observe them, never read once at start or resume
- [`memory/domains/rust-ui-dev/domain/atspi-e2e-lessons.md`](memory/domains/rust-ui-dev/domain/atspi-e2e-lessons.md) — Driving a Slint/AccessKit window over AT-SPI in tests -- what the adapter answers, focus under Xvfb, hearing announcements, SELinux on this host
- [`memory/domains/rust-ui-dev/domain/bounded-drain-not-exhausted.md`](memory/domains/rust-ui-dev/domain/bounded-drain-not-exhausted.md) — Consuming a bounded event drain -- a short or empty return is not "nothing left" when notices, duplicates or undecodable items take slots
- [`memory/domains/rust-ui-dev/domain/cargo-graph-all-targets.md`](memory/domains/rust-ui-dev/domain/cargo-graph-all-targets.md) — Choosing a GUI backend crate set -- Cargo resolves every target's cfg-gated deps, so measure candidates in a scratch copy under cargo deny
- [`memory/domains/rust-ui-dev/domain/commit-show-before-awaiting.md`](memory/domains/rust-ui-dev/domain/commit-show-before-awaiting.md) — A client command that commits state must hand its update to the view before it awaits the network; an inline first attempt hides the committed row and coalesces away "Sending"
- [`memory/domains/rust-ui-dev/domain/dashboard-data-freshness.md`](memory/domains/rust-ui-dev/domain/dashboard-data-freshness.md) — Status boards over many sources -- each value keeps its own freshness, stale shows age and why, unknown or failed is never drawn as none or zero
- [`memory/domains/rust-ui-dev/domain/device-case-reads-while-connected.md`](memory/domains/rust-ui-dev/domain/device-case-reads-while-connected.md) — an e2e assertion on connection-scoped UI state (route indicator) must read it while the peer is still connected; a phone's case ends its runtime when it answers
- [`memory/domains/rust-ui-dev/domain/device-tests-host-first.md`](memory/domains/rust-ui-dev/domain/device-tests-host-first.md) — Instrumented device tests for a Rust core in an Android app -- run the same case bodies on a host stand-in of the SAME composition first, so a device failure is a platform fact
- [`memory/domains/rust-ui-dev/domain/e2e-waits-from-dependency-cadence.md`](memory/domains/rust-ui-dev/domain/e2e-waits-from-dependency-cadence.md) — Fixing end-to-end flakes against a networked service -- reproduce under parallel load, bound waits by the state needed or by the dependency's retry cadence, probe the right readiness
- [`memory/domains/rust-ui-dev/domain/effective-state-from-the-operation.md`](memory/domains/rust-ui-dev/domain/effective-state-from-the-operation.md) — A client choosing among server-side resources (which endpoint to claim) -- use the operation's own answer as the effective state, not a separate list read
- [`memory/domains/rust-ui-dev/domain/error-display-source-chain.md`](memory/domains/rust-ui-dev/domain/error-display-source-chain.md) — Diagnosing an opaque Rust error from a device -- Display can be empty, the cause sits in source(); never flatten an error with to_string()
- [`memory/domains/rust-ui-dev/domain/global-sink-test-isolation.md`](memory/domains/rust-ui-dev/domain/global-sink-test-isolation.md) — A Rust test that counts lines in a process-global log or sink flakes when sibling tests in the same binary emit the same line in parallel -- give it its own binary
- [`memory/domains/rust-ui-dev/domain/network-denied-posture.md`](memory/domains/rust-ui-dev/domain/network-denied-posture.md) — Designing a client's state when the platform refuses it network access (Android 17 runtime INTERNET) -- local data stays usable, no false promise, one action
- [`memory/domains/rust-ui-dev/domain/peer-chosen-dedup-ids.md`](memory/domains/rust-ui-dev/domain/peer-chosen-dedup-ids.md) — Deduplicating received messages by a peer-chosen id -- compare content too, and never let dedup hide a row the store still holds
- [`memory/domains/rust-ui-dev/domain/platform-copy-per-situation.md`](memory/domains/rust-ui-dev/domain/platform-copy-per-situation.md) — One shared UI text table across desktop and mobile when the remedy differs by platform -- one key per situation, per-platform values chosen at the composition root
- [`memory/domains/rust-ui-dev/domain/refusal-leaves-tree-untouched.md`](memory/domains/rust-ui-dev/domain/refusal-leaves-tree-untouched.md) — A refused start or lock acquire must judge every existing directory before creating anything, and its test must assert the directory is absent too
- [`memory/domains/rust-ui-dev/domain/runtime-end-wakes-service.md`](memory/domains/rust-ui-dev/domain/runtime-end-wakes-service.md) — Hosting an embedded runtime in an Android foreground service -- the blocking wait must also return when the runtime dies on its own, distinguishably
- [`memory/domains/rust-ui-dev/domain/security-overlay-loss-asymmetry.md`](memory/domains/rust-ui-dev/domain/security-overlay-loss-asymmetry.md) — Judging a security setting that does not survive a restart -- a lost revoke silently re-admits, which honest copy does not fix
- [`memory/domains/rust-ui-dev/domain/slint-changed-handlers-deferred.md`](memory/domains/rust-ui-dev/domain/slint-changed-handlers-deferred.md) — Slint `changed prop =>` handlers run at the event loop's next turn, not on the change; never keep a Rust copy of a window-derived state, read it live
- [`memory/domains/rust-ui-dev/domain/slint-rendered-window-lessons.md`](memory/domains/rust-ui-dev/domain/slint-rendered-window-lessons.md) — Slint 1.18 layout/font traps the testing backend does not show -- monospace by name, wrap min-width, a component's height from its only child layout; look at the winit window under Xvfb
- [`memory/domains/rust-ui-dev/domain/slint-royalty-free-attribution.md`](memory/domains/rust-ui-dev/domain/slint-royalty-free-attribution.md) — Meeting the Slint Royalty-free 2.0 attribution duty -- AboutSlint needs an image feature; the download-page badge is the alternative
- [`memory/domains/rust-ui-dev/domain/slint-styledtext-links.md`](memory/domains/rust-ui-dev/domain/slint-styledtext-links.md) — Rendering rich message text in Slint -- StyledText links are pointer-only and from_markdown is a second parser; draw from your own tree, links as separate controls
- [`memory/domains/rust-ui-dev/domain/slint-swipe-in-flickable.md`](memory/domains/rust-ui-dev/domain/slint-swipe-in-flickable.md) — Slint 1.18.1 swipe rows inside a Flickable: what the toolkit does to a press, how to move a row without breaking its height, what a device showed (j82, #289)
- [`memory/domains/rust-ui-dev/domain/slint-window-size-binding-loop.md`](memory/domains/rust-ui-dev/domain/slint-window-size-binding-loop.md) — Slint 1.18 reads a Window's width/height as its layout info, so a responsive flag on root.width loops; a placed child (x/y) leaves the root's layout info; SLINT_COMPILER_DENY_WARNINGS
- [`memory/domains/rust-ui-dev/domain/sqlite-deletion-residue.md`](memory/domains/rust-ui-dev/domain/sqlite-deletion-residue.md) — Proving deletion in a SQLite local store -- where released plaintext survives (freed cells, WAL), the pragmas that remove it, and the byte-search test with a live control
- [`memory/domains/rust-ui-dev/domain/state-machine-signals-read-back.md`](memory/domains/rust-ui-dev/domain/state-machine-signals-read-back.md) — Before encoding a UI state machine someone else specified -- read every signal back live; unobservable ones are a finding with an observable substitute
- [`memory/domains/rust-ui-dev/domain/talkback-on-opens-permission-dialog.md`](memory/domains/rust-ui-dev/domain/talkback-on-opens-permission-dialog.md) — Turning TalkBack on over adb on the Pixel 9a opens a phone-call permission dialog that takes every injected key; check the focused window before each step
- [`memory/domains/rust-ui-dev/domain/terminal-keys-no-collision.md`](memory/domains/rust-ui-dev/domain/terminal-keys-no-collision.md) — Choosing key bindings for a terminal multiplexer that hosts agent harnesses -- every key reaches the pane; own actions on keys no harness, shell or desktop uses, pinned by a test
- [`memory/domains/rust-ui-dev/domain/tests-under-umask-002.md`](memory/domains/rust-ui-dev/domain/tests-under-umask-002.md) — Tests of owner-only-directory code pass under umask 022 and fail under 002 with a shared primary group -- make test dirs 0700 explicitly
- [`memory/domains/rust-ui-dev/domain/type-encode-ui-rules.md`](memory/domains/rust-ui-dev/domain/type-encode-ui-rules.md) — Agreeing an API a client renders or acts on -- put the UI's rule in the type: closed error enums, markers for forbidden values, diagnostics off the view's type, tested code tables across FFI
- [`memory/domains/rust-ui-dev/domain/ui-deferred-input-queue.md`](memory/domains/rust-ui-dev/domain/ui-deferred-input-queue.md) — When view callbacks queue raw input that is resolved later against the model -- identity not position, never reorder, drop newest, text and focus are state
- [`memory/domains/rust-ui-dev/domain/ui-thread-wakeups-bounded.md`](memory/domains/rust-ui-dev/domain/ui-thread-wakeups-bounded.md) — Bridging a worker thread to a Slint window -- invoke_from_event_loop per message is an unbounded queue; bound the channel and coalesce the wake-up
- [`memory/domains/rust-ui-dev/domain/uncertain-outcome-state-and-copy.md`](memory/domains/rust-ui-dev/domain/uncertain-outcome-state-and-copy.md) — How a client shows an operation whose outcome is unknown -- classify by dispatch state, monotone may-have-reached, copy that never claims nothing changed
- [`memory/domains/rust-ui-dev/domain/untrusted-text-in-terminal-views.md`](memory/domains/rust-ui-dev/domain/untrusted-text-in-terminal-views.md) — Drawing text other accounts or agents wrote in a terminal UI -- sanitise to cells, show as plain text, never invent a reason
- [`memory/domains/rust-ui-dev/domain/vuln-ignore-entries-checked.md`](memory/domains/rust-ui-dev/domain/vuln-ignore-entries-checked.md) — Accepting a known vulnerability in a build-tool classpath (OSV/cargo-deny ignore) -- the entry names what was checked and when, and ends early on a new stable release

## solution

- [`.agent-fabric/memory/rust-ui-dev/solution.md`](.agent-fabric/memory/rust-ui-dev/solution.md) — an Undo of a destructive outbound action restores the deleted record (ids + stored bytes), never a re-composed copy; held in session memory only

## recall

- [`identities/roles/rust-ui-dev/recall.md`](identities/roles/rust-ui-dev/recall.md) — Where rust-ui-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
