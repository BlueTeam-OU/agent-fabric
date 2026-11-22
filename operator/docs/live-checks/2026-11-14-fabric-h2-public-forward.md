# fabric-h2's public InterWeave forward answers (2026-11-14)

**What was checked.** The provider confirmed its DNAT of 195.69.140.18 TCP
47100-47199 to fabric-h2 (VM 101 on s13337; the owner, 2026-11-14). Before
any roster row names fabric-h2, this check asks whether a connection to the
public address actually reaches a process on fabric-h2.

**How.** All of it ran from develop-qzapp as the operator, through
`fabric-host fabric-h2 run`:

1. On fabric-h2, `firewall-cmd --add-port=47100/tcp`, in the runtime
   configuration only and never `--permanent`. firewalld's public zone
   admitted only ssh, cockpit and dhcpv6-client, so without this the host's
   own firewall would be expected to stop the connection (expected, not
   measured: see Not checked).
2. On fabric-h2, a 60-second Python listener on 0.0.0.0:47100 that writes
   `h2-probe-ok` to the first connection.
3. From develop-qzapp, `/dev/tcp/195.69.140.18/47100`.
4. On fabric-h2, the port removed from the runtime firewall, and `ss -ltn`
   showing no listener on 47100.

**Measured.** The first attempt read `h2-probe-ok` (rc 0). Afterwards
`firewall-cmd --list-ports` (runtime) and `firewall-cmd --permanent
--list-ports` (read later the same day, at the review) were both empty,
and nothing listened on 47100.

**Control.** Before step 1, `ss -ltnu` on fabric-h2 showed only sshd (22)
and chronyd listening, and nothing in 47100-47199. So the only process that
could answer `h2-probe-ok` was the probe's own listener on fabric-h2.

**What it decides.** The provider's forward reaches fabric-h2, for one port
of the range, from develop-qzapp on its present network path.

**Not checked:**
- a negative control: no connect attempt was made while the port was
  closed, so it is not measured that a closed host firewall would have
  refused the connection;
- the other 99 ports of the range;
- a source outside the owner's networks (develop-qzapp while travelling);
- whether the connection hairpinned through the provider's LAN, which the
  listener's view of the source address would show;
- InterWeave itself: no profile is installed on fabric-h2 yet.

ADR-064 rule 1 (A 2026-11-14) says that fabric-h2's firewall admits the
roster's range from any source. No provisioning step opens that range
permanently in firewalld yet. Until a step does, it is a manual act on the
host when the first profile is placed there, and this check did not do it.
