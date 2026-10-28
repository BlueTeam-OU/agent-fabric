# ADR-064 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-24 — the carrier's codec is zlib, a receipt also answers a message not addressed here, and the carrier contract is written

What changed: §5 rule 8's codec, `;ce=br` (brotli, the content-encoding
of InterWeave's human facade), becomes zlib under the carrier's own media
type, `;ce=deflate`. §5 rule 7, and §2's delivery bullet, add that the
receiving carrier also answers with a receipt when it decides a message
is not addressed to its agent. Rule 8 names the carrier contract,
`communication/gzcoord/docs/CARRIER-CONTRACT.md`, as where the names,
the framing, the receipt and the adapter channel are fixed.

Why, the codec: the build found it unbuildable as written. The fleet's
pinned Python (3.13) has neither brotli nor zstd, and ADR-040 holds the
fabric's tooling to the standard library; a brotli module would be an
unpinned dependency diverging between accounts. The codec is between two
carriers only: the daemon never decompresses and no human client
receives these payloads, so InterWeave's choice for its human facade
does not bind it. Why, the receipt: rule 6 sends a `TO-ROLE` or a
broadcast to every roster member, and each filters as its inbox does;
a member that filters a message out would never append it, so under the
old text its sender retried it for ever.

Raised by python-dev-02 building the carrier (j89, its QUESTIONs of
2026-10-24); the contract is its draft, reviewed and changed by the
coordinator. Accepted by the owner, 2026-10-24 ("adr 64 accepted", in the
coordinator's session).

### Amendment 2026-10-25 — an InterWeave install or update is a control-plane action, checked after the restart

What changed: §5 gains rule 14. Installing or updating the InterWeave
programs is a control-plane action. It restarts the units that were
running, checks them through the control plane (each of those units
active, the daemon's process running the program now installed, the
programs release.json pins printing their version, the carrier
answering `status`; on a first install, the version alone), and
reports done only after that check. A failed check puts
back the previous programs and says so. The same check is the control
plane's read of each account's InterWeave state after any restart.

Why: the archive's `install.sh` replaces the programs and enables
nothing, so a running daemon keeps the old binary until it is
restarted (the carrier, the fabric's own client, restarts after it),
and the restart takes the account's InterWeave channel down. If the restart goes wrong, the agent is unreachable on
that channel and nobody is told. The control plane stays on the relay
(rule 12), so it can still reach the account while that channel is
down. It is therefore the one place that can confirm the account came
back.

Raised and accepted by the owner, 2026-10-25, in the coordinator's
session: "when an install/update of interweave happens the
channel/communication become unavailable, if things go wrong agent
become 'invisible' so a control plane check after the restart should
be required".

The same amendment records that the build's precondition is met: §6,
§8 and the Scope line name InterWeave v0.1.0, pinned in
`runtime/interweave/release.json`, instead of waiting on a tag. Its
review (PR #376, round 1) found two gaps in rule 14 as first written,
closed before it landed: a first install has no running unit and no
previous programs, so its check is the version and its reply says so;
and a program's `--version` on disk reports the new version even when
the running process was never restarted, so the check is that the
daemon unit's process runs the program now installed.

### Amendment 2026-10-26 — The roster's ports are reserved from the host's ephemeral range

What changed: §5 rule 1 says the roster's port range is reserved on the
host, so the kernel never hands one of its ports out as the source port
of an outgoing connection.

Why: the first fleet start (2026-10-26) found the host's ephemeral range
at 32768-60999, which holds the roster's 47100-47199. With the fleet's daemons
dialling each other, an outgoing connection had taken 47124, the
coordinator's roster port, as its source port, and the coordinator's
daemon exited "Address already in use" five times while nothing
listened there; a later try started it. Rule 13 measured the kernel's
refusal of a held port; this is the same refusal from a port no daemon
meant to hold. The owner reserved 47100-47199 the same day
(`/etc/sysctl.d/90-interweave-roster-ports.conf`); reserved ports stay
bindable explicitly. A second host needs the same before its first
start. Raised by the coordinator from that start. Accepted by the owner,
2026-10-26 ("yes", in the coordinator's session, asked whether the
rule 1 amendment is accepted).

### Amendment 2026-10-26 — The parity evidence is gathered through the control plane

What changed: §5 rule 11 names how the report's inputs reach the
operator. The arrival logs and delivery records are per account, so
`fabric-ctl all interweave-evidence` (ADR-029 §2, python-dev-02's #390,
j94) reads them, metadata only, and `gzcoord-carrier parity --collected`
computes the report from the files it wrote. The rule's content (the
window, the pairs, the counts, the rollback drill) is unchanged.

### Amendment 2026-10-27 — One host is the first milestone; a second host is the next

The owner, 2026-10-27, on reading that InterWeave is one host only by
ADR-064 rule 1: "that is not a rule, is a first milestone". The fleet
is to move agents to remote hosts (the first likely edge-hosting). Whether
the control plane rides InterWeave is agent-fabric j422's question;
rule 12 stands until its own amendment. §2's lead and one-host bullet, rule 1 and §7
now call one host the first milestone and a second host the next,
opened by an amendment naming the host, routable roster addresses and
how InterWeave ADR-0034 §7 and SPIKE-004's limits are consumed or
accepted on the owner's word. Until it lands, profiles still listen on
`127.0.0.1` only; nothing else changes.

### Amendment 2026-10-28 — The pin moves to InterWeave v0.2.0; the record names the pin, not a version

What changed: `runtime/interweave/release.json` `current` is 0.2.0
(tag v0.2.0, commit 32ade966, release run 40568434157 attempt 1,
success), its 0.1.0 entry kept. The archive's SHA-256 was computed from
fabric-coordinator's own download and matched the release page's
digest and the `.sha256` asset; `transportctl` and `transport-daemon`
print `0.2.0+32ade966cff8`, and their digests are pinned beside it. The
two user-unit templates are byte-for-byte the ones 0.1.0 installed.
§6 and §8 now name the pin, not a version, so the next move is a commit
to release.json alone.

Why: the owner, 2026-10-28, in the coordinator's session: "0.2.0
landed". The fleet installs it by `fabric-ctl <login|all>
interweave-install` (rule 14), two accounts first with rule 13's
procedure re-run on the new programs, then the rest; the dual run's
parity window counts from after the fleet runs one version.

### Amendment 2026-10-28 — The control plane rides the profile's fabric-control endpoint through interweave-human

What changed: rule 12 no longer keeps the control plane on the relay.
It rides the GZCoord profile on its own `fabric-control` endpoint,
through `interweave-human` under agentd (ADR-029 rule 18, amended the
same day), never through this record's carrier; the profile is the
control plane's alone (its only human endpoint, no person's client,
`gzcoord` automated-only). §3's first alternative says why the CLI,
refused for GZCoord, is taken for control. Rule 14's install, start,
stop and check stay on the relay.

Why: the owner's direction of 2026-10-27 (the control plane on the
InterWeave CLI, so agents can move hosts; agent-fabric j422), and
InterWeave #477 in v0.2.0, which answered §1's objections to the CLI
for traffic of this shape. The second-host amendment of rule 1 is
drafted in `docs/proposals/j422-control-plane-on-interweave-cli.md`
and waits for a named host.
