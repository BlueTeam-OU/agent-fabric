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
the operator's inventory, ADR-069 here; §2's one-host bullet and §7 say
the same.

Why: ADR-045 §5 rule 4. Rules 2-14 and rule 1's milestone are the carrier;
the named second host and its waivers are this deployment's
(docs/split/adr-classification.md, ADR-064 row): ADR-069 rule 2 holds
fabric-h2 and the owner's two waivers, and the host is registered in
`runtime/hosts/registry.json`.

### Amendment 2026-11-13 — The relay-outage drill reads the senders' backfill logs

The drill's three properties showed that a message the carrier alone
held reached its addressee and was not shown twice; none showed that
the relay's record, still the transport of record (rule 11), ever got
it. python-dev-03's BlueTeam-OU/agent-fabric#573 (j134) backfills the
relay as it returns and logs each finished row to the sender's
`gzcoord-backfill.jsonl` (MESSAGE-ID, outcome, time, delay, channel),
but nothing read that log. python-dev-02's BlueTeam-OU/agent-fabric#590
(j145) gathers it as a fifth `interweave-evidence` section (ADR-029
amendment of the same date) and `gzcoord-carrier parity --relay-drill`
reads it across every account, since the log is the sender's: for each
pair the carrier alone held, a "relay record" column (posted or present
with the delay, over-age, none, or not collected) and a fourth property.

Over-age or none fails the property. A collection without the log (one
made before #590, such as the 2026-11-12 drill's) or with a line that
could not be read reads "not collected" and the property "not judged":
never passed and never a refusal, so earlier collections still compute.
Rule 11's switching condition is otherwise unchanged; the cutover's own
amendment of ADR-033 is not this one.

### Amendment 2026-11-14 — A send the relay took counts as on its record

The fourth property asked whether every message the carrier alone held
reached the relay's record by backfill. A message the relay accepted at
send needs no backfill and left no line, so the property read "none"
for a message the relay held all along. python-dev-04's
BlueTeam-OU/agent-fabric#592 (j120) gathers a derived `relay-took-send`
row for each such send (ADR-029 amendment of the same date), and
`gzcoord-carrier parity --relay-drill` reads it as held, after a
backfill that posted or found the message present and ahead of
over-age and none; the report says "the relay took it at send".

"None" is now said only when the sender's collection carries the
derived rows (`meta.json` `backfill_log.send_rows` true) as well as its
whole log; a collection without them, as every one made before #592,
reads "not collected" and the property "not judged", never passed and
never a refusal. The switching condition is otherwise unchanged.

### Amendment 2026-11-14 — A second host with no fixed coordinator address is reached at a public forward, any source

Rule 1 had the second host's firewall admit the roster's range only from
the coordinator's host's address as the second host sees it, and the
2026-11-11 amendment had develop-qzapp reach fabric-h2 over the LAN and
its VPN. develop-qzapp runs on the owner's laptop, which travels, so the
coordinator's host has no fixed public address to admit. On 2026-11-13
the owner asked fabric-h2's provider, who manages the OPNsense in front
of its node, for a DNAT of the public address's TCP 47100-47199 to the
VM on the same ports and a WAN rule admitting it from any source
(devex-tooling's REQUEST 01a1d3c7-8b7d-718f-bb6e-c77c11fd9f70).

Rule 1 now allows that shape where the coordinator's host has no fixed
address, on the owner's word, named in the operator's record: the
registry's `interweave_address` is the public address, the second host
still cannot dial back, and admission is the roster's PeerId allowlist
alone — deny by default, a row counting only when signed by its login
and countersigned by the coordinator, so an unknown source opens TCP and
gets no session. What is left exposed is InterWeave's transport
handshake and parser, reachable from the internet. The owner accepted it
on 2026-11-14, in the coordinator's session, as a known limit for
fabric-h2 over the whole range; ADR-069 rule 2 records the forward and
the word. The address-bound form stays the default for a second host
whose coordinator has a fixed address.

### Amendment 2026-11-14 — The cutover past the dual run: data plane first, three modes per account

The owner asked on 2026-11-13 what stands between the fleet and a
GZCoord data plane on InterWeave only; the answer is the plan
`docs/proposals/gzcoord-interweave-only-cutover.md`. The owner decided
the same day, in the coordinator's session, each as the plan
recommended: D1, the data plane first, through gates 1 and 2, with
presence and the queue moved off the relay's outage path inside gate 2,
and the relay's retirement, control included, a later gate 3; D2 and
D10, three modes per account, `relay-record`, `carrier-record`,
`carrier-only`, set by a signed control action and kept in the account's
state, not in a committed file, python-dev-02 and python-dev-03 first and
the coordinator's account last; D5, the global seq, keyword alerts on
others' traffic and the whole-channel record are given up. §7 now names
that path. No rule moves yet: rules 7, 8, 11 and 14 change when each
gate's word is given, on the evidence the plan's §4 names. The retention
period for the relay's last database copy is not named yet.

### Amendment 2026-11-15 — The drills read each account's watch log; a carrier-outage drill is judged

Rule 11's relay-outage drill could not say whether a watch restarted or
gave up inside the outage. BlueTeam-OU/agent-fabric#620 (j152) gathers
each account's watch log (ADR-029 amendment of the same date), and
`gzcoord-carrier parity --relay-drill` prints per account the starts
inside the drill, each with how the watch before it ended, and whether
a watch gave up (exit 5); an account whose log was not collected whole
reads not collected, never none.

Gate 2 of `docs/proposals/gzcoord-interweave-only-cutover.md` names a
carrier-outage drill, one account's units stopped in `carrier-record`.
Rule 11 now says how it is judged: `parity --carrier-drill START END
LOGIN` takes every message addressed to that account, made inside the
window, that a sender's outbox recorded and that no copy reached before
the window ended, and asks that the carrier delivered it once after it
(the relay mirror's copy beside it is normal; a second copy of either
carrier fails) and that it was shown to the session once. A pair the files cannot show, a showing
interrupted for one, is unsettled, never passed.

### Amendment 2026-11-16 — journal off, a carrier mode sends through the carrier and refuses a receive

What changed: §5 rule 8's last sentence said that with the journal off
the route is the relay alone. It now says the route is the mode's
primary with no mirror: the relay alone in `relay-record`, as before;
in `carrier-record` and `carrier-only` the carrier, the send appending
its bypass line first (ADR-041 rule 10) and the outbox keeping the
text; and a journal-off receive is refused in both carrier modes.

Why: the cutover plan's D7 (`docs/proposals/gzcoord-interweave-only-cutover.md`
§7). A relay-alone route has no place once an account leaves the relay,
and the outbox already keeps what a journal-off send carried, so the
carrier can take it with its audit line. A receive has nothing to keep
the arrival in; the human relay is the break-glass for an account whose
journal cannot be written. The code landed first, in #623 (W17,
`tools/fabric/gzcoord/transport/__init__.py` `open_transport`); this
amendment brings the record to it, as #624's review found it behind.

