#!/usr/bin/env python3
"""Tests for tools/fabric/new_agent.py and new_agent_worker.py; the
behaviour is tests/test_new_agent_cli.py's, run against the
new-agent.sh shim and the new-agent-worker.sh step-runner (ADR-040 §5 rule
5). What is here is what that suite does not reach: the worker's
argument quirks, each decision on its own (the claude version, the
subordinate ids, the host keys, the audit, the closing list), the
verification read-backs, and the orchestrator's usage, refusals, bounds
and pipelines. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stderr

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import new_agent as na  # noqa: E402
import new_agent_worker as w  # noqa: E402

SHIM = os.path.join(HERE, "runtime", "provisioning", "new-agent.sh")


def clean_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_"))}
    env.update(extra)
    return env


def worker_args(*argv: str):
    try:
        return 0, w.args(list(argv))
    except w.Exit as exc:
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
        rc, out = worker_args("prepare", "a-login", "a-role", "--claude", "1.2.3", "--dry-run")
        got = subprocess.run(["bash", "-c", out + 'printf "%s|%s|%s|%s|%s" "$PHASE" "$LOGIN" "$ROLE" "$DRY" "$CLAUDE_TARGET"'],
                             capture_output=True, text=True, timeout=30).stdout
        check("prepare: every variable, quoted for eval", rc == 0 and got == "prepare|a-login|a-role|1|1.2.3", got)
        rc, out = worker_args("finish", "l", "r", "--clone", "demo=git@h:o/d.git", "--clone=x=y=z", "--project", "p")
        got = subprocess.run(["bash", "-c", out + 'printf "%s;" "${PROJECTS[@]}"; printf "%s;" "${REMOTE[demo]}" "${REMOTE[x]}"'],
                             capture_output=True, text=True, timeout=30).stdout
        check("finish: --clone <id>=<remote> splits at the first =, spaced or =; --project adds a project",
              rc == 0 and got == "demo;x;p;git@h:o/d.git;y=z;", got)
        rc, out = worker_args("prepare", "l", "r", "--clone", "x';touch /tmp/pwned;'=y")
        got = subprocess.run(["bash", "-c", out + 'printf "%s" "${PROJECTS[0]}"'], capture_output=True, text=True,
                             timeout=30).stdout
        check("a value carrying shell characters stays a value through the eval", got == "x';touch /tmp/pwned;'", got)
        check("no phase: the usage, exit 2", worker_args() == (2, w.USAGE) and worker_args("bogus")[0] == 2)
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
              r.returncode == 2 and r.stderr == w.USAGE + "\n" and r.stdout == "", r.stderr)
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
                    return w.claude_want(root, target), err.getvalue()
            except w.Exit as exc:
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
        check("empty files: SUB_UID_MIN and SUB_UID_COUNT's defaults", w.subids("n", etc) == "alloc 524288-589823\n")
        put(f"{etc}/login.defs", "# defs\nSUB_UID_MIN  100000\nSUB_UID_COUNT 1000\n")
        put(f"{etc}/subuid", "a:100000:1000\nb:200000:500\n")
        put(f"{etc}/subgid", "a:100000:1000\nc:300000:65536\n")
        check("the next block above every range in either file, login.defs' size",
              w.subids("n", etc) == "alloc 365536-366535\n", w.subids("n", etc))
        check("an account with both ranges keeps them", w.subids("a", etc) == "have 100000:1000\n")
        check("…but one with a uid range only gets both anew", w.subids("b", etc).startswith("alloc "))

        print("the GitHub host keys")
        keys = put(f"{tmp}/keys", "github.com ssh-ed25519 AAA\ngithub.com ecdsa BBB\n\n")
        check("the published lines the account does not hold, whole lines only",
              w.missing_keys(keys, "github.com ssh-ed25519 AAA\nother.com x y\n") == "github.com ecdsa BBB\n")
        check("…none when it holds them all", w.missing_keys(keys, "github.com ecdsa BBB\ngithub.com ssh-ed25519 AAA\n") == "")
        check("…and all of them when it holds none", w.missing_keys(keys, "").count("\n") == 2)
        check("a line that only contains a published key is not that key (whole lines, as grep -x)",
              w.missing_keys(keys, "github.com ecdsa BBB # pinned\ngithub.com ssh-ed25519 AAA\n") == "github.com ecdsa BBB\n")

        print("the host audit")
        check("nothing missing: the count of the contract",
              w.audit("fedora", "1", "dnf", "23", []) == "new-agent: 0. fedora: host tools present (23, the fabric's contract)\n")
        check("missing on a host that keeps packages: the hint with the packages",
              w.audit("debian", "1", "sudo apt-get install", "23", ["gh", "jq"])
              == "new-agent: 0. debian: this host lacks gh jq: sudo apt-get install gh jq\n")
        check("missing on an AppVM: two lines, and the restart",
              w.audit("fedora-qubes", "0", "dnf in the template", "23", ["gh"]).count("\n") == 2
              and "(then restart this AppVM)" in w.audit("fedora-qubes", "", "x", "1", ["gh"]))

        print("the closing list")
        c = w.closing("acct", "absent", "no", "demo")
        check("no GPG key and no template: both named, with the commands, and the first launch in the first project",
              "GPG secret key: the signing key's is NOT" in c and "sudo -u acct gpg --batch --import" in c and "bin/fabric-accounts assign acct" in c
              and "moveto acct demo   then" in c and c.startswith("new-agent: done."))
        c = w.closing("acct", "present", "template", "")
        check("…present ones said as present; no project, no clone name",
              "GPG secret key: the signing key's, present" in c and "a template token (plain-claude path ready)" in c and "moveto acct   then" in c)

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
        mine = {name: w.signs_with_secret(text) for name, text in listings.items()}
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
            check("hostname -s first, then the account", w.host_check("here") == "far-host\naccount: present\n"
                  and w.host_check("gone") == "far-host\naccount: absent\n")
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

        def verify_with(answers: dict, projects: list[str]) -> tuple[str, str, list[str]]:
            asked = []

            def fake_run(self, line, *, stderr=None):
                asked.append(line)
                return next((v for k, v in answers.items() if k in line), b"")
            saved_run, saved_err = w.Account.run, sys.stderr
            w.Account.run = fake_run
            buf = io.BytesIO()
            wrapper = sys.stderr = io.TextIOWrapper(buf, encoding="utf-8")
            try:
                text = w.verify(root, "acct", home, f"{tmp}/vbin/sudo", projects)
                wrapper.flush()
                said = buf.getvalue().decode()
            finally:
                w.Account.run, sys.stderr = saved_run, saved_err
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
                  w.signs_with_secret(out) is want, out)
        put(f"{home}/.config/agent-fabric/secrets.env", "export CLAUDE_CODE_OAUTH_TOKEN='x'\n")
        text, _, _ = verify_with({}, [])
        check("…and a template token in the synced record is read through sudo", "a template token" in text)
        saved_path = os.environ["PATH"]
        os.environ["PATH"] = f"{tmp}/vbin:{saved_path}"
        try:
            out = w.Account("acct", home, f"{tmp}/vbin/sudo").run("echo as-the-account")
        finally:
            os.environ["PATH"] = saved_path
        calls = open(f"{tmp}/sudo.calls").read().splitlines()
        check("a read-back is a login shell as the account through sudo -u, never as root",
              out == b"as-the-account\n" and any(c.startswith("-n -u acct -H env -i HOME=") and " bash -lc " in c
                                                  for c in calls), calls[-1:])
        saved_err = sys.stderr
        sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        try:
            missing = w.quiet_run([f"{tmp}/no-fabric-ctl"], stderr=subprocess.STDOUT)
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
        r = shim("l", "r", "--claude", "9.9")
        check("--claude 9.9 is not a version", r.returncode == 2 and "--claude takes stable, latest or a version" in r.stderr)
        check("values spaced or with =, flags anywhere",
              na.parse(["--project=a", "l", "--host", "h", "r", "--project", "b", "--claude=latest"])
              == {"dry": False, "login": "l", "role": "r", "projects": ["a", "b"], "claude": "latest", "host": "h"})

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
        secrets = put(f"{fk}/fabric-secrets", "#!/usr/bin/env bash\necho '[{\"status\": \"written\"}]'\n", 0o755)
        enroll = put(f"{fk}/store-enroll.sh", "#!/usr/bin/env bash\nexit 0\n", 0o755)
        reg = put(f"{fk}/registry.json", json.dumps({"projects": {"demo": {"remotes": ["https://h/o/d.git", "git@h:o/d.git"]}}}))
        hosts = put(f"{fk}/hosts.json", json.dumps({"hosts": {"here": {"ssh": None}, "far": {"ssh": "op@far"}},
                                                    "placement": {"placed": "far"}}))
        saved = (na.HX, na.STORE, na.SECRETS, na.STORE_ENROLL, na.REGISTRY, na.ROOT)
        na.HX, na.STORE, na.SECRETS, na.STORE_ENROLL, na.REGISTRY = hx, store, secrets, enroll, reg
        os.makedirs(f"{fk}/root/identities/roles/r")
        put(f"{fk}/root/identities/roles/r/charter.md", "x")
        na.ROOT = f"{fk}/root"

        def orchestrate(*argv, hosts_path=hosts):
            for f in ("hx.calls", "taken"):
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
                  rc == 1 and "answers as 'elsewhere'" in msg and "prepare" not in calls)
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
        finally:
            na.HX, na.STORE, na.SECRETS, na.STORE_ENROLL, na.REGISTRY, na.ROOT = saved

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
        saved_bounds = (w.READBACK_TIMEOUT_S, getattr(w, "STOP_GRACE_S", None))
        w.READBACK_TIMEOUT_S, w.STOP_GRACE_S = 1, 0.5
        try:
            with redirect_stderr(io.StringIO()):
                w.quiet_run(wrapper)
        finally:
            w.READBACK_TIMEOUT_S, w.STOP_GRACE_S = saved_bounds
        check("a worker read-back that runs out ends what it started, not only its wrapper", gone(tree))
        os.remove(tree)
        w.STOP_GRACE_S = 0.5
        try:
            rc, _ = na.Steps(log).capture(wrapper, timeout=1)
        finally:
            w.STOP_GRACE_S = saved_bounds[1]
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
        saved_grace = w.STOP_GRACE_S
        w.STOP_GRACE_S, os.kill = 2, refusing_kill
        err = io.StringIO()
        t0 = time.monotonic()
        try:
            with redirect_stderr(err):
                w.stop_tree(p)
        finally:
            os.kill, w.STOP_GRACE_S = real_kill, saved_grace
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
            w.STOP_GRACE_S, os.kill = 2, vanished_kill
            with redirect_stderr(err):
                w.stop_tree(p)
        finally:
            os.kill, w.STOP_GRACE_S = real_kill, saved_grace
            if vanishing:
                real_kill(vanishing, signal.SIGKILL)
            p.kill()
            p.wait()
            p.stdout.close()
        check("a process that just exited is not named another account's",
              "could not be signalled" not in err.getvalue() and "still running" not in err.getvalue(), err.getvalue())

        hang = put(f"{tmp}/hang-bin/getent", "#!/usr/bin/env bash\nexec sleep 60\n", 0o755)
        r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import new_agent_worker as w; "
                            "w.READBACK_TIMEOUT_S = 1; w.STOP_GRACE_S = 0.5; sys.exit(w.main(['host-check', 'x']))"
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
                "sys.exit(na.main(['l', 'r', '--host', 'here']))") % (tools, slow, f"{fk}/root")
        p = subprocess.Popen([sys.executable, "-c", code], process_group=0, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             env=clean_env(TMPDIR=scratch, AGENT_FABRIC_HOSTS_REGISTRY=hosts))
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
