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
spec = importlib.util.spec_from_file_location("secrets_sync", TOOL)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

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

    def run(fn, *a) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = fn(*a)
        return rc, out.getvalue() + err.getvalue()

    saved = {k: os.environ.get(k) for k in ("HOME", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")}
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
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
            check("bashrc sources the env file once", open(s.bashrc()).read().count("agent-fabric secrets") == 1)
            check("git identity, signing key and program applied",
                  (git("user.name"), git("user.signingkey"), git("gpg.program"), git("commit.gpgsign"))
                  == ("Fixture Person", "0123456789ABCDEF0123456789ABCDEF01234567", "/usr/bin/gpg", "true"))
            check("the ssh private key is written 0600, the public key beside it",
                  s.file_mode(s.ssh_key()) == 0o600 and open(s.ssh_key() + ".pub").read() == "ssh-ed25519 AAAAFIXTURE fixture\n")
            check("sync prints no value", "sk-or-FIXTURE" not in out and "ghp_FIXTUREGH" not in out, out)
            check("the report names the store", f"store={s.store_path()}" in out, out)

            run(s.sync, False, False)
            check("idempotent: a second sync adds no second bashrc line", open(s.bashrc()).read().count("agent-fabric secrets") == 1)

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

            store["values"] = fixture(ME)
            rc, out = run(s.sync, False, False, True)
            check("--quiet with everything present prints nothing, exit 0", rc == 0 and out == "", out)
            store["values"] = fixture(ME, "GH_TOKEN")
            rc, out = run(s.sync, False, False, True)
            check("--quiet with a name missing says so in one line, exit 2",
                  rc == 2 and out == "fabric-secrets: missing in the store: GH_TOKEN\n", repr(out))

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
            real_root = s.ROOT
            s.ROOT = fab
            try:
                store["values"] = fixture(ME)
                rc, out = run(s.sync, False, False)
                check("without the optional name: exit 0, not reported missing", rc == 0 and "DEMO_PORT_OFFSET" not in out, out)
                store["values"] = {**fixture(ME), "DEMO_PORT_OFFSET": "640"}
                rc, out = run(s.sync, False, False)
                check("with it: exported and listed as applied",
                      rc == 0 and "export DEMO_PORT_OFFSET=640" in open(envf).read() and "DEMO_PORT_OFFSET" in out, out)
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
                json.dump({"projects": {"demo": {"agent_env": {"DEMO_PORT_OFFSET": "the login stack offset"}}}},
                          open(os.path.join(fab, "projects", "registry.json"), "w"))
                rc, out = run(s.status, True)
                check("a store holding it is not unexpected, the registry naming it or not",
                      json.loads(out)["unexpected"] == [], out[:300])
            finally:
                s.ROOT = real_root

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
