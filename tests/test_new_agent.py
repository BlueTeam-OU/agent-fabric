#!/usr/bin/env python3
"""Tests for tools/fabric/new_agent.py and tools/fabric/provisioning/; the
behaviour is tests/test_new_agent_cli.py's, run against the
new-agent.sh shim and the new-agent-worker.sh step-runner (ADR-040 §5 rule
5). What is here is what that suite does not reach: the worker's
argument quirks, each decision on its own (the claude version, the
subordinate ids, the host keys, the audit, the closing list), the
verification read-backs, and the orchestrator's usage, refusals, bounds
and pipelines. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stderr

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import new_agent as na  # noqa: E402
from provisioning import bounded, host_steps as hs, verify as vf, worker_args as wa  # noqa: E402

SHIM = os.path.join(HERE, "runtime", "provisioning", "new-agent.sh")


def clean_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_"))}
    env.update(extra)
    return env


def worker_args(*argv: str):
    try:
        return 0, wa.parse_args(list(argv))
    except wa.Exit as exc:
        return exc.code, exc.msg


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + str(detail).replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        def put(path: str, text: str, mode: int = 0o644) -> str:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(path, mode)
            return path

        print("the worker's arguments, as the bash shifted them")
        rc, got = worker_args("prepare", "a-login", "a-role", "--claude", "1.2.3", "--dry-run")
        check("prepare: every field", rc == 0 and (got.phase, got.login, got.role, got.dry, got.claude, got.human)
              == ("prepare", "a-login", "a-role", True, "1.2.3", False), got)
        rc, got = worker_args("finish", "l", "r", "--clone", "demo=git@h:o/d.git", "--clone=x=y=z", "--project", "p")
        check("finish: --clone <id>=<remote> splits at the first =, spaced or =; --project adds a project",
              rc == 0 and got.projects == ["demo", "x", "p"] and got.remote == {"demo": "git@h:o/d.git", "x": "y=z"}, got)
        rc, got = worker_args("prepare", "l", "r", "--clone", "x';touch /tmp/pwned;'=y")
        check("a value carrying shell characters stays a value (it is data now, never evaluated)",
              got.projects == ["x';touch /tmp/pwned;'"], got)
        check("no phase: the usage, exit 2", worker_args() == (2, wa.USAGE) and worker_args("bogus")[0] == 2)
        fp = "0123456789ab"
        rc, got = worker_args("finish", "l", "r", "--claude-account", f"acct-one={fp}")
        check("finish: --claude-account <slug>=<fp12>, spaced or =, reaches the verification",
              rc == 0 and got.account == f"acct-one={fp}" and not got.no_account
              and worker_args("finish", "l", "r", f"--claude-account=acct-one={fp}")[1].account == f"acct-one={fp}", got)
        rc, got = worker_args("finish", "l", "r", "--no-claude-account")
        check("…--no-claude-account too", rc == 0 and got.no_account and got.account == "", got)
        rc, got = worker_args("finish", "l", "r")
        check("…neither: no flag", rc == 0 and not got.no_account and got.account == "", got)
        check("…a value that is not <slug>=<12 hex> is refused",
              all(worker_args("finish", "l", "r", "--claude-account", v)[0] == 2
                  for v in ("acct-one", f"Acct={fp}", f"a';id;'={fp}", "a=0123456789AB", f"a={fp}0")))
        check("…both together are refused", worker_args("finish", "l", "r", "--no-claude-account", "--claude-account",
                                                        f"a={fp}")[0] == 2)
        check("…and a missing value is exit 1", worker_args("finish", "l", "r", "--claude-account")[0] == 1)
        check("prepare with only a login: the login is an unknown argument (bash's shift 2 || true, kept)",
              worker_args("prepare", "x") == (2, "new-agent-worker: unknown argument x"))
        check("no login: said", worker_args("prepare") == (2, "new-agent-worker: no login"))
        check("an unknown argument: said, exit 2", worker_args("finish", "l", "r", "--frob") == (2, "new-agent-worker: unknown argument --frob"))
        check("--claude without a value: exit 1, one line", worker_args("prepare", "l", "r", "--claude")[0] == 1)
        check("host-check takes a login and no role", worker_args("host-check", "l")[0] == 0)
        check("an empty role is no role", worker_args("prepare", "l", "") == (2, "new-agent-worker: no role"))
        step_runner = os.path.join(HERE, "runtime", "provisioning", "new-agent-worker.sh")
        r = subprocess.run(["bash", step_runner], capture_output=True, text=True, timeout=60, env=clean_env())
        check("the step-runner stops where its arguments fail, with their status and words",
              r.returncode == 2 and r.stderr == wa.USAGE + "\n" and r.stdout == "", r.stderr)
        scratch = f"{tmp}/worker-tmp"
        os.makedirs(scratch)
        r = subprocess.run(["bash", step_runner, "host-check", "nobody-here"], capture_output=True, text=True, timeout=60,
                           env=clean_env(TMPDIR=scratch))
        check("host-check answers and leaves nothing in its TMPDIR (an exec would skip the trap that removes its log)",
              r.returncode == 0 and r.stdout.endswith("account: absent\n") and os.listdir(scratch) == [],
              f"{r.stderr} {os.listdir(scratch)}")

        print("the claude version")
        root = f"{tmp}/fab"
        pin = f"{root}/runtime/claude-code/harness.json"

        def want(target: str):
            err = io.StringIO()
            try:
                with redirect_stderr(err):
                    return hs.claude_want(root, target), err.getvalue()
            except wa.Exit as exc:
                return exc.code, exc.msg
        put(pin, json.dumps({"claude": "2.1.285"}))
        check("the fleet's pin, when the caller names none", want("") == ("2.1.285", ""))
        check("the caller's target over the pin", want("latest")[0] == "latest" and want("2.1.282-beta.1")[0] == "2.1.282-beta.1")
        put(pin, json.dumps({"claude": "2.1.282'; touch /tmp/pwned; '"}))
        code, msg = want("")
        check("a pin that is not a version is refused before any installer line is built",
              code == 1 and "pins claude '2.1.282'; touch /tmp/pwned; '', which is not a version; nothing installed" in msg)
        put(pin, json.dumps({"claude": 2}))
        check("…a number is not a version either", want("")[0] == 1)
        os.remove(pin)
        got, err = want("")
        check("no readable pin: latest, and that is said", got == "latest" and "no readable pin" in err)
        code, msg = want("1.2.3';id;'")
        check("a target with shell characters is refused here too", code == 1 and "is not stable, latest or a version" in msg)

        print("the subordinate ids")
        etc = f"{tmp}/etc"
        os.makedirs(etc)
        check("empty files: SUB_UID_MIN and SUB_UID_COUNT's defaults", hs.subids("n", etc) == "alloc 524288-589823\n")
        put(f"{etc}/login.defs", "# defs\nSUB_UID_MIN  100000\nSUB_UID_COUNT 1000\n")
        put(f"{etc}/subuid", "a:100000:1000\nb:200000:500\n")
        put(f"{etc}/subgid", "a:100000:1000\nc:300000:65536\n")
        check("the next block above every range in either file, login.defs' size",
              hs.subids("n", etc) == "alloc 365536-366535\n", hs.subids("n", etc))
        check("an account with both ranges keeps them", hs.subids("a", etc) == "have 100000:1000\n")
        check("…but one with a uid range only gets both anew", hs.subids("b", etc).startswith("alloc "))

        print("the GitHub host keys")
        keys = put(f"{tmp}/keys", "github.com ssh-ed25519 AAA\ngithub.com ecdsa BBB\n\n")
        check("the published lines the account does not hold, whole lines only",
              hs.missing_keys(keys, "github.com ssh-ed25519 AAA\nother.com x y\n") == "github.com ecdsa BBB\n")
        check("…none when it holds them all", hs.missing_keys(keys, "github.com ecdsa BBB\ngithub.com ssh-ed25519 AAA\n") == "")
        check("…and all of them when it holds none", hs.missing_keys(keys, "").count("\n") == 2)
        check("a line that only contains a published key is not that key (whole lines, as grep -x)",
              hs.missing_keys(keys, "github.com ecdsa BBB # pinned\ngithub.com ssh-ed25519 AAA\n") == "github.com ecdsa BBB\n")

        print("the host audit")
        check("nothing missing: the count of the contract",
              hs.audit("fedora", "1", "dnf", "23", []) == "new-agent: 0. fedora: host tools present (23, the fabric's contract)\n")
        check("missing on a host that keeps packages: the hint with the packages",
              hs.audit("debian", "1", "sudo apt-get install", "23", ["gh", "jq"])
              == "new-agent: 0. debian: this host lacks gh jq: sudo apt-get install gh jq\n")
        check("missing on an AppVM: two lines, and the restart",
              hs.audit("fedora-qubes", "0", "dnf in the template", "23", ["gh"]).count("\n") == 2
              and "(then restart this AppVM)" in hs.audit("fedora-qubes", "", "x", "1", ["gh"]))

        print("the closing list")
        c = vf.closing("acct", "absent", "no", "demo")
        check("no GPG key and no template: both named, with the commands, and the first launch in the first project",
              "GPG secret key: the signing key's is NOT" in c and "sudo -u acct gpg --batch --import" in c and "fabric-accounts assign acct" in c and "bin/fabric-accounts" not in c
              and "moveto acct demo   then" in c and c.startswith("new-agent: done."))
        c = vf.closing("acct", "present", "template", "")
        check("…present ones said as present; no project, no clone name",
              "GPG secret key: the signing key's, present" in c and "a template token (plain-claude path ready)" in c and "moveto acct   then" in c)
        c = vf.closing("acct", "present", "applied", "", account="acct-one=0123456789ab")
        check("an account named and applied: its slug and fingerprint", c.startswith("new-agent: done.")
              and "- Claude account: acct-one (token 0123456789ab), applied (plain-claude path ready)" in c)
        c = vf.closing("acct", "present", "not-applied", "", account="acct-one=0123456789ab")
        check("…named and not applied: not done, and how to apply it", c.startswith("new-agent: NOT done")
              and "acct-one (token 0123456789ab) was assigned and is NOT applied" in c and "fabric-secrets sync" in c)
        c = vf.closing("acct", "present", "declined", "")
        check("--no-claude-account: said, with how to assign one later", c.startswith("new-agent: done.")
              and "not assigned (--no-claude-account: the broker path only); no template token" in c
              and "fabric-accounts assign acct" in c and "bin/fabric-accounts" not in c)

        print("the signing key's secret: the colon listing, judged as fabric-ctl keys judges it")
        listings = {
            "a signing primary key": "sec:u:255:22:K:1:::u:::scESC:::+::ed25519:::0:\n",
            "a stub primary (#)": "sec:u:255:22:K:1:::u:::scESC:::#::ed25519:::0:\n",
            "a stub primary, a signing subkey": "sec:u:255:22:K:1:::u:::cC:::#::ed25519:::0:\n"
                                                "ssb:u:255:22:S:1::::::s:::+::ed25519::\n",
            "an encryption-only subkey": "sec:u:255:22:K:1:::u:::cC:::#::ed25519:::0:\nssb:u:255:18:E:1::::::e:::+::cv25519::\n",
            "capability S only (the key's total, not the key)": "sec:u:255:22:K:1:::u:::cSC:::+::ed25519:::0:\n",
            "a line short of field 15": "sec:u:255:22:K:1:::u:::s\n",
            "a public key line": "pub:u:255:22:K:1:::u:::scESC::::::::0:\n",
            "nothing": "",
        }
        mine = {name: vf.signs_with_secret(text) for name, text in listings.items()}
        node = subprocess.run(
            ["node", "--input-type=module", "-e",
             "const { signingSecret } = await import(process.argv[1]);"
             "const cases = JSON.parse(process.argv[2]); const out = {};"
             "for (const [n, t] of Object.entries(cases))"
             "  out[n] = (await signingSecret(async (cmd) => cmd === 'git' ? 'K\\n' : t)).present;"
             "console.log(JSON.stringify(out));",
             os.path.join(HERE, "runtime", "control", "ops.mjs"), json.dumps(listings)],
            capture_output=True, text=True, timeout=60, env=clean_env())
        check("fabric-ctl keys (ops.mjs signingSecret) answered", node.returncode == 0, node.stderr)
        theirs = json.loads(node.stdout) if node.returncode == 0 else {}
        check("…and agrees with the read-back on every listing", mine == theirs, (mine, theirs))
        check("…which is present only with a signing secret held here",
              [n for n, v in mine.items() if v] == ["a signing primary key", "a stub primary, a signing subkey",
                                                     "a line short of field 15"], mine)

        print("the host names itself")
        put(f"{tmp}/hbin/hostname", "#!/usr/bin/env bash\n[[ $1 == -s ]] && echo far-host\n", 0o755)
        put(f"{tmp}/hbin/getent", "#!/usr/bin/env bash\n[[ $2 == here ]]\n", 0o755)
        saved_path = os.environ["PATH"]
        os.environ["PATH"] = f"{tmp}/hbin:{saved_path}"
        try:
            check("hostname -s first, then the account", hs.host_check("here") == "far-host\naccount: present\n"
                  and hs.host_check("gone") == "far-host\naccount: absent\n")
        finally:
            os.environ["PATH"] = saved_path

        print("the verification")
        # The read-backs are stubbed where they leave this process: the host's
        # own gh, git and gpg must not answer (its real gpg reaches the real
        # keyring even under a scratch home). Account.run itself is checked
        # once below, through a recording sudo, with a line that reads nothing.
        home = f"{tmp}/acct"
        os.makedirs(f"{home}/.config/agent-fabric")
        put(f"{root}/bin/fabric-ctl", "#!/usr/bin/env bash\necho header\necho pong\n", 0o755)
        put(f"{tmp}/vbin/sudo", f"#!/usr/bin/env bash\necho \"$*\" >> {tmp}/sudo.calls\n[[ $1 == -n ]] && shift; [[ $1 == -u ]] && shift 2; [[ $1 == -H ]] && shift\nexec \"$@\"\n", 0o755)

        SIGNING_SECRET = b"sec:u:255:22:AAAA1111BBBB2222:1700000000:::u:::scESC:::+::ed25519:::0:\n"
        SIGNING_STUB = b"sec:u:255:22:AAAA1111BBBB2222:1700000000:::u:::scESC:::#::ed25519:::0:\n"

        def verify_with(answers: dict, projects: list[str], **account) -> tuple[str, str, list[str]]:
            asked = []

            def fake_run(self, line, *, stderr=None):
                asked.append(line)
                return next((v for k, v in answers.items() if k in line), b"")
            saved_run, saved_err = vf.Account.run, sys.stderr
            vf.Account.run = fake_run
            buf = io.BytesIO()
            wrapper = sys.stderr = io.TextIOWrapper(buf, encoding="utf-8")
            try:
                text, failed = vf.verify(root, "acct", home, f"{tmp}/vbin/sudo", projects, **account)
                text += failed
                wrapper.flush()
                said = buf.getvalue().decode()
            finally:
                vf.Account.run, sys.stderr = saved_run, saved_err
                wrapper.detach()
            return text, said, asked
        text, said, asked = verify_with({"gpg --list-secret-keys": SIGNING_SECRET, "ls-remote": b"ssh to origin: ok\n",
                                         "gh auth status": b"Logged in to github.com\n"}, ["demo"])
        check("each read-back's lines prefixed; the ping's first line dropped",
              "   control plane: pong\n" in said and "header" not in said and "   demo ssh to origin: ok\n" in said
              and "   gh: Logged in to github.com\n" in said, said)
        check("…the signing key's secret asked for by the key git signs with: present",
              "GPG secret key: the signing key's, present" in text
              and any("user.signingkey" in x and 'gpg --list-secret-keys --with-colons -- "$k"' in x for x in asked), asked)
        check("…both launch paths read back, from the first project", sum("--provider anthropic --print" in a or
              "--provider openrouter --print" in a for a in asked) == 2 and all("cd ~/projects/demo &&" in a for a in asked
                                                                               if "--print" in a))
        text, _, _ = verify_with({"gpg --list-secret-keys": b""}, [])
        check("…absent (an account holding only its own store key, rust-ui-dev-01's case): the commands to "
              "import it", "GPG secret key: the signing key's is NOT" in text
              and "gpg --batch --import" in text)
        text, _, _ = verify_with({"gpg --list-secret-keys": b"garbage\n"}, [])
        check("…any other answer is absent", "GPG secret key: the signing key's is NOT" in text)
        text, _, _ = verify_with({"gpg --list-secret-keys": SIGNING_STUB}, [])
        check("…a stub (gpg lists it and exits 0; the secret is elsewhere) is absent",
              "GPG secret key: the signing key's is NOT" in text)
        # The line itself, run as the account would: a listing gpg printed
        # while exiting non-zero is no answer, as fabric-ctl keys reads it
        # (review carry from #91); exit 0 is the control.
        line = next(x for x in asked if "user.signingkey" in x and "--list-secret-keys" in x)
        fakes = f"{tmp}/gpgfake"
        os.makedirs(fakes, exist_ok=True)
        put(f"{fakes}/git", "#!/bin/sh\necho AAAA1111BBBB2222\n", 0o755)
        for code, want in ((0, True), (2, False)):
            put(f"{fakes}/gpg", f"#!/bin/sh\nprintf '%s' '{SIGNING_SECRET.decode()}'\nexit {code}\n", 0o755)
            out = subprocess.run(["bash", "-c", line], env={"PATH": f"{fakes}:/usr/bin:/bin", "HOME": home},
                                 capture_output=True, timeout=10).stdout.decode()
            check(f"…the read-back line with gpg exiting {code}: {'present' if want else 'absent, as fabric-ctl keys says'}",
                  vf.signs_with_secret(out) is want, out)
        put(f"{home}/.config/agent-fabric/secrets.env", "export CLAUDE_CODE_OAUTH_TOKEN='x'\n")
        text, _, _ = verify_with({}, [])
        check("…and a template token in the synced record is read through sudo", "a template token" in text)
        # With a person at the terminal new-agent imports the key next (11):
        # the closing says so, prints no hand-import lines, and is not "done".
        text, _, _ = verify_with({"gpg --list-secret-keys": b""}, [], signing_next=True)
        check("…absent with step 11 to follow: said, no lines to run by hand, not yet done",
              "new-agent imports it next, on this terminal (11)" in text and "gpg --batch --import" not in text
              and text.startswith("new-agent: 0-10 done; 11, the signing key, follows."), text)
        text, _, _ = verify_with({"gpg --list-secret-keys": SIGNING_SECRET}, [], signing_next=True)
        check("…present already: present and done, whatever follows", "the signing key's, present" in text
              and text.startswith("new-agent: done."), text)
        check("the two lines a person runs: the export piped into the account's import, and its ownertrust",
              vf.signing_key_lines("acct") == [
                  'gpg --export-secret-keys "$(git config --get user.signingkey)" | sudo -u acct gpg --batch --import',
                  "sudo -u acct bash -c \"echo '$(git config --get user.signingkey):6:' | gpg --import-ownertrust\""])

        check("…for an account on another host, both through fabric-host, never a local sudo",
              vf.signing_key_lines("acct", "far") == [
                  'gpg --export-secret-keys "$(git config --get user.signingkey)" | fabric-host far run --as acct -- '
                  'gpg --batch --import',
                  'echo "$(git config --get user.signingkey):6:" | fabric-host far run --as acct -- gpg --import-ownertrust'])
        text, _, _ = verify_with({"gpg --list-secret-keys": b""}, [], via="far")
        check("…and the closing prints those for an account reached via its host",
              "fabric-host far run --as acct -- gpg --batch --import" in text and "sudo -u acct" not in text and "bin/fabric-host" not in text, text)

        def verify_human_with(answers: dict) -> tuple[str, str, str, list[str]]:
            asked = []

            def fake_run(self, line, *, stderr=None):
                asked.append(line)
                return next((v for k, v in answers.items() if k in line), b"")
            saved_run, saved_err = vf.Account.run, sys.stderr
            vf.Account.run = fake_run
            buf = io.BytesIO()
            wrapper = sys.stderr = io.TextIOWrapper(buf, encoding="utf-8")
            try:
                text, failed = vf.verify_human("person", home, f"{tmp}/vbin/sudo")
                wrapper.flush()
                said = buf.getvalue().decode()
            finally:
                vf.Account.run, sys.stderr = saved_run, saved_err
                wrapper.detach()
            return text, failed, said, asked
        well = {"status >/dev/null": b"status=0\n", "for p in": b"probed\n", "grep -E": b"OK\n"}
        text, failed, said, asked = verify_human_with(well)
        check("a human's verification: status OK, nothing of a session, done; the person's list names moveto's grant "
              "and Fleet Deck", failed == "" and text.startswith("new-agent: done.") and "nothing of a session" in said
              and "moveto's sudo grant" in text and "Fleet Deck, run as person" in text and "no signing key" in text
              and not any("launch" in a or "gh auth" in a for a in asked), f"{text}{failed}{said}")
        check("…its probe asks for every piece bootstrap, a binding and a launch would leave",
              all(p in next(a for a in asked if "for p in" in a) for p in
                  ("~/.claude/agents", "agent-fabric-agentd.service", "~/projects/CLAUDE.md", "binding.json",
                   "~/.local/bin/claude", "~/.local/bin/ori")))
        for label, change, why in (
                ("status NOT OK", {"status >/dev/null": b"status=1\n"}, "fabric-secrets status as person is not OK (status=1)"),
                ("status with no answer", {"status >/dev/null": b""}, "is not OK (no answer)"),
                ("a session's pieces in its home", {"for p in": b"/h/.claude/agents\n/h/.config/systemd/user/x\nprobed\n"},
                 "it holds a session's pieces, which a human never has (ADR-044 rule 2): /h/.claude/agents /h/.config"),
                ("a probe that did not answer", {"for p in": b""}, "could not be read for a session's pieces")):
            text, failed, said, _ = verify_human_with({**well, **change})
            check(f"…{label}: a failed step, not done", failed.startswith("new-agent: step failed: ") and why in failed
                  and text.startswith("new-agent: NOT done"), f"{text}{failed}")
        tok_fp = hashlib.sha256(b"x").hexdigest()[:12]
        text, _, _ = verify_with({}, [], account=f"acct-one={tok_fp}")
        check("…an account named: its token's fingerprint compared, applied", "acct-one (token " + tok_fp + "), applied" in text
              and "step failed" not in text, text)
        text, _, _ = verify_with({}, [], account="acct-one=0123456789ab")
        check("…another token applied: the step fails, both named by fingerprint, the value never",
              f"not applied (expected 0123456789ab; token {tok_fp} in" in text and "'x'" not in text
              and "a re-run of new-agent reaches the store only once identities/keys/ is merged" in text, text)
        text, _, _ = verify_with({}, [], no_account=True)
        check("…--no-claude-account on an account that holds one: not assigned by this run, and the token it holds said",
              f"not assigned by this run (--no-claude-account); a template token is already applied (token {tok_fp})" in text
              and "no template token" not in text and "step failed" not in text, text)
        unread = "could not be read as sync writes it"
        for body, what, said in (("", "no export line", "; no token in"),
                                 ("export CLAUDE_CODE_OAUTH_TOKEN='x'\nexport CLAUDE_CODE_OAUTH_TOKEN='x'\n", "two export lines",
                                  unread),
                                 ("export CLAUDE_CODE_OAUTH_TOKEN='x\n", "an unclosed quote", unread),
                                 ("export CLAUDE_CODE_OAUTH_TOKEN=''\n", "an empty value", unread)):
            put(f"{home}/.config/agent-fabric/secrets.env", body)
            text, _, _ = verify_with({}, [], account=f"acct-one={tok_fp}")
            check(f"…{what}: the step fails, said as {'absent' if 'no token' in said else 'unreadable, never absent'}",
                  "expected " + tok_fp in text and said in text and "step failed" in text, text)
        os.remove(f"{home}/.config/agent-fabric/secrets.env")
        text, _, _ = verify_with({}, [], account=f"acct-one={tok_fp}")
        check("…no secrets.env at all: unreadable, the step fails", unread in text and "step failed" in text, text)
        text, _, _ = verify_with({}, [], no_account=True)
        check("…--no-claude-account: nothing compared, the closing says it", "not assigned (--no-claude-account" in text
              and "step failed" not in text, text)
        put(f"{home}/.config/agent-fabric/secrets.env", "export CLAUDE_CODE_OAUTH_TOKEN='x'\n")
        saved_path = os.environ["PATH"]
        os.environ["PATH"] = f"{tmp}/vbin:{saved_path}"
        try:
            out = vf.Account("acct", home, f"{tmp}/vbin/sudo").run("echo as-the-account")
        finally:
            os.environ["PATH"] = saved_path
        calls = open(f"{tmp}/sudo.calls").read().splitlines()
        check("a read-back is a login shell as the account through sudo -u, never as root",
              out == b"as-the-account\n" and any(c.startswith("-n -u acct -H env -i HOME=") and " bash -lc " in c
                                                  for c in calls), calls[-1:])
        saved_err = sys.stderr
        sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        try:
            missing = bounded.quiet_run([f"{tmp}/no-fabric-ctl"], stderr=subprocess.STDOUT)
        finally:
            sys.stderr = saved_err
        check("a command that cannot start, its stderr merged: bash's error line is its output",
              missing == f"{tmp}/no-fabric-ctl: No such file or directory\n".encode())

        print("the orchestrator's command line")
        def shim(*args, **env):
            return subprocess.run(["bash", SHIM, *args], capture_output=True, text=True, timeout=60,
                                  env=clean_env(AGENT_FABRIC_PYTHON=sys.executable, **env))
        r = shim("--help")
        check("--help: the header, on stdout, exit 0", r.returncode == 0 and r.stdout == na.HELP and
              r.stdout.startswith("runtime/provisioning/new-agent.sh — give a role its own account"))
        r = shim()
        check("no login or role: the usage line, exit 2", r.returncode == 2 and r.stderr == na.USAGE)
        r = shim("l", "r", "x")
        check("a third positional: exit 2, named", r.returncode == 2 and r.stderr == "new-agent: unexpected argument x\n")
        r = shim("l", "r", "--host")
        check("a flag without its value: exit 1, one line, never a traceback",
              r.returncode == 1 and r.stderr == "new-agent: --host needs a value\n")
        r = shim("l", "r")
        check("no Claude account named: exit 2, both flags named",
              r.returncode == 2 and r.stderr == na.NO_ACCOUNT_CHOICE + "\n")
        r = shim("l", "r", "--no-claude-account", "--claude-account", "a")
        check("…both: exit 2", r.returncode == 2 and r.stderr == na.NO_ACCOUNT_CHOICE + "\n")
        check("…and the choice names fabric-accounts bare", "(fabric-accounts templates)" in na.NO_ACCOUNT_CHOICE
              and "bin/" not in na.NO_ACCOUNT_CHOICE)
        r = shim("l", "r", "--claude-account")
        check("…--claude-account without its value: exit 1, one line",
              r.returncode == 1 and r.stderr == "new-agent: --claude-account needs a value\n")
        r = shim("l", "r", "--claude", "9.9")
        check("--claude 9.9 is not a version", r.returncode == 2 and "--claude takes stable, latest or a version" in r.stderr)
        check("values spaced or with =, flags anywhere",
              na.parse(["--project=a", "l", "--host", "h", "r", "--project", "b", "--claude=latest", "--claude-account=a-b"])
              == {"dry": False, "login": "l", "role": "r", "projects": ["a", "b"], "claude": "latest", "host": "h",
                  "claude-account": "a-b", "no-claude-account": False, "human": False, "no-signing-key": False}
              and na.parse(["l", "--claude-account", "a", "r"])["claude-account"] == "a")
        check("--no-signing-key is a flag of an agent's run",
              na.parse(["l", "r", "--no-claude-account", "--no-signing-key"])["no-signing-key"] is True)
        # A human login (ADR-044): its login and --host, nothing of a session.
        check("--human: a login and no role", na.parse(["--human", "p", "--host=h"])
              == {"dry": False, "login": "p", "role": "", "projects": [], "claude": "", "host": "h", "claude-account": None,
                  "no-claude-account": False, "human": True, "no-signing-key": False})
        for argv, said in ((["p", "r", "--human"], "a human login has no role"),
                           (["p", "--human", "--claude-account", "a"], "--human takes --host and --dry-run only"),
                           (["p", "--human", "--no-claude-account"], "--human takes --host and --dry-run only"),
                           (["p", "--human", "--claude", "latest"], "--human takes --host and --dry-run only"),
                           (["p", "--human", "--project", "demo"], "--human takes --host and --dry-run only"),
                           (["--human"], "usage:")):
            try:
                na.parse(argv)
                code, msg = 0, ""
            except na.Exit as exc:
                code, msg = exc.code, exc.msg or ""
            check(f"--human refuses {' '.join(argv)}: exit 2", code == 2 and said in msg, f"{code} {msg}")
        rc, got = worker_args("prepare", "p", "--human", "--dry-run")
        check("the worker: prepare <login> --human sets human and no role",
              rc == 0 and got.human and got.role == "" and got.dry, got)
        rc, got = worker_args("finish", "l", "r", "--no-claude-account", "--signing-key-next")
        check("…an agent's finish carries --signing-key-next to the verification",
              rc == 0 and not got.human and got.no_account and got.signing_next, got)
        rc, got = worker_args("finish", "l", "r", "--no-claude-account", "--via-host", "far")
        check("…and --via-host, the account's host id, to it too", rc == 0 and got.no_account and got.via == "far", got)
        rc, out = worker_args("finish", "l", "r", "--via-host", "far;id")
        check("…a host id that is not one is refused: exit 2", rc == 2 and "--via-host takes" in out, out)
        for extra in (["--no-claude-account"], ["--claude-account", "a=0123456789ab"], ["--clone", "x=y"],
                      ["--claude", "latest"], ["--signing-key-next"], ["--via-host", "far"]):
            rc, out = worker_args("finish", "p", "--human", *extra)
            check(f"…and refuses --human with {extra[0]}: exit 2", rc == 2 and "--human takes no" in out, out)

        r = subprocess.run(["bash", SHIM, "--help"], capture_output=True, text=True, timeout=30,
                           env=clean_env(AGENT_FABRIC_PYTHON=f"{tmp}/no-python"))
        check("the shim with no pinned interpreter: exit 127, one line",
              r.returncode == 127 and r.stderr.count("\n") == 1 and "python_pin.py install" in r.stderr)

        print("the orchestrator, against fakes")
        # A fake host executor and store tools: each answers from files the
        # case writes and records what it was asked.
        fk = f"{tmp}/fakes"
        hx = put(f"{fk}/hostexec", f"""#!/usr/bin/env bash
