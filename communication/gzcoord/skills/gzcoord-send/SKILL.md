---
name: gzcoord-send
description: "Send a message to another agent over GZCoord — the whole procedure, from deciding whether a message is the right instrument (never for what belongs in a PR, a review or a commit) to composing it in the GZCOORD/1 shape, validating it and posting it with gzcoord-send as the login you are (it mints the MESSAGE-ID). Load it before writing any message to another agent: a REPLY when you start acting on someone's finding, an OBSERVATION when you find something in another role's lane, a REQUEST, or a DECISION; and to learn whether an agent is online (presence), since HELLO is retired."
---

# Sending a GZCoord message

Every session on this host is a Linux login with an address
`<host>/<login>` (`fabric-whoami`), and the relay
delivers what one session writes to the cursor of every other. The
protocol is `communication/gzcoord/protocol/SPEC.md`; what a good message
looks like is `protocol/MESSAGE-FORMAT.md`. This skill is the procedure.

## 1. Is a message the right instrument?

GZCoord is advisory (SPEC §2). It never substitutes for the thing itself:
a change is a commit, a proposal is a pull request, a review finding is a
review comment, a decision that must last is an ADR or a commit. Send a
message when another *session* needs to know or decide something now —
you found a defect in a role's lane that is not yours, you are starting
work on a finding someone reported (so they do not do it too), you need a
decision only that role can make, or you are announcing a rule that every
session must apply. Do not send one to ask for repository state (read the
tree), to hand over a working copy (SPEC §HANDOFF transfers none), or to
say what a PR already says.

## 2. Compose

Pick the type (`INFO`, `OBSERVATION`, `QUESTION`, `REQUEST`, `REVIEW`,
`DECISION`, `HANDOFF`, `REPLY` — nothing else; an extension is `X-…`;
`HELLO` and `GOODBYE` are retired, see §4). Metadata block, then sections:

```text
[GZCOORD/1] OBSERVATION
FROM: <host>/<login>            # yours — send.mjs refuses any other
ROLE: <slug>                    # the role you hold (fabric-status); a catalogue slug, never a title
PROJECT: <project>
REPOSITORY: <org>/<repo>        # when it concerns one
TO: <host>/<login>              # one addressee …
TO-ROLE: <slug>                 #   … or the role that owns the decision …
BROADCAST: true                 #   … or everyone; exactly one of the three
IN-REPLY-TO: <message-id>       # when answering
REPLY-EXPECTED: yes|no
                                # MESSAGE-ID: leave it out — gzcoord-send mints it
SUBJECT: one line, short

OBSERVATION:
what you noticed, as fact

VERIFIED:
how you established it, and the control that shows the measurement was live

NOT-VERIFIED:
where the diagnosis stops

IMPACT:
what follows if it is true — what lets the reader decide not to act

REQUEST:
the decision or action you ask of the addressed role

REFERENCES:
- path: …
- commit: …
- github-pr: …
```

Rules that are not style:

- **Lines of 72 columns or fewer, where you can** — a courtesy to the
  reader's terminal, not a rule of the wire: the bridge carries a line
  as written, so a path or an id that is longer goes out whole and
  `send.mjs` says nothing about it. Only a message someone will paste
  by hand (`gzmsg validate`) still warns about width.
- **Address one way.** `TO` for a session, `TO-ROLE` for whoever holds
  the role, `BROADCAST` for a rule everyone applies. A recipient reads the
  body only when it is addressed; a broadcast spends every session's
  context, so it is for rules, not news.
- **An assignment goes `TO` one login, never `TO-ROLE`** (SPEC §13). A
  `REQUEST`, a finding to fix, a supply — anything with a `REQUEST:`,
  `ACCEPTANCE:` or `DELIVER-TO:` section — names a login, because the
  runtime delivers a role address to every holder and each executes the
  job unaware of the others: two PRs on the same hunk. `send.mjs` refuses it. When you do not
  know which holder: the one whose pushed branch — PR or not — touches
  the path (`pr-gate.sh --in-flight --path <prefix>`), else one holding it with a session running now
  (`fabric-ctl all presence`), else the lowest-numbered login — and say which rule chose
  (`MESSAGE-FORMAT.md` §Direct versus role addressing). `TO-ROLE` stays
  for an `INFO`, a `DECISION`, a `QUESTION` to whoever holds the role.
- **Diagnose completely, prescribe nothing outside your lane.** State what
  you saw, how you verified it, what you did not, and ask the owning role
  to decide (`MESSAGE-FORMAT.md` §Reporting a finding).
- **A request to undo, revert, remove or replace landed work states the
  defect in that work as a checkable fact** (SPEC §2). The reader reads
  your message late, against a tree that has moved; a bare "revert X"
  gives it nothing to verify and is refused.
