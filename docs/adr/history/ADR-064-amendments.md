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
stop and check stay on the relay. Rule 12 also says what the render
configures (`fabric-control`, the default endpoint pinned to `gzcoord`,
no channels) and that this carrier refuses a `fabric-control/1 ` body,
both built with ADR-029 rule 18's carrier and not before.
§6 no longer says an off-host agent stays on the relay alone.

Why: the owner's direction of 2026-10-27 (the control plane on the
InterWeave CLI, so agents can move hosts; agent-fabric j422), and
InterWeave #477 in v0.2.0, which answered §1's objections to the CLI
for traffic of this shape. The second-host amendment of rule 1 is
drafted in `docs/proposals/j422-control-plane-on-interweave-cli.md`
and waits for a named host.

### Amendment 2026-10-31 — The archive is checked against the owner's minisign signature as well as its digest

What changed: rule 4 adds that the archive must also verify against the
owner's minisign signature before it is extracted, the key pinned in
`runtime/interweave/release.json` as InterWeave's
`packaging/release-keys.toml` holds it on InterWeave's main (the copy its
release job signs with), and that a release with no signature is not
installed. The pin carries, per release, the key and the InterWeave commit
it was read from, and, per build, the signature's three lines, so nothing
about the signature is fetched at install time. v0.1.0, which predates
the key, is marked unsigned.

Why: the digest proves the bytes are the ones fabric-coordinator
reviewed, not that the owner released them; a digest copied wrong at a
pin move, or taken from a page that was not the release's, installs
whatever it names. v0.2.0 is the first release that ships a `.minisig`,
and InterWeave's release job refuses to publish an archive its pinned
key cannot check. The measurement, with its controls, is
`docs/live-checks/2026-10-31-interweave-archive-signature.md`: the
signature verifies with `minisign` and with the standard library alone
(BLAKE2b-512 and Ed25519 verification), which is what the installer
uses, since the fleet's pinned Python has no `cryptography` and no host
is provisioned with `minisign`. The installer's check is python-dev's
(agent-fabric j449); until it lands the pin's new fields are read by no
code, and the digest stays the only check.

### Amendment 2026-11-01 — Provisioning makes the reserved ports and keeps them across a reboot

What changed: rule 1 adds who makes the reservation and keeps it:
provisioning, from the roster's range, by `fabric-host <host> persist`
(`tools/fabric/provisioning/persist_host_settings.py`, python-dev's #449,
agent-fabric j469). It adds the range to the live value, keeping any other
reservation, and reads it back; where the root does not survive a reboot
(a Qubes AppVM) it installs `/rw/config/rc.local.d/agent-fabric-interweave.rc`,
which adds the range at boot, and elsewhere
`/etc/sysctl.d/90-agent-fabric-interweave.conf`. `fabric-ctl <login>
interweave` reports `reserved_ports` (`covered`, `not-covered`, or
`unreadable` with its reason), and a start refused for the reservation
names the step as the fix. The step fixes `not-covered`; an `unreadable`
roster or live value it refuses too, since writing over a value it cannot
parse would drop whatever that value holds.

Why: the 2026-10-26 amendment's reservation was a file the owner put in
`/etc/sysctl.d/`, and develop-qzapp is an AppVM whose `/etc` comes back
from the template: after the reboot of 2026-10-30 05:08Z the value was
empty, and `fabric-ctl all interweave-start` refused all 30 accounts. The
owner's hand copy under `/rw` restored it, written over any other
reservation and from a range typed by hand. A setting the carrier cannot
start without is provisioning's, like the accounts' own boot script
(ADR-010). The measurement, with its controls and what it leaves for the
next reboot, is `docs/live-checks/2026-11-01-reserved-ports-persist.md`.

### Amendment 2026-11-08 — The parity soak includes a relay-outage drill

What changed: rule 11's soak adds a relay-outage drill beside the
rollback drill: the relay refuses every fetch for part of the window,
and a message only the InterWeave carrier holds reaches its addressee's
session, is not shown again when the inbox watch restarts, and is not
shown again when the relay comes back with its own copy, which is then
acknowledged. The parity report cannot show this: `fabric-ctl all
interweave-evidence` collects arrival logs and delivery records, and
`gzcoord-carrier parity` (`tools/fabric/gzcoord/carrier/parity.py`)
renders only the rollback drill, while the three properties are in the
addressee's shown ledger (`gzcoord-shown.jsonl`) and the relay's
acknowledgements. So the drill's evidence is a `docs/live-checks/`
record read from those, beside the report; parity tooling that reads
them is owed, not built. The relay stays the transport of
record; the drill is evidence the owner's word on a switch is given on,
not a switch.

Why: an external review of the transport (agent-fabric j598) found that
the inbox watch read the carrier only after a relay fetch succeeded
(`tools/fabric/gzcoord/inbox_parts/watch.py`), so in a relay outage the
second carrier delivered nothing to the session, and the rollback drill,
which switches off the other carrier, could not have shown it.
python-dev's BlueTeam-OU/agent-fabric#499 (j115, merged 2026-11-07)
fixed the watch and proves the three properties against a relay that
answers 500 to every fetch (`tests/test_gzcoord_carrier_inbox.py`, cases
(a)–(c); #499 reports (a) and (c) failing before the fix, while (b), no
second showing after a restart, also held before it, when nothing was
shown at all). That is a test double of the
relay; a claim that the carrier covers a relay outage rests on the live
drill. Known limit: a relay that accepts the wait and never answers
delays a carrier-only message by one wait slice plus the request
timeout (`inbox.py` fetches with `slice_ + API_TIMEOUT`, 55 s and 300 s),
up to about six minutes, since the watch asks the carrier only after
the fetch returns or fails; a relay that refuses is read at once.