echo "$*" >> {fk}/hx.calls
[[ $1 == --resolve ]] && exit "$(cat {fk}/resolve.rc 2>/dev/null || echo 0)"
case "$*" in
  *host-check*) [[ -e {fk}/check.fails ]] && {{ echo "unreachable" >&2; exit 255; }}; cat {fk}/reports 2>/dev/null || echo "$1"; echo "account: absent" ;;
  *take-bundle*) cat > {fk}/taken; grep -q BEGIN {fk}/taken ;;
  *sync*) exit "$(cat {fk}/sync.rc 2>/dev/null || echo 0)" ;;
esac
exit 0
""", 0o755)
        store = put(f"{fk}/secret_store.py", f"""import sys
a = sys.argv[1:]
if a[:1] == ["child-bundle"]:
    print("-----BEGIN AGENT-FABRIC STORE BUNDLE-----")
    print("bundle on stderr", file=sys.stderr)
    import os
    sys.exit(1 if os.path.exists("{fk}/bundle.fails") else 0)
sys.exit(0)
""")
        # The parent's store: templates answer from $fk/templates, assign
        # from $fk/assign (its rows, then its exit); provision writes.
        secrets = put(f"{fk}/fabric-secrets", f"""#!/usr/bin/env bash
echo "$*" >> {fk}/secrets.calls
case "$1 $2" in
  "store templates") cat {fk}/templates ;;
  "store assign") head -1 {fk}/assign; exit "$(sed -n 2p {fk}/assign)" ;;
  "provision share") st=written; [[ -e {fk}/share.skipped ]] && st=skipped
                     echo '[{{"login": "'"$3"'", "name": "'"${{@: -1}}"'", "status": "'"$st"'"}}]' ;;
  *) echo '[{{"status": "written"}}]' ;;
