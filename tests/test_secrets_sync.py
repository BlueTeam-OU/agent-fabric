#!/usr/bin/env python3
"""Tests for tools/fabric/secrets_sync.py (fabric-secrets sync|status): what
a sync writes from the store's values, what it refuses, and what it never
prints. The store is faked at its two readers (fetch_values, fetch_names);
tests/test_secret_store.py drives the same sync through a real store. Runs
in a sandbox HOME, where git's --global config lands too."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import pwd
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(HERE, "tools", "fabric", "secrets_sync.py")
SHIM = os.path.join(HERE, "runtime", "provisioning", "secrets", "fabric-secrets")
FAKE_GH = os.path.join(HERE, "tests", "fixtures", "fake-gh-auth.sh")
spec = importlib.util.spec_from_file_location("secrets_sync", TOOL)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

from instance_fixtures import write_secrets_instance  # noqa: E402 — tests/, the script's own directory

ME = pwd.getpwuid(os.getuid()).pw_name


def fixture(login: str, *omit: str) -> dict[str, str]:
    d = {"AGENT_LOGIN": login, "AGENT_HOST": "fixture-host",
         "OPENROUTER_API_KEY": "sk-or-FIXTURE-OPENROUTER", "GH_TOKEN": "ghp_FIXTUREGH",
         "CLAUDE_BRIDGE_AUTH_TOKEN": "bridge-FIXTURE with 'quote' and $dollar",
         "GIT_USER_NAME": "Fixture Person", "GIT_USER_EMAIL": "fixture@example.invalid",
         "GIT_SIGNING_KEY": "0123456789ABCDEF0123456789ABCDEF01234567", "GIT_GPG_PROGRAM": "/usr/bin/gpg",
         # Deliberately NOT shaped like a real key: GitHub secret scanning
         # flags the BEGIN/END armour even around fixture text (alert on cdac5d2).
         "SSH_PRIVATE_KEY": "fixture-private-key-material FIXTUREKEYMATERIAL (not a key)",
         "SSH_PUBLIC_KEY": "ssh-ed25519 AAAAFIXTURE fixture"}
    for k in omit:
        d.pop(k, None)
    return d


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    store: dict = {"values": fixture(ME), "error": None}
    pulls: list[bool] = []

    def fake_fetch_values(pull: bool = True):
        pulls.append(pull)
        return (None, store["error"]) if store["error"] else (dict(store["values"]), None)
    s.fetch_values = fake_fetch_values
    s.fetch_names = lambda: (None, store["error"]) if store["error"] else (list(store["values"]), None)
    real_load_store = s.load_store

    def run(fn, *a) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = fn(*a)
        return rc, out.getvalue() + err.getvalue()

    saved = {k: os.environ.get(k) for k in ("HOME", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "AGENT_FABRIC_GH",
                                             "GH_CONFIG_DIR", "XDG_CONFIG_HOME", "FAKE_GH_LOGIN_EXIT",
                                             "AGENT_FABRIC_HOSTS_REGISTRY", "AGENT_FABRIC_OPERATOR", "AGENT_FABRIC_ROOT")}
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        # The registries are instance data, read from the operator root: this
        # fixture's, never the checkout's (cases below set their own).
        write_secrets_instance(os.path.join(tmp, "operator"))
        os.environ["AGENT_FABRIC_OPERATOR"] = os.path.join(tmp, "operator")
        os.environ.pop("AGENT_FABRIC_ROOT", None)
        # Never the real gh: it follows XDG_CONFIG_HOME and the keyring, not
        # HOME (it once read the runner's token from here).
        os.environ["AGENT_FABRIC_GH"] = FAKE_GH
        for k in ("GH_CONFIG_DIR", "XDG_CONFIG_HOME", "FAKE_GH_LOGIN_EXIT", "AGENT_FABRIC_HOSTS_REGISTRY"):
            os.environ.pop(k, None)
        os.environ.pop("GIT_CONFIG_GLOBAL", None)
        os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
        git = lambda k: subprocess.run(["git", "config", "--global", "--get", k], capture_output=True, text=True).stdout.strip()
        envf = s.env_file()
        try:
            # --no-pull: a new account applies the copy it was just handed
            # (store take-bundle); every other sync pulls first.
            pulls.clear()
            rc, _ = run(s.main, ["sync", "--quiet"])
            rc2, _ = run(s.main, ["sync", "--quiet", "--no-pull"])
            rc3, _ = run(s.main, ["status", "--no-pull"])
            check("sync pulls; --no-pull does not; status refuses the flag",
                  pulls == [True, False] and rc == 0 and rc2 == 0 and rc3 == 2, (pulls, rc, rc2, rc3))
            rc, out = run(s.sync, False, False)
            check("sync exits 0 with every name present", rc == 0, out)
            check("the env file is 0600", s.file_mode(envf) == 0o600)
            body = open(envf).read()
            exports = [l.split("=", 1)[0][len("export "):] for l in body.splitlines() if l.startswith("export ")]
            check("the env file exports exactly the three environment names", exports == s.ENV_NAMES, exports)
            check("the env file carries no git string and no key material",
                  "Fixture Person" not in body and "FIXTUREKEYMATERIAL" not in body)
            sourced = subprocess.run(["bash", "-c", f"source '{envf}'; printf '%s' \"$CLAUDE_BRIDGE_AUTH_TOKEN\""],
                                     capture_output=True, text=True).stdout
            check("a value with quotes and a dollar survives sourcing", sourced == "bridge-FIXTURE with 'quote' and $dollar", sourced)
            rc_text = open(s.bashrc()).read()
            check("bashrc sources env.sh once, and secrets.env never",
                  rc_text.count("agent-fabric secrets") == 1 and s.shell_env_file() in rc_text and envf not in rc_text,
                  rc_text)
            shell = open(s.shell_env_file()).read()
            check("env.sh is 0600 and carries no secret (nothing is marked plain here)",
                  s.file_mode(s.shell_env_file()) == 0o600 and "export " not in shell, shell)
            # A clean environment (the runner's own shell may hold the real
            # names), and the shell answers set/unset per name, never a value:
            # this check once printed a real token when it failed.
            names = ("GH_TOKEN", "OPENROUTER_API_KEY", "CLAUDE_BRIDGE_AUTH_TOKEN")
            probe = "; ".join(f'[ -n "${{{n}+x}}" ] && echo {n}=set || echo {n}=unset' for n in names)
            leaked = subprocess.run(["bash", "-ic", probe], capture_output=True, text=True,
                                    env={"HOME": tmp, "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "TERM": "dumb"}).stdout
            check("an interactive shell of the account holds no synced secret",
                  leaked.split() == [f"{n}=unset" for n in names], leaked.split())
            check("gh holds GH_TOKEN, through its own configuration", s.gh_token_matches("ghp_FIXTUREGH") is True)
            check("git identity, signing key and program applied",
                  (git("user.name"), git("user.signingkey"), git("gpg.program"), git("commit.gpgsign"))
                  == ("Fixture Person", "0123456789ABCDEF0123456789ABCDEF01234567", "/usr/bin/gpg", "true"))
            check("the ssh private key is written 0600, the public key beside it",
                  s.file_mode(s.ssh_key()) == 0o600 and open(s.ssh_key() + ".pub").read() == "ssh-ed25519 AAAAFIXTURE fixture\n")
            check("sync prints no value", "sk-or-FIXTURE" not in out and "ghp_FIXTUREGH" not in out, out)
            check("the report names the store", f"store={s.store_path()}" in out, out)

            rc, out = run(s.sync, False, True)
            check("idempotent: a second sync adds no second bashrc line, and gh is unchanged",
                  open(s.bashrc()).read().count("agent-fabric secrets") == 1
                  and not [a for a in json.loads(out)["applied"] if "bashrc" in a or "into gh" in a], out[:400])

            # An older sync's line sourced secrets.env: replaced in place, the
            # rest of ~/.bashrc kept byte for byte, and status says it until then.
            old = f"[ -r {envf} ] && . {envf}  # agent-fabric secrets"
            with open(s.bashrc(), "w") as fh:
                fh.write(f"# mine, above\nalias ll='ls -l'\n{old}\nexport MINE=1\n")
            os.chmod(s.bashrc(), 0o640)
            rc, out = run(s.status, False)
            check("status: a bashrc that sources secrets.env is NOT OK, and said",
                  rc == 1 and "SOURCES secrets.env" in out, out)
            rc, out = run(s.sync, False, True)
            after = open(s.bashrc()).read()
            check("sync replaces that line in place, keeping the rest and the mode",
                  after == f"# mine, above\nalias ll='ls -l'\n{s.source_line()}\nexport MINE=1\n"
                  and s.file_mode(s.bashrc()) == 0o640
                  and "bashrc (now sources env.sh, not secrets.env)" in json.loads(out)["applied"], after)
            with open(s.bashrc(), "a") as fh:
                fh.write(f"{old}\n")
            run(s.sync, False, False)
            check("a second marked line goes too: exactly one remains", open(s.bashrc()).read().count("# agent-fabric secrets") == 1,
                  open(s.bashrc()).read())

            # A dotfiles-managed ~/.bashrc: the line is fixed in its target,
            # and the link stays a link.
            target = os.path.join(tmp, "dotfiles-bashrc")
            os.replace(s.bashrc(), target)
            with open(target, "a") as fh:
                fh.write(f"{old}\n")
            os.symlink(target, s.bashrc())
            run(s.sync, False, False)
            check("a symlinked ~/.bashrc is fixed in its target and stays a link",
                  os.path.islink(s.bashrc()) and envf not in open(target).read()
                  and open(target).read().count("# agent-fabric secrets") == 1, open(target).read())
            os.remove(s.bashrc())
            os.replace(target, s.bashrc())

            # gh refusing the token: exit 2, said, never the token.
            os.remove(os.path.join(tmp, ".config", "gh", "fake-token"))
            os.environ["FAKE_GH_LOGIN_EXIT"] = "1"
            rc, out = run(s.sync, False, True)
            os.environ.pop("FAKE_GH_LOGIN_EXIT")
            check("gh refusing GH_TOKEN fails the sync (exit 2), named, valueless",
                  rc == 2 and "GH_TOKEN into gh (gh auth login exit 1)" in json.loads(out)["skipped"]
                  and "ghp_FIXTUREGH" not in out, out[:400])
            rc, out = run(s.status, False)
            check("…and status is NOT OK while the store holds GH_TOKEN and gh holds none",
                  rc == 1 and "gh has a token: False" in out, out)
            os.environ.pop("AGENT_FABRIC_GH")
            check("a sandbox HOME with no fake named never reaches a real gh", s.gh_binary() is None)
            os.environ["AGENT_FABRIC_GH"] = FAKE_GH
            run(s.sync, False, False)

            open(s.ssh_key(), "w").write("LOCAL-KEY")
            rc, out = run(s.sync, False, False)
            check("an existing ssh key is kept, and the skip said",
                  open(s.ssh_key()).read() == "LOCAL-KEY" and "SSH_PRIVATE_KEY (present; --force replaces)" in out, out)
            run(s.sync, True, False)
            check("--force replaces it", "FIXTUREKEYMATERIAL" in open(s.ssh_key()).read())

            store["values"] = fixture("someone-else")
            before = open(envf).read()
            rc, out = run(s.sync, False, False)
            check("a store naming another login is refused (exit 3), and says why",
                  rc == 3 and "AGENT_LOGIN=someone-else" in out, out)
            check("…and nothing was rewritten", open(envf).read() == before)

            store["values"] = fixture(ME, "OPENROUTER_API_KEY", "GIT_SIGNING_KEY")
            rc, out = run(s.sync, False, False)
            check("missing names: exit 2, listed", rc == 2 and "missing: OPENROUTER_API_KEY, GIT_SIGNING_KEY" in out, out)
            body = open(envf).read()
            check("…the env file drops the missing key and keeps the rest",
                  "OPENROUTER_API_KEY" not in body and "export GH_TOKEN=" in body)

            store["values"] = fixture(ME)
            run(s.sync, False, False)
            rc, out = run(s.status, False)
            check("status exits 0 when all is present and applied", rc == 0, out)
            check("status prints no secret", "FIXTURE" not in out, out)
            rc, out = run(s.status, True)
            check("status --json is JSON naming the login and the store",
                  json.loads(out)["login"] == ME and json.loads(out)["source"] == "store", out[:200])
            store["values"] = fixture(ME, "GH_TOKEN")
            rc, out = run(s.status, False)
            check("status exits 1 when a name is missing, and names it", rc == 1 and "missing: GH_TOKEN" in out, out)

            # The stores' verification state (ADR-042), faked at its reader:
            # a missing base is NOT OK, said as a refusal is, and a reading
            # that fails is never a clean bill (review of #94).
            store["values"] = fixture(ME)
            real_verification = s.fetch_verification
            kid = "01a106ee-84ec-74bc-84ef-3720a55d6a3f"
            try:
                s.fetch_verification = lambda: ([], [], None)
                rc, out = run(s.status, False)
                check("control: nothing refused and every base there, status is OK", rc == 0 and "BASE" not in out, out)
                s.fetch_verification = lambda: ([], [{"store": kid, "state": "no base", "path": "/m/" + kid}], None)
                rc, out = run(s.status, False)
                check("a mirror with no base: exit 1, its repair and the owner named",
                      rc == 1 and f"NO BASE: the mirror of agent {kid} has no trusted base" in out
                      and f"trust-base --store /m/{kid}, with the owner where its history cannot be verified" in out, out)
                rc, out = run(s.status, True)
                check("…--json lists it under no_trusted_base",
                      rc == 1 and json.loads(out)["no_trusted_base"] == [{"store": kid, "state": "no base", "path": "/m/" + kid}], out[:300])
                s.fetch_verification = lambda: ([], [{"store": "own", "state": "unreadable", "reason": "r"}], None)
                rc, out = run(s.status, False, True)
                check("--quiet: an unreadable base in one line, exit 1",
                      rc == 1 and out == "fabric-secrets: BASE UNREADABLE: the store: r — its trusted base cannot be read; "
                      "this account looks at it (ADR-042)\n", repr(out))
                s.fetch_verification = lambda: ([{"store": "own", "commit": "c" * 40, "at": "T", "reason": "not signed"}],
                                                [{"store": kid, "state": "no base", "path": "p"}], None)
                rc, out = run(s.status, False, True)
                check("--quiet: a refusal and a missing base, both in the one line",
                      rc == 1 and out.count("\n") == 1 and "REFUSED: the store" in out and "; NO BASE: the mirror" in out, repr(out))
                s.fetch_verification = lambda: ([], [], "the stores' refusals and trusted bases could not be read: x")
                rc, out = run(s.status, True)
                check("a reading that fails: exit 1, said as the error",
                      rc == 1 and json.loads(out)["error"].endswith("could not be read: x"), out[:300])
                s.load_store = lambda: (_ for _ in ()).throw(RuntimeError("no module"))
                s.fetch_verification = real_verification
                check("…the real reader turns any failure into that error, never an empty list",
                      s.fetch_verification() == ([], [], "the stores' refusals and trusted bases could not be read: no module"))
            finally:
                s.fetch_verification = real_verification
                s.load_store = real_load_store

            store["values"] = fixture(ME)
            rc, out = run(s.sync, False, False, True)
            check("--quiet with everything present prints nothing, exit 0", rc == 0 and out == "", out)
            store["values"] = fixture(ME, "GH_TOKEN")
            rc, out = run(s.sync, False, False, True)
            check("--quiet with a name missing says so in one line, exit 2",
                  rc == 2 and out == "fabric-secrets: missing in the store: GH_TOKEN\n", repr(out))

            # The names required are the login's kind's (ADR-044): a human
            # holds who it is and the relay credential, nothing of a session.
            hosts = os.path.join(tmp, "hosts.json")
            human = {k: v for k, v in fixture(ME).items() if k in ("AGENT_LOGIN", "AGENT_HOST", "CLAUDE_BRIDGE_AUTH_TOKEN")}

            def kinds(table: object) -> None:
                with open(hosts, "w", encoding="utf-8") as fh:
                    json.dump({"hosts": {}, "placement": {ME: "h"}, **({} if table is None else {"kinds": table})}, fh)
            os.environ["AGENT_FABRIC_HOSTS_REGISTRY"] = hosts
            real_verification = s.fetch_verification
            s.fetch_verification = lambda: ([], [], None)
            try:
                store["values"] = human
                kinds(None)
                rc, out = run(s.status, True)
                check("control: a login kinds does not name is an agent, and a human's store is missing its names",
                      rc == 1 and "GH_TOKEN" in json.loads(out)["missing"], out[:300])
                kinds({ME: "human"})
                rc, out = run(s.sync, False, True)
                check("a human: sync applies its three names, exit 0, nothing missing",
                      rc == 0 and json.loads(out)["missing"] == [] and "CLAUDE_BRIDGE_AUTH_TOKEN" in json.loads(out)["applied"],
                      out[:300])
                rc, out = run(s.status, False)
                check("…and status is OK for it", rc == 0 and "missing: (none)" in out and "  OK" in out, out)
                store["values"] = {k: v for k, v in human.items() if k != "CLAUDE_BRIDGE_AUTH_TOKEN"}
                rc, out = run(s.status, False)
                check("a human without the relay credential: status exits 1, naming it",
                      rc == 1 and "missing: CLAUDE_BRIDGE_AUTH_TOKEN" in out, out)
                # An agent's names in a human's store are withheld: never
                # applied, and both sync and status fail on them (#118, Codex).
                store["values"] = {**human, "GH_TOKEN": "ghp_FIXTUREGH", "SSH_PRIVATE_KEY": "fixture-private-key-material"}
                os.remove(envf)
                rc, out = run(s.sync, False, True)
                body = open(envf).read()
                check("a human whose store holds an agent's names: sync withholds them, exit 2, named",
                      rc == 2 and json.loads(out)["withheld"] == ["GH_TOKEN", "SSH_PRIVATE_KEY"]
                      and "GH_TOKEN" not in body and "CLAUDE_BRIDGE_AUTH_TOKEN" in body
                      and "GH_TOKEN" not in json.loads(out)["applied"]
                      and "holds an agent's names, not applied: GH_TOKEN, SSH_PRIVATE_KEY" in json.loads(out)["error"],
                      out[:400])
                rc, out = run(s.status, True)
                check("…and status exits 1, naming them", rc == 1 and json.loads(out)["withheld"] == ["GH_TOKEN", "SSH_PRIVATE_KEY"],
                      out[:300])
                kinds({ME: "agent"})
                store["values"] = fixture(ME)
                rc, out = run(s.sync, False, True)
                check("…while an agent's store withholds nothing (the control)",
                      rc == 0 and json.loads(out)["withheld"] == [], out[:300])
                store["values"] = fixture(ME)
                for label, table in (("an unknown kind", {ME: "robot"}), ("a kinds that is not a table", ["x"])):
                    kinds(table)
                    rc, out = run(s.status, True)
                    check(f"{label}: status exits 1, the kind said unreadable, never taken for an agent",
                          rc == 1 and "kind could not be read" in json.loads(out).get("error", ""), out[:300])
                os.remove(hosts)
                rc, out = run(s.status, True)
                check("no hosts registry: status exits 1, said", rc == 1 and "kind could not be read" in json.loads(out)["error"],
                      out[:300])
                rc, out = run(s.sync, False, True)
                check("…and sync applies, then exits 2 with it",
                      rc == 2 and json.loads(out)["error"].startswith("applied, but this login's kind could not be read")
                      and "GH_TOKEN" in json.loads(out)["applied"], out[:300])
            finally:
                s.fetch_verification = real_verification
                os.environ.pop("AGENT_FABRIC_HOSTS_REGISTRY", None)
                store["values"] = fixture(ME)

            store["error"] = "store: git pull: could not reach the remote"
            rc, out = run(s.sync, False, True)
            check("an unreadable store: exit 1, the error in the JSON report the control agent reads",
                  rc == 1 and json.loads(out)["error"].startswith("store:"), out[:200])
            store["error"] = None

            # A project's declared per-agent names: exported when present,
            # never missing, never unexpected.
            fab = os.path.join(tmp, "fabric")
            os.makedirs(os.path.join(fab, "projects"))
            json.dump({"projects": {"demo": {"agent_env": {"DEMO_PORT_OFFSET": "the login stack offset"}}}},
                      open(os.path.join(fab, "projects", "registry.json"), "w"))
            # The instance data (the registry) is read from the operator root.
            real_operator = os.environ.get("AGENT_FABRIC_OPERATOR")
            os.environ["AGENT_FABRIC_OPERATOR"] = fab
            # Every fabric has a hosts registry; the login's kind is read there.
            os.makedirs(os.path.join(fab, "runtime", "hosts"))
            json.dump({"hosts": {}, "placement": {}}, open(os.path.join(fab, "runtime", "hosts", "registry.json"), "w"))
            try:
                store["values"] = fixture(ME)
                rc, out = run(s.sync, False, False)
                check("without the optional name: exit 0, not reported missing", rc == 0 and "DEMO_PORT_OFFSET" not in out, out)
                store["values"] = {**fixture(ME), "DEMO_PORT_OFFSET": "640"}
                rc, out = run(s.sync, False, False)
                check("with it: exported and listed as applied",
                      rc == 0 and "export DEMO_PORT_OFFSET=640" in open(envf).read() and "DEMO_PORT_OFFSET" in out, out)
                check("…but not into env.sh: a name nobody marked plain is a secret", "DEMO_PORT_OFFSET" not in open(s.shell_env_file()).read())
                json.dump({"projects": {"demo": {"agent_env": {"DEMO_PORT_OFFSET": "the login stack offset"},
                                                 "plain_env": ["DEMO_PORT_OFFSET", "GH_TOKEN"]}}},
                          open(os.path.join(fab, "projects", "registry.json"), "w"))
                run(s.sync, False, False)
                shell = open(s.shell_env_file()).read()
                check("marked plain: in env.sh, and a fabric secret marked plain is still never there",
                      "export DEMO_PORT_OFFSET=640" in shell and "GH_TOKEN" not in shell, shell)
                rc, out = run(s.status, True)
                check("status does not call it unexpected", json.loads(out)["unexpected"] == [], out[:300])

                # The operator's signing key stays in the store, even where
                # the registry declares it fabric-wide (as it did when a
                # reviewer printed it from the environment), and a line an
                # older sync wrote goes with the next one.
                sk = "ed25519-pkcs8:FIXTURE-SIGNING-KEY"
                json.dump({"agent_env": {"FABRIC_CONTROL_SIGNING_KEY": "the operator's key"},
                           "projects": {"demo": {"agent_env": {"DEMO_PORT_OFFSET": "the login stack offset"}}}},
                          open(os.path.join(fab, "projects", "registry.json"), "w"))
                with open(envf, "a") as fh:
                    fh.write(f"export FABRIC_CONTROL_SIGNING_KEY={sk}\n")
                store["values"] = {**fixture(ME), "DEMO_PORT_OFFSET": "640", "FABRIC_CONTROL_SIGNING_KEY": sk}
                rc, out = run(s.sync, False, True)
                written = open(envf).read()
                check("the signing key is never written into secrets.env, and a stale line is gone",
                      rc == 0 and "FABRIC_CONTROL_SIGNING_KEY" not in written and "export DEMO_PORT_OFFSET=640" in written,
                      written)
                check("nor listed as applied, nor printed",
                      "FABRIC_CONTROL_SIGNING_KEY" not in json.loads(out)["applied"] and sk not in out, out[:300])
                # values_sha256 covers what sync applies: a store-only key is
                # not applied, so changing it is no change (review of #96).
                store["values"] = {**store["values"], "FABRIC_CONTROL_SIGNING_KEY": sk + "-rotated"}
                rc2, out2 = run(s.sync, False, True)
                store["values"] = {**store["values"], "DEMO_PORT_OFFSET": "641"}
                rc3, out3 = run(s.sync, False, True)
                digest = lambda o: json.loads(o)["values_sha256"]  # noqa: E731
                check("the signing key is not in values_sha256; an applied value is (the control)",
                      rc2 == rc3 == 0 and digest(out2) == digest(out) and digest(out3) != digest(out2), (out2[:200], out3[:200]))
                json.dump({"projects": {"demo": {"agent_env": {"DEMO_PORT_OFFSET": "the login stack offset"}}}},
                          open(os.path.join(fab, "projects", "registry.json"), "w"))
                rc, out = run(s.status, True)
                check("a store holding it is not unexpected, the registry naming it or not",
                      json.loads(out)["unexpected"] == [], out[:300])
            finally:
                if real_operator is None:
                    del os.environ["AGENT_FABRIC_OPERATOR"]
                else:
                    os.environ["AGENT_FABRIC_OPERATOR"] = real_operator

            # write_private: a symlink or a looser file at the old fixed
            # temporary path is never written through, and nothing is left.
            cfg = os.path.join(tmp, "wp")
            os.makedirs(cfg, mode=0o700)
            outside = os.path.join(tmp, "outside")
            open(outside, "w").close()
            os.symlink(outside, os.path.join(cfg, "secrets.env.tmp"))
            s.write_private(os.path.join(cfg, "secrets.env"), "export X='CANARY-WP'\n", 0o600)
            check("write_private never writes through a symlink at <path>.tmp",
                  open(outside).read() == "" and open(os.path.join(cfg, "secrets.env")).read() == "export X='CANARY-WP'\n",
                  open(outside).read())
            check("and leaves only the target, 0600",
                  os.listdir(cfg) == ["secrets.env"] and s.file_mode(os.path.join(cfg, "secrets.env")) == 0o600, os.listdir(cfg))
            s.write_private(os.path.join(cfg, "id.pub"), "pub\n", 0o644)
            check("a public file still gets the mode asked for", s.file_mode(os.path.join(cfg, "id.pub")) == 0o644,
                  oct(s.file_mode(os.path.join(cfg, "id.pub")) or 0))

            # The shim: sync and status go to this module, an unknown command
            # is usage (2), and no Doppler is asked — there is none.
            r = subprocess.run([SHIM, "digest"], capture_output=True, text=True, env={**os.environ, "HOME": tmp})
            check("the shim refuses the retired digest as usage (exit 2)", r.returncode == 2 and "usage" in r.stderr, r.stderr)
            r = subprocess.run([SHIM, "--help"], capture_output=True, text=True, env={**os.environ, "HOME": tmp})
            check("--help names no Doppler", r.returncode == 0 and "doppler" not in r.stderr.lower(), r.stderr)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