### Amendment 2026-11-08 — The parity report reads the relay-outage drill

The amendment above left the drill's tooling owed: the report rendered
only the rollback drill, and the three properties were to be read by
hand from the addressee's shown ledger and the relay's
acknowledgements. python-dev-03's BlueTeam-OU/agent-fabric#509 (j118)
builds it. The inbox watch now logs each acknowledgement it makes
(`gzcoord-acks.jsonl`, a refused one included), `interweave-evidence`
gathers that log and the shown ledger as two more sections (ADR-029
amendment of the same date), and `gzcoord-carrier parity --collected
PATH --relay-drill START END` adds a "Relay-outage drill" section: per
(MESSAGE-ID, addressee) made in the drill, whether the carrier alone
held it, whether it was shown once, shown again after a restart or on
the relay's return, and whether the relay copy was acknowledged, an
unknown kept unknown. The live drill's record in `docs/live-checks/`
is still what the owner's word is given on.

What changed in meaning: the acknowledgement evidence is the account's
record of the relay's answer to its `POST /api/ack`, not the relay's
own state. The relay has no endpoint that reads a consumer's cursor
without being that consumer, and a live relay read from the control
daemon would put the account's token in a second path. An ack that
moved the cursor past a message without naming it is not credited; the
watch acknowledges each record by its id.

Written by fabric-coordinator as job j652, beside the ADR-029 amendment
python-dev-03 asked for (OBSERVATION 01a1ba62).

### Amendment 2026-11-11 — The second host is fabric-h2, reached from develop-qzapp only

Rule 1's next milestone opened in the 2026-10-27 amendment on three
conditions: a named host, routable addresses for its accounts, and
InterWeave ADR-0034 §7 and SPIKE-004 consumed or accepted. This
amendment names the host and says how the other two are met.

The host is `fabric-h2`, VM 101 on the Proxmox node s13337, which
also runs gzapp in production. The node is not a fabric host. devex-tooling
created the VM through the PVE API (j320), the owner installed
AlmaLinux 10.2 on its console, and it is registered with its sshd host
keys pinned. `fabric-host fabric-h2 check` answers
(`docs/live-checks/2026-11-11-fabric-h2-registered.md`).

The network is not the plan's. `docs/proposals/j422-control-plane-on-interweave-cli.md`
§3.1 decided a WireGuard overlay run by each host's operator, and the
owner had left the mesh question to the day the host existed. On
2026-11-11 the owner chose neither. develop-qzapp reaches fabric-h2
over the LAN and the VPN it already has, and fabric-h2's address is
reserved in the LAN's DHCP. The live check found that the way back is
closed: from fabric-h2, a connection to develop-qzapp's address as
fabric-h2 sees it fails. So every connection between the two hosts
is opened by develop-qzapp, and the render's static bootstrap on
fabric-h2 to a develop-qzapp row dials nothing. Whether InterWeave
keeps a connection usable both ways when only one side can dial is
what P2's two-host check measures. ADR-0055 decision 5b's
two-namespace case had both sides dialable.

The gates. InterWeave's ADR-0055 decision 5b (A 2026-10-27) states the
limits of a two-host deployment: static operator-supplied addresses,
no discovery, connectivity roles off. The owner accepted them for the
first remote host that day. ADR-034's order put the relay drill
(§7 step 2, done 2026-11-07) and the scheduled drain (step 3, built,
with its 14-day bound reported but not held) before a second host. On
2026-11-11 the owner waived the held bound and P1's control parity
report for P2 only: the registry entry, and a throwaway login's ping,
identity and one GZCoord message each way.

What stays as planned. An agent moves to fabric-h2, edge-hosting
first (plan §3.5), only on the owner's word on the control parity
report. Its keyring and ADR-038 subkey are carried over and not
rotated, on the owner's word of 2026-10-30 ("move means move"), which
reverses the plan's §3.4. Whether the agents run in the VM itself or
in a container inside it stays the owner's to decide. ADR-048 is
amended the same day for sshd beyond loopback.

Written by fabric-coordinator as job j706, from architect-cto-01's
REQUEST 01a1c063.

### Amendment 2026-11-12 — the second host is any host in the registry, not a named one

What changed: rule 1's paragraph on the second host no longer names the
host, its Proxmox node, the coordinator's host by name or the owner's two
waivers for the throwaway login. It says a second host is one registered in
`runtime/hosts/registry.json`, reached directly by the coordinator's host,
with no overlay, connections opening only from the coordinator's host, its
firewall admitting the roster's range only from that host's address, the
InterWeave limits accepted on the owner's word, a third host a further
amendment, and an agent moving there only on the owner's word on the
control parity report. The first-milestone sentence is unchanged; the
next milestone, which opened by an amendment naming the host, now opens
once the host is registered in `runtime/hosts/registry.json` and named in
the operator's inventory, ADR-069 here.

Why: ADR-045 §5 rule 4. Rules 2-14 and rule 1's milestone are the carrier;
the named second host and its waivers are this deployment's
(docs/split/adr-classification.md, ADR-064 row): ADR-069 rule 2 holds
fabric-h2 and the owner's two waivers, and the host is registered in
`runtime/hosts/registry.json`.