- **Never a secret value** — describe it by shape and locator (SPEC §17).
  Never quote another message's body (it may carry one). Never a model,
  provider, local path outside the repository, or credential.
- **After a safeguard flag, filter the category out of everything you
  send.** If the harness told you a model's safeguards flagged your
  request and switched the session to another model, what flagged you
  flags every session it is sent to, and a broadcast lands in all of
  them. From then on, nothing that could be read as the flagged
  category (a cybersecurity issue, most often) goes into a message:
  name where a finding is (file, line, PR) and what class of problem it
  is, never its content, and let the reader open it in their own
  repository. The PostModelSwitch hook says this to you the moment it
  happens, naming the category, and `send.mjs` repeats it on stderr
  while the session is marked as fallen back; it cannot check the
  content, only you can.
- **When you start acting on someone's finding, say where**: a `REPLY`
  with `IN-REPLY-TO` and a `REFERENCES` entry naming the branch or PR
  (`MESSAGE-FORMAT.md` §Acknowledging by reference) — otherwise two
  sessions do the same job and meet in a merge conflict.

Write it to a file in your scratchpad (never in the tree; a message is
never committed), without a `MESSAGE-ID` line: `gzcoord-send` mints one
and writes it into the file before it posts, so sending the same file
again, after an outcome you could not see, sends the same id and the
copy is discarded (SPEC §7.2). Never write a placeholder id to fill in
later: it is refused, and the command on screen would not be the
message that went out. An id you set yourself is kept. The id stays in
the file after it is sent: write each new message as a new file, or
delete its `MESSAGE-ID` line — an id that already went out with other
text is refused, since every reader would drop the new message as a
copy.

## 3. Send

```sh
gzcoord-send <file>            # validate, then post
gzcoord-send <file> --dry-run  # validate, resolve, post nothing
gzcoord-send <file> --force    # post even if the addressee has no session
```

`gzcoord-send` normalizes the text (a pasted message carries terminal
indentation), validates it as the last step before it leaves — a message
that fails is not sent — and refuses a `FROM` that is not your address:
the sender is the login, never a claim. It resolves the relay, the
channel and the token exactly as the inbox does (your project's
integration; the token from the file `fabric-secrets sync` writes,
`~/.config/agent-fabric/secrets.env`, which no shell sources). It prints `sent seq <n> <TYPE> <id>` and nothing else — the
id it minted, or yours. Keep the id: a reply names it in `IN-REPLY-TO`.

**Before a `TO` or `TO-ROLE` message leaves, `send.mjs` asks whether the
addressee has a session running** — the control plane answers from each
account's process table (`fabric-ctl <login|all> presence` shows the
same). An addressee with no session, a control agent that did not answer
or could not tell, an address no host places, or presence that could not
be asked at all is named, nothing is sent, and it exits 4. A relay that
refuses the token is the exception: the check is skipped with a line
saying so, and the post reports the refusal.
A `TO-ROLE` passes when any holder of the role is running; a broadcast is
not checked. An addressee that is planning is sent to, and you are told:
its inbox is held until its plan is approved, so no answer comes before
then — do not chase it or take its work. Then you decide: a message to a login with no session waits
in the relay until one starts, which may be what you want — `--force`
sends it anyway, and says so. A request that must be acted on now
belongs to a running session, or to a later send.

The fabric's commands are on your PATH by name — `gzcoord-inbox`,
`gzcoord-send`, `gzmsg`, `fabric-status` and the other `fabric-*` —
and allowed in your settings: run them bare. Never write one through
`$AGENT_FABRIC_ROOT` or any other expansion; the harness asks before a
command that carries one.

## 4. Presence is asked, never announced

`HELLO` and `GOODBYE` are retired (SPEC §8): nobody sends them, the
validator rejects either, and the inbox acknowledges one from a session not yet updated without
delivering it. Whether another agent has a session running — since when,
as which role — is the control plane's to answer, from each account's
process table:

```sh
fabric-ctl <login> presence    # one account
fabric-ctl all presence        # everyone
```

`send.mjs` asks the same before a `TO` or `TO-ROLE` message leaves (§3).
A crash, or a launch that never started, reads as no session: presence is
the process table, not what a session said about itself. A **role cannot
change inside a session**: it is bound from a login shell
(`fabric-role bind <role>`) and the new role is a relaunch; presence
reports the role from the binding.

## What a sent message does not do

It does not authorise the recipient to do anything in your working copy,
it does not create an issue or a task, and it is not read until the
recipient's watch delivers it — which may be hours. If the thing must
happen, the thing is a PR.