Accepted by the owner, 2026-11-15 (D7, in the coordinator's session).
ADR-041 rule 10 is amended the same day for the receive.

### Amendment 2026-11-18 — The data plane's first gate: the record is the account's mode's

What changed: §2's dual-run bullet and rule 11 said the relay stays the
transport of record until the owner's word. The word is given, and the
record is now the account's mode's (§7): the relay in `relay-record`,
InterWeave in `carrier-record`, where the relay is the mirror both
ways. Every message still goes by both carriers; the dual run ends at
gate 2. Rule 11 keeps the parity report and the drills as the evidence
a later word is given on. Rule 7 says which carrier sets the journal
row: the mode's primary posts first, so in `carrier-record` the
carrier's acceptance sets it; the row is still accepted when either
carrier accepts, and in `carrier-record` the send's exit status is the
carrier's answer alone, a relay mirror's copy said and never counted
(`send.py` `carrier_not_accepted`, #613). In `relay-record` nothing
changes: a carrier mirror's copy is said only for a `TO` to one login.

Why: gate 1 of the cutover plan
(`docs/proposals/gzcoord-interweave-only-cutover.md` §4), whose evidence
is filed: #573's real-carrier read-back, the rollback drill
(`docs/live-checks/2026-11-12-interweave-drills.md`), the relay-outage
drill (`docs/live-checks/2026-11-15-relay-outage-drill.md`) and the
parity report of 562 pairs with no InterWeave miss and no duplicate
copy (`docs/live-checks/2026-11-18-interweave-parity.md`). The first
accounts to move are python-dev-02 and python-dev-03 (§7, D8), by the
signed `interweave-mode` action, after this amendment merges and after
the fix of a `send.py` defect #650's review found: a send is put on the
sent ledger once its primary took it, whether or not the relay did (a
`carrier-record` send whose mirror failed, a `carrier-only` send, a send under
`GZCOORD_TRANSPORT_MODE=carrier-only`), and is then never backfilled (REQUEST 01a1ed4e-82ec to python-dev).

Accepted by the owner, 2026-11-18, in the coordinator's session (gate
1's word). ADR-033 is amended the same day.

### Amendment 2026-11-18 — The carrier's own ops when control rides InterWeave alone

Rule 14 kept installing, starting and stopping the carrier, and reading
its state, on the relay, because they must reach an account while its
InterWeave channel is down. With `control_carrier` naming InterWeave
alone (ADR-029 rule 18) there is no relay. BlueTeam-OU/agent-fabric#656
(python-dev-04, j145) sends install, start and stop only through
ADR-029 rule 19's break-glass path, as before, and carries the read over
InterWeave while the carrier answers; an account that has not answered
within 30 seconds, or that the send never reached, is read again through
that path, and the row names which path answered. Before #656 the
carrier computed the read and dropped it at all four of its refusal
sites; it now answers it only when agentd runs on InterWeave alone.
Under `relay` and `dual` nothing changes.

### Amendment 2026-11-18 — An account starts its own carrier

On 2026-11-18 the coordinator's two fleet upgrades (for #656 and #659)
restarted every account's carrier. The inbox watches of legal-expert-ge
and rust-services-dev-01 gave up after 15 minutes of silence (exit 5).
The text they gave up with named `fabric-ctl <login> interweave` and
`interweave-start`, and both refused those logins: neither is a host
operator in `runtime/hosts/registry.json`. Both agents stopped and
reported to the coordinator, although their carriers were by then
running again. Rule 14 made every start a control-plane action because
an install or update takes the channel down and can fail unseen.
Starting units that are both down, from the programs the pin names,
cannot make an account less reachable than it already is, so that start
moves to the account's own login. A restart does not: `interweave-start`
restarts running units, and a failed check then stops both, so a
restart or a start over a live unit would be an unsigned stop. The
command therefore refuses unless both units are inactive or failed (a
unit in auto-restart reads activating and counts as running), and when
the installed programs are not the pin's (#658 review rounds 1 and 2,
F1). Its failed check stops what it started and, unlike the signed
start, which disables both, leaves each unit enabled or disabled as it
was; it renders no configuration (rounds 2 and 3, F6 and F8). Units that
are down because an operator stopped them must stay down: a signed stop,
a drill's window and a failed signed start all leave both units
disabled, while a crash or an upgrade's restart leaves them enabled. So
the command also refuses unless both are enabled, and it takes the
account's install/start/stop lock (ADR-029 rule 12), so it never runs
beside a signed action (#658 full review, F9). A failed check leaves a
mark only a signed install, start or stop clears, and the command
refuses while it stands; without it a failed start would leave the
units enabled and down, the state the next self-start accepts, and an
agent retrying after each give-up would start and stop a broken carrier
in a loop (#658 full review round 2). The command writes the mark under
the lock before it starts anything and clears it only on a passing check,
so an interrupted self-start leaves the mark too; the row and the DIGEST
list the mark among the conditions (round 3, F13). Rule 14 now cites
ADR-029 rule 18 alone for keeping install and update on the relay, since
rule 12 points to rule 14 (round 3, F12). Install, update, restart
and stop stay as they were. The local command and the watch's exit text
are python-dev's to build.

### Amendment 2026-11-26 — A pair that did not answer is started again before a rollback

On 2026-11-26 the move of the pin from InterWeave 0.3.0 to 0.4.0 left
accounts dark. After the install restarted both units, the channel
check failed on accounts under host load, and rule 14 then put back the
0.3.0 programs. Started by hand with the start's longer status wait,
the same 0.4.0 programs came up on two accounts at host load 40 to 53:
the carrier verifies the roster before it opens its socket, and the
restart's check gave it less time than the start does. The rollback
itself did not bring the account back: the pinned human-facing program
refuses the 0.3.0 one, so programs that were "back" were not carrying,
and the reply did not say so. One start was refused twice because the
previous daemon's closed connection held its port in TIME_WAIT for the
kernel's 60 seconds; it succeeded minutes later. So, when both units
ran, the manager answered and the login resolves, a failed check now
stops both and starts them once, as a start does, before any rollback,
and a failure of that stop or start goes on to it; a rollback onto
programs the pin refuses is reported as not carrying, with the pin's
refusal; and the signed start, and the retry's start, wait up to 75 seconds
for a port held only in TIME_WAIT when the pair is not both running
and the daemon is not active, while any other holder refuses it at
once; the account's self-start does not look at the port. `install.sh` is
not run again for the retry: its programs are in place and match the
pin. Built by python-dev-04 on #715 (REQUEST 01a21930, j165); the rule
text is the coordinator's (j1116).
