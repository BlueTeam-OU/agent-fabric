#!/usr/bin/env python3
"""tools/fabric/store_enroll.py — give an account its own key and its own
encrypted store (agent-fabric ADR-038), run by its PARENT, the
fabric-coordinator login that provisioned it (ADR-040 Wave 5;
runtime/provisioning/secrets/store-enroll.sh is its shim, and new-agent.sh
and the README keep that path).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      <login>... [--host <id> | --host=<id>] [--born-now] [--dry-run],
            or --self, or --rename <old> <new>; flags anywhere, in any
            order. -h/--help prints HELP (below) on stdout, exit 0. No
            login and no --self/--rename: HELP on stderr, exit 2. An
            unknown flag: exit 2. --self with a login, --rename without
            exactly two: exit 1.
  stdin     never read.
  env       AGENT_FABRIC_HOSTS_REGISTRY (default runtime/hosts/registry.json),
            AGENT_FABRIC_HOSTEXEC (default runtime/hostexec/hostexec),
            AGENT_FABRIC_SECRETS_ORG (default gzapi-org),
            AGENT_FABRIC_SECRETS_REMOTE_BASE (replaces git@github.com:<org>),
            GH (default gh), HOME (the mirror's parent); everything else
            is passed to the store tool and the host executor as found.
  stdout    HELP for --help; nothing else of its own. The store tool's and
            git's output is sent to stderr, as the bash's `>&2` did.
  stderr    `store-enroll: …` lines: a refusal, a step that failed, each
            account's result, and the closing "commit identities/keys/".
  exit      0 when every login was enrolled (or --self, --rename, a dry
            run); 1 when any login failed (the others still run), or on a
            refusal; 2 for usage.

Deliberate differences from the bash, where it printed a traceback or
could hang: --host without a value is one line and exit 1 (bash: "unbound
variable"); a hosts registry that cannot be read is one line, then the
login is "not placed", as before; every subprocess is bounded
(STEP_TIMEOUT_S), and one that runs out is that step's failure. Helpers
run on this interpreter (the fleet's pin), where the bash ran PATH's python3.

No step needs the parent and the child on one host, and no value crosses
between them: only a public key and ciphertext do.
"""
from __future__ import annotations

import json
import os
import pwd
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import roots  # noqa: E402
STORE = os.path.join(HERE, "secret_store.py")
# The account's own fabric checkout, relative to ITS home (the worker
# starts there); the parent's checkout is not readable to it.
ACCOUNT_SECRETS = "projects/agent-fabric/bin/fabric-secrets"
# A store operation as the account can cross a host (ssh), sign with gpg
# and push; none is expected near this, and a hung one must not hold every
# other login of the run.
STEP_TIMEOUT_S = 900
STDERR_FD = 2
AGENT_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")

HELP = """\
runtime/provisioning/secrets/store-enroll.sh — give an account its own
key and its own encrypted store (agent-fabric ADR-038). Run by its
PARENT, the fabric-coordinator login that provisioned it, from the
parent's own checkout.

  store-enroll.sh <login>... [--host <id>] [--born-now] [--dry-run]
  store-enroll.sh --self                    the parent's own key and store,
                                            recorded as the root of the chain
  store-enroll.sh --rename <old> <new>      a login renamed: its lineage entry's
                                            login and its repository's description

Commands take logins; each resolves the login to the agent's id first,
and what is stored (repository, files, folders) is named by that id
(ADR-039). The repository's description carries both.

For each login, idempotently:
  0. its agent id (ADR-039): the one lineage.json already records for
     the login, else the one its own store already holds (a run that
     stopped before certification), else minted here — a UUIDv7 whose time is the account's
     birth: its home directory's creation time, or with --born-now (a
     new account, new-agent.sh) this moment;
  1. the private repository <org>/agent-fabric-secrets-<id> exists (the
     parent's gh; AGENT_FABRIC_SECRETS_ORG, default the fabric's own org);
  2. AS THE ACCOUNT, on the host it is placed on (runtime/hosts/registry.json,
     reached through runtime/hostexec/hostexec — directly, or over ssh):
     its key and store (`fabric-secrets store init --agent-id --remote`),
     pushed — with --born-now handed to the parent as a bundle and
     pushed by it (`store bundle | store seed-child`), the account having
     no GitHub key yet; its PUBLIC key exported to the parent;
"""




class Usage(Exception):
    """Exit 2 with a message (or with HELP on stderr when it has none)."""


class Refused(Exception):
    """`store-enroll: <message>`, exit 1, nothing further."""


