#!/usr/bin/env python3
"""tools/fabric/gzcoord/carrier/roster.py (ADR-064 rules 1-3) with real
OpenPGP keys made in scratch homes (tests/signing_fixture.py): a row counts
only when its login signed what `identity show` printed with the signing
subkey of the committed key AND the lineage's root countersigned the row;
every other shape renders nothing; the rendered config.yaml allowlists the
other valid rows and nothing else. Plain script: prints ok/FAIL, exit 1 on
any failure."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from gzcoord.carrier import roster as R  # noqa: E402
from signing_fixture import drop_key, make_agent_key, make_key  # noqa: E402

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def b58(raw: bytes) -> str:
    n, out = int.from_bytes(raw, "big"), ""
    while n:
        n, r = divmod(n, 58)
        out = R._B58[r] + out
    return out


def peer_id(seed: str) -> str:
    # the leading zero byte of the multihash is a leading "1" in base58
    return "1" + b58(bytes([0x24, 0x08, 0x01, 0x12, 0x20]) + hashlib.sha256(seed.encode()).digest())


class Agent:
    def __init__(self, parent: str, name: str, agent_id: str, login: str) -> None:
        self.home, self.primary, self.sub = make_agent_key(os.path.join(parent, name))
        self.agent_id, self.login = agent_id, login
        env = {**os.environ, "GNUPGHOME": self.home}
        self.pub = subprocess.run(["gpg", "--batch", "--armor", "--export", self.primary], env=env,
                                  capture_output=True, check=True, timeout=30).stdout

    def sign(self, data: bytes, key: str | None = None) -> str:
        env = {**os.environ, "GNUPGHOME": self.home}
        return subprocess.run(["gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase", "", "--armor",
                               "--detach-sign", "--local-user", (key or self.sub) + "!"], env=env, input=data,
                              capture_output=True, check=True, timeout=30).stdout.decode()


class Keys:
    def __init__(self, agents: list[Agent], root: Agent) -> None:
        self.by = {a.agent_id: a for a in agents + [root]}
        self.doc = {a.agent_id: {"login": a.login, "fingerprint": a.primary,
                                 "parent": None if a is root else root.agent_id} for a in agents + [root]}

    def lineage(self) -> dict:
        return self.doc

    def public_key(self, agent_id: str) -> bytes | None:
        a = self.by.get(agent_id)
        return a.pub if a else None


def row(agent: Agent, root: Agent, seed: str, port: int, *, signer: Agent | None = None,
        countersigner: Agent | None = None, show: str | None = None, host: str | None = None,
        host_after_signing: str | None = None) -> dict:
    pid = peer_id(seed)
    shown = show if show is not None else pid + "\n"
    r = {"agent_id": agent.agent_id, "login": agent.login, "peer_id": pid, "endpoint": "gzcoord", "port": port,
         "identity_show": shown, "login_signature": (signer or agent).sign(shown.encode())}
    if host is not None:
        r["host"] = host
    r["countersignature"] = (countersigner or root).sign(R.canonical_row(r))
    if host_after_signing is not None:
        r["host"] = host_after_signing
    return r


def doc(rows: list[dict], lo: int = 47100, hi: int = 47199) -> R.Roster:
    return R.Roster("gzcoord", "gzcoord", (lo, hi), tuple(rows))


def refused_for(rows: list[dict], keys: Keys, hosts: dict | None = None) -> dict[str, str]:
    good, bad = R.valid_rows(R.Roster("gzcoord", "gzcoord", (47100, 47199), tuple(rows), hosts or {}), keys)
    return {b.login: b.reason for b in bad}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gzr-") as d:
        root = Agent(d, "root", "00000000-0000-7000-8000-000000000001", "user")
        a = Agent(d, "a", "00000000-0000-7000-8000-00000000000a", "alpha")
        b = Agent(d, "b", "00000000-0000-7000-8000-00000000000b", "beta")
        c = Agent(d, "c", "00000000-0000-7000-8000-00000000000c", "gamma")
        keys = Keys([a, b, c], root)
        try:
            ra, rb = row(a, root, "a", 47101), row(b, root, "b", 47102)
            good, bad = R.valid_rows(doc([ra, rb]), keys)
            check("positive control: two correctly signed rows both count", len(good) == 2 and not bad, str(bad))

            check("the PeerId check accepts what it should and refuses a mangled one",
                  R.peer_id_ok(peer_id("x")) and not R.peer_id_ok(peer_id("x")[:-1]) and not R.peer_id_ok(peer_id("x") + "1")
                  and not R.peer_id_ok("12D3KooW" + "1" * 44))

            cases = {
                "login signature by another agent": row(c, root, "c", 47103, signer=a),
                "countersignature by the login, not the coordinator": row(c, root, "c", 47103, countersigner=c),
                "identity_show does not name the PeerId": row(c, root, "c", 47103, show=peer_id("other") + "\n"),
            }
            for name, bad_row in cases.items():
                got = refused_for([ra, bad_row], keys)
                check(f"refused: {name}", list(got) == ["gamma"], str(got))
                check(f"  and the good row beside it still counts: {name}",
                      [g["login"] for g in R.valid_rows(doc([ra, bad_row]), keys)[0]] == ["alpha"])

            phome, pfpr = make_key(os.path.join(d, "plain"))
            penv = {**os.environ, "GNUPGHOME": phome}
            ppub = subprocess.run(["gpg", "--batch", "--armor", "--export", pfpr], env=penv,
                                  capture_output=True, check=True, timeout=30).stdout
            psig = subprocess.run(["gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase", "", "--armor",
                                   "--detach-sign"], env=penv, input=b"data", capture_output=True,
                                  check=True, timeout=30).stdout.decode()
            check("a signature by a primary that is itself the signer is refused (a subkey signs, ADR-038 rule 1)",
                  R.verify_detached(psig, b"data", ppub, pfpr) == "signed by the primary, not by a signing subkey")
            check("  with a different committed fingerprint it is refused as another key's",
                  R.verify_detached(psig, b"data", ppub, "A" * 40) == "signed by a key that is not the committed agent key")
            check("  and a tampered body does not verify", R.verify_detached(psig, b"datA", ppub, pfpr)
                  == "the signature does not verify")
            drop_key(phome)

            t = copy.deepcopy(rb)
            t["port"] = 47150      # a field changed after the countersignature
            check("refused: a row edited after it was countersigned", list(refused_for([t], keys)) == ["beta"])
            t = copy.deepcopy(rb)
            t["identity_show"] = peer_id("b") + "\n\n"
            check("refused: identity_show edited after the login signed it", list(refused_for([t], keys)) == ["beta"])

            check("refused: a port outside the roster's range",
                  list(refused_for([row(c, root, "c", 47200)], keys)) == ["gamma"])
            check("refused: an endpoint other than the roster's",
                  list(refused_for([dict(row(c, root, "c", 47103), endpoint="other")], keys)) == ["gamma"])
            check("refused: a malformed PeerId", list(refused_for([row(c, root, "c", 47103, show="x\n") | {"peer_id": "x"}], keys)) == ["gamma"])
            extra = row(c, root, "c", 47103)
            extra["note"] = "hi"
            check("refused: a field the roster does not define", list(refused_for([extra], keys)) == ["gamma"])
            import copy as _copy
            c_other_login = _copy.copy(c)
            c_other_login.login = "gamma2"          # same key and id, signed correctly, but not the lineage's login
            wrong = row(c_other_login, root, "c", 47103)
            check("refused: a correctly signed row whose login is not the lineage's for that agent id",
                  refused_for([wrong], keys) == {"gamma2": "the lineage has no such agent under that login"}, str(refused_for([wrong], keys)))
            ghost = Agent(d, "g", "00000000-0000-7000-8000-0000000000ff", "ghost")
            check("refused: an agent id the lineage does not know", list(refused_for([row(ghost, root, "g", 47109)], keys)) == ["ghost"])

            for field, value in (("agent_id", 7), ("login", ["x"]), ("peer_id", None), ("endpoint", 1), ("port", "47103"),
                                 ("port", True), ("identity_show", 5), ("login_signature", None)):
                bad = dict(row(c, root, "c", 47103), **{field: value})
                try:
                    got = R.valid_rows(doc([ra, bad]), keys)[1]
                    crashed = False
                except Exception:  # noqa: BLE001 — a crash is what this case is for
                    crashed = True
                check(f"a row whose {field} is {value!r} is refused, never a crash", not crashed and len(got) == 1, str(got))

            dup = refused_for([row(a, root, "a", 47101), row(b, root, "b", 47101)], keys)
            check("a port claimed twice refuses both rows, neither is guessed", sorted(dup) == ["alpha", "beta"], str(dup))
            dup = refused_for([row(a, root, "a", 47101), row(b, root, "a", 47102)], keys)
            check("a PeerId claimed twice refuses both rows", sorted(dup) == ["alpha", "beta"], str(dup))

            good, _ = R.valid_rows(doc([ra, rb, row(c, root, "c", 47103, signer=a)]), keys)
            cfg_a = R.render_config(doc([ra, rb]), good, a.agent_id)
            check("the config allowlists the other valid peers and not itself nor a refused one",
                  json.dumps([peer_id("b")]) in cfg_a and peer_id("a") not in cfg_a.split("allowed_peers")[1].split("\n")[0]
                  and peer_id("c") not in cfg_a)
            check("it listens on loopback at its own port and bootstraps the others' loopback addresses",
                  '"/ip4/127.0.0.1/tcp/47101"' in cfg_a and f"/ip4/127.0.0.1/tcp/47102/p2p/{peer_id('b')}" in cfg_a
                  and "0.0.0.0" not in cfg_a)
            check("it admits only the automated client kind on the gzcoord endpoint and joins no channel",
                  "allowed_client_kinds: [automated-client]" in cfg_a and "channels: { desired: [] }" in cfg_a)
            try:
                R.render_config(doc([ra, rb]), good, c.agent_id)
                refusing = False
            except R.RosterError:
                refusing = True
            check("an account with no valid row renders nothing", refusing)

            cfgdir = os.path.join(d, "cfg", "p")
            path = os.path.join(cfgdir, "config.yaml")
            R.write_config(path, cfg_a)
            R.write_config(path, cfg_a + "# again\n")
            check("config.yaml is written atomically, owner-only, with nothing left beside it",
                  open(path).read().endswith("# again\n") and oct(os.stat(path).st_mode & 0o777) == "0o600"
                  and os.listdir(cfgdir) == ["config.yaml"] and oct(os.stat(cfgdir).st_mode & 0o777) == "0o700")
            # --- rows with a host (ADR-064 §5, j422 F4): inert until a row carries one
            golden = (
                "# Rendered from runtime/interweave/roster.json by agent-fabric; never hand-edited\n"
                "schema_version: 2\nprofile: { name: gzcoord }\ntrust:\n  policy: static-allowlist\n"
                f"  allowed_peers: [\"{peer_id('b')}\"]\nendpoints:\n  default_direct_endpoint: gzcoord\n  entries:\n"
                "    - { id: gzcoord, enabled: true, advertise: false, allowed_client_kinds: [automated-client] }\n"
                "channels: { desired: [] }\ndiscovery:\n  providers:\n    - type: static-bootstrap\n      enabled: true\n"
                f"      priority: 5\n      config:\n        peers: [\"/ip4/127.0.0.1/tcp/47102/p2p/{peer_id('b')}\"]\n"
                "transport: { listen: { addresses: [\"/ip4/127.0.0.1/tcp/47101\"] } }\nobservability: { log_level: info }\n")
            check("a roster with no host renders exactly the loopback config (golden)", cfg_a == golden)
            check("canonical_row of a row without host is the five-field form every signed row has",
                  R.canonical_row(ra) == json.dumps({k: ra[k] for k in R.SIGNED_KEYS}, sort_keys=True, separators=(",", ":")).encode()
                  and b'"host"' not in R.canonical_row(ra)
                  and b'"host":"h1"' in R.canonical_row(dict(ra, host="h1")))
            hosts = {"h1": {"interweave_address": "10.9.0.1"}, "h2": {"interweave_address": "10.9.0.2"},
                     "h6": {"interweave_address": "fd00::6"}, "noaddr": {}, "named": {"interweave_address": "h1.example"}}

            def hdoc(rows: list[dict]) -> R.Roster:
                return R.Roster("gzcoord", "gzcoord", (47100, 47199), tuple(rows), hosts)
            ha, hb, hc = row(a, root, "a", 47101, host="h1"), row(b, root, "b", 47102, host="h2"), row(c, root, "c", 47103, host="h1")
            hall = hdoc([ha, hb, hc])
            good, bad = R.valid_rows(hall, keys)
            check("positive control: rows on two hosts, each signed over its own form, all count", len(good) == 3 and not bad, str(bad))
            cfg_ha, cfg_hb, cfg_hc = (R.render_config(hall, good, x.agent_id) for x in (a, b, c))
            check("an account with a host listens on the wildcard of its address's family, never on the address or loopback",
                  'listen: { addresses: ["/ip4/0.0.0.0/tcp/47101"] }' in cfg_ha and 'addresses: ["/ip4/0.0.0.0/tcp/47102"]' in cfg_hb
                  and "10.9.0.1/tcp/47101\"" not in cfg_ha and "127.0.0.1/tcp/47101" not in cfg_ha)
            check("a peer on the SAME host is bootstrapped on loopback, one on another host at that host's address",
                  f"/ip4/127.0.0.1/tcp/47103/p2p/{peer_id('c')}" in cfg_ha and f"/ip4/10.9.0.2/tcp/47102/p2p/{peer_id('b')}" in cfg_ha
                  and f"/ip4/10.9.0.1/tcp/47101/p2p/{peer_id('a')}" in cfg_hb and f"/ip4/10.9.0.1/tcp/47103/p2p/{peer_id('c')}" in cfg_hb
                  and f"/ip4/127.0.0.1/tcp/47101/p2p/{peer_id('a')}" in cfg_hc)
            check("the allowlist is still every other valid PeerId and nothing else",
                  json.dumps([peer_id("b"), peer_id("c")]) in cfg_ha and cfg_ha.count("allowed_peers") == 1)
            nohost = row(c, root, "c", 47103)
            good_m, _ = R.valid_rows(hdoc([ha, nohost]), keys)
            cfg_m_a, cfg_m_c = (R.render_config(hdoc([ha, nohost]), good_m, x.agent_id) for x in (a, c))
            check("a row with no host listens on loopback and is bootstrapped there; a hosted peer is dialled at its address",
                  'addresses: ["/ip4/127.0.0.1/tcp/47103"]' in cfg_m_c and f"/ip4/10.9.0.1/tcp/47101/p2p/{peer_id('a')}" in cfg_m_c
                  and f"/ip4/127.0.0.1/tcp/47103/p2p/{peer_id('c')}" in cfg_m_a)
            h6 = row(a, root, "a", 47101, host="h6")
            good6, _ = R.valid_rows(hdoc([h6, rb]), keys)
            cfg6 = R.render_config(hdoc([h6, rb]), good6, a.agent_id)
            check("an IPv6 host listens on :: and is dialled as an /ip6/ multiaddr",
                  'addresses: ["/ip6/::/tcp/47101"]' in cfg6 and f"/ip4/127.0.0.1/tcp/47102/p2p/{peer_id('b')}" in cfg6
                  and f"/ip6/fd00::6/tcp/47101/p2p/{peer_id('a')}" in R.render_config(hdoc([h6, rb]), good6, b.agent_id))
            inj = "fe80::1%x\"] } }\ntrust:\n  policy: allow-all\n#"
            for bad_addr in (inj, "fe80::1%eth0", "0.0.0.0", "::", "224.0.0.1", "::ffff:10.9.0.1", "255.255.255.255", "240.0.0.1"):
                hosts["evil"] = {"interweave_address": bad_addr}
                g, bd = R.valid_rows(hdoc([row(a, root, "a", 47101, host="evil"), rb]), keys)
                check(f"an interweave_address of {bad_addr[:14]!r} is refused in one line, the rest still count",
                      [x["login"] for x in g] == ["beta"] and len(bd) == 1 and "\n" not in bd[0].reason, str(bd))
            del hosts["evil"]
            late = row(a, root, "a", 47101, host_after_signing="h2")
            check("a host the countersignature does not cover is refused",
                  "countersignature" in refused_for([late], keys, hosts).get("alpha", ""), str(refused_for([late], keys, hosts)))
            moved = dict(ha, host="h2")
            check("moving a signed host to another is refused too", "countersignature" in refused_for([moved], keys, hosts).get("alpha", ""))
            dropped = {k: v for k, v in ha.items() if k != "host"}
            check("dropping a signed host is refused too", "countersignature" in refused_for([dropped], keys, hosts).get("alpha", ""))
            for why_case, hrow in (("unknown host", row(a, root, "a", 47101, host="nowhere")),
                                   ("host without an address", row(a, root, "a", 47101, host="noaddr")),
                                   ("host whose address is a name", row(a, root, "a", 47101, host="named")),
                                   ("malformed host id", row(a, root, "a", 47101, host="H 1"))):
                g, bd = R.valid_rows(hdoc([hrow, rb]), keys)
                check(f"{why_case}: the row is refused with one line and the rest still count",
                      [x["login"] for x in g] == ["beta"] and len(bd) == 1 and "\n" not in bd[0].reason, str(bd))
            try:
                R.render_config(hdoc([row(a, root, "a", 47101, host="nowhere"), rb]), [row(a, root, "a", 47101, host="nowhere"), rb], b.agent_id)
                silent = True
            except R.RosterError:
                silent = False
            check("render_config never falls back to loopback for a row whose host has no address", not silent)
            g, bd = R.valid_rows(R.Roster("gzcoord", "gzcoord", (47100, 47199), (ha, rb)), keys)
            check("a roster whose hosts registry was not attached refuses a row with a host", [x["login"] for x in g] == ["beta"] and len(bd) == 1)
            check("a non-text host is refused, never a crash", len(R.valid_rows(hdoc([dict(ha, host=7)]), keys)[1]) == 1)
            regp = os.path.join(d, "reg.json")
            with open(regp, "w") as fh:
                json.dump({"hosts": hosts}, fh)
            plain = R.Roster("gzcoord", "gzcoord", (47100, 47199), (ra, rb))
            check("with_hosts reads the registry only when a row names a host",
                  R.with_hosts(plain, os.path.join(d, "absent.json")) is plain
                  and R.with_hosts(hdoc([ha]), regp).hosts == hosts and R.with_hosts(R.Roster("g", "g", (1, 2), (ha,)), regp).hosts == hosts)
            try:
                R.with_hosts(R.Roster("g", "g", (1, 2), (ha,)), os.path.join(d, "absent.json"))
                unread = False
            except R.RosterError:
                unread = True
            check("a row with a host and an unreadable registry is a RosterError", unread)

            # a git that hangs, or cannot run, is a roster that does not verify: a RosterError
            fake = os.path.join(d, "fakebin")
            os.makedirs(fake)
            with open(os.path.join(fake, "git"), "w") as fh:
                fh.write("#!/bin/sh\nexec /usr/bin/sleep 20\n")
            os.chmod(os.path.join(fake, "git"), 0o755)
            saved = os.environ["PATH"]
            os.environ["PATH"] = fake
            try:
                outcomes = []
                for how in ("hangs", "missing"):
                    if how == "missing":
                        os.environ["PATH"] = os.path.join(d, "nowhere")
                    try:
                        R.GitMainKeys(d, timeout=0.3).lineage()
                        outcomes.append("no error")
                    except R.RosterError:
                        outcomes.append("RosterError")
                    except Exception as e:  # noqa: BLE001 — the case is what else could escape
                        outcomes.append(type(e).__name__)
            finally:
                os.environ["PATH"] = saved
            check("a git that hangs, or is not there, is a RosterError, not an exception that ends the carrier",
                  outcomes == ["RosterError", "RosterError"], str(outcomes))
        finally:
            for ag in (root, a, b, c):
                drop_key(ag.home)
    print(f"\ntest_gzcoord_carrier_roster: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
