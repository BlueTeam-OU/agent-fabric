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
   own firewall, not the provider, would have answered.
2. On fabric-h2, a 60-second Python listener on 0.0.0.0:47100 that writes
   `h2-probe-ok` to the first connection.
3. From develop-qzapp, `/dev/tcp/195.69.140.18/47100`.
4. On fabric-h2, the port removed from the runtime firewall, and `ss -ltn`
   showing no listener on 47100.

**Measured.** The first attempt read `h2-probe-ok` (rc 0). Afterwards
`firewall-cmd --list-ports` was empty and nothing listened on 47100.

**Control.** Before step 1, `ss -ltnu` on fabric-h2 showed only sshd (22)
and chronyd listening, and nothing in 47100-47199. So the only process that
could answer `h2-probe-ok` was the probe's own listener on fabric-h2.

**What it decides.** The provider's forward reaches fabric-h2, for one port
of the range, from develop-qzapp on its present network path.

**Not checked:**
- the other 99 ports of the range;
- a source outside the owner's networks (develop-qzapp while travelling);
- whether the connection hairpinned through the provider's LAN, which the
  listener's view of the source address would show;
- InterWeave itself: no profile is installed on fabric-h2 yet.

Opening the range permanently in firewalld is provisioning's step for a
profile placed on fabric-h2 (ADR-048), and is not done here.
