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