esac
""", 0o755)
        put(f"{fk}/templates", '[{"account": "acct-one", "token_sha256_12": "0123456789ab"}]\n')
        put(f"{fk}/assign", '[{"login": "new", "status": "written", "token_sha256_12": "0123456789ab"}]\n0\n')
        enroll = put(f"{fk}/store-enroll.sh", "#!/usr/bin/env bash\nexit 0\n", 0o755)
        reg = put(f"{fk}/root/projects/registry.json", json.dumps({"projects": {"demo": {"remotes": ["https://h/o/d.git", "git@h:o/d.git"]}}}))
        hosts = put(f"{fk}/hosts.json", json.dumps({"hosts": {"here": {"ssh": None}, "far": {"ssh": "op@far"}},
                                                    "placement": {"placed": "far"}}))
        saved = (na.HX, na.STORE, na.SECRETS, na.STORE_ENROLL, na.ROOT, os.environ.get("AGENT_FABRIC_OPERATOR"))
        na.HX, na.STORE, na.SECRETS, na.STORE_ENROLL = hx, store, secrets, enroll
        # The instance data (registry, roles) is the operator root's.
        os.environ["AGENT_FABRIC_OPERATOR"] = f"{fk}/root"
        os.makedirs(f"{fk}/root/identities/roles/r")
        put(f"{fk}/root/identities/roles/r/charter.md", "x")
        na.ROOT = f"{fk}/root"

        signed: list[tuple[str, str]] = []
        vias: list[str] = []
        saved_terminal, saved_signing = na.on_terminal, na.signing_key

        def orchestrate(*argv, hosts_path=hosts, terminal=False, signing_rc=0):
            if not any(a.startswith("--claude-account") or a in ("--no-claude-account", "--human") for a in argv):
                argv = (*argv, "--claude-account", "acct-one")
            # Never the runner's own terminal: a case says whether there is one.
            na.on_terminal = lambda: terminal
            signed.clear()
            vias.clear()
            na.signing_key = lambda login, host, via="": signed.append((login, host)) or vias.append(via) or signing_rc
            for f in ("hx.calls", "taken", "secrets.calls"):
                if os.path.exists(f"{fk}/{f}"):
                    os.remove(f"{fk}/{f}")
            saved_env = os.environ.get("AGENT_FABRIC_HOSTS_REGISTRY")
            os.environ["AGENT_FABRIC_HOSTS_REGISTRY"] = hosts_path
            err = io.StringIO()
            try:
                with redirect_stderr(err):
                    rc = na.new_agent(list(argv))
                    msg = None
            except na.Exit as exc:
                rc, msg = exc.code, exc.msg
            finally:
                if saved_env is None:
                    os.environ.pop("AGENT_FABRIC_HOSTS_REGISTRY", None)
                else:
                    os.environ["AGENT_FABRIC_HOSTS_REGISTRY"] = saved_env
            calls = open(f"{fk}/hx.calls").read() if os.path.exists(f"{fk}/hx.calls") else ""
            return rc, msg, err.getvalue(), calls
        try:
            check("the registry's SSH remote, though it is not the first", na.project_remote("demo") == "git@h:o/d.git")
            rc, msg, err, calls = orchestrate("placed", "r", "--dry-run")
            check("a placed account goes to its host, not this one", calls.startswith("--resolve far\n"), calls)
            rc, msg, err, calls = orchestrate("new", "r", "--dry-run")
            check("an unplaced one to this host", calls.startswith("--resolve here\n"), calls)
            nohost = put(f"{fk}/nohost.json", json.dumps({"hosts": {"far": {"ssh": "op@far"}}}))
            rc, msg, err, calls = orchestrate("new", "r", "--dry-run", hosts_path=nohost)
            check("no --host, no placement, no host of this one's: refused, nothing asked",
                  rc == 1 and "no host: name one with --host" in msg and calls == "")
            put(f"{fk}/resolve.rc", "1")
            rc, msg, err, calls = orchestrate("new", "r", "--dry-run")
            check("a host hostexec cannot resolve: exit 1, hostexec's word, nothing after",
                  rc == 1 and msg is None and calls == "--resolve here\n", calls)
            os.remove(f"{fk}/resolve.rc")
            put(f"{fk}/check.fails", "")
            rc, msg, err, calls = orchestrate("new", "r", "--dry-run")
            check("a host whose worker does not answer: its last words, then refused",
                  rc == 1 and "unreachable" in err and "host here: unreachable, or its worker did not run" in msg)
            os.remove(f"{fk}/check.fails")
            put(f"{fk}/reports", "elsewhere\n")
            rc, msg, err, calls = orchestrate("new", "r", "--dry-run")
            check("a host that names itself otherwise is refused before any step",
                  rc == 1 and "answers as 'elsewhere'" in msg and "prepare" not in calls
                  and re.search(r"\(fabric-host \S+ check\)", msg) and "bin/fabric-host" not in msg)
            os.remove(f"{fk}/reports")
            saved_pwd = na.pwd.getpwuid
            na.pwd.getpwuid = lambda uid: type("P", (), {"pw_name": "root"})()
            try:
                rc, msg, err, calls = orchestrate("new", "r", "--dry-run")
            finally:
                na.pwd.getpwuid = saved_pwd
            check("root is refused: the store is filled from the coordinator's own", rc == 1 and "not root" in msg and calls == "")
            rc, msg, err, calls = orchestrate("new", "r", "--project", "demo")
            check("the whole run on fakes: the bundle handed over, prepare and finish with the clone",
                  rc == 0 and open(f"{fk}/taken").read().startswith("-----BEGIN") and "finish new r --clone demo=git@h:o/d.git" in calls,
                  f"{msg}\n{err}")
            put(f"{fk}/bundle.fails", "")
            rc, msg, err, calls = orchestrate("new", "r")
            check("a bundle that failed is a failed hand-over, whatever the account took",
                  rc == 1 and "its store did not reach new as a bundle" in msg and "finish" not in calls)
            os.remove(f"{fk}/bundle.fails")
            put(f"{fk}/sync.rc", "2")
            rc, msg, err, calls = orchestrate("new", "r")
            check("a sync that exits 2 (applied, names missing) goes on; finish says what is missing", rc == 0, f"{msg}")
            put(f"{fk}/sync.rc", "3")
            rc, msg, err, calls = orchestrate("new", "r")
            check("…one that exits 3 stops, named with its code", rc == 1 and "fabric-secrets sync as new (exit 3)" in msg)
            os.remove(f"{fk}/sync.rc")

            def secrets_calls() -> str:
                return open(f"{fk}/secrets.calls").read() if os.path.exists(f"{fk}/secrets.calls") else ""
            rc, msg, err, calls = orchestrate("new", "r")
            sc = secrets_calls().splitlines()
            check("an account named: assigned after the keys, and finish told its slug and fingerprint",
                  rc == 0 and sc[0] == "store templates --json" and sc[-1] == "store assign acct-one new --json"
                  and sc[-2] == "provision issue-key openai new"
                  and "finish new r --claude-account acct-one=0123456789ab" in calls
                  and "Claude account: acct-one, written (token 0123456789ab)" in err, f"{sc}\n{calls}\n{err}")
            rc, msg, err, calls = orchestrate("new", "r", "--claude-account", "other")
            check("an unknown template: refused before the host is asked", rc == 1 and calls == ""
                  and "'other' is not a template in this store (fabric-accounts templates); nothing made" in msg
                  and "bin/fabric-accounts" not in msg, f"{msg}\n{calls}")
            for body, said in (('[{"account": "acct-one", "token_sha256_12": null}]', "holds no CLAUDE_CODE_OAUTH_TOKEN"),
                               ("not json", "templates could not be read"), ('{"account": "acct-one"}', "could not be read"),
                               ('[{"account": "acct-one", "token_sha256_12": "zz"}]', "a fingerprint that is not one")):
                put(f"{fk}/templates", body)
                rc, msg, err, calls = orchestrate("new", "r", "--dry-run")
                check(f"…templates answering {body[:24]!r}: refused before the host", rc == 1 and calls == ""
                      and said in msg, f"{msg}\n{calls}")
            put(f"{fk}/templates", '[{"account": "acct-one", "token_sha256_12": "0123456789ab"}]\n')
            rc, msg, err, calls = orchestrate("new", "r", "--dry-run")
            check("the dry run names the assignment and writes none", rc == 0
                  and "would: fabric-secrets store assign acct-one new (token 0123456789ab)" in err
                  and "store assign" not in secrets_calls(), err)
            put(f"{fk}/assign", '[{"login": "new", "from": "none", "status": "failed", "reason": "no committed key"}]\n1\n')
            rc, msg, err, calls = orchestrate("new", "r")
            check("a failed assignment stops before the bundle, with the store's reason",
                  rc == 1 and "store assign acct-one new: no committed key" in msg and not os.path.exists(f"{fk}/taken")
                  and "finish" not in calls, msg)
            for rows, code in (('[{"login": "new", "status": "written", "token_sha256_12": "0123456789ab"}]', 1),
                               ("[]", 0), ("garbage", 0),
                               ('[{"login": "new", "status": "written"}, {"login": "x", "status": "written"}]', 0),
                               ('[{"login": "x", "status": "written", "token_sha256_12": "0123456789ab"}]', 0)):
                put(f"{fk}/assign", f"{rows}\n{code}\n")
                rc, msg, err, calls = orchestrate("new", "r")
                check(f"…so does an assignment answering {rows[:30]!r} with exit {code}",
                      rc == 1 and "step failed: fabric-secrets store assign" in msg and "finish" not in calls, msg)
            put(f"{fk}/assign", '[{"login": "new", "status": "unchanged", "token_sha256_12": "ffffffffffff"}]\n0\n')
            rc, msg, err, calls = orchestrate("new", "r")
            check("…and one that wrote another token than the one checked (the template changed)",
                  rc == 1 and "wrote token ffffffffffff, not the 0123456789ab checked" in msg and "finish" not in calls, msg)
            put(f"{fk}/assign", '[{"login": "new", "status": "unchanged", "token_sha256_12": "0123456789ab"}]\n0\n')
            rc, msg, err, calls = orchestrate("new", "r")
            check("an unchanged assignment (a re-run) goes on", rc == 0 and "acct-one, unchanged" in err, msg)
            rc, msg, err, calls = orchestrate("new", "r", "--no-claude-account")
            check("--no-claude-account: no template read, nothing assigned, finish told so",
                  rc == 0 and "store" not in secrets_calls() and "finish new r --no-claude-account" in calls, calls)

            # Step 11, the signing key: only with a person at the terminal, an
            # agent, and no --no-signing-key; finish is told it follows.
            rc, msg, err, calls = orchestrate("new", "r", "--no-claude-account")
            check("no terminal: no step 11, finish prints the lines as before",
                  rc == 0 and signed == [] and "--signing-key-next" not in calls, calls)
            rc, msg, err, calls = orchestrate("new", "r", "--no-claude-account", terminal=True)
            check("a terminal: finish told the key follows, then step 11 for the account on its host",
                  rc == 0 and signed == [("new", "here")] and "finish new r --no-claude-account --signing-key-next" in calls,
                  f"{signed}\n{calls}")
            check("…an account on this host: no --via-host, step 11's lines local", "--via-host" not in calls and vias == [""],
                  calls)
            rc, msg, err, calls = orchestrate("placed", "r", "--no-claude-account", terminal=True)
            check("…one on another host: finish and step 11 told its host, for the hand-import lines",
                  rc == 0 and "finish placed r --no-claude-account --signing-key-next --via-host far" in calls
                  and signed == [("placed", "far")] and vias == ["far"], f"{calls}\n{vias}")
            rc, msg, err, calls = orchestrate("new", "r", "--no-claude-account", "--no-signing-key", terminal=True)
            check("…--no-signing-key: none, the lines printed as without a terminal",
                  rc == 0 and signed == [] and "--signing-key-next" not in calls, calls)
            rc, msg, err, calls = orchestrate("new", "r", "--no-claude-account", "--dry-run", terminal=True)
            check("…a dry run names it and runs none",
                  rc == 0 and signed == [] and "would: 11. export this login's signing key" in err, err)
            rc, msg, err, calls = orchestrate("new", "r", "--no-claude-account", terminal=True, signing_rc=1)
            check("…a step 11 that fails: new-agent exits 1, and 0-10 stayed done",
                  rc == 1 and msg is None and "finish new r" in calls and signed == [("new", "here")], f"{rc} {msg}")

            print("the orchestrator, a human login (ADR-044)")
            humans = put(f"{fk}/humans.json", json.dumps({
                "hosts": {"here": {"ssh": None}, "far": {"ssh": "op@far"}},
                "placement": {"person": "far", "agentish": "here", "oddity": "here"},
                "kinds": {"person": "human", "oddity": "robot"}}))
            rc, msg, err, calls = orchestrate("person", "--human", hosts_path=humans, terminal=True)
            sc = secrets_calls().splitlines()
            check("a human: on its placement's host, prepare and finish --human, nothing of a session",
                  rc == 0 and calls.startswith("--resolve far\n") and "prepare person --human\n" in calls
                  and "finish person --human\n" in calls and "a human (ADR-044)" in err, f"{msg}\n{calls}\n{err}")
            check("…its store: identity and the relay credential only — no template, no other name, no issued key",
                  sc == ["provision identity person --host far", "provision share person --name CLAUDE_BRIDGE_AUTH_TOKEN"],
                  sc)
            check("…handed over and synced as itself, its inbox caught up on the fleet's channel",
                  open(f"{fk}/taken").read().startswith("-----BEGIN")
                  and "relay_catchup.py agent-fabric" in calls, calls)
            check("…and never the signing key, terminal or not (ADR-044 rule 3)", signed == [] and "signing" not in calls,
                  calls)
            rc, msg, err, calls = orchestrate("person", "--human", "--dry-run", hosts_path=humans, terminal=True)
            check("…its dry run plans the one shared name and no step 11",
                  rc == 0 and "share CLAUDE_BRIDGE_AUTH_TOKEN only" in err and "would: 11" not in err
                  and secrets_calls() == "", err)
            put(f"{fk}/share.skipped", "")
            rc, msg, err, calls = orchestrate("person", "--human", hosts_path=humans)
            check("…a relay credential the parent cannot give (skipped): stopped before the hand-over, named",
                  rc == 1 and "CLAUDE_BRIDGE_AUTH_TOKEN did not reach person's store" in msg
                  and not os.path.exists(f"{fk}/taken") and "finish" not in calls, f"{msg}\n{calls}")
            os.remove(f"{fk}/share.skipped")
            for login, why in (("newcomer", "is not placed as a human"), ("agentish", "is not placed as a human"),
                               ("oddity", "the kind of oddity cannot be read")):
                rc, msg, err, calls = orchestrate(login, "--human", hosts_path=humans)
                check(f"--human for {login}: refused before the host is asked", rc == 1 and why in (msg or "")
                      and "--resolve" not in calls, f"{msg}\n{calls}")
            rc, msg, err, calls = orchestrate("person", "r", "--no-claude-account", hosts_path=humans)
            check("an agent's run on a human login: refused, nothing asked (ADR-044 rule 5)",
                  rc == 1 and "person is a human login" in msg and "--resolve" not in calls, f"{msg}\n{calls}")
            rc, msg, err, calls = orchestrate("agentish", "r", "--no-claude-account", hosts_path=humans)
            check("…while a placed login kinds does not name is an agent (the control)", rc == 0, f"{msg}")
            rc, msg, err, calls = orchestrate("person", "--human", hosts_path=put(f"{fk}/badkinds.json", json.dumps({
                "hosts": {"far": {"ssh": "op@far"}}, "placement": {"person": "far"}, "kinds": ["person"]})))
            check("…and a kinds that is not a table is no answer: refused", rc == 1 and "cannot be read" in msg, msg)
        finally:
            na.HX, na.STORE, na.SECRETS, na.STORE_ENROLL, na.ROOT = saved[:5]
            if saved[5] is None:
                os.environ.pop("AGENT_FABRIC_OPERATOR", None)
            else:
                os.environ["AGENT_FABRIC_OPERATOR"] = saved[5]
            na.on_terminal, na.signing_key = saved_terminal, saved_signing

        print("step 11, the signing key, between two scratch keyrings")
        # The coordinator's keyring (gA) and the account's (gB), each its own
        # GNUPGHOME under the scratch dir — never the runner's ~/.gnupg, whose
        # agent a test would share (the GNUPGHOME default-agent trap). The
        # account is reached through a fake host executor that runs the
        # command after `--` with gB; a fault file fails one of its steps.
        gA, gB, gEmpty = f"{tmp}/gA", f"{tmp}/gB", f"{tmp}/gE"
        for d in (gA, gB, gEmpty):
            os.makedirs(d, mode=0o700)
        hxg = put(f"{fk}/hx-gpg", f"""#!/usr/bin/env bash
