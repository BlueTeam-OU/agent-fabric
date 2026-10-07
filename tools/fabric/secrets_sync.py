#!/usr/bin/env python3
"""tools/fabric/secrets_sync.py — an identity's secrets, from its own store
(ADR-038), into the places the tools read them. Runs AS THE ACCOUNT, behind
`fabric-secrets sync|status`.

    fabric-secrets sync [--force] [--json] [--quiet] [--no-pull]
                                  pull this login's store, apply it (--quiet:
                                  one line, only when something is missing
                                  or failed; --no-pull: apply it as it is,
                                  once, right after `store take-bundle` — a
                                  new account has no key to pull with yet)
    fabric-secrets status [--json] [--quiet]
                                  what is present, missing, applied; and
                                  each store (its own, each child's mirror)
                                  that refused a commit or has no trusted
                                  base (ADR-042), which is NOT OK (exit 1)

The store is this login's pass-format repository (secret_store.py). sync
writes
    ~/.config/agent-fabric/secrets.env   (0600) — the string secrets, read
                                         from the file by the tools that need
                                         one and never sourced by a shell:
                                         OPENROUTER_API_KEY, GH_TOKEN,
                                         CLAUDE_BRIDGE_AUTH_TOKEN, and the
                                         registry's per-agent names but
                                         STORE_ONLY's, which a tool
                                         decrypts itself when it needs one
    ~/.config/agent-fabric/env.sh        (0600) — only the names the registry
                                         marks `plain_env`: values that are
                                         the login's, not secrets
    ~/.bashrc                            one marked line sourcing env.sh
    gh's own configuration               GH_TOKEN, by `gh auth login
                                         --with-token`, so gh needs nothing
                                         in the environment
    ~/.gitconfig                         user.name/email, signing key and
                                         program (strings; the key material
                                         stays in the keyring)
    ~/.ssh/id_ed25519(.pub)              only when absent; --force replaces
and refuses when the store's AGENT_LOGIN is not this login — location and
configuration never decide who an agent is, the login does.

The contract (ADR-038 §5 rule 7), frozen when this moved from the bash
heredoc and its Doppler reader retired: the exit codes — 0 applied, 1
unreadable, 2 applied with required names missing (or gh refusing
GH_TOKEN), 3 the store names another login and nothing is applied; the JSON report's `error` and
`missing`, which the control agent reads (runtime/control/secrets.mjs);
the `--quiet` line on stderr, which moveto's shell entry shows. status
exits 0 or 1; its JSON lists `refused` and `no_trusted_base` per store
("store": "own" or the child's agent id; a base's "state" is "no base" or
"unreadable", as fabric-ctl keys names it).

Nothing here prints a secret value: names, presence, ages and modes only.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
import pwd
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", ".."))
MARKER = "# agent-fabric secrets"
ENV_NAMES = ["OPENROUTER_API_KEY", "GH_TOKEN", "CLAUDE_BRIDGE_AUTH_TOKEN"]
GIT_NAMES = {"GIT_USER_NAME": "user.name", "GIT_USER_EMAIL": "user.email",
             "GIT_SIGNING_KEY": "user.signingkey", "GIT_GPG_PROGRAM": "gpg.program"}
SSH_NAMES = ["SSH_PRIVATE_KEY", "SSH_PUBLIC_KEY"]
IDENTITY_NAMES = ["AGENT_LOGIN", "AGENT_HOST"]
# Never written into secrets.env, whatever the registry declares: ~/.bashrc
# sourced that file, so an exported name was in every shell and subagent of
# the account, and a reviewer printed its environment with the operator's
# signing key in it (rotated, #95). No shell sources secrets.env any more
# (ADR-038 rule 9), but a file every tool may read is still no place for
# the key that signs fleet actions. fabric-ctl decrypts it from the store
# when it signs (runtime/control/ctl.mjs signingKey()). Known, so a store
# holding it is not "unexpected"; and since the file is rewritten whole,
# the next sync drops a line an older one wrote.
STORE_ONLY = ["FABRIC_CONTROL_SIGNING_KEY"]
ALL_NAMES = IDENTITY_NAMES + ENV_NAMES + list(GIT_NAMES) + SSH_NAMES
USAGE = "usage: fabric-secrets sync [--force] [--json] [--quiet] [--no-pull] | status [--json] | store …"


def login() -> str:
    return pwd.getpwuid(os.getuid()).pw_name


def home() -> str:
    return os.environ.get("HOME") or pwd.getpwuid(os.getuid()).pw_dir


def env_file() -> str:
    return os.path.join(home(), ".config", "agent-fabric", "secrets.env")


def shell_env_file() -> str:
    return os.path.join(home(), ".config", "agent-fabric", "env.sh")


def store_path() -> str:
    return os.environ.get("AGENT_FABRIC_SECRET_STORE") or os.path.join(home(), ".local", "share", "agent-fabric", "secrets")


def project_agent_env(root: str | None = None) -> list[str]:
    """Names the registry declares as per-agent environment — fabric-wide
    (top-level `agent_env`) or per project (`projects.<id>.agent_env`):
    secrets a script reads directly (OPENAI_API_KEY), or values that
    belong to the login rather than to a clone — a project's per-login port
    offset, whose per-clone home (a table keyed by the clone's basename)
    stopped meaning anything once every clone was named after its project.
    Exported when the store has them; their absence is never a missing name."""
    try:
        reg = json.load(open(os.path.join(root or ROOT, "projects", "registry.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    names: list[str] = []
    # Fabric-wide names first (registry top-level agent_env), then each project's.
    for holder in [reg, *((reg.get("projects") or {}).values())]:
        for n in (holder.get("agent_env") or {}):
            if n not in names and n not in ENV_NAMES and n not in STORE_ONLY:
                names.append(n)
    return names


def plain_env_names(root: str | None = None) -> list[str]:
    """The per-agent names the registry marks `plain_env` — fabric-wide or
    per project — the only ones a shell may carry. Everything else synced is
    a secret, read from secrets.env by the tool that needs it: a name nobody
    marked is never exported, so a new secret is safe by default."""
    try:
        reg = json.load(open(os.path.join(root or ROOT, "projects", "registry.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    names: list[str] = []
    for holder in [reg, *((reg.get("projects") or {}).values())]:
        for n in (holder.get("plain_env") or []):
            if n not in names and n not in ENV_NAMES and n not in STORE_ONLY:
                names.append(n)
    return names


def load_store():
    spec = importlib.util.spec_from_file_location("fabric_secret_store", os.path.join(ROOT, "tools", "fabric", "secret_store.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fetch_names() -> tuple[list[str] | None, str | None]:
    try:
        return load_store().names(), None
    except Exception as e:  # noqa: BLE001 — reported as the store's error, never a value
        return None, f"store: {e}"


def fetch_values(pull: bool = True) -> tuple[dict[str, str] | None, str | None]:
    # A pull that fails is an error, not a note: a stale copy would be
    # applied as if it were the store, and the sync would say applied.
    # Skipped only when asked: the copy was just taken from the parent's
    # bundle, and the key to pull with is what this sync writes.
    try:
        st = load_store()
        if pull:
            st.pull()
        return st.values(), None
    except Exception as e:  # noqa: BLE001 — the store's error, never a value
        return None, f"store: {e}"


def fetch_verification() -> tuple[list[dict], list[dict], str | None]:
    """The last refused commit of the own store and of each child's mirror
    (ADR-042 rule 5), and every one of them with no trusted base, each
    named. Either reading that fails is said, never an empty list: status
    read clean whenever it could not look (review of #94)."""
    try:
        st = load_store()
        return st.refusals(), st.bases(), None
    except Exception as e:  # noqa: BLE001 — said as the error; names and paths only, never a value
        return [], [], f"the stores' refusals and trusted bases could not be read: {e}"


def git_get(key: str) -> str:
    r = subprocess.run(["git", "config", "--global", "--get", key], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def git_set(key: str, value: str) -> None:
    subprocess.run(["git", "config", "--global", key, value], check=True)


def write_private(path: str, content: str, mode: int) -> None:
    """Written beside the target and renamed over it. The temporary file is
    made new by mkstemp (O_EXCL, 0600) before a byte of the secret reaches
    it: the fixed `<path>.tmp` this once opened with O_TRUNC followed a
    symlink planted there and kept a looser mode an earlier file had. One
    such file an older sync left is removed, never written through."""
    d = os.path.dirname(path)
    os.makedirs(d, mode=0o700, exist_ok=True)
    with contextlib.suppress(FileNotFoundError):
        os.unlink(path + ".tmp")
    fd, tmp = tempfile.mkstemp(dir=d, prefix=f".{os.path.basename(path)}.")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
            os.fchmod(fh.fileno(), mode)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def file_mode(path: str) -> int | None:
    try:
        return stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        return None


def bashrc() -> str:
    return os.path.join(home(), ".bashrc")


def bashrc_marked_lines() -> list[str]:
    try:
        return [line.rstrip("\n") for line in open(bashrc(), encoding="utf-8") if MARKER in line]
    except FileNotFoundError:
        return []


def source_line() -> str:
    f = shlex.quote(shell_env_file())
    return f"[ -r {f} ] && . {f}  {MARKER}"


def bashrc_sources(which: str) -> bool:
    """Whether a marked ~/.bashrc line sources `which` (a path)."""
    return any(which in line or shlex.quote(which) in line for line in bashrc_marked_lines())


def settle_bashrc() -> str | None:
    """Exactly one marked line, sourcing env.sh. A line an older sync wrote
    sources secrets.env, and every shell, session and subagent of the
    account then held every secret (ADR-038 rule 9): it is replaced in
    place, the rest of the file kept byte for byte and its mode kept.
    Returns what was done, or None when the file was already right."""
    want = source_line()
    # Through a symlink to its target: a dotfiles-managed ~/.bashrc replaced
    # by a regular file would leave the target, still sourcing secrets.env,
    # for anything that reads it directly.
    path = os.path.realpath(bashrc())
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
        mode = file_mode(path)
    except FileNotFoundError:
        lines, mode = [], None
    marked = [i for i, line in enumerate(lines) if MARKER in line]
    if [lines[i] for i in marked] == [want]:
        return None
    if marked:
        lines[marked[0]] = want
        lines = [line for i, line in enumerate(lines) if i not in marked[1:]]
        done = "bashrc (now sources env.sh, not secrets.env)"
    else:
        lines += [want, ""] if lines and lines[-1] == "" else ["", want, ""]
        done = "bashrc"
    write_private(path, "\n".join(lines), mode if mode is not None else 0o644)
    return done


# gh reads GH_TOKEN from the environment first and its own configuration
# second; the token goes to the second, so no shell needs the first. The
# binary is AGENT_FABRIC_GH where a test points it at a fake: a sync in a
# sandbox HOME must never sign the real gh in, nor reach the network.
GH_ENV_TOKENS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
GH_TIMEOUT_S = 60


def gh_binary() -> str | None:
    """A sandbox HOME (a test, a probe) never reaches the login's real gh:
    gh follows XDG_CONFIG_HOME and the keyring, not HOME, and a test once
    read the runner's token and tried a network login with a fixture."""
    if os.environ.get("AGENT_FABRIC_GH"):
        return os.environ["AGENT_FABRIC_GH"]
    if os.path.realpath(home()) != os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir):
        return None
    return shutil.which("gh")


def _gh(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess | None:
    gh = gh_binary()
    if not gh:
        return None
    # gh's own resolution of its configuration (GH_CONFIG_DIR, then
    # XDG_CONFIG_HOME, then ~/.config) is the one the account's shells use.
    # A sandbox HOME gets here only when AGENT_FABRIC_GH names a fake
    # (gh_binary), and that caller clears GH_CONFIG_DIR and XDG_CONFIG_HOME
    # itself, or the fake writes where they point.
    env = {k: v for k, v in os.environ.items() if k not in GH_ENV_TOKENS}
    try:
        return subprocess.run([gh, *args], input=stdin if stdin is not None else "", env=env, capture_output=True,
                              text=True, timeout=GH_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return None


def gh_token_matches(token: str | None = None) -> bool | None:
    """Whether gh's own configuration holds a token for github.com (and,
    given one, that token). Compared in this process; never printed. None:
    no gh to ask."""
    r = _gh(["auth", "token", "--hostname", "github.com"])
    if r is None:
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return False
    return token is None or r.stdout.strip() == token.strip()


def apply_gh_token(token: str) -> str:
    """'unchanged', 'applied', or why not — never the token."""
    if gh_token_matches(token):
        return "unchanged"
    if gh_binary() is None:
        return "no gh (not on PATH, or a sandbox HOME)"
    r = _gh(["auth", "login", "--hostname", "github.com", "--with-token", "--insecure-storage"], stdin=token.strip() + "\n")
    if r is None:
        return f"gh auth login did not finish within {GH_TIMEOUT_S} s"
    if r.returncode != 0:
        return f"gh auth login exit {r.returncode}"
    return "applied" if gh_token_matches(token) else "gh auth login reported success, but gh holds another token"


def ssh_key() -> str:
    return os.path.join(home(), ".ssh", "id_ed25519")


def local_state() -> dict:
    f = env_file()
    mode = file_mode(f)
    age = int(time.time() - os.stat(f).st_mtime) if mode is not None else None
    exported = []
    if mode is not None:
        for line in open(f, encoding="utf-8"):
            if line.startswith("export ") and "=" in line:
                exported.append(line[len("export "):].split("=", 1)[0])
    return {
        "env_file": f, "env_file_mode": (f"{mode:04o}" if mode is not None else None),
        "env_file_age_seconds": age, "env_file_exports": exported,
        "bashrc_sources_shell_env": bashrc_sources(shell_env_file()),
        "bashrc_sources_secrets": bashrc_sources(f),
        "gh_has_token": gh_token_matches(),
        "ssh_key_present": os.path.exists(ssh_key()),
        "git": {key: bool(git_get(key)) for key in GIT_NAMES.values()},
        "commit_gpgsign": git_get("commit.gpgsign") == "true",
    }


def values_digest(values: dict[str, str], known: list[str]) -> str:
    """sha256 over every name sync applies and its value, in a canonical
    form, the SSH key and the git strings included, which secrets.env does
    not carry: two syncs applied the same values when it is equal. Only
    the hash is printed. STORE_ONLY is known but never applied, so not in
    it (review of #96)."""
    applied = {n: values[n] for n in known if n in values and n not in STORE_ONLY}
    return hashlib.sha256(json.dumps(applied, sort_keys=True).encode()).hexdigest()


def _refused_line(r: dict) -> str:
    which = "the store" if r.get("store") == "own" else f"the mirror of agent {r.get('store')}"
    who = "the store's parent or the owner" if r.get("store") == "own" else "this account, the child's parent, or the owner"
    if r.get("unreadable"):
        return (f"REFUSAL UNREADABLE: {which}: {r.get('reason', '?')} — a refusal may stand; {who} looks at it "
                "(ADR-042)")
    return (f"REFUSED: {which} refused commit {str(r.get('commit', '?'))[:12]} at {r.get('at', '?')}: "
            f"{r.get('reason', '?')} — {who} repairs it (ADR-042)")


def _base_line(b: dict) -> str:
    """A store with no trusted base refuses every verified operation, so it
    is said as a refusal is, with its repair (the coordinator's ruling of
    2026-10-04): the own store's base is its head, once; a mirror's history
    came from the child's remote, so its base is set with the owner."""
    own = b.get("store") == "own"
    which = "the store" if own else f"the mirror of agent {b.get('store')}"
    if b.get("state") == "unreadable":
        who = "this account" if own else "this account, the child's parent, or the owner"
        return f"BASE UNREADABLE: {which}: {b.get('reason', '?')} — its trusted base cannot be read; {who} looks at it (ADR-042)"
    if own:
        return (f"NO BASE: {which} has no trusted base, so it takes nothing in — "
                "fabric-secrets store trust-base, once, at the head it holds (ADR-042)")
    return (f"NO BASE: {which} has no trusted base, so it takes nothing in — "
            f"fabric-secrets store trust-base --store {b.get('path', '?')}, with the owner where its history "
            "cannot be verified (ADR-042)")


def _verification_lines(obj: dict) -> list[str]:
    return [_refused_line(r) for r in obj.get("refused") or []] + \
        [_base_line(b) for b in obj.get("no_trusted_base") or []]


def report(obj: dict, as_json: bool, quiet: bool, ok: bool) -> None:
    if quiet:
        # For a shell entry (moveto): silence when all is well, one line otherwise.
        if not ok:
            said = _verification_lines(obj)
            what = obj.get("error") or ("; ".join(said) if said else
                                        f"missing in the store: {', '.join(obj.get('missing', []))}")
            print(f"fabric-secrets: {what}", file=sys.stderr)
        return
    if as_json:
        print(json.dumps(obj, indent=2, sort_keys=True))
        return
    print(f"fabric-secrets: login={obj['login']} store={obj['store']}")
    if obj.get("error"):
        print(f"  error: {obj['error']}")
    for line in _verification_lines(obj):
        print(f"  {line}")
    if "present" in obj:
        print(f"  present: {', '.join(obj['present']) or '(none)'}")
        print(f"  missing: {', '.join(obj['missing']) or '(none)'}")
    if "applied" in obj:
        print(f"  applied: {', '.join(obj['applied']) or '(none)'}")
        if obj.get("skipped"):
            print(f"  skipped: {', '.join(obj['skipped'])}")
    ls = obj["local"]
    env = f"{ls['env_file']} mode={ls['env_file_mode']} age={ls['env_file_age_seconds']}s exports={','.join(ls['env_file_exports'])}" \
        if ls["env_file_mode"] else f"{ls['env_file']} (absent)"
    print(f"  env file: {env}")
    if ls["bashrc_sources_secrets"]:
        print("  ~/.bashrc SOURCES secrets.env: every shell holds every secret — fabric-secrets sync replaces the line")
    print(f"  bashrc sources env.sh: {ls['bashrc_sources_shell_env']}   gh has a token: {ls['gh_has_token']}   ssh key: {ls['ssh_key_present']}   "
          f"git: {', '.join(k for k, v in ls['git'].items() if v) or '(unset)'}   commit.gpgsign: {ls['commit_gpgsign']}")
    print("  " + ("OK" if ok else "NOT OK"))


def status(as_json: bool, quiet: bool = False) -> int:
    optional = project_agent_env()
    known = ALL_NAMES + optional + STORE_ONLY
    obj = {"login": login(), "source": "store", "store": store_path(), "local": local_state()}
    names, err = fetch_names()
    ok = True
    if err:
        obj["error"] = err
        ok = False
    else:
        obj["present"] = [n for n in ALL_NAMES if n in names]
        obj["missing"] = [n for n in ALL_NAMES if n not in names]
        obj["optional"] = [n for n in optional if n in names]
        obj["unexpected"] = sorted(n for n in names if n not in known)
        ok = not obj["missing"]
    # A refused commit is a security event (ADR-042 rule 5): said here until
    # the store is repaired, whatever else is well. So is a store with no
    # trusted base, which refuses everything it is given; and so is not
    # being able to tell.
    refused, unbased, verr = fetch_verification()
    if refused:
        obj["refused"] = refused
        ok = False
    if unbased:
        obj["no_trusted_base"] = unbased
        ok = False
    if verr:
        obj["error"] = f"{obj['error']}; {verr}" if obj.get("error") else verr
        ok = False
    ls = obj["local"]
    ok = ok and ls["env_file_mode"] == "0600" and ls["bashrc_sources_shell_env"] and not ls["bashrc_sources_secrets"] \
        and (ls["gh_has_token"] is not False or "GH_TOKEN" not in obj.get("present", []))
    report(obj, as_json, quiet, ok)
    return 0 if ok else 1


def sync(force: bool, as_json: bool, quiet: bool = False, pull: bool = True) -> int:
    me = login()
    optional = project_agent_env()
    known = ALL_NAMES + optional + STORE_ONLY
    obj = {"login": me, "source": "store", "store": store_path(), "applied": [], "skipped": []}
    values, err = fetch_values(pull)
    if err:
        obj["error"] = err
        obj["local"] = local_state()
        report(obj, as_json, quiet, False)
        return 1
    obj["present"] = [n for n in ALL_NAMES if n in values]
    obj["missing"] = [n for n in ALL_NAMES if n not in values]
    obj["optional"] = [n for n in optional if n in values]
    obj["unexpected"] = sorted(n for n in values if n not in known)
    obj["values_sha256"] = values_digest(values, known)
    # The invariant, enforced: a store that does not name this login is
    # someone else's, whatever key opened it.
    if values.get("AGENT_LOGIN") != me:
        obj["error"] = (f"the store names AGENT_LOGIN={values.get('AGENT_LOGIN') or '(unset)'}, "
                        f"this login is {me}; nothing applied")
        obj["local"] = local_state()
        report(obj, as_json, quiet, False)
        return 3
    # 1. the env files: secrets.env holds every string a tool reads; env.sh
    #    only what the registry marks plain, the one a shell sources
    stamp = f"{MARKER}: written by fabric-secrets sync, {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}; do not edit"
    plain = plain_env_names()
    lines, shell_lines = [stamp], [stamp + " (plain values only: never a secret)"]
    for name in ENV_NAMES + optional:
        if name in values:
            lines.append(f"export {name}={shlex.quote(values[name])}")
            if name in plain:
                shell_lines.append(lines[-1])
            obj["applied"].append(name)
    write_private(env_file(), "\n".join(lines) + "\n", 0o600)
    write_private(shell_env_file(), "\n".join(shell_lines) + "\n", 0o600)
    # 2. ~/.bashrc sources env.sh, once, and secrets.env never
    done = settle_bashrc()
    if done:
        obj["applied"].append(done)
    # 2b. gh holds GH_TOKEN itself
    gh_failed = None
    if "GH_TOKEN" in values:
        gh = apply_gh_token(values["GH_TOKEN"])
        if gh == "applied":
            obj["applied"].append("GH_TOKEN into gh")
        elif gh.startswith("no gh"):
            obj["skipped"].append(f"GH_TOKEN into gh ({gh}): nothing here can use it")
        elif gh != "unchanged":
            gh_failed = f"GH_TOKEN into gh ({gh})"
            obj["skipped"].append(gh_failed)
    # 3. git identity and signing — strings, not key material
    for name, key in GIT_NAMES.items():
        if name in values:
            git_set(key, values[name])
            obj["applied"].append(name)
    if "GIT_SIGNING_KEY" in values:
        git_set("commit.gpgsign", "true")
        git_set("tag.gpgsign", "true")
    # 4. the SSH key — never silently replace one that is already there
    if "SSH_PRIVATE_KEY" in values:
        if os.path.exists(ssh_key()) and not force:
            obj["skipped"].append("SSH_PRIVATE_KEY (present; --force replaces)")
        else:
            write_private(ssh_key(), values["SSH_PRIVATE_KEY"].rstrip("\n") + "\n", 0o600)
            obj["applied"].append("SSH_PRIVATE_KEY")
            if "SSH_PUBLIC_KEY" in values:
                write_private(ssh_key() + ".pub", values["SSH_PUBLIC_KEY"].rstrip("\n") + "\n", 0o644)
                obj["applied"].append("SSH_PUBLIC_KEY")
    obj["local"] = local_state()
    ok = not obj["missing"] and not gh_failed
    if gh_failed:
        obj["error"] = f"applied, but gh does not hold the token: {gh_failed}"
    report(obj, as_json, quiet, ok)
    return 0 if ok else 2


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE, file=sys.stderr)
        return 0 if argv else 2
    cmd, flags = argv[0], argv[1:]
    if cmd not in ("sync", "status") or [f for f in flags if f not in ("--force", "--json", "--quiet", "--no-pull")] \
            or (cmd == "status" and "--no-pull" in flags):
        print(USAGE, file=sys.stderr)
        return 2
    if cmd == "status":
        return status("--json" in flags, "--quiet" in flags)
    return sync("--force" in flags, "--json" in flags, "--quiet" in flags, pull="--no-pull" not in flags)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
