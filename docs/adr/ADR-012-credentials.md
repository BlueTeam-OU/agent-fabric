# ADR-012 — Credentials

**Date:** 2026-09-14
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #51 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** fabric-coordinator (the Doppler layout, 2026-09-14; the credential rules of the launcher, review of #31 and #33); the GZCoord protocol's §17 (a secret by shape and locator)
**Scope:** every credential an agent account uses: Doppler project `agent-fabric`, runtime/provisioning/secrets/ (enroll.sh, enroll-worker.sh, fabric-secrets), ~/.config/agent-fabric/secrets.env, runtime/openrouter/launch's credential handling, and how a secret may appear in a message, a commit, a log or a test
**Pillar:** P1

## 1. Context and Problem

Each agent is a Linux login, and each needs its own credentials: an
OpenRouter key, a GitHub token, an OpenAI key, a GZCoord token, a git
identity and signing key, an SSH key, and for plain claude a Claude sign-in.
Before 2026-09-14 they lived in each account's shell profile, a clone's
`settings.local.json` and `gh`'s stored login — scattered, copied by hand,
and not attributable per agent.

Two failures shaped the rules around them. A secret quoted as "evidence"
in a message is a second copy in a second place, and every reply, review
and transcript that relays it is another. And on 2026-09-23 (review of
#31) a fix cleared `ANTHROPIC_BASE_URL` for a plain-claude child launched
from a broker session but kept `ANTHROPIC_API_KEY`, where `ori claude` puts
the account's **OpenRouter** key: the child would have sent that key to
`api.anthropic.com`. The fix made a worse defect than the one it closed.

## 2. Decision

An identity's secrets are recorded in **Doppler**, project `agent-fabric`,
**one config per Linux login** (the branch config `<env>_<login>` under
`agents`, `agents2`, … — the login is the branch, never the environment).
Each account holds exactly one bootstrap secret, a read-only service token
for its own config; `bin/fabric-secrets sync`, run as the account, puts
everything else where the tools read it (`~/.config/agent-fabric/secrets.env`
0600, `~/.gitconfig`, `~/.ssh/`). **Credentials never enter a committed
file.**

Around that record:

- a secret is **never reproduced** — not in a message, a log, a commit, a
  test's output — and is described **by shape and locator**;
- **a destination and its credential move together**: a change to where a
  request goes moves every credential and header bound to that destination
  in the same change, with a destination-independent check on the secret
  itself;
- credentials are **tested by shape**, never by value.

## 3. Alternatives Considered

- **Keys in each account's shell profile or a clone's settings.** The state
  before; retired by `enroll.sh`, which migrates and removes the old
  sources.
- **One Doppler environment per login.** Not possible on the plan in use
  (four environments of ten configs); the login is the branch config.
- **Quoting a secret as evidence of a finding.** Refused by the protocol
  (§17): a finding described by shape and location is fully actionable.
- **Clearing only the base URL** when a request is redirected. Refused by
  the incident of 2026-09-23.

## 4. Rationale

One config per login makes a credential an attribute of the agent, like its
role: revoking an agent is revoking one token, and spend is reported per
key, i.e. per agent. Refusing a config whose `AGENT_LOGIN` is not the login
running it enforces the identity invariant at the secret boundary (ADR-002).

## 5. Binding Rules

1. No credential is committed to this repository or a managed project's
   `.agent-fabric/`; an identity's secrets live only in its Doppler config.
2. Each account holds one read-only service token for its own config.
   `fabric-secrets sync` refuses a config whose `AGENT_LOGIN` is not the
   login running it; the config is the one `enroll.sh` recorded at scope
   `/`, never a directory scope.
3. `fabric-secrets sync` and `status` print names, presence, modes and ages
   — never a value. Enrolment moves values inside `doppler` calls or API →
   Doppler, never through a terminal or argv.
4. `fill-from` never copies the identity names, the coordinator's own
   credentials (`*_ADMIN_KEY`, `*_PROVISIONING_KEY`,
   `AGENT_FABRIC_READ_TOKEN`), or a per-login `agent_env` name; a login gets
   its own OpenRouter and OpenAI keys (`issue-openrouter-keys`,
   `issue-openai-keys`). The coordinator's Doppler admin token lives in the
   coordinator's home and nowhere in this tree.
5. A message, review, commit or report that concerns a secret describes it
   by shape (pattern, length) and locator (file and line, variable name,
   message id and section, …) and never reproduces it — in whole, in part,
   as an example, or in a `VERIFIED` section (GZCoord SPEC §17). Quoting a
   message body that may carry one is the same act.
6. A change to where a request goes (base URL, endpoint, proxy) first
   reads what the setter actually puts in the environment and moves every
   credential and header bound to that destination with it; a second,
   destination-independent check guards the secret itself. On the
   plain-claude path the launcher drops an `ANTHROPIC_API_KEY` equal to
   `OPENROUTER_API_KEY` or shaped `sk-or-`, and on the broker path drops
   `CLAUDE_CODE_OAUTH_TOKEN`, naming what it dropped, never the value.
7. Tests check credentials by shape (unset, empty, `sk-or-`, `sk-ant-`),
   never by a real value, and assert that output lacks the fixture secret.
8. Rotation is a change in the Doppler dashboard followed by
   `enroll.sh sync-all`.

## 6. Consequences

- An account's credentials follow the account; `moveto` runs
  `fabric-secrets sync`, so a rotated value arrives on the next entry.
- Spend is reported per key, so per agent, on OpenRouter and OpenAI; a
  value copied by `fill-from` is shared, and its spend follows the source's
  key until the target gets its own.
- The signing key for control-plane actions lives in the operator's
  Doppler config; anything that can run as the operator can sign.

## 7. Future Evolution

None stated.

## 8. Decision Status

Accepted; the Doppler layout since 2026-09-14, the launcher's credential
rules since the reviews of #31 (2026-09-23) and #33.

## References

- `CLAUDE.md` §"Licence, runtime state and credentials";
  `runtime/provisioning/README.md` §Secrets.
- `runtime/provisioning/secrets/` (`enroll.sh`, `enroll-worker.sh`,
  `fabric-secrets`, `test_enroll.sh`, `test_fabric-secrets.sh`),
  `bin/fabric-secrets`.
- `communication/gzcoord/protocol/SPEC.md` §17;
  `communication/gzcoord/skills/gzcoord-send/SKILL.md`.
- `runtime/openrouter/launch` (the broker environment and the key check).
- ADR-002 (the login is the identity), ADR-009 (the operator's signing key),
  ADR-010 (enrolment through the host executor).
