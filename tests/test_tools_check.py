#!/usr/bin/env python3
"""tools/fabric/tools_check.py (bin/fabric-tools): a project's declared tools
proved on this account. A present tool is ok with what its proof printed;
a missing command, a failing proof and a hung one are said; a role-only
tool is checked only for its roles; an optional missing tool never fails
the check."""
from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import tools_check as tc  # noqa: E402

REG = {"projects": {"demo": {"tools": [
    {"name": "present", "proof": "sh -c 'echo demo 1.2'", "version": "1.x", "why": "w", "where": "host"},
    {"name": "absent", "proof": "fabric-no-such-command --version", "version": "any", "why": "w", "where": "host"},
    {"name": "broken", "proof": "sh -c 'echo nope >&2; exit 3'", "version": "any", "why": "w", "where": "account"},
    {"name": "roleonly", "proof": "fabric-no-such-command", "version": "any", "why": "w", "where": "host",
     "roles": ["flutter-dev"]},
    {"name": "maybe", "proof": "fabric-no-such-command", "version": "any", "why": "w", "where": "host",
     "optional": True}]},
    "bare": {}}}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    rows = {r["name"]: r for r in tc.check(["demo"], "python-dev", REG)}
    check("a present tool: ok, with its proof's first line", rows["present"]["status"] == "ok"
          and rows["present"]["found"] == "demo 1.2", rows["present"])
    check("a missing command: missing, named", rows["absent"]["status"] == "missing"
          and "not found" in rows["absent"]["found"], rows["absent"])
    check("a failing proof: failed, with its exit and first line", rows["broken"]["status"] == "failed"
          and "exit 3" in rows["broken"]["found"] and "nope" in rows["broken"]["found"], rows["broken"])
    check("a role-only tool is not checked for another role", "roleonly" not in rows)
    check("…and is for its role", "roleonly" in {r["name"] for r in tc.check(["demo"], "flutter-dev", REG)})
    check("an optional tool is reported", rows["maybe"]["optional"] and rows["maybe"]["status"] == "missing")
    tc.PROOF_TIMEOUT_S, saved = 1, tc.PROOF_TIMEOUT_S
    try:
        st, why = tc.prove("sleep 5")
    finally:
        tc.PROOF_TIMEOUT_S = saved
    check("a proof that hangs: its own state, timeout, said as a rerun (j177)",
          st == "timeout" and "not answered in 1 s, rerun" in why, (st, why))

    # bound_role: identity's refusals (SystemExit for a login another host
    # holds) are no role, never the end of the check.
    import identity
    agent, binding = identity.current_agent, identity.read_binding

    def refuse(*_: object) -> str:
        raise SystemExit("identity: refused")

    def fail(*_: object) -> str:
        raise RuntimeError("unreadable")
    try:
        identity.current_agent, identity.read_binding = (lambda: "pd-x"), (lambda login: {"role": "python-dev"})
        check("bound_role: the binding's role", tc.bound_role() == "python-dev")
        identity.current_agent = refuse
        try:
            got: object = tc.bound_role()
        except SystemExit as e:
            got = f"SystemExit({e})"
        check("…none when identity exits", got is None, got)
        identity.current_agent = fail
        check("…none when identity raises", tc.bound_role() is None)
    finally:
        identity.current_agent, identity.read_binding = agent, binding

    # A tree pin: the proof printing the version is not enough (review of #229) — the single-file Codex
    # 0.162.1 did, and ran no command.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="test_tools_check.") as home:
        bindir = os.path.join(home, ".local", "bin")
        os.makedirs(bindir)
        script = '#!/bin/sh\necho "treetool 1.0"\n'
        pin = {"version": "1.0", "url": "https://example.invalid/t.tgz", "sha256": "0" * 64, "root": "pkg",
               "members": ["bin/treetool", "lib.txt"], "entrypoint": "bin/treetool"}
        tree_reg = {"projects": {"demo": {"tools": [{"name": "treetool", "proof": "treetool --version", "version": "1.0",
                                                     "why": "w", "where": "account", "install": pin}]}}}
        with open(os.path.join(bindir, "treetool"), "w") as fh:
            fh.write(script)
        os.chmod(os.path.join(bindir, "treetool"), 0o755)
        saved_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bindir}:{saved_path}"
        try:
            row = tc.check(["demo"], None, tree_reg, home=home)[0]
            check("a tree pin whose ~/.local/bin entry is a lone file: incomplete, with the --install hint",
                  row["status"] == "incomplete" and "fabric-tools --install treetool" in row["found"]
                  and "treetool 1.0" in row["found"], row)
            tree = os.path.join(home, ".local", "lib", "agent-fabric-tools", "treetool", "1.0")
            os.makedirs(os.path.join(tree, "bin"))
            os.rename(os.path.join(bindir, "treetool"), os.path.join(tree, "bin", "treetool"))
            os.symlink(os.path.join(tree, "bin", "treetool"), os.path.join(bindir, "treetool"))
            row = tc.check(["demo"], None, tree_reg, home=home)[0]
            check("…a link into a tree missing a member: incomplete", row["status"] == "incomplete", row)
            open(os.path.join(tree, "lib.txt"), "w").close()
            row = tc.check(["demo"], None, tree_reg, home=home)[0]
            check("…the whole tree linked: ok (positive control)", row["status"] == "ok" and row["found"] == "treetool 1.0", row)
            os.unlink(os.path.join(tree, "lib.txt"))
            real_reg, real_home = tc.registry, os.environ.get("HOME")
            tc.registry, os.environ["HOME"] = (lambda: tree_reg), home
            try:
                out = io.StringIO()
                with redirect_stdout(out):
                    rc = tc.main(["--project", "demo", "--role", "python-dev"])
            finally:
                tc.registry = real_reg
                if real_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = real_home
            check("fabric-tools: an incomplete tree is a failure, exit 1, the hint printed",
                  rc == 1 and "incomplete" in out.getvalue() and "fabric-tools --install treetool" in out.getvalue(), (rc, out.getvalue()))
        finally:
            os.environ["PATH"] = saved_path

    # A rustup-target pin: the proof exits 0 for a toolchain that lacks the target, so the list's lines decide.
    with tempfile.TemporaryDirectory(prefix="test_tools_check.") as home:
        bindir = os.path.join(home, ".cargo", "bin")
        os.makedirs(bindir)
        fake = os.path.join(bindir, "rustup")
        with open(fake, "w") as fh:
            fh.write('#!/bin/sh\necho x86_64-unknown-linux-gnu\necho aarch64-linux-androideabi\n'
                     '[ -e "$HOME/.has-target" ] && echo aarch64-linux-android\n'
                     '[ -e "$HOME/.list-fails" ] && { echo "error: toolchain is not installed" >&2; exit 1; }\nexit 0\n')
        os.chmod(fake, 0o755)
        tpin = {"kind": "rustup-target", "toolchain": "1.98.1", "target": "aarch64-linux-android"}
        treg = {"projects": {"demo": {"tools": [{"name": "rust-std-android",
                                                 "proof": "rustup target list --installed --toolchain 1.98.1",
                                                 "version": "any", "why": "w", "where": "account", "install": tpin}]}}}
        saved_path, saved_home = os.environ.get("PATH", ""), os.environ.get("HOME")
        # The check runs the list as --install does, from the account's ~/.cargo/bin: the session's PATH has no rustup.
        os.environ["PATH"], os.environ["HOME"] = "/usr/bin:/bin", home
        try:
            row = tc.check(["demo"], None, treg, home=home)[0]
            check("a target pin whose list exits 0 without the target (a decoy name is listed): missing, said",
                  row["status"] == "missing" and "aarch64-linux-android is not installed for toolchain 1.98.1" in row["found"], row)
            open(os.path.join(home, ".has-target"), "w").close()
            row = tc.check(["demo"], None, treg, home=home)[0]
            check("...the target listed: ok (positive control)", row["status"] == "ok" and row["found"] == "aarch64-linux-android for 1.98.1", row)
            open(os.path.join(home, ".list-fails"), "w").close()
            row = tc.check(["demo"], None, treg, home=home)[0]
            check("...a list that fails (the toolchain is not installed) is failed, whatever it printed",
                  row["status"] == "failed" and "exit 1" in row["found"], row)
            os.unlink(os.path.join(home, ".list-fails"))
            bad = {"projects": {"demo": {"tools": [{**treg["projects"]["demo"]["tools"][0],
                                                    "install": {**tpin, "target": "x;y"}}]}}}
            row = tc.check(["demo"], None, bad, home=home)[0]
            check("...a pin naming no plain target proves nothing, though the list exits 0", row["status"] == "failed", row)
            open(os.path.join(home, ".has-target"), "w").close()
            stale = {"projects": {"demo": {"tools": [{**treg["projects"]["demo"]["tools"][0],
                                                      "proof": "rustup target list --installed --toolchain 1.97.0"}]}}}
            row = tc.check(["demo"], None, stale, home=home)[0]
            check("...a proof naming another toolchain is failed, as --install refuses it, though it lists the target",
                  row["status"] == "failed" and "1.98.1" in row["found"], row)
            other = os.path.join(home, "other")
            os.makedirs(other)
            os.rename(fake, os.path.join(other, "rustup"))
            os.environ["PATH"] = f"{other}:/usr/bin:/bin"
            row = tc.check(["demo"], None, treg, home=home)[0]
            check("...no rustup under the account's ~/.cargo/bin is missing even when the session's PATH has one",
                  row["status"] == "missing", row)
        finally:
            os.environ["PATH"] = saved_path
            if saved_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = saved_home

    real = tc.registry
    tc.registry = lambda: REG
    try:
        def run(*args: str) -> tuple[int, str]:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = tc.main(list(args))
            return rc, out.getvalue()
        rc, out = run("--project", "demo", "--role", "python-dev", "--json")
        doc = json.loads(out)
        check("a required tool missing: exit 1, ok false", rc == 1 and doc["ok"] is False, (rc, doc["ok"]))
        rc, out = run("--project", "bare", "--role", "python-dev")
        check("a project that declares none: exit 0, said", rc == 0 and "declares no tools" in out, (rc, out))
        rc, _ = run("--project", "nosuch")
        check("an unknown project: exit 2", rc == 2)
        REG["projects"]["demo"]["tools"] = [t for t in REG["projects"]["demo"]["tools"] if t["name"] in ("present", "maybe")]
        rc, _ = run("--project", "demo", "--role", "python-dev")
        check("only an optional tool missing: exit 0", rc == 0, rc)
    finally:
        tc.registry = real
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
