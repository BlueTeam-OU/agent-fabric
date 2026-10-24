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
        countersigner: Agent | None = None, show: str | None = None) -> dict:
    pid = peer_id(seed)
    shown = show if show is not None else pid + "\n"
    r = {"agent_id": agent.agent_id, "login": agent.login, "peer_id": pid, "endpoint": "gzcoord", "port": port,
         "identity_show": shown, "login_signature": (signer or agent).sign(shown.encode())}
    r["countersignature"] = (countersigner or root).sign(R.canonical_row(r))
    return r


def doc(rows: list[dict], lo: int = 47100, hi: int = 47199) -> R.Roster:
    return R.Roster("gzcoord", "gzcoord", (lo, hi), tuple(rows))


def refused_for(rows: list[dict], keys: Keys) -> dict[str, str]:
    good, bad = R.valid_rows(doc(rows), keys)
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
