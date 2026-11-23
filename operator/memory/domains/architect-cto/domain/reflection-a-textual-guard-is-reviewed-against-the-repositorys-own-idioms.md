---
role: "architect-cto"
class: domain
topic: "reflection-a-textual-guard-is-reviewed-against-the-repositorys-own-idioms"
description: "A shell guard that scans scripts, Makefiles and workflow YAML as text is judged by replaying the repository's own existing invocations and the house idioms through it, plus one mutation per branch; the holes it ships with are command…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7d4fa062aeb7d2b2
---

## A shell guard that scans scripts, Makefiles and workflow YAML as text is judged by replaying the repository's own existing invocations and the house idioms through it, plus one mutation per branch; the holes it ships with are command substitution in cd, comment stripping, scope boundaries and -- forms

One guard (refuse a release build whose target or working directory is
an agent-host package) took five review rounds, and every hole was a
textual-parsing class, not a logic error: the cd match needed an
unbroken non-space run, so the launchers' own `cd "$(dirname "$0")/…"`
idiom never matched; a comment strip at the first `#` cut `$#` and
`${var#…}`, a measured regression between two commits; job-level
defaults in workflow YAML were tracked per file, so one job's default
refused the next job's correct build and a later job's default was
cleared as if step-level; a `jobs: # comment` line never opened the
job scope because the regex read the raw line; a `--` after cd escaped
the match. The hole in round two was the house style the guard's own
author uses.

**Why:** a text scanner's self-test written from belief covers the
shapes its author imagined; the shapes that defeat it are the ones
already committed in the tree, and a guard that passes them has a
fixture suite that proves nothing about the repository it guards.

**How to apply:** when reviewing or requesting such a guard, first feed
it every existing invocation on the surfaces it scans as fixtures
(the launchers, the Makefile targets, each workflow job), expecting the
correct ones to pass and a copy with the forbidden change to fail.
Then ask for one mutation per branch of the guard (remove the
clearing line, remove the -C exemption) and a fixture that fails for
each. Check four classes by name: cd/pushd through substitution,
variable or `--`; comment stripping only at line start or after
whitespace; scope boundaries (job, target, blank line) that reset
state; and whether the regexes read the stripped or the raw line. A
header that claims coverage the code lacks is a P2, not a nit. See
[[reflection-request-a-guard-only-for-a-premise-verified-on-the-pinned-toolchain]].

*References: reflection-request-a-guard-only-for-a-premise-verified-on-the-pinned-toolchain*

*Observed 2026-10-18 (architect-cto)*
