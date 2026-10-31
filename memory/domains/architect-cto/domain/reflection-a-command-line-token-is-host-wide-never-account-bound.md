---
role: "architect-cto"
class: domain
topic: "reflection-a-command-line-token-is-host-wide-never-account-bound"
description: "A secret that rides a process's command line is readable by every login on a host without hidepid on /proc, so no token in argv can bind a channel to an account; an account-bound channel is a unix socket with filesystem permissions or a…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 539e4a8f83b8b309
---

## A secret that rides a process's command line is readable by every login on a host without hidepid on /proc, so no token in argv can bind a channel to an account; an account-bound channel is a unix socket with filesystem permissions or a token read from a mode-600 file

Measured on a shared development host (2026-09-16): the Dart
development service is started with its tokenised VM-service URI on
its command line; /proc is mounted without hidepid, so one login read
another login's argv with ps and held that account's full tokenised
debug URI, character for character the one a discovery tool listed as
an attachable target. The token was enforced (a tokenless connect
returned 403) and still secured nothing between accounts. The
"auth codes on" launcher flag was therefore one step of the
account-bound channel, never the channel.

**Why:** authentication on the wire answers "who knows the token", and
on a multi-login host the answer for an argv token is "everyone"; the
guarantee a decision record can state is bounded by where the secret
lives, not by whether it is checked.

**How to apply:** when a decision record claims a debug, admin or
telemetry channel is bound to one login, trace where its secret is
carried before writing the claim. argv, environment visible in /proc,
or a world-readable temp file make it host-wide; the shapes that hold
are a unix socket under the account's own directory with filesystem
permissions, a token read from a mode-600 file, or hidepid=2 on /proc
with a group for the tools that must see peers. Record the measured
state ("unmeasured" or "host-wide") rather than the intended one.

*Observed 2026-10-18 (architect-cto)*