echo "$*" >> {fk}/hxg.calls
while [[ $1 != -- ]]; do shift; done; shift
if [[ -e {fk}/import.fails && "$*" == *--import ]]; then cat >/dev/null; echo "gpg: import failed (injected)" >&2; exit 2; fi
home={gB}; [[ -e {fk}/sign.fails && "$*" == *detach-sign* ]] && home={gEmpty}
exec env GNUPGHOME="$home" "$@"
""", 0o755)
        gitconfig = f"{tmp}/coordinator.gitconfig"
        gpg_env = {"GNUPGHOME": gA, "GIT_CONFIG_GLOBAL": gitconfig, "GIT_CONFIG_NOSYSTEM": "1", "GPG_TTY": ""}
        saved_env = {k: os.environ.get(k) for k in gpg_env}
        saved_hx, saved_root = na.HX, na.ROOT

        def gpg(home: str, *argv: str, data: bytes | None = None) -> subprocess.CompletedProcess:
            return subprocess.run(["gpg", "--homedir", home, "--batch", *argv], input=data, capture_output=True, timeout=120)

        def step11() -> tuple[int, str, str]:
            if os.path.exists(f"{fk}/hxg.calls"):
                os.remove(f"{fk}/hxg.calls")
            err = io.StringIO()
            with redirect_stderr(err):
                rc = na.signing_key("new", "here")
            calls = open(f"{fk}/hxg.calls").read() if os.path.exists(f"{fk}/hxg.calls") else ""
            return rc, err.getvalue(), calls

        def held(home: str, fpr: str) -> bool:
            r = gpg(home, "--list-secret-keys", "--with-colons", "--", fpr)
            return r.returncode == 0 and vf.signs_with_secret(r.stdout.decode())
        try:
            os.environ.update(gpg_env)
            na.HX, na.ROOT = hxg, f"{fk}/root"
            made = gpg(gA, "--pinentry-mode", "loopback", "--passphrase", "", "--quick-gen-key",
                       "Fixture Signer <fixture@example.invalid>", "ed25519", "sign", "never")
            listing = gpg(gA, "--list-secret-keys", "--with-colons").stdout.decode()
            fpr = na.primary_fingerprint(listing)
            check("fixture: a signing key in the coordinator's scratch keyring", made.returncode == 0 and len(fpr) == 40,
                  made.stderr.decode())
            put(gitconfig, f"[user]\n\tsigningkey = {fpr}\n")

            rc, err, calls = step11()
            trust = gpg(gB, "--export-ownertrust").stdout.decode()
            check("imported and proved: the account's keyring holds the secret, trusted, and a signature was made as it",
                  rc == 0 and held(gB, fpr) and f"{fpr}:6:" in trust
                  and "in new's keyring, trusted, and a test signature made as it — done" in err
                  and "--tty --as new -- " in calls and "--detach-sign" in calls, f"rc={rc}\n{err}\n{calls}\n{trust}")
            # The signature's stdout is the person's terminal, never a pipe:
            # over ssh -t pinentry's prompt comes back there (#118 review, F1).
            seen: list = []
            real_bounded = na.run_bounded

            def recording(cmd, **kw):
                seen.append((cmd, kw.get("stdout", "unset")))
                return real_bounded(cmd, **kw)
            na.run_bounded = recording
            try:
                rc, err, calls = step11()
            finally:
                na.run_bounded = real_bounded
            imports = [ln for ln in calls.splitlines() if ln.endswith("gpg --batch --import")]
            check("a re-run: already there, nothing exported or imported again, its ownertrust and signature again",
                  rc == 0 and "already in new's keyring" in err and imports == [] and "--import-ownertrust" in calls
                  and "--detach-sign" in calls and "— done" in err, f"{err}\n{calls}")
            check("…the test signature runs with its stdout on the terminal, never captured",
                  [out for cmd, out in seen if "--tty" in cmd] == [None], seen)
            # An ownertrust an earlier run did not set is repaired by the next
            # one, never reported done from the secret alone (#118 review, F2).
            gpg(gB, "--import-ownertrust", data=f"{fpr}:2:\n".encode())
            lost = f"{fpr}:6:" not in gpg(gB, "--export-ownertrust").stdout.decode()
            rc, err, calls = step11()
            check("a re-run after an ownertrust was lost: set again, proved, done",
                  lost and rc == 0 and f"{fpr}:6:" in gpg(gB, "--export-ownertrust").stdout.decode(), f"{err}\n{calls}")

            subprocess.run(["gpgconf", "--homedir", gB, "--kill", "all"], capture_output=True, timeout=60)
            subprocess.run(["gpgconf", "--homedir", gB, "--remove-socketdir"], capture_output=True, timeout=60)
            shutil.rmtree(gB)
            os.makedirs(gB, mode=0o700)
            put(f"{fk}/import.fails", "")
            rc, err, calls = step11()
            check("a failed import: exit 1, gpg's last line, and the two lines a person runs",
                  rc == 1 and "11. the signing key: FAILED — the import as new: gpg: import failed (injected)" in err
                  and "sudo -u new gpg --batch --import" in err and "gpg --import-ownertrust" in err
                  and not held(gB, fpr) and "--import-ownertrust" not in calls, f"rc={rc}\n{err}\n{calls}")
            err = io.StringIO()
            with redirect_stderr(err):
                rc = na.signing_key("new", "here", via="far")
            check("…the lines for an account on another host go through fabric-host",
                  rc == 1 and "fabric-host far run --as new -- gpg --batch --import" in err.getvalue() and "bin/fabric-host" not in err.getvalue()
                  and "sudo -u new" not in err.getvalue(), err.getvalue())
            os.remove(f"{fk}/import.fails")
            put(f"{fk}/sign.fails", "")
            rc, err, calls = step11()
            check("a test signature that fails is a failed step, with gpg's line, though the import went in",
                  rc == 1 and "FAILED — the test signature as new: " in err and "gpg:" in err.split("test signature as new: ")[1]
                  and held(gB, fpr), f"rc={rc}\n{err}")
            os.remove(f"{fk}/sign.fails")
            put(gitconfig, "")
            rc, err, calls = step11()
            check("no user.signingkey here: exit 1, said, nothing asked of the account",
                  rc == 1 and "names no user.signingkey" in err and calls == "", f"{err}\n{calls}")
            put(gitconfig, "[user]\n\tsigningkey = 0000000000000000000000000000000000000000\n")
            rc, err, calls = step11()
            check("…a signing key this keyring does not hold: exit 1, said, nothing asked",
                  rc == 1 and "holds no signing secret for 0000" in err and calls == "", f"{err}\n{calls}")
        finally:
            na.HX, na.ROOT = saved_hx, saved_root
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            # Each scratch keyring's agent, then its socket directory under
            # /run/user, which gpg made for it: nothing left that was not found.
            for d in (gA, gB, gEmpty):
                subprocess.run(["gpgconf", "--homedir", d, "--kill", "all"], capture_output=True, timeout=60)
                subprocess.run(["gpgconf", "--homedir", d, "--remove-socketdir"], capture_output=True, timeout=60)

        print("the orchestrator's steps")
        log = put(f"{tmp}/log", "")
        s = na.Steps(log)
        r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import new_agent as na; "
                            "print(na.Steps.indented(['bash', '-c', 'echo bundle; echo first-err >&2; exit 3'], "
                            "['bash', '-c', 'cat; echo last-err >&2; exit 5']))" % os.path.join(HERE, "tools", "fabric")],
                           capture_output=True, text=True, timeout=60)
        check("a pipeline's statuses, each its own, as PIPESTATUS gave them", r.stdout.strip() == "[3, 5]")
        check("…the last command's stderr merged and every line indented; the first's stderr left as it was",
              r.stderr.splitlines() == ["first-err", "   bundle", "   last-err"]
              or sorted(r.stderr.splitlines()) == sorted(["first-err", "   bundle", "   last-err"]), r.stderr)
        saved_timeout = na.STEP_TIMEOUT_S
        t0 = time.monotonic()
        with redirect_stderr(io.StringIO()):
            statuses = na.Steps.indented(["sleep", "60"], timeout=1)
        took = time.monotonic() - t0
        check("a pipeline that hangs is killed at its bound and fails", statuses == [124] and took < 10, f"{statuses} {took:.1f}")
        na.STEP_TIMEOUT_S = saved_timeout
        rc, out = s.capture(["bash", "-c", "echo out; echo to-the-log >&2; exit 4"])
        check("a captured step: its stdout, its stderr kept in the log for the failure",
              (rc, out) == (4, "out") and "to-the-log" in open(log).read())
        err = io.StringIO()
        with redirect_stderr(err):
            s.tail(1)
        check("…and the log's last lines shown when it fails", err.getvalue() == "to-the-log\n")
        with redirect_stderr(io.StringIO()):
            reg = na.hosts_registry(put(f"{tmp}/hosts.json", "{ not json"))
        check("a hosts registry that cannot be read is empty, said in one line", reg == {})

        print("a step that runs out, and an interrupted run (review of #80)")
        tools = os.path.join(HERE, "tools", "fabric")

        def gone(pid_file: str) -> bool:
            """Whether the process is gone; one that is not is killed here,
            so a regression fails the check without leaving it behind."""
            with open(pid_file, encoding="utf-8") as fh:
                pid = int(fh.read())
            try:
                with open(f"/proc/{pid}/stat", encoding="ascii") as fh:
                    if fh.read().rsplit(")", 1)[1].split()[0] == "Z":
                        return True
            except OSError:
                return True
            os.kill(pid, signal.SIGKILL)
            return False
        # A wrapper that ignores SIGTERM, as its child then does: only
        # SIGKILL ends either, and the child is what the old kill left.
        tree = f"{tmp}/tree.pid"
        wrapper = ["bash", "-c", f"trap '' TERM; sleep 300 & echo $! > {tree}; wait"]
        saved_bounds = (bounded.READBACK_TIMEOUT_S, bounded.STOP_GRACE_S)
        bounded.READBACK_TIMEOUT_S, bounded.STOP_GRACE_S = 1, 0.5
        try:
            with redirect_stderr(io.StringIO()):
                bounded.quiet_run(wrapper)
        finally:
            bounded.READBACK_TIMEOUT_S, bounded.STOP_GRACE_S = saved_bounds
        check("a worker read-back that runs out ends what it started, not only its wrapper", gone(tree))
        os.remove(tree)
        bounded.STOP_GRACE_S = 0.5
        try:
            rc, _ = na.Steps(log).capture(wrapper, timeout=1)
        finally:
            bounded.STOP_GRACE_S = saved_bounds[1]
        check("…and so does a coordinator step", rc == 124 and gone(tree), str(rc))

        # A grandchild of another account (root's, under sudo) is not ours to
        # signal: its kill is refused, so here every signal to it is refused,
        # as the kernel would. No wait makes it end, so none is spent on it,
        # and it is named as what it is, not as a SIGKILL that did not take.
        orphan = f"{tmp}/orphan.pid"
        p = subprocess.Popen(["bash", "-c", f"sleep 300 & echo $! > {orphan}; wait"])
        for _ in range(100):
            if os.path.exists(orphan) and open(orphan).read().strip():
                break
            time.sleep(0.02)
        theirs = int(open(orphan).read())
        real_kill = os.kill

        def refusing_kill(pid: int, sig: int) -> None:
            if pid == theirs:
                raise PermissionError(1, "Operation not permitted")
            real_kill(pid, sig)
        saved_grace = bounded.STOP_GRACE_S
        bounded.STOP_GRACE_S, os.kill = 2, refusing_kill
        err = io.StringIO()
        t0 = time.monotonic()
        try:
            with redirect_stderr(err):
                bounded.stop_tree(p)
        finally:
            os.kill, bounded.STOP_GRACE_S = real_kill, saved_grace
            took = time.monotonic() - t0
            real_kill(theirs, signal.SIGKILL)
        check("a process no signal reaches is not waited for, and named as such",
              took < 1.5 and f"could not be signalled (another account's): pid {theirs}" in err.getvalue()
              and "still running after SIGKILL" not in err.getvalue(), f"{took:.1f} s: {err.getvalue()}")

        # A process that exits between its /proc read and its kill answers
        # ESRCH, not EPERM: here every signal to it says so while /proc
        # still shows it. It is gone, not another account's, and is named
        # as neither.
        # The pid comes from the child's stdout, so no file a slow start can
        # race; whatever happens after the Popen, the finally ends both.
        p = subprocess.Popen(["bash", "-c", "sleep 300 & echo $!; wait"], stdout=subprocess.PIPE, text=True)
        vanishing = 0

        def vanished_kill(pid: int, sig: int) -> None:
            if pid == vanishing:
                raise ProcessLookupError(3, "No such process")
            real_kill(pid, sig)
        err = io.StringIO()
        try:
            vanishing = int(p.stdout.readline())
            bounded.STOP_GRACE_S, os.kill = 2, vanished_kill
            with redirect_stderr(err):
                bounded.stop_tree(p)
        finally:
            os.kill, bounded.STOP_GRACE_S = real_kill, saved_grace
            if vanishing:
                real_kill(vanishing, signal.SIGKILL)
            p.kill()
            p.wait()
            p.stdout.close()
        check("a process that just exited is not named another account's",
              "could not be signalled" not in err.getvalue() and "still running" not in err.getvalue(), err.getvalue())

        hang = put(f"{tmp}/hang-bin/getent", "#!/usr/bin/env bash\nexec sleep 60\n", 0o755)
        r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); from provisioning import bounded, worker; "
                            "bounded.READBACK_TIMEOUT_S = 1; bounded.STOP_GRACE_S = 0.5; sys.exit(worker.main(['host-check', 'x']))"
                            % tools], env=clean_env(PATH=f"{os.path.dirname(hang)}:{os.environ['PATH']}"),
                           capture_output=True, text=True, timeout=60)
        check("a host-check whose account lookup gets no answer: neither present nor absent, one line, exit 1",
              r.returncode == 1 and r.stdout == "" and r.stderr == "new-agent: getent: no answer within 1 s\n",
              f"rc={r.returncode} {r.stdout!r} {r.stderr}")

        scratch = f"{tmp}/interrupted-tmp"
        os.makedirs(scratch)
        started = f"{tmp}/hx-started"
        slow = put(f"{tmp}/slow-hx", f"#!/usr/bin/env bash\ntouch {started}\nexec sleep 60\n", 0o755)
        code = ("import sys; sys.path.insert(0, %r); import new_agent as na; na.HX = %r; na.ROOT = %r; "
                "sys.exit(na.main(['l', 'r', '--host', 'here', '--no-claude-account']))") % (tools, slow, f"{fk}/root")
        p = subprocess.Popen([sys.executable, "-c", code], process_group=0, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             env=clean_env(TMPDIR=scratch, AGENT_FABRIC_HOSTS_REGISTRY=hosts,
                                           AGENT_FABRIC_OPERATOR=f"{fk}/root"))
        deadline = time.monotonic() + 30
        while not os.path.exists(started) and time.monotonic() < deadline and p.poll() is None:
            time.sleep(0.05)
        os.killpg(p.pid, signal.SIGINT)
        rc = p.wait(timeout=30)
        check("Ctrl-C mid-run: the run ends by SIGINT, and its log is gone, as the bash's EXIT trap left it",
              rc == -signal.SIGINT and os.listdir(scratch) == [], f"rc={rc} left={os.listdir(scratch)}")

    print("test_new_agent.py: OK" if not fails else f"test_new_agent.py: {fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
