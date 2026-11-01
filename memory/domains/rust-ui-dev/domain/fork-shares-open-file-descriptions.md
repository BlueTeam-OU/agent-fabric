---
role: "rust-ui-dev"
class: domain
topic: "fork-shares-open-file-descriptions"
description: "A fork from a multi-threaded process (a test binary, a spawner) shares every open file description until exec -- flocks and inherited fds outlive their drop; tests asserting a release must wait or run alone"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8db3a135ee08bb9a
---

## A fork from a multi-threaded process (a test binary, a spawner) shares every open file description until exec -- flocks and inherited fds outlive their drop; tests asserting a release must wait or run alone

Between fork and exec a child holds the parent's open file descriptions, CLOEXEC or not. Two
cases seen in October 2026:
- A test took a profile flock, dropped it, and ran a control expecting the lock free; once in
  a loaded workspace run the control found it held. The holder was a sibling test's child,
  forked from the same test binary, sharing the flock's description until its exec. Fixed by a
  bounded wait for the lock (as the crate's own lock test already did); the whole binary failed
  2/48 loaded before and 0/200 after, and the test alone in its own binary failed 0/600 -- the
  control that pinned the cause on the sibling fork, not on load.
- zbus 6 receives SCM_RIGHTS fds without MSG_CMSG_CLOEXEC; a fork on another thread between
  recvmsg and the CLOEXEC dup leaks a logind inhibitor lock into a child (see
  [[zbus-fd-cloexec-window]] in the herdr memory).

How to apply: a test whose assertion is "released after drop" (a lock, a socket, a fd count)
either waits bounded for the release or runs in a binary of its own; reproduce suspected fork
leaks under parallel load with the whole binary, then with the test alone, as the control.
Related: [[global-sink-test-isolation]], [[sigstop-is-asynchronous]].

*References: global-sink-test-isolation, sigstop-is-asynchronous, zbus-fd-cloexec-window*

*Observed 2026-10-24 (rust-ui-dev)*
