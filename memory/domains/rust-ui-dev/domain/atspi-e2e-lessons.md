---
role: "rust-ui-dev"
class: domain
topic: "atspi-e2e-lessons"
description: "Driving a Slint/AccessKit window over AT-SPI in tests -- what the adapter answers, focus under Xvfb, hearing announcements, SELinux on this host"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - bfc33a1097346ee2
---

## Driving a Slint/AccessKit window over AT-SPI in tests -- what the adapter answers, focus under Xvfb, hearing announcements, SELinux on this host

Learned building tests/desktop-e2e/tests/human_app/a11y.rs (2026-10-04, commit 8b497609):
- AccessKit's AT-SPI adapter does NOT implement GetRoleName or the NActions property: use GetRole + Role::name() ("button", "list item", "label") and GetActions. pyatspi hides this (computes client-side).
- Find a client by process: registry root children -> bus unique name -> org.freedesktop.DBus.GetConnectionUnixProcessID on the a11y bus (parallel tests share one bus).
- Live regions: AccessKit emits org.a11y.atspi.Event.Object "Announcement" (siiva{sv}, text in the variant) when a live node is added/changes; the test can HEAR announcements -- mutation `accessible-live-region: off` makes it fail.
- Xvfb has no window manager: a window never gets input focus by itself; give it with x11rb set_input_focus on the window whose _NET_WM_PID is the pid. Only one window holds focus, so focus-dependent cases are serialized (static tokio Mutex).
- Find the a11y bus like a screen reader: session bus org.a11y.Bus GetAddress (CI's tools/ci/with_display.sh does not export AT_SPI_BUS_ADDRESS).
- On develop-qzapp (SELinux enforcing) dbus activation of at-spi (gnome_atspi_exec_t) is denied. As seen in the tree 2026-10-05, tools/ci/with_display.sh handles it (starts launcher+registryd directly on a Spawn error) -- no hand script needed. `cargo xtask ci` runs cargo test WITHOUT the wrapper, so locally the 4 AT-SPI cases (accessibility + reading::*) fail with 'never reached the AT-SPI registry, which lists []' -- environment, not code; re-run `tools/ci/with_display.sh cargo test --workspace --all-targets --no-fail-fast` (cargo test stops at the first failing binary otherwise).
- A shared target/ with a worktree build of another tree left a stale rmeta (compile error naming a variant absent from source): `cargo clean -p` the crates named.
Related: [[slint-rendered-window-lessons]], [[desktop-e2e-stale-binary]]

*References: desktop-e2e-stale-binary, slint-rendered-window-lessons*

*Observed 2026-10-05 (rust-ui-dev)*
