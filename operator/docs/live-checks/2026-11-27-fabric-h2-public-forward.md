# 2026-11-27 — fabric-h2's public forward reaches the VM, source kept

**Decides:** the provider's forward 195.69.140.18 → 192.168.200.79
(fabric-h2) carries the InterWeave range over TCP, end to end, from a
source outside the provider's network. j860's wait on the provider is
over (the owner, 2026-11-27: "it is implemented"). What it does not
decide is in "Not measured" below.

**Who, from where:** fabric-coordinator (`user` on develop-qzapp). This
host leaves through 2.35.202.83, not 195.69.140.18, so the probe takes
the public path; no hairpin is involved (the #597 review's risk). The
VM was reached with `fabric-host fabric-h2 run`, as `op`.

## Measured

1. **No listener, the VM's firewall unchanged.** fabric-h2 runs
   firewalld, zone `public`, with services cockpit, dhcpv6-client and ssh,
   and no ports open. Nothing listens on 47100-47199.
   - `connect 195.69.140.18:47199` gave `EHOSTUNREACH` after 0.08 s.
   - `connect 195.69.140.18:47100` gave `EHOSTUNREACH` after 0.07 s.
   - Control: `connect 195.69.140.18:22`, a port outside the forward,
     timed out after 10 s.
   A fast reject for the range against a timeout for an unforwarded port
   is consistent with firewalld on the VM rejecting the packet.
2. **End to end.** On the VM:
   `firewall-cmd --add-port=47199/tcp --timeout=90`, which is
   runtime-only and expires by itself. A one-shot listener on
   0.0.0.0:47199 writes one line and exits within 60 s.
   - From develop-qzapp: connected in 0.19 s and read
     `fabric-h2 probe`.
   - The listener logged `accepted from 2.35.202.83`, this host's public
     address. **The forward keeps the source address (no SNAT).**
3. **Put back.** `firewall-cmd --remove-port=47199/tcp` ran. The
   runtime and permanent port lists are both empty, and
   `connect 195.69.140.18:47199` gives `EHOSTUNREACH` again.

## What follows

- **fabric-h2's firewall must open the InterWeave ports before any
  roster row names fabric-h2.** Today the forward arrives and is
  rejected. `fabric-host persist` owns the host settings the fabric
  needs (ADR-064); whether it opens firewalld on an EL host is the next
  thing to check, not assumed here.
- The kept source address means admission by roster PeerId (#597,
  ADR-064 rule 1) also sees the real peer address, for logs and limits.

## Not measured

- UDP, or any InterWeave daemon: TCP connect only, one port (47199) end
  to end and two by their reject.
- Ports other than 47199 and 47100 across the range.
- A dial from fabric-h2 outward. The way back stays way (a), the kept
  connection, which is j880's two-host check.
