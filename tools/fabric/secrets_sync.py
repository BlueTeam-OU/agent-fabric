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
    fabric-secrets status [--json]
                                  what is present, missing, applied

The store is this login's pass-format repository (secret_store.py). sync
writes
    ~/.config/agent-fabric/secrets.env   (0600) — the string secrets the
                                         tools read from the environment:
                                         OPENROUTER_API_KEY, GH_TOKEN,
                                         CLAUDE_BRIDGE_AUTH_TOKEN, and the
                                         registry's per-agent names
    ~/.bashrc                            one marked line sourcing that file
    ~/.gitconfig                         user.name/email, signing key and
                                         program (strings; the key material
                                         stays in the keyring)
    ~/.ssh/id_ed25519(.pub)              only when absent; --force replaces
and refuses when the store's AGENT_LOGIN is not this login — location and
configuration never decide who an agent is, the login does.

The contract (ADR-038 §5 rule 7), frozen when this moved from the bash
heredoc and its Doppler reader retired: the exit codes — 0 applied, 1
unreadable, 2 applied with required names missing, 3 the store names
another login and nothing is applied; the JSON report's `error` and
`missing`, which the control agent reads (runtime/control/secrets.mjs);
the `--quiet` line on stderr, which moveto's shell entry shows.

Nothing here prints a secret value: names, presence, ages and modes only.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pwd
import shlex
import stat
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", ".."))
MARKER = "# agent-fabric secrets"
ENV_NAMES = ["OPENROUTER_API_KEY", "GH_TOKEN", "CLAUDE_BRIDGE_AUTH_TOKEN"]
GIT_NAMES = {"GIT_USER_NAME": "user.name", "GIT_USER_EMAIL": "user.email",
             "GIT_SIGNING_KEY": "user.signingkey", "GIT_GPG_PROGRAM": "gpg.program"}
SSH_NAMES = ["SSH_PRIVATE_KEY", "SSH_PUBLIC_KEY"]
IDENTITY_NAMES = ["AGENT_LOGIN", "AGENT_HOST"]
ALL_NAMES = IDENTITY_NAMES + ENV_NAMES + list(GIT_NAMES) + SSH_NAMES
USAGE = "usage: fabric-secrets sync [--force] [--json] [--quiet] [--no-pull] | status [--json] | store …"


def login() -> str:
    return pwd.getpwuid(os.getuid()).pw_name


def home() -> str:
    return os.environ.get("HOME") or pwd.getpwuid(os.getuid()).pw_dir


def env_file() -> str:
    return os.path.join(home(), ".config", "agent-fabric", "secrets.env")


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
            if n not in names and n not in ENV_NAMES:
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


def git_get(key: str) -> str:
    r = subprocess.run(["git", "config", "--global", "--get", key], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def git_set(key: str, value: str) -> None:
    subprocess.run(["git", "config", "--global", key, value], check=True)


def write_private(path: str, content: str, mode: int) -> None:
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w") as fh:
        fh.write(content)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def file_mode(path: str) -> int | None:
    try:
        return stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        return None


def bashrc() -> str:
    return os.path.join(home(), ".bashrc")


def bashrc_has_line() -> bool:
    try:
        return any(MARKER in line for line in open(bashrc(), encoding="utf-8"))
    except FileNotFoundError:
        return False


def source_line() -> str:
    f = env_file()
    return f"[ -r {f} ] && . {f}  {MARKER}" if " " not in f else f"[ -r {shlex.quote(f)} ] && . {shlex.quote(f)}  {MARKER}"


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
        "bashrc_sources_env_file": bashrc_has_line(),
        "ssh_key_present": os.path.exists(ssh_key()),
        "git": {key: bool(git_get(key)) for key in GIT_NAMES.values()},
        "commit_gpgsign": git_get("commit.gpgsign") == "true",
    }


def values_digest(values: dict[str, str], known: list[str]) -> str:
    """sha256 over every name sync applies and its value, in a canonical
    form, the SSH key and the git strings included, which secrets.env does
    not carry: two syncs applied the same values when it is equal. Only
    the hash is printed."""
    applied = {n: values[n] for n in known if n in values}
    return hashlib.sha256(json.dumps(applied, sort_keys=True).encode()).hexdigest()


def report(obj: dict, as_json: bool, quiet: bool, ok: bool) -> None:
    if quiet:
        # For a shell entry (moveto): silence when all is well, one line otherwise.
        if not ok:
            what = obj.get("error") or f"missing in the store: {', '.join(obj.get('missing', []))}"
            print(f"fabric-secrets: {what}", file=sys.stderr)
        return
    if as_json:
        print(json.dumps(obj, indent=2, sort_keys=True))
        return
    print(f"fabric-secrets: login={obj['login']} store={obj['store']}")
    if obj.get("error"):
        print(f"  error: {obj['error']}")
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
    print(f"  bashrc sources it: {ls['bashrc_sources_env_file']}   ssh key: {ls['ssh_key_present']}   "
          f"git: {', '.join(k for k, v in ls['git'].items() if v) or '(unset)'}   commit.gpgsign: {ls['commit_gpgsign']}")
    print("  " + ("OK" if ok else "NOT OK"))


def status(as_json: bool, quiet: bool = False) -> int:
    optional = project_agent_env()
    known = ALL_NAMES + optional
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
    ok = ok and obj["local"]["env_file_mode"] == "0600" and obj["local"]["bashrc_sources_env_file"]
    report(obj, as_json, quiet, ok)
    return 0 if ok else 1


def sync(force: bool, as_json: bool, quiet: bool = False, pull: bool = True) -> int:
    me = login()
    optional = project_agent_env()
    known = ALL_NAMES + optional
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
    # 1. the env file — only the names the tools read from the environment
    lines = [f"{MARKER}: written by fabric-secrets sync, {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}; do not edit"]
    for name in ENV_NAMES + optional:
        if name in values:
            lines.append(f"export {name}={shlex.quote(values[name])}")
            obj["applied"].append(name)
    write_private(env_file(), "\n".join(lines) + "\n", 0o600)
    # 2. ~/.bashrc sources it (once)
    if not bashrc_has_line():
        with open(bashrc(), "a", encoding="utf-8") as fh:
            fh.write(f"\n{source_line()}\n")
        obj["applied"].append("bashrc")
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
    ok = not obj["missing"]
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