def say(msg: str) -> None:
    print(f"store-enroll: {msg}", file=sys.stderr, flush=True)


def die(msg: str) -> "NoReturn":  # noqa: F821
    raise Refused(msg)


def run(cmd: list[str], *, capture: bool = False, quiet: bool = False, merge: bool = False,
        stdin=subprocess.DEVNULL) -> tuple[int, str]:
    """A step: its status and, when captured, its stdout with the trailing
    newlines a command substitution drops. Uncaptured stdout goes to file
    descriptor 2, as `>&2` sent it; quiet drops stderr, merge captures it
    too."""
    sys.stderr.flush()
    try:
        r = subprocess.run(cmd, stdin=stdin, stdout=subprocess.PIPE if capture else STDERR_FD,
                           stderr=subprocess.STDOUT if merge else (subprocess.DEVNULL if quiet else None),
                           text=True, errors="surrogateescape", timeout=STEP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        say(f"{os.path.basename(cmd[0])} {cmd[1] if len(cmd) > 1 else ''}: no answer within {STEP_TIMEOUT_S} s")
        return 124, ""
    except OSError as exc:
        say(f"{cmd[0]}: {exc.strerror or exc}")
        return 127, ""
    return r.returncode, (r.stdout or "").rstrip("\n") if capture else ""


def store(*args: str, **kw) -> tuple[int, str]:
    return run([sys.executable, STORE, *args], **kw)


class Enrol:
    def __init__(self, *, dry: bool, born_now: bool, host_flag: str):
        env = os.environ
        self.dry, self.born_now, self.host_flag = dry, born_now, host_flag
        self.hosts = roots.hosts_registry(environ=env)
        self.hx = env.get("AGENT_FABRIC_HOSTEXEC") or os.path.join(ROOT, "runtime", "hostexec", "hostexec")
        self.org = env.get("AGENT_FABRIC_SECRETS_ORG") or "gzapi-org"
        self.gh = env.get("GH") or "gh"
        self.me = pwd.getpwuid(os.getuid()).pw_name

    # The base is the org on GitHub over SSH: the accounts' project
    # checkouts are git@github.com (the fabric's own is https, being public),
    # and no account has an HTTPS credential helper — an https remote to a
    # private repository could not push. Read back on the coordinator's own
    # enrolment: the push over SSH to its new private repository worked. AGENT_FABRIC_SECRETS_REMOTE_BASE replaces
    # the base (the test's bare repositories).
    def repo_url(self, aid: str) -> str:
        base = os.environ.get("AGENT_FABRIC_SECRETS_REMOTE_BASE") or f"git@github.com:{self.org}"
        return f"{base}/agent-fabric-secrets-{aid}.git"

    @staticmethod
    def describe(login: str, aid: str) -> str:
        return f"agent-fabric secrets. Linux login: {login}. Agent id: {aid}. (ADR-038, ADR-039)"

    def ensure_repo(self, aid: str, login: str) -> None:
        """The private repository, made by the parent when absent."""
        name = f"{self.org}/agent-fabric-secrets-{aid}"
        if run([self.gh, "repo", "view", name], capture=True, quiet=True)[0] == 0:
            return
        if self.dry:
            say(f"would: gh repo create {name} --private")
            return
        if run([self.gh, "repo", "create", name, "--private", "--description", self.describe(login, aid)],
               capture=True)[0] != 0:
            die(f"could not create {name} (the parent's gh must be able to create a private repository in {self.org})")

    def id_of(self, login: str) -> str | None:
        """The id lineage.json records for a login, "" when it records no
        agent with that login (the store tool's exit 3), None on any other
        failure — a lineage that cannot be read must not read as "no agent"
        and mint a second id."""
        rc, out = store("id-of", login, capture=True, merge=True)
        if rc == 0:
            return out
        if rc == 3:
            return ""
        say(f"{login}: identities/keys/lineage.json could not be read (exit {rc}): {out.rsplit(chr(10), 1)[-1]}; "
            "nothing made")
        return None

    def mint(self, born: str) -> str | None:
        rc, out = store("mint-id", born, capture=True)
        return out if rc == 0 else None

    def host_of(self, login: str) -> str:
        if self.host_flag:
            return self.host_flag
        try:
            with open(self.hosts, encoding="utf-8") as fh:
                return str((json.load(fh).get("placement") or {}).get(login, ""))
        except (OSError, ValueError, AttributeError) as exc:
            say(f"{self.hosts}: {exc}")
            return ""

    def as_login(self, login: str, *cmd: str) -> list[str]:
        return [self.hx, self.host_of(login), "--as", login, "--", *cmd]

    # ── the three commands ───────────────────────────────────────────
    def rename(self, old: str, new: str) -> int:
        aid = self.id_of(old)
        if aid is None:
            return 1
        if not aid:
            die(f"{old}: no agent with that login in identities/keys/lineage.json")
        if self.dry:
            say(f"would: agent {aid}: login {old} -> {new} in lineage.json and its repository's description")
            return 0
        if store("rename", old, new)[0] != 0:
            die("rename failed")
        if run([self.gh, "repo", "edit", f"{self.org}/agent-fabric-secrets-{aid}", "--description",
                self.describe(new, aid)], capture=True)[0] != 0:
            die(f"agent {aid}: the lineage says {new}; its repository's description still names {old} "
                "(re-run gh repo edit, nothing else)")
        say(f"agent {aid} is now {new}; nothing stored moves. Commit identities/keys/; the Linux account, its runtime "
            "state and its relay address are renamed on its host.")
        return 0

    def birth(self, home_stat: list[str]) -> str:
        if self.born_now:
            return "now"
        return run(home_stat, capture=True)[1]

    def self_enrol(self) -> int:
        # As for a child: only "no id yet" (exit 3) may lead to minting.
        idrc, aid = store("id", capture=True, quiet=True)
        if idrc not in (0, 3):
            die(f"this store's agent id could not be read (exit {idrc}); nothing made")
        if not aid:
            aid = self.id_of(self.me)
            if aid is None:
                return 1
        if not aid:
            born = self.birth(["stat", "-c", "%w", os.environ.get("HOME", "")])
            aid = self.mint(born)
            if aid is None:
                die(f"no birth for {self.me}: its home's creation time is unknown here ({born})")
        self.ensure_repo(aid, self.me)
        if self.dry:
            say(f"would: init my store as agent {aid}, push it, certify --root")
            return 0
        if store("init", "--agent-id", aid, "--remote", self.repo_url(aid))[0] != 0:
            die("init failed")
        if store("push")[0] != 0:
            die("push failed")
        if store("certify", "--root")[0] != 0:
            die("certify --root failed")
        say(f"{self.me}: agent {aid}, the root of the chain, is recorded; commit identities/keys/, then fabric-secrets "
            "store recovery-copy and store backup")
        return 0

    def enrol(self, logins: list[str]) -> int:
        if store("export-key", capture=True, quiet=True)[0] != 0:
            die("this login has no store yet: store-enroll.sh --self first (the parent certifies with its own key)")
        fail = 0
        for login in logins:
            fail |= not self.enrol_one(login)
        if not self.dry:
            say("commit identities/keys/ (the certified keys and lineage.json)")
        return fail

    def enrol_one(self, login: str) -> bool:
        if login == self.me:
            say(f"{login}: that is this login; use --self")
            return False
        host = self.host_of(login)
        if not host:
            say(f"{login}: not placed in runtime/hosts/registry.json (or name --host)")
            return False
        aid = self.id_of(login)
        if aid is None:
            return False
        # A run that stopped after init and before certification left the id in
        # the account's store: minting again would be refused there forever.
        if not aid:
            # Only "no id yet" (exit 3) lets the parent mint: any other failure to
            # read the account's store would mint an id its store then refuses,
            # after a repository had been made for it.
            idrc, aid = run(self.as_login(login, ACCOUNT_SECRETS, "store", "id"), capture=True, quiet=True)
            if idrc not in (0, 3):
                say(f"{login}: its store's agent id could not be read on {host} (exit {idrc}); nothing made")
                return False
            if idrc == 3:
                aid = ""
        # Read back from another host: only an id, or it names a repository.
        if aid and not AGENT_ID.fullmatch(aid):
            say(f"{login}: its store answered an agent id that is not one: {aid[:60]}")
            return False
        if not aid:
            born = self.birth(self.as_login(login, "sh", "-c", 'stat -c %w "$HOME"'))
            aid = self.mint(born)
            if aid is None:
                say(f"{login}: no birth: its home's creation time is unknown on {host} ({born})")
                return False
        self.ensure_repo(aid, login)
        url = self.repo_url(aid)
        if self.dry:
            say(f"would: on {host} as {login}: store init --agent-id {aid} --remote {url}, push, export-key; certify; mirror")
            return True
        if run(self.as_login(login, ACCOUNT_SECRETS, "store", "init", "--agent-id", aid, "--remote", url))[0] != 0:
            say(f"{login}: init failed on {host}")
            return False
        if self.born_now:
            # A new account has no GitHub key yet (it comes from this store), so
            # its first commit reaches its repository through its parent: an
            # armored bundle of ciphertext, pushed with the parent's own access.
            if not self.seed(login, aid, url):
                say(f"{login}: its first commit did not reach its repository through this login")
                return False
        elif run(self.as_login(login, ACCOUNT_SECRETS, "store", "push"))[0] != 0:
            say(f"{login}: push failed")
            return False
        rc, pub = run(self.as_login(login, ACCOUNT_SECRETS, "store", "export-key"), capture=True)
        if rc != 0 or "BEGIN PGP PUBLIC KEY BLOCK" not in pub:
            say(f"{login}: its public key did not come back")
            return False
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", errors="surrogateescape", suffix=".asc") as fh:
            fh.write(pub + "\n")
            fh.flush()
            if store("certify", login, fh.name)[0] != 0:
                say(f"{login}: certification failed")
                return False
        if not self.mirror(login, aid, url):
            return False
        say(f"{login}: agent {aid}, key certified, store at {url}, mirrored; its recovery copy: bin/fabric-host {host} "
            f"run --as {login} -- {ACCOUNT_SECRETS} store recovery-copy")
        return True

    def seed(self, login: str, aid: str, url: str) -> bool:
        """`store bundle | store seed-child`: the pipeline fails when
        either side does, as under pipefail."""
        sys.stderr.flush()
        try:
            bundle = subprocess.Popen(self.as_login(login, ACCOUNT_SECRETS, "store", "bundle"),
                                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
        except OSError as exc:
            say(f"{self.hx}: {exc.strerror or exc}")
            return False
        try:
            seeded = subprocess.run([sys.executable, STORE, "seed-child", aid, "--remote", url], stdin=bundle.stdout,
                                    stdout=STDERR_FD, timeout=STEP_TIMEOUT_S).returncode
            bundled = bundle.wait(timeout=STEP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            bundle.kill()
            bundle.wait()
            say(f"{login}: the bundle and its push took more than {STEP_TIMEOUT_S} s")
            return False
        finally:
            bundle.stdout.close()
        return seeded == 0 and bundled == 0

    def mirror(self, login: str, aid: str, url: str) -> bool:
        """The parent's mirror of the child's store, made and moved only
        through secret_store.py (ADR-042, the coordinator's ruling of
        2026-10-04): made from the account's own bundle (bundle |
        seed-child, which records its first contact as the mirror's
        trusted base and verifies the rest), brought up by the verified
        fetch on a re-run. Never a raw clone or pull: a clone is a fetch,
        which sets no base, and a pull takes commits unverified."""
        mirror = os.path.join(os.environ.get("HOME", ""), ".local", "share", "agent-fabric", "children", aid)
        if not os.path.isdir(os.path.join(mirror, ".git")):
            if not self.seed(login, aid, url):
                say(f"{login}: its mirror could not be made from its bundle")
                return False
            return True
        if store("refresh-mirror", aid)[0] != 0:
            say(f"{login}: its mirror could not be brought up to date")
            return False
        return True

def parse(argv: list[str]) -> tuple[dict, list[str]]:
    opts = {"dry": False, "self": False, "rename": False, "born_now": False, "host": "", "help": False}
    logins, it = [], iter(argv)
    for a in it:
        if a == "--host":
            value = next(it, None)
            if value is None:
                raise Refused("--host needs a host id")
            opts["host"] = value
        elif a.startswith("--host="):
            opts["host"] = a[len("--host="):]
        elif a == "--dry-run":
            opts["dry"] = True
        elif a == "--self":
            opts["self"] = True
        elif a == "--rename":
            opts["rename"] = True
        elif a == "--born-now":
            opts["born_now"] = True
        elif a in ("-h", "--help"):
            opts["help"] = True
            break
        elif a.startswith("-"):
            raise Usage(f"unknown flag {a}")
        else:
            logins.append(a)
    return opts, logins


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="surrogateescape")
    try:
        opts, logins = parse(argv)
        if opts["help"]:
            sys.stdout.write(HELP)
            return 0
        e = Enrol(dry=opts["dry"], born_now=opts["born_now"], host_flag=opts["host"])
        if opts["rename"]:
            if len(logins) != 2:
                die("--rename takes <old> <new>")
            return e.rename(*logins)
        if opts["self"]:
            if logins:
                die("--self takes no login")
            return e.self_enrol()
        if not logins:
            raise Usage("")
        return e.enrol(logins)
    except Usage as exc:
        if str(exc):
            say(str(exc))
        else:
            sys.stderr.write(HELP)
        return 2
    except Refused as exc:
        say(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
