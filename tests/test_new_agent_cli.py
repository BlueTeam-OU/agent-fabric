#!/usr/bin/env python3
"""runtime/provisioning/new-agent.sh refuses what the fabric does not
know, its dry run names every step without touching the host, and the
REAL sequence — against fakes for sudo, useradd, getent, id, curl (the
vendor installers), ssh-keyscan, git clone, store-enroll.sh and
fabric-secrets provision, in a sandbox — stops where a step fails, names
it, runs nothing after it, and converges on the re-run (review,
2026-09-16). Root, the stores and the network are what the fakes stand in
for. Ported from runtime/provisioning/test_new-agent.sh (ADR-040 Wave 6),
case for case. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "runtime", "provisioning")
sys.path.insert(0, os.path.join(ROOT, "tests"))
from instance_fixtures import SECRETS_REGISTRY, write_json  # noqa: E402
LOGIN = pwd.getpwuid(os.geteuid()).pw_name
# The fixture template's token and its fingerprint, as store templates prints it.
TOKEN = "sk-ant-oat01-fixture-token"
FP = hashlib.sha256(TOKEN.encode()).hexdigest()[:12]
ACCOUNT_FLAGS = ("--claude-account", "--no-claude-account")


def with_account(args: tuple[str, ...], default: tuple[str, ...]) -> list[str]:
    """Every run names its Claude account (2026-10-07); a case that does
    not is about something else and gets the default."""
    named = any(a in ACCOUNT_FLAGS or a.startswith("--claude-account=") or a == "--human" for a in args)
    return [*args] if named or "--no-account-flag" in args else [*args, *default]

# The fakes, as the bash suite wrote them: {SEQ}, {BIN}, {HOMES}, {CALLS},
# {FAULT}, {SANDBOX} are filled in.
FAKES = {
    # sudo drops `-n -u X -H` and runs the rest as this user. The fakes
    # first, and never /usr/local/bin: a real claude there must not be what
    # the fixture account runs. Whole lines in the log: a cap only moves
    # where a long TMPDIR truncates an assertion away.
    "sudo": r'''#!/usr/bin/env bash
[[ "$1" == -n ]] && shift; [[ "$1" == true ]] && exit 0
[[ "$1" == -u ]] && shift 2; [[ "$1" == -H ]] && shift
args=(); for a in "$@"; do
  [[ "$a" == PATH=* ]] && a="PATH={BIN}:${a#PATH=}" && a="${a//\/usr\/local\/bin:/}"
  [[ "$a" == AGENT_FABRIC_PATH=* ]] && a="AGENT_FABRIC_PATH={BIN}:${a#AGENT_FABRIC_PATH=}" && a="${a//\/usr\/local\/bin:/}"
  args+=("$a"); done
echo "sudo ${args[*]}" >> "{CALLS}"
grep -qsxF "${args[0]}" "{FAULT}" && { echo "fake: ${args[0]} failed (injected)" >&2; exit 1; }
[[ "${args[0]}" == chown ]] && exit 0
exec "${args[@]}"
''',
    "useradd": r'''#!/usr/bin/env bash
login="${@: -1}"; mkdir -p "{HOMES}/$login"; echo "$login" >> "{SEQ}/passwd"; echo "useradd $login" >> "{CALLS}"
''',
    # The subordinate-range allocation records itself and writes the range
    # where the worker reads it back (AGENT_FABRIC_ETC), so the second run
    # finds it and allocates nothing.
    "usermod": r'''#!/usr/bin/env bash
echo "usermod $*" >> "{CALLS}"
login="${@: -1}"; r=""; while [[ $# -gt 0 ]]; do [[ "$1" == --add-subuids ]] && r="$2"; shift; done
[[ -n "$r" ]] && mkdir -p "{SANDBOX}/persist/etc" && printf '%s:%s:%s\n' "$login" "${r%-*}" "$(( ${r#*-} - ${r%-*} + 1 ))" | tee -a "{SANDBOX}/persist/etc/subuid" >> "{SANDBOX}/persist/etc/subgid"
''',
    "loginctl": '#!/usr/bin/env bash\necho "loginctl $*" >> "{CALLS}"\n',
    "getent": r'''#!/usr/bin/env bash
case "$1" in
  passwd) grep -qsxF "$2" "{SEQ}/passwd" && echo "$2:x:1000:1000::{HOMES}/$2:/bin/bash" ;;
  group) exit 2 ;;
esac
''',
    "id": r'''#!/usr/bin/env bash
[[ "$1" == -gn ]] && { echo staff; exit 0; }
[[ "$1" == -nG ]] && { echo ""; exit 0; }
exec /usr/bin/id "$@"
''',
    "curl": r'''#!/usr/bin/env bash
echo "curl $*" >> "{CALLS}"
grep -qsxF curl "{FAULT}" && exit 22
case "$*" in
  *claude-code-releases/latest*) echo "9.9.9" ;;
  *claude.ai/install.sh*) printf 'v="${1:-9.9.9}"; mkdir -p ~/.local/share/claude/versions ~/.local/bin; printf "#!/bin/sh\\necho %%s-fake\\n" "$v" > ~/.local/share/claude/versions/$v; chmod +x ~/.local/share/claude/versions/$v; ln -sf ~/.local/share/claude/versions/$v ~/.local/bin/claude\n' ;;
  *ori/install.sh*) printf 'mkdir -p ~/.local/bin; printf "#!/bin/sh\\necho ori-0.1-fake\\n" > ~/.local/bin/ori; chmod +x ~/.local/bin/ori\n' ;;
  *) exit 22 ;;
esac
''',
    "ssh-keyscan": '#!/usr/bin/env bash\necho "ssh-keyscan $*" >> "{CALLS}"; '
                   'echo "fake: ssh-keyscan must never be called (the host keys are committed)" >&2; exit 99\n',
    "gh": '#!/usr/bin/env bash\necho "gh auth: Logged in to github.com"\n',
    "git": r'''#!/usr/bin/env bash
[[ "$1" == clone ]] && grep -qsxF git "{FAULT}" && { echo "fake git: clone failed (injected)" >&2; exit 128; }
exec /usr/bin/git "$@"
''',
    "npm": '#!/usr/bin/env bash\n[[ "$1" == ci ]] && mkdir -p node_modules; exit 0\n',
    "gpg": "#!/usr/bin/env bash\nexit 0\n",
    # The far host is this machine behind a fake ssh.
    "ssh": r'''#!/usr/bin/env bash
printf '%s\n' "$*" >> "{SEQ}/ssh.log"; args=("$@"); PATH="{SEQ}/farbin:$PATH" exec bash -c "${args[-1]}"
''',
}
STORE_ENROLL = r'''#!/usr/bin/env bash
echo "store-enroll $*" >> "{CALLS}"
grep -qsxF "store-enroll" "{FAULT}" && { echo "store-enroll: injected failure" >&2; exit 1; }
[[ -f "{SEQ}/enrolled" ]] || echo '[]' > "{SEQ}/enrolled"
'''
# provision answers rows as the real one does: a name the store holds is
# present, any other is written and remembered.
PROVISION = r'''#!/usr/bin/env bash
echo "secrets $*" >> "{CALLS}"
# The parent's Claude templates (fabric-secrets store templates/assign): one
# with a token, one without. assign writes the token into the child's
# store, which the fakes keep in $SEQ/token for the account's sync to apply.
if [[ "$1 $2" == "store templates" ]]; then
  grep -qsxF "store templates" "{FAULT}" && { echo "store: injected failure" >&2; exit 1; }
  echo '[{"account": "acct-one", "token_sha256_12": "{FP}"}, {"account": "acct-empty", "token_sha256_12": null}]'; exit 0
fi
if [[ "$1 $2" == "store assign" ]]; then
  grep -qsxF "store assign" "{FAULT}" && { echo '[{"login": "'"$4"'", "from": "none", "status": "failed", "reason": "injected"}]'; exit 1; }
  [[ "$3" == acct-one ]] || exit 9
  st=written; [[ "$(cat "{SEQ}/token" 2>/dev/null)" == "{TOKEN}" ]] && st=unchanged
  printf '%s' "{TOKEN}" > "{SEQ}/token"
  echo '[{"login": "'"$4"'", "from": "none", "to": "acct-one", "status": "'"$st"'", "token_sha256_12": "{FP}"}]'; exit 0
fi
[[ "$1" == provision ]] || exit 9
grep -qsxF "provision $2" "{FAULT}" && { echo "provision: injected failure" >&2; exit 1; }
case "$2" in identity) names="AGENT_LOGIN AGENT_HOST" ;; share) names="GH_TOKEN SSH_PRIVATE_KEY"; [[ "$4" == --name ]] && names="$5" ;;
  issue-key) [[ "$3" == openrouter ]] && names=OPENROUTER_API_KEY || names=OPENAI_API_KEY ;; esac
python3 - "{SEQ}/enrolled" $names <<'PY'
import json, sys
f, names = sys.argv[1], sys.argv[2:]
have = json.load(open(f))
rows = [{"login": "x", "name": n, "status": "present" if n in have else "written"} for n in names]
json.dump(sorted(set(have) | set(names)), open(f, "w"))
print(json.dumps(rows))
PY
'''
SECRET_STORE = r'''#!/usr/bin/env python3
import os, sys
a = sys.argv[1:]
if a == ["export-key"]:
    sys.exit(0)
if a[:1] == ["child-bundle"]:
    open("{CALLS}", "a").write("secret_store " + " ".join(a) + "\n")
    if os.path.exists("{FAULT}") and "child-bundle" in open("{FAULT}").read().split("\n"):
        sys.exit("fake: child-bundle failed (injected)")
    print("-----BEGIN AGENT-FABRIC STORE BUNDLE-----\nAAAA\n-----END AGENT-FABRIC STORE BUNDLE-----")
    sys.exit(0)
sys.exit(9)
'''
# The account's own fabric-secrets: its sync answers 3 (a store naming
# another login) when the fault file says account-sync; its calls are kept
# in order; take-bundle must be handed an armored bundle.
ACCOUNT_SECRETS = r'''#!/usr/bin/env bash
echo "$*" >> "{SEQ}/account-calls"
[[ "$*" == "store take-bundle" ]] && { grep -q "BEGIN AGENT-FABRIC STORE BUNDLE" || { echo "no bundle on stdin" >&2; exit 1; }; echo "taken"; exit 0; }
grep -qsxF account-sync "{FAULT}" && { echo "fabric-secrets: the store names another login" >&2; exit 3; }
# sync applies the token the store holds, as secrets.env's export line;
# account-token makes it apply another one.
if [[ "$1" == sync && -f "{SEQ}/token" ]]; then
  t="$(cat "{SEQ}/token")"; grep -qsxF account-token "{FAULT}" && t="other-token"
  for h in "{HOMES}"/*/; do mkdir -p "$h.config/agent-fabric"; printf "export CLAUDE_CODE_OAUTH_TOKEN='%s'\n" "$t" > "$h.config/agent-fabric/secrets.env"; done
fi
echo "fabric-secrets: OK"
'''


def main() -> int:
    fails = 0

    def ok(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    def has(pattern: str, text: str) -> bool:
        return re.search(pattern, text, re.M) is not None

    local = subprocess.run(["hostname", "-s"], stdout=subprocess.PIPE, text=True, check=True, timeout=10).stdout.strip()
    base = {k: v for k, v in os.environ.items()
            if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}

    with tempfile.TemporaryDirectory() as sandbox:
        def put(path: str, text: str, mode: int = 0o644) -> None:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(path, mode)

        def read(path: str) -> str:
            try:
                with open(path, encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                return ""

        # A fixture fabric: its own role and registry, a fake claude to
        # copy from; a fixture copies the modules of the scripts it copies
        # (ADR-040 §5 rule 5).
        fab = f"{sandbox}/fabric"
        for d in ("runtime/provisioning/secrets", "projects", "runtime/claude-code", "tools/fabric"):
            os.makedirs(f"{fab}/{d}")
        os.makedirs(f"{sandbox}/home/.local/bin")
        # The role the cases ask for, and the registry's projects; the remotes are the fixture's.
        put(f"{fab}/identities/roles/backend-dev/charter.md", "# backend-dev\n")
        write_json(f"{fab}/projects/registry.json", SECRETS_REGISTRY)
        for f in ("new-agent.sh", "new-agent-worker.sh", "persist-accounts.sh", "github-host-keys"):
            shutil.copy2(f"{HERE}/{f}", f"{fab}/runtime/provisioning/")
        shutil.copytree(f"{ROOT}/runtime/hostexec", f"{fab}/runtime/hostexec", symlinks=True)
        shutil.copytree(f"{HERE}/platform", f"{fab}/runtime/provisioning/platform", symlinks=True)
        shutil.copy(f"{ROOT}/runtime/claude-code/harness.json", f"{fab}/runtime/claude-code/")
        for f in ("new_agent.py", "new_agent_worker.py", "roots.py"):
            shutil.copy2(f"{ROOT}/tools/fabric/{f}", f"{fab}/tools/fabric/")
        put(f"{sandbox}/home/.local/bin/claude", "#!/bin/sh\necho fake\n", 0o755)
        # The host registry the orchestrator reads: this host (direct) and a
        # far one reached over a fake ssh that runs the same worker here.
        hosts = f"{sandbox}/hosts.json"
        put(hosts, json.dumps({"version": 1, "hosts": {
            local: {"platform": "fedora-qubes", "ssh": None, "operator": LOGIN, "fabric": fab},
            "far-host": {"platform": "debian", "ssh": "op@far.example", "operator": "op", "fabric": fab}},
            "placement": {"placed-elsewhere": "far-host", "human-here": local, "human-far": "far-host"},
            "kinds": {"human-here": "human", "human-far": "human"}}))
        base["AGENT_FABRIC_HOSTS_REGISTRY"] = hosts
        shim = f"{fab}/runtime/provisioning/new-agent.sh"

        def run(*args: str, **extra: str) -> tuple[int, str]:
            argv = [a for a in with_account(args, ("--no-claude-account",)) if a != "--no-account-flag"]
            r = subprocess.run(["bash", shim, *argv], env={**base, "HOME": f"{sandbox}/home", **extra},
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
            return r.returncode, r.stdout

        print("new-agent: refusals")
        rc, out = run()
        ok("no arguments: usage, exit 2", rc == 2 and has(r"^usage:", out), out)
        rc, out = run("some-login", "no-such-role", "--dry-run")
        ok("an unknown role is refused before anything runs", rc == 1 and "no role 'no-such-role'" in out, out)
        rc, out = run("some-login", "backend-dev", "--project", "not-registered", "--dry-run")
        ok("an unregistered project is refused", rc == 1 and "not in projects/registry.json" in out, out)
        rc, out = run("some-login", "backend-dev", "--bogus", "--dry-run")
        ok("an unknown flag is a usage error", rc == 2, out)
        rc, out = run("placed-elsewhere", "backend-dev", "--host", local, "--dry-run")
        ok("an account placed on another host is not made again here", rc == 1 and "is placed on far-host" in out, out)
        rc, out = run("some-login", "backend-dev", "--host", "nowhere", "--dry-run")
        ok("an unregistered host is refused", rc == 1 and "unknown host 'nowhere'" in out, out)
        rc, out = run("some-login", "backend-dev", "--dry-run", "--no-account-flag")
        ok("no Claude account named: exit 2, both flags named, before anything runs",
           rc == 2 and "--claude-account <slug>" in out and "--no-claude-account" in out and "host" not in out, out)
        rc, out = run("some-login", "backend-dev", "--claude-account", "acct-one", "--no-claude-account", "--dry-run")
        ok("…both named: exit 2", rc == 2 and "--claude-account <slug>" in out, out)
        rc, out = run("some-login", "backend-dev", "--claude-account=Acct;x", "--dry-run")
        ok("…a slug that is not one: exit 2", rc == 2 and "is not an account slug" in out, out)
        rc, out = run("some-login", "backend-dev", "--claude-account=", "--dry-run")
        ok("…an empty one is named, not taken for none: exit 2", rc == 2 and "is not an account slug" in out, out)

        print("new-agent: the dry run names every step and touches nothing")
        rc, out = run("zz-fixture-login", "backend-dev", "--project", "gzapp", "--project", "agent-fabric", "--dry-run")
        ok("exits 0", rc == 0, f"rc={rc}\n{out}")
        for step in ("useradd", "chmod 700", "mkdir -p", "curl -fsSL https://claude.ai/install.sh | bash -s -- ",
                     "curl -fsSL https://openrouter.ai/labs/ori/install.sh | bash", "append GitHub's published host keys",
                     "git clone -q 'https://github.com/gzapi-org/agent-fabric.git'", "store-enroll.sh zz-fixture-login --host",
                     "provision identity, share, issue-key openrouter and openai",
                     "git clone -q 'git@github.com:fixture-org/gzapp.git'", "bootstrap.sh", "fabric-role bind 'backend-dev'"):
            ok(f"plans: {step}", step in out, out)
        ok("…and verifies nothing", "dry run: nothing verified" in out, out)
        ok("no account was created", subprocess.run(["getent", "passwd", "zz-fixture-login"], stdout=subprocess.DEVNULL,
                                                     timeout=30).returncode != 0)
        ok("a project clone uses the registry's SSH remote", "git@github.com" in out, out)
        ok("no binary is ever copied from another account", not re.search(r"copied|copy from", out, re.I), out)
        ok("the host audit runs first, naming the platform",
           has(r"^new-agent: 0\. [a-z-]*: host tools present", out) or has(r"^new-agent: 0\. [a-z-]*: this", out), out)
        # A PATH with everything the dry run needs except gh: the audit must
        # name gh's Debian package and apt-get.
        nogh = f"{sandbox}/nogh"
        os.makedirs(nogh)
        for tool in ("bash", "python3", "getent", "id", "sudo", "hostname", "readlink", "dirname", "basename", "cut", "grep",
                     "sed", "head", "tail", "tr", "sort", "uniq", "mktemp", "cat", "env", "cp", "mkdir", "rm", "ls", "ln",
                     "chmod", "tee", "wc", "awk", "xargs", "curl", "ssh", "git", "jq", "gpg", "node", "npm", "sha256sum",
                     "stat", "pgrep", "timeout", "flock", "useradd", "usermod", "shred", "install"):
            src = shutil.which(tool, path=base.get("PATH"))
            if src:
                os.symlink(src, f"{nogh}/{tool}")
        rc, out_deb = run("zz-fixture-login", "backend-dev", "--dry-run", AGENT_FABRIC_PLATFORM="debian", PATH=nogh)
        ok("the Debian profile names the missing tool's package and apt-get",
           has(r"^new-agent: 0\. debian: this host lacks .*gh.*: sudo apt-get install", out_deb), out_deb)
        ok("the host is named, and a missing placement is asked for",
           has(rf"^new-agent: host {re.escape(local)} \(this host\)", out) and 'placement: add "zz-fixture-login"' in out,
           out)
        rc, out = run("some-login", "backend-dev", "--claude", "9.9", "--dry-run")
        ok("--claude takes stable, latest or a full version", rc == 2, out)
        rc, out = run("some-login", "backend-dev", "--claude", "1.2.3-x';id;'", "--dry-run")
        ok("--claude with shell characters in its suffix is refused", rc == 2, out)
        rc, out = run("zz-fixture-login", "backend-dev", "--claude", "2.1.282-beta.1", "--dry-run")
        ok("…while a real pre-release suffix still passes", "install.sh | bash -s -- 2.1.282-beta.1" in out, out)
        rc, out = run("zz-fixture-login", "backend-dev", "--claude", "latest", "--dry-run")
        ok("--claude latest reaches the installer", "install.sh | bash -s -- latest" in out, out)
        with open(f"{ROOT}/runtime/claude-code/harness.json", encoding="utf-8") as fh:
            pin = json.load(fh)["claude"]
        rc, out = run("zz-fixture-login", "backend-dev", "--dry-run")
        ok(f"no --claude: the fleet's pinned version ({pin}) reaches the installer",
           has(rf"install\.sh \| bash -s -- {re.escape(pin)}$", out),
           "\n".join(ln for ln in out.split("\n") if "install.sh" in ln))
        put(f"{fab}/runtime/claude-code/harness.json", '{"claude": "2.1.282\'; touch /tmp/pwned; \'"}')
        rc, out = run("zz-fixture-login", "backend-dev", "--dry-run")
        ok("a pin that is not a version is refused before it reaches the installer's command line",
           rc != 0 and "is not a version; nothing installed" in out and "install.sh | bash" not in out, f"rc={rc}\n{out}")
        os.remove(f"{fab}/runtime/claude-code/harness.json")
        rc, out = run("zz-fixture-login", "backend-dev", "--dry-run")
        ok("no pin: latest, and that is said",
           has(r"no readable pin .* the vendor's latest instead", out) and "install.sh | bash -s -- latest" in out, out)
        shutil.copy(f"{ROOT}/runtime/claude-code/harness.json", f"{fab}/runtime/claude-code/")

        # ---- the real sequence, against fakes, with a failure injected at
        # each must. useradd makes a sandbox home; getent answers for it;
        # curl "installs" claude and ori from a fixture; git clones from a
        # local bare repository (AGENT_FABRIC_CLONE_URL and a registry
        # pointing at it); a fake store-enroll.sh and a fake fabric-secrets
        # record their calls, and the fake provision keeps the names a store
        # holds in $SEQ/enrolled. A fault file names one command the fakes
        # must fail.
        print("new-agent: the real sequence, then a failure at each step")
        seq = f"{sandbox}/seq"
        bin_, homes, fault, calls = f"{seq}/bin", f"{seq}/home", f"{seq}/fault", f"{seq}/calls"
        os.makedirs(bin_)
        os.makedirs(homes)
        fill = {"{SEQ}": seq, "{BIN}": bin_, "{HOMES}": homes, "{CALLS}": calls, "{FAULT}": fault, "{SANDBOX}": sandbox,
                "{TOKEN}": TOKEN, "{FP}": FP}

        def filled(text: str) -> str:
            for k, v in fill.items():
                text = text.replace(k, v)
            return text
        seq_env = {**base, "PATH": f"{bin_}:/usr/bin:/bin"}

        def sh(*argv: str, cwd: str | None = None) -> None:
            subprocess.run(list(argv), cwd=cwd, env=seq_env, check=True, timeout=60, stdout=subprocess.DEVNULL)
        bare = f"{seq}/fabric.git"
        sh("git", "init", "-q", "--bare", "-b", "main", bare)
        src = f"{seq}/fabric-src"
        put(f"{src}/runtime/claude-code/bootstrap.sh", '#!/usr/bin/env bash\necho "bootstrap: ok"\n', 0o755)
        put(f"{src}/bin/fabric-role", '#!/usr/bin/env bash\ncase "$1" in status) echo "role      (none active)";; '
            'bind) echo "bound. role $2";; esac\n', 0o755)
        put(f"{src}/bin/fabric-secrets", filled(ACCOUNT_SECRETS), 0o755)
        put(f"{src}/tools/fabric/relay_catchup.py", "#!/usr/bin/env python3\nimport sys\n"
            f'open("{seq}/account-calls", "a").write("relay_catchup " + " ".join(sys.argv[1:]) + "\\n")\n')
        put(f"{src}/runtime/openrouter/launch", '#!/usr/bin/env bash\necho "launch: resolved profile x"\n', 0o755)
        sh("git", "-C", src, "init", "-q", "-b", "main")
        sh("git", "-C", src, "add", "-A")
        sh("git", "-C", src, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q",
           "-m", "init")
        sh("git", "-C", src, "push", "-q", bare, "HEAD:main")
        demo, demo_src = f"{seq}/demo.git", f"{seq}/demo-src"
        sh("git", "init", "-q", "--bare", "-b", "main", demo)
        put(f"{demo_src}/package-lock.json", "{}")
        sh("git", "-C", demo_src, "init", "-q", "-b", "main")
        sh("git", "-C", demo_src, "add", "-A")
        sh("git", "-C", demo_src, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit",
           "-q", "-m", "init")
        sh("git", "-C", demo_src, "push", "-q", demo, "HEAD:main")
        with open(f"{fab}/projects/registry.json", encoding="utf-8") as fh:
            reg = json.load(fh)
        reg["projects"]["demo"] = {"remotes": [demo], "license": "Apache-2.0"}
        put(f"{fab}/projects/registry.json", json.dumps(reg))
        for name, text in FAKES.items():
            put(f"{bin_}/{name}", filled(text), 0o755)
        put(f"{seq}/farbin/hostname", '#!/usr/bin/env bash\n[[ "$1" == -s ]] && { echo far-host; exit 0; }; '
            'exec /usr/bin/hostname "$@"\n', 0o755)
        put(f"{fab}/runtime/provisioning/secrets/store-enroll.sh", filled(STORE_ENROLL), 0o755)
        put(f"{fab}/runtime/provisioning/secrets/fabric-secrets", filled(PROVISION), 0o755)
        put(f"{seq}/tools/secret_store.py", filled(SECRET_STORE), 0o755)
        shutil.copy2(f"{seq}/tools/secret_store.py", f"{fab}/tools/fabric/")
        ssh_log = f"{seq}/ssh.log"

        def seq_run(backend: str, *args: str) -> tuple[int, str]:
            if os.path.exists(calls):
                os.remove(calls)
            h = ["--host", "far-host"] if backend == "ssh" else []
            env = {**seq_env, "SUDO": f"{bin_}/sudo", "SSH": f"{bin_}/ssh", "AGENT_FABRIC_CLONE_URL": bare,
                   "HOME": f"{sandbox}/home", "AGENT_FABRIC_ACCOUNTS_SNAPSHOT": f"{sandbox}/persist/snap",
                   "AGENT_FABRIC_RC_LOCAL_D": f"{sandbox}/persist/rcd", "AGENT_FABRIC_ETC": f"{sandbox}/persist/etc",
                   "AGENT_FABRIC_LOGINCTL": f"{bin_}/loginctl", "AGENT_FABRIC_LEASES": f"{sandbox}/persist/leases",
                   "AGENT_FABRIC_TMPFILES_D": f"{sandbox}/persist/tmpfiles.d"}
            argv = with_account(args, ("--claude-account", "acct-one"))
            r = subprocess.run(["bash", shim, *argv, *h], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, timeout=600)
            return r.returncode, r.stdout

        def reset_seq() -> None:
            shutil.rmtree(homes, ignore_errors=True)
            for f in (f"{seq}/passwd", f"{seq}/enrolled", fault, f"{seq}/account-calls", f"{seq}/token",
                      f"{sandbox}/persist/etc/subuid", f"{sandbox}/persist/etc/subgid"):
                if os.path.exists(f):
                    os.remove(f)
            os.makedirs(homes)

        def lines(path: str) -> list[str]:
            return read(path).split("\n")

        def git_out(*args: str) -> str:
            return subprocess.run(["git", *args], env=seq_env, stdout=subprocess.PIPE, text=True, timeout=60).stdout.strip()

        h = f"{homes}/seq-login"
        for backend in ("local", "ssh"):
            print(f"new-agent: the real sequence on the {backend} backend")
            put(ssh_log, "")
            reset_seq()
            rc, out = seq_run(backend, "seq-login", "backend-dev", "--project", "demo")
            ok("the whole sequence exits 0", rc == 0, f"rc={rc}\n{out}")
            where = "far-host" if backend == "ssh" else local
            ok("5: the account keyed on its host, its store filled by the parent, and synced",
               f"store-enroll seq-login --host {where} --born-now" in lines(calls)
               and has(r"^secrets provision identity seq-login --host", read(calls))
               and has(r"^secrets provision share seq-login", read(calls))
               and "5. its key made and certified, its store filled and synced" in out, read(calls) + out)
            # A new account has no key to pull with: its filled store reaches
            # it as a bundle, then a sync without a pull.
            acc = [ln for ln in lines(f"{seq}/account-calls") if re.match(r"^(store take-bundle|sync)", ln)]
            ok("…its store handed over as a bundle, then synced without a pull",
               "secret_store child-bundle seq-login" in lines(calls)
               and acc[:2] == ["store take-bundle", "sync --quiet --no-pull"], read(calls) + read(f"{seq}/account-calls"))
            # Its inbox starts at the channel's newest message, for the
            # projects it was made for.
            acc = [ln for ln in lines(f"{seq}/account-calls") if re.match(r"^(sync|relay_catchup)", ln)]
            ok("…then its inbox cursor moved to the newest message, after the sync, for its projects",
               acc[-2:] == ["sync --quiet --no-pull", "relay_catchup demo"], read(f"{seq}/account-calls"))
            # The Claude account: checked before the account is made, its token
            # written into the child's store after the keys and before the
            # bundle, applied by the first sync, and its fingerprint compared.
            c = lines(calls)
            at = {k: next((i for i, ln in enumerate(c) if ln.startswith(k)), -1) for k in
                  ("secrets store templates --json", "useradd", "secrets provision issue-key openai",
                   "secrets store assign acct-one seq-login --json", "secret_store child-bundle")}
            ok("the Claude account: templates read before useradd; assigned after the keys, before the bundle",
               -1 not in at.values() and at["secrets store templates --json"] < at["useradd"]
               and at["secrets provision issue-key openai"] < at["secrets store assign acct-one seq-login --json"]
               < at["secret_store child-bundle"], f"{at}\n{read(calls)}")
            ok("…the token present in secrets.env after the first sync, its fingerprint compared, and said",
               f"export CLAUDE_CODE_OAUTH_TOKEN='{TOKEN}'" in read(f"{h}/.config/agent-fabric/secrets.env")
               and f"Claude account: acct-one, written (token {FP})" in out
               and f"- Claude account: acct-one (token {FP}), applied" in out and TOKEN not in out, out)
            if backend == "local":
                # A parent without a store of its own cannot key a child: a
                # stop, named, before any clone.
                os.remove(f"{fab}/tools/fabric/secret_store.py")
                reset_seq()
                rcns, outns = seq_run(backend, "seq-login", "backend-dev", "--project", "demo")
                ok("no parent store: stopped at step 5, named, nothing after it",
                   rcns == 1 and "store-enroll.sh --self first" in outns and not has(r"^store-enroll", read(calls))
                   and not os.path.isdir(f"{h}/projects/demo"), outns)
                shutil.copy2(f"{seq}/tools/secret_store.py", f"{fab}/tools/fabric/")
                for slug, said in (("no-such", "'no-such' is not a template in this store"),
                                   ("acct-empty", "template acct-empty holds no CLAUDE_CODE_OAUTH_TOKEN yet")):
                    reset_seq()
                    rcu, outu = seq_run(backend, "seq-login", "backend-dev", "--claude-account", slug, "--project", "demo")
                    ok(f"Claude account {slug}: refused before any account is made, nothing after it",
                       rcu == 1 and said in outu and lines(calls)[:-1] == ["secrets store templates --json"]
                       and not os.path.isdir(h), f"rc={rcu}\n{outu}\n{read(calls)}")
                reset_seq()
                put(fault, "store templates\n")
                rcu, outu = seq_run(backend, "seq-login", "backend-dev", "--project", "demo", "--dry-run")
                ok("…templates that cannot be read refuse, never skip the check, dry run included",
                   rcu == 1 and "templates could not be read" in outu and not has(r"^useradd", read(calls)), outu)
                reset_seq()
                rcu, outu = seq_run(backend, "seq-login", "backend-dev", "--project", "demo", "--dry-run")
                ok("the dry run names the assignment and its fingerprint, and writes nothing",
                   rcu == 0 and f"would: fabric-secrets store assign acct-one seq-login (token {FP})" in outu
                   and not has(r"^secrets store assign", read(calls)), outu)
                reset_seq()
                rcu, outu = seq_run(backend, "seq-login", "backend-dev", "--no-claude-account", "--project", "demo")
                ok("--no-claude-account: nothing assigned, and the closing says so",
                   rcu == 0 and not has(r"^secrets store", read(calls))
                   and "- Claude account: not assigned (--no-claude-account: the broker path only)" in outu,
                   f"rc={rcu}\n{outu}")
                reset_seq()
                rc, out = seq_run(backend, "seq-login", "backend-dev", "--project", "demo")   # the plain run the next checks read
            ok("the account is persisted: persist-accounts.sh through sudo, linger enabled",
               "persist-accounts.sh seq-login" in read(calls) and has(r"^loginctl enable-linger seq-login", read(calls)),
               "\n".join(ln for ln in lines(calls) if re.search(r"persist|linger", ln, re.I)))
            keys = [ln for ln in read(f"{HERE}/github-host-keys").split("\n") if ln]
            known = [ln for ln in lines(f"{h}/.ssh/known_hosts") if ln.startswith("github.com ")]
            ok("account, binaries, the published host keys (no keyscan), fabric and project clones, enrolment, toolchain all there",
               os.access(f"{h}/.local/bin/claude", os.X_OK) and os.access(f"{h}/.local/bin/ori", os.X_OK)
               and os.path.isdir(f"{h}/projects/agent-fabric/.git") and os.path.isdir(f"{h}/projects/demo/.git")
               and os.path.isdir(f"{h}/projects/demo/node_modules") and len(known) == len(keys)
               and not has(r"^ssh-keyscan", read(calls)) and has(r"^secrets provision issue-key openrouter seq-login", read(calls))
               and has(r"^secrets provision issue-key openai seq-login", read(calls)), out + "\n" + read(calls))
            fps = subprocess.run(["ssh-keygen", "-lf", f"{h}/.ssh/known_hosts"], stdout=subprocess.PIPE, text=True,
                                 timeout=60).stdout
            got = sorted(f"{p[1]} {p[3].strip('()')}" for p in (ln.split() for ln in fps.split("\n") if ln) if len(p) >= 4)
            want = sorted(ln for ln in read(f"{HERE}/github-host-keys.fingerprints").split("\n") if ln)
            ok("the account's known_hosts carries exactly the committed fingerprints", got == want, fps)
            ok("chown uses the account's primary group, not the login", "chown seq-login:staff" in read(calls),
               "\n".join(ln for ln in lines(calls) if "chown" in ln))
            ok("a subordinate uid and gid range is allocated for the new account (rootless podman)",
               has(r"^usermod --add-subuids 524288-589823 --add-subgids 524288-589823 seq-login", read(calls))
               and "seq-login:524288:65536" in lines(f"{sandbox}/persist/etc/subuid")
               and "seq-login:524288:65536" in lines(f"{sandbox}/persist/etc/subgid"), read(f"{sandbox}/persist/etc/subuid"))
            ok("…and the person's list is printed", "new-agent: done" in out, out)
            if backend == "ssh":
                log = read(ssh_log)
                ok("ssh: host-check, prepare and finish each went to the far host's worker",
                   "new-agent-worker.sh host-check seq-login" in log and "new-agent-worker.sh prepare seq-login backend-dev" in log
                   and "new-agent-worker.sh finish seq-login backend-dev --clone demo=" in log, log)
                ok("…and the run says so", has(r"^new-agent: host far-host \(over ssh\)", out), out)
                ok("…while the store was filled on the coordinator, and only the hand-over and the sync ran on the host",
                   "store-enroll" not in log and "fabric-secrets provision" not in log
                   and "fabric-secrets store take-bundle" in log and "fabric-secrets sync" in log, log)
            else:
                ok("local: ssh never called", not read(ssh_log), read(ssh_log))
            rc, out = seq_run(backend, "seq-login", "backend-dev", "--project", "demo")
            ok("a second run skips every step already true",
               "1. account seq-login exists" in out and f"2. claude {pin} present" in out and "OpenRouter key: 1 present" in out
               and not has(r"^useradd", read(calls)) and not has(r"^usermod --add-subuids", read(calls))
               and "subuid/subgid: 524288:65536" in out, out)
            if backend == "local":
                # Step 4: a fabric clone already there is brought to
                # origin/main, never left old (bootstrap and the launcher run
                # from it), and one off main is refused rather than moved.
                sh("git", "-C", src, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit",
                   "-q", "--allow-empty", "-m", "newer")
                sh("git", "-C", src, "push", "-q", bare, "HEAD:main")
                rc, out = seq_run(backend, "seq-login", "backend-dev", "--project", "demo")
                ok("an account's fabric clone behind origin/main is fast-forwarded, and that is said",
                   rc == 0 and git_out("-C", f"{h}/projects/agent-fabric", "rev-parse", "HEAD")
                   == git_out("--git-dir", bare, "rev-parse", "main") and "4. ~/projects/agent-fabric at origin/main" in out,
                   f"rc={rc}\n{out}")
                sh("git", "-C", f"{h}/projects/agent-fabric", "checkout", "-q", "-b", "elsewhere")
                rc, out = seq_run(backend, "seq-login", "backend-dev", "--project", "demo")
                ok("…and one off main is refused, named, nothing after it",
                   rc == 1 and "agent-fabric is on elsewhere, not main" in out and "7. bootstrap run" not in out,
                   f"rc={rc}\n{out}")
                sh("git", "-C", f"{h}/projects/agent-fabric", "checkout", "-q", "main")
                # On main but ahead: pull --ff-only exits 0 there, so only a
                # count of what origin/main lacks refuses it (review of #80).
                sh("git", "-C", f"{h}/projects/agent-fabric", "-c", "user.name=t", "-c", "user.email=t@t", "-c",
                   "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "local")
                rc, out = seq_run(backend, "seq-login", "backend-dev", "--project", "demo")
                ok("…and one with local commits is refused, counted, nothing after it",
                   rc == 1 and "agent-fabric has 1 commit(s) not on origin/main" in out and "7. bootstrap run" not in out,
                   f"rc={rc}\n{out}")
                sh("git", "-C", f"{h}/projects/agent-fabric", "reset", "-q", "--hard", "origin/main")

            for fault_name in ("useradd", "git", "store-enroll", "provision share", "provision issue-key", "store assign",
                               "child-bundle", "account-sync", "account-token", "curl"):
                reset_seq()
                put(fault, fault_name + "\n")
                rc, out = seq_run(backend, "seq-login", "backend-dev", "--project", "demo")
                ok(f"a failed '{fault_name}' stops the script, named, before the closing list",
                   rc == 1 and "step failed" in out and "new-agent: done" not in out, f"rc={rc}\n{out}")
                c = read(calls)
                if fault_name == "useradd":
                    ok("…and nothing after useradd ran", not os.path.isdir(h) and not has(r"^(curl|store-enroll)", c), c)
                elif fault_name == "curl":
                    ok("…and nothing after the installer ran", not has(r"^(store-enroll|ssh-keyscan)", c), c)
                elif fault_name == "store-enroll":
                    ok("…and no clone, nothing provisioned after a failed enrolment",
                       not has(r"^secrets provision", c) and not os.path.isdir(f"{h}/projects/demo"), c)
                elif fault_name == "provision share":
                    ok("…and no key minted, no clone after a failed share",
                       not has(r"^secrets provision issue-key", c) and not os.path.isdir(f"{h}/projects/demo"), c)
                elif fault_name == "provision issue-key":
                    ok("…and no clone after a failed key", not os.path.isdir(f"{h}/projects/demo"), c)
                elif fault_name == "child-bundle":
                    ok("…and no sync, no clone after a failed hand-over",
                       "its store did not reach seq-login as a bundle" in out
                       and not has(r"^sync", read(f"{seq}/account-calls")) and not os.path.isdir(f"{h}/projects/demo"),
                       out + read(f"{seq}/account-calls"))
                elif fault_name == "store assign":
                    ok("…named with the store's reason, and no hand-over, no clone after a failed assignment",
                       "fabric-secrets store assign acct-one seq-login: injected" in out
                       and "secret_store child-bundle" not in c and not os.path.isdir(f"{h}/projects/demo"), out + c)
                elif fault_name == "account-token":
                    ok("…an applied token other than the template's fails the verification, by fingerprint only",
                       f"CLAUDE_CODE_OAUTH_TOKEN not applied (expected {FP}; token " in out
                       and "is NOT applied" in out and "other-token" not in out and TOKEN not in out, out)
                elif fault_name == "account-sync":
                    ok("…and a sync that exits 3 is named with its code, no clone after it",
                       "fabric-secrets sync as seq-login (exit 3)" in out and not os.path.isdir(f"{h}/projects/demo"), out)
                os.remove(fault)
                rc, out = seq_run(backend, "seq-login", "backend-dev", "--project", "demo")
                ok(f"…and the re-run after '{fault_name}' converges",
                   rc == 0 and os.path.isdir(f"{h}/projects/demo/node_modules"), f"rc={rc}\n{out}\n{read(calls)}")

        # ---- a human login (ADR-044): the account, its key, store and relay
        # credential, its fabric clone; nothing of a session, on both backends.
        rc, out = run("human-here", "--human", "--dry-run")
        ok("a human's dry run: the account and the fabric clone, no installer, no bootstrap, no role",
           rc == 0 and "useradd" in out and "git clone -q 'https://github.com/gzapi-org/agent-fabric.git'" in out
           and "install.sh" not in out and "bootstrap.sh" not in out and "fabric-role bind" not in out
           and "8. role" not in out, f"rc={rc}\n{out}")
        rc, out = run("human-here", "backend-dev", "--no-claude-account", "--dry-run")
        ok("an agent's run on a login placed as a human is refused", rc == 1 and "human-here is a human login" in out, out)
        rc, out = run("zz-fixture-login", "--human", "--dry-run")
        ok("--human for a login not placed as one is refused, nothing made",
           rc == 1 and "is not placed as a human" in out and "useradd" not in out, out)
        for backend, login in (("local", "human-here"), ("ssh", "human-far")):
            print(f"new-agent: a human login on the {backend} backend")
            put(ssh_log, "")
            reset_seq()
            hh = f"{homes}/{login}"
            rc, out = seq_run(backend, login, "--human")
            c, acc = read(calls), lines(f"{seq}/account-calls")
            ok("the whole sequence exits 0, said as a human's", rc == 0 and "a human (ADR-044)" in out
               and "10. verification" in out and "new-agent: done." in out, f"rc={rc}\n{out}")
            ok("…the account made, its fabric cloned; no claude, ori, ~/.claude, ~/.ssh or ~/.config/gh",
               has(rf"^useradd {login}$", c) and os.path.isdir(f"{hh}/projects/agent-fabric/.git")
               and not os.path.exists(f"{hh}/.local/bin/claude") and not os.path.exists(f"{hh}/.local/bin/ori")
               and not os.path.exists(f"{hh}/.claude") and not os.path.exists(f"{hh}/.ssh") and not os.path.exists(f"{hh}/.config/gh")
               and not has(r"^curl", c), f"{out}\n{c}")
            ok("…its key and store: identity and the relay credential only, no template, assignment or issued key",
               has(rf"^store-enroll {login} --host", c) and has(rf"^secrets provision identity {login} --host", c)
               and has(rf"^secrets provision share {login} --name CLAUDE_BRIDGE_AUTH_TOKEN$", c)
               and not has(r"^secrets (provision issue-key|store templates|store assign)", c), c)
            ok("…its store handed over and synced as itself, its inbox caught up on the fleet's channel",
               acc[:3] == ["store take-bundle", "sync --quiet --no-pull", "relay_catchup agent-fabric"], "\n".join(acc))
            ok("…no bootstrap, no role bound, no toolchain; verified as a human, its person's list named",
               "7. bootstrap run" not in out and "8. role" not in out and "9. " not in out
               and "nothing of a session" in out and "status" in acc and "Fleet Deck, run as " + login in out
               and "moveto's sudo grant" in out, out)
            if backend == "ssh":
                log = read(ssh_log)
                ok("ssh: prepare and finish went to the far host's worker with --human",
                   f"new-agent-worker.sh prepare {login} --human" in log and f"new-agent-worker.sh finish {login} --human" in log,
                   log)
            rc, out = seq_run(backend, login, "--human")
            ok("a second run converges", rc == 0 and f"1. account {login} exists" in out and not has(r"^useradd", read(calls)),
               f"rc={rc}\n{out}")
            os.makedirs(f"{hh}/.claude/agents")
            rc, out = seq_run(backend, login, "--human")
            ok("…and a human holding an agent's files fails its verification, naming them",
               rc == 1 and "a session's pieces" in out and ".claude/agents" in out and "NOT done" in out, f"rc={rc}\n{out}")
            shutil.rmtree(f"{hh}/.claude")
            put(fault, "provision share\n")
            rc, out = seq_run(backend, login, "--human")
            ok("…a failed share stops it before the hand-over, named", rc == 1 and "step failed" in out
               and "new-agent: done" not in out, f"rc={rc}\n{out}")
            os.remove(fault)

    print(f"\ntest_new_agent_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
