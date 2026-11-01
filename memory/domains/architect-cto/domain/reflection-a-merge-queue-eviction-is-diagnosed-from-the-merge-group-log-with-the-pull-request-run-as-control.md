---
role: "architect-cto"
class: domain
topic: "reflection-a-merge-queue-eviction-is-diagnosed-from-the-merge-group-log-with-the-pull-request-run-as-control"
description: "W44 - a PR evicted from GitHub's merge queue is diagnosed before it is re-armed: read the merge_group run's failing step, with the pull_request run of the same head as the control; an install or CDN failure re-arms the unchanged head, a…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-01"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c32a75dee61d4d73
---

## W44 - a PR evicted from GitHub's merge queue is diagnosed before it is re-armed: read the merge_group run's failing step, with the pull_request run of the same head as the control; an install or CDN failure re-arms the unchanged head, a one-in-N test failure is an OBSERVATION to the owning lane and its deflake lands alone as the CI-blocking exception; every eviction costs each queued PR a full run

Three evictions in a week, three causes. gzapp #1170 (2026-10-25):
all four backend shards died in actions/setup-dotnet 75 s in ("Could
not find .NET Core SDK 10.0.403"), no test ran; the pull_request run
on the same head had passed with the same pin minutes earlier, so the
vendor endpoint was the cause and the re-arm re-queued the same head.
gzapp #1176 (docs only, ADR text): evicted by a shared Flutter test
that passed in the two merge_group runs before and in both of the
PR's own runs; the OBSERVATION went to the lowest-numbered running
flutter-dev with nothing in flight on the path, who reproduced it
(the test awaited pumpEventQueue, not the body controller's
onListen; a loaded runner let cancel land first) and landed the fix
alone on #1177, armed below the floor the same hour. InterWeave #501:
evicted by relay_client's released-port-0 fixture racing another
nextest process; the free_port class landed alone on #504 and #507.

**Why:** a merge_group failure says nothing about the diff by itself;
the control is the same head's pull_request run. An eviction costs
every queued PR a full detector-bypassed run (28 minutes on gzapp)
plus a re-arm, so a flake is worth landing before the next queue run,
and the one-open-PR rule names a CI-blocking fix as its exception.

**How to apply:** `gh run view <merge_group run> --json jobs`, name
the failing step and quote its error; read the pull_request run on
the same head; write the OBSERVATION with VERIFIED (the control),
NOT-VERIFIED (cause, frequency) and IMPACT (a re-arm re-queues the
unchanged head; if it fails the same way it is devex-tooling's CI
lane). Re-arm an infrastructure eviction at once; a flake goes to the
lane that owns the test, and its fix arms on my word below the floor.
Related: [[reflection-a-queued-pr-reports-no-automerge-request]],
[[owner-merge-asap-on-another-roles-pr-is-a-drive]].

*References: owner-merge-asap-on-another-roles-pr-is-a-drive, reflection-a-queued-pr-reports-no-automerge-request*

*Observed 2026-10-31 (architect-cto)*
