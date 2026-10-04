#!/usr/bin/env python3
"""tools/fabric/secret_store.py — an agent's own encrypted secrets
(agent-fabric ADR-038), behind `fabric-secrets store …`.

    fabric-secrets store init --agent-id ID [--remote URL]
                                                 in the account: its key and its store
    fabric-secrets store mint-id BORN            a new agent id, a UUIDv7 of that birth (ADR-039)
    fabric-secrets store id                      this store's agent id (exit 3: none yet)
    fabric-secrets store id-of LOGIN             the agent id lineage.json records for a login
                                                 (exit 3: no agent with that login)
    fabric-secrets store rename OLD NEW          a login renamed; its id, key and store stay
    fabric-secrets store set NAME                the agent writes an entry (value on stdin)
    fabric-secrets store export-key              the agent's PUBLIC key, armored (for its parent)
    fabric-secrets store push                    the store to its remote
    fabric-secrets store bundle                  this store, armored, for its parent (first contact)
    fabric-secrets store take-bundle             the child takes its parent's bundle (stdin)
    fabric-secrets store seed-child ID --remote URL
                                                 the parent takes a new child's bundle (stdin) as its
                                                 mirror and pushes it
    fabric-secrets store child-bundle LOGIN|ID   the parent's mirror of a child, armored
    fabric-secrets store refresh-mirror LOGIN|ID the parent's mirror of a child, brought up to its remote
                                                 by the verified fetch (ADR-042)
    fabric-secrets store trust-base [COMMIT] [--store DIR]
                                                 the commit up to which the store's history is
                                                 trusted unsigned (ADR-042; the migration, once)
    fabric-secrets store names [--json]          the entries, by name
    fabric-secrets store put LOGIN|ID NAME [--store DIR]
                                                 the parent writes into a child's store
                                                 (value on stdin; the child's committed key)
    fabric-secrets store certify LOGIN KEYFILE | --root
                                                 the parent attests a child's key
    fabric-secrets store verify                  every committed key against its lineage
    fabric-secrets store paper [--out FILE]      the key and its revocation, for the owner
    fabric-secrets store recovery-key init       the OWNER, in a terminal: the recovery key (passphrase-protected,
                                                 its private half only in Proton)
    fabric-secrets store recovery-copy           this login's recovery copy, encrypted to the recovery key
    fabric-secrets store backup [--verify]       every store held, as git bundles, into Proton Drive
    fabric-secrets store template-set SLUG       a Claude account's setup-token into this
                                                 (the coordinator's) store (value on stdin)
    fabric-secrets store templates [--json]      the templates, by fingerprint
    fabric-secrets store assign SLUG LOGIN|ID... each agent's store gets the template's token
                                                 (ADR-031, through its parent)

The store is a git repository in the layout pass(1) reads, so QtPass and
browserpass open it: `.gpg-id` names the key, and each secret is
`env/<NAME>.gpg`, its value on the first line. It is encrypted to the
agent's key alone. Anyone holding the committed public key can add an
entry, and only the agent can read one: the parent writes and never reads.

A key is an agent's when its public half is committed at
`identities/keys/<agent id>.asc` with its parent's certification on the
user id addressed to that id, and `identities/keys/lineage.json` records
that parent (ADR-039: stored under the id, typed as the login). Placement is not
part of it: no host is named anywhere, and nothing here needs the
parent and the child on one machine. They meet only through git.

WHO MAY WRITE A STORE (ADR-042). Every commit to a store is signed by its
writer's own key, and a store takes in only commits signed by its writers:
the agent's own key and its recorded parent's, as lineage.json and
identities/keys/ stand at the fabric checkout's origin/main. pull, the
write paths' fetch, take-bundle, seed-child, child-bundle, refresh-mirror
and push's fast-forward verify every commit beyond the store's trusted
base (agent-fabric.trustedbase in its .git/config, set by `trust-base` or
a new store's init, moved forward by each verified fetch). A refusal names
the commit and why, applies nothing, and is kept beside the store for
`fabric-secrets status` and `fabric-ctl keys` until a verified fetch
succeeds. First contact, before a new agent's keys reach main, is the one
exception, on both sides and only through a bundle: seed-child records the
child's first bundle as its mirror's base, and the child's first
take-bundle records its parent's (once).

No function here prints a secret value. `values()` returns them to the
caller in-process (fabric-secrets sync); everything else deals in names,
fingerprints and paths.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# The parts are found beside this file however it is loaded: the CLI runs it
# as a script, and tests/test_first_contact.py loads it by its path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from secretstore.core import (  # noqa: E402
    HERE,
    FABRIC_ROOT,
    NAME_RE,
    LOGIN_RE,
    UID_DOMAIN,
    StoreError,
    NotInLineage,
    login,
    AGENT_ID_RE,
    REPO_PREFIX,
    mint_agent_id,
    born_of,
    born_ms_of,
    own_agent_id,
    home,
    store_dir,
    children_dir,
    keys_dir,
    _GIT_REPO_ENV,
    _git_scrubbed,
    _run,
    _failure,
    GPG_COMMANDS,
    gpg,
    git,
)
from secretstore.keys import (  # noqa: E402
    fingerprints,
    key_of_store,
    KEY_USES,
    _key_caps,
    _ensure_use_subkeys,
    uid_of,
    export_key,
    _signing_args,
    _signing_subkeys,
    _key_file_fingerprint,
    _key_agent_ids,
)
from secretstore.trust import (  # noqa: E402
    _git_env,
    _commit,
    TRUST_KEY,
    REFUSAL_FILE,
    _read_base,
    trusted_base,
    _full,
    _is_ancestor,
    _set_base,
    trust_base,
    _no_base,
    _main_show,
    writers,
    _record_refusal,
    _kept_refusal,
    refusal,
    _mirror_ids,
    refusals,
    base_state,
    bases,
    _clear_refusal,
    _verify_incoming,
    FIRST_CONTACT_KEY,
    on_main,
    _taken,
    _take_verified,
)
from secretstore.entries import (  # noqa: E402
    init,
    _require_clean,
    _check_name,
    _one_line_off,
    _write_entry,
    _decrypt,
    _remote,
    _branch,
    _before_write,
    _push_if_ahead,
    _after_commit,
    stdin_value,
    set_entry,
    names,
    pull,
    values,
)
from secretstore.mirrors import (  # noqa: E402
    BUNDLE_BEGIN,
    BUNDLE_END,
    MAIN,
    _bundle_armored,
    _bundle_file,
    _bundle_identity,
    bundle_own,
    _rebuild_mirror,
    _mirror_lock,
    seed_child,
    child_bundle,
    refresh_mirror,
    take_bundle,
    lineage,
    _write_lineage,
    resolve,
    put,
    certify,
    rename,
    verify,
)
from secretstore.accounts import (  # noqa: E402
    TEMPLATE_PREFIX,
    ASSIGNED_PREFIX,
    SLUG_RE,
    _slug_name,
    _assigned_name,
    _sha12,
    template_set,
    templates,
    assign,
    _sheet_text,
    paper,
)


# ── Proton Drive: the stores' backup and the keys' recovery copies ─────
# The owner's decision (ADR-038 §7): a dedicated Proton account holds, in
# /my-files/agent-fabric/, every store as a git bundle (ciphertext only)
# with a manifest, and each key's recovery copy. The CLI's session is an
# entry of the running login's own store (PROTON_DRIVE_CREDENTIALS_STORE=
# pass over this store), so it is readable by this login alone; `auth
# login` is the owner's, in a terminal. Nothing here prints a value.
PROTON_ROOT = "/my-files/agent-fabric"


def _proton(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "PASSWORD_STORE_DIR": store_dir(), "PROTON_DRIVE_CREDENTIALS_STORE": "pass"}
    exe = os.environ.get("PROTON_DRIVE_BIN") or shutil.which("proton-drive")
    if not exe:
        raise StoreError("the Proton Drive CLI is not installed (proton-drive in ~/.local/bin)")
    r = subprocess.run([exe, *args], capture_output=True, env=env, timeout=600)
    if check and r.returncode != 0:
        lines = [l for l in (r.stderr or r.stdout).decode(errors="replace").splitlines() if l.strip()]
        why = (lines or [f"exit {r.returncode}"])[-1]
        # The sign-in hint only when the CLI's own words are about signing
        # in: on any other error it would send the owner the wrong way.
        hint = (" (the session has lapsed: the owner runs `proton-drive auth login` with PASSWORD_STORE_DIR "
                "set to this store and PROTON_DRIVE_CREDENTIALS_STORE=pass)"
                if re.search(r"auth|session|log ?in|401|unauthori", why, re.I) else "")
        raise StoreError(f"proton-drive {args[0]} {args[1] if len(args) > 1 else ''}: {why}{hint}")
    return r


def _proton_folder(path: str) -> str:
    """The folder at path, made (with its parents) when absent. Asked with
    `info`, whose exit status says whether the node exists: `list` prints
    a decorated table, not paths, and reading it as paths made every run
    after the first try to create a folder that was there."""
    if path in ("", "/my-files"):
        # The drive's root always exists: failing on it is the session or
        # the network, said in the CLI's own words (and _proton's sign-in
        # hint), never a recursion past the root.
        _proton("filesystem", "info", "/my-files")
        return "/my-files"
    if _proton("filesystem", "info", path, check=False).returncode == 0:
        return path
    parent, name = path.rsplit("/", 1)
    _proton_folder(parent)
    _proton("filesystem", "create-folder", parent, name)
    return path


def _upload(local: str, folder: str) -> None:
    # A new revision, never a replacement: Proton keeps what was there.
    _proton("filesystem", "upload", "-f", "create-new-revision", "-t", local, folder)


def _sha256_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


RECOVERY_UID = f"agent-fabric recovery <recovery@{UID_DOMAIN}>"


def recovery_pub(fabric: str | None = None) -> str:
    return os.path.join(fabric or FABRIC_ROOT, "identities", "recovery.asc")


RECOVERY_MIN_PASSPHRASE = 12


def _read_recovery_passphrase() -> str:
    """Asked here, on the owner's terminal, never through gpg's pinentry:
    the first run left the prompt to the desktop's pinentry, the owner saw
    none, and the key was made with no private half kept anywhere."""
    import getpass
    first = getpass.getpass("recovery passphrase (only you keep it): ")
    if len(first) < RECOVERY_MIN_PASSPHRASE:
        raise StoreError(f"a recovery passphrase has at least {RECOVERY_MIN_PASSPHRASE} characters; nothing was made")
    if getpass.getpass("the same again: ") != first:
        raise StoreError("the two passphrases differ; nothing was made")
    return first


def _make_recovery_key(homedir: str, passphrase: str) -> tuple[str, str, str]:
    """The recovery key in homedir, every secret part protected by the
    passphrase (checked, not assumed); returns its fingerprint, its public
    half and its protected private half, both armoured."""
    base = ["gpg", "--homedir", homedir, "--batch", "--pinentry-mode", "loopback", "--passphrase-fd", "0"]
    def run(*a: str) -> bytes:
        return subprocess.run([*base, *a], input=passphrase.encode(), capture_output=True, check=True,
                              env={**os.environ, "GNUPGHOME": homedir}).stdout
    run("--quick-gen-key", RECOVERY_UID, "ed25519", "cert", "never")
    fpr = fingerprints(homedir=homedir, secret=True)[0]
    run("--quick-add-key", fpr, "cv25519", "encr", "never")
    info = subprocess.run(["gpg-connect-agent", "--homedir", homedir, "KEYINFO --list", "/bye"],
                          capture_output=True, text=True, check=True).stdout.split("\n")
    # KEYINFO: S KEYINFO <grip> <type> <serial> <idstr> <cached> <protection> …; P is protected.
    marks = [l.split()[7] for l in info if l.startswith("S KEYINFO")]
    if len(marks) != 2 or set(marks) != {"P"}:
        raise StoreError("the recovery key is not protected by the passphrase; nothing was published")
    public = gpg("--armor", "--export", fpr, homedir=homedir).stdout.decode()
    private = run("--armor", "--export-secret-keys", fpr).decode()
    if "BEGIN PGP PRIVATE KEY BLOCK" not in private:
        raise StoreError("the recovery key's private half did not export; nothing was published")
    return fpr, public, private


def recovery_key_init(force: bool = False) -> dict:
    """The owner's recovery key (ADR-038 §5 rule 1): made in a throwaway
    keyring, protected by a passphrase the owner types here; its protected
    private half uploaded to Proton (/my-files/agent-fabric/keys/
    recovery-key-<fpr16>.asc) and never kept on the host, and only then its public
    half written to identities/recovery.asc, so no agent can encrypt to a
    key whose private half is kept nowhere. Refused inside a model session:
    the passphrase is the owner's."""
    if os.environ.get("CLAUDECODE"):
        raise StoreError("refused inside a model session: the owner runs this in a terminal and types the passphrase")
    if not sys.stdin.isatty():
        raise StoreError("stdin is not a terminal: the owner types the passphrase")
    pub = recovery_pub()
    if os.path.exists(pub) and not force:
        raise StoreError(f"{pub} exists; a new recovery key is a rotation (--force), and every copy is then re-made")
    passphrase = _read_recovery_passphrase()
    old = _key_file_fingerprint(pub) if os.path.exists(pub) else None
    with tempfile.TemporaryDirectory() as tmp:
        os.chmod(tmp, 0o700)
        try:
            fpr, public, private = _make_recovery_key(tmp, passphrase)
            # Named by its fingerprint, so the new key goes up beside the
            # old one: every step below that fails leaves recovery.asc
            # naming a key whose private half is in Proton. Deleting first
            # once risked the fleet's only recovery key on a failed upload.
            protected = os.path.join(tmp, _recovery_key_name(fpr))
            with open(protected, "w", encoding="utf-8") as fh:
                fh.write(private)
            _upload(protected, _proton_folder(f"{PROTON_ROOT}/keys"))
        finally:
            _run(["gpgconf", "--homedir", tmp, "--kill", "all"], check=False)
    with open(pub, "w", encoding="utf-8") as fh:
        fh.write(public)
    # The key rotated away is deleted, never kept as a revision; copies
    # still encrypted to it are unreadable from here until each agent's
    # recovery-copy re-makes its own (it sees the new recipient).
    if old and old != fpr:
        name = _recovery_key_name(old)
        if _proton("filesystem", "info", f"{PROTON_ROOT}/keys/{name}", check=False).returncode == 0:
            _proton("filesystem", "trash", f"{PROTON_ROOT}/keys/{name}")
            _proton("filesystem", "delete", f"/trash/{name}")
    return {"fingerprint": fpr, "public": pub, "private": f"{PROTON_ROOT}/keys/{_recovery_key_name(fpr)}"}


def _recovery_key_name(fpr: str) -> str:
    return f"recovery-key-{fpr[-16:]}.asc"


def recovery_copy(force: bool = False) -> dict:
    """This login's key recovery copy, encrypted to the owner's recovery
    key, committed into its own store as recovery/<agent id>.key.gpg and
    pushed; the parent's backup carries it to Proton. Nothing is printed
    but a path and a hash, and once written not even this login can read
    it back: only the owner, with the recovery passphrase."""
    pub = recovery_pub()
    if not os.path.exists(pub):
        raise StoreError("no recovery key yet (identities/recovery.asc): the owner runs `fabric-secrets store recovery-key init`")
    rfpr = _key_file_fingerprint(pub)
    store = store_dir()
    key_of_store(store)
    _require_clean(store)
    _before_write(store)
    aid = own_agent_id(store)
    if not aid:
        raise StoreError("this store has no agent id yet (store-enroll.sh)")
    path = os.path.join(store, "recovery", f"{aid}.key.gpg")
    note = os.path.join(store, "recovery", f"{aid}.recipient")
    if os.path.exists(path) and not force and open(note, encoding="utf-8").read().strip() == rfpr:
        _push_if_ahead(store)
        return {"path": path, "changed": False, "recipient": rfpr}
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    gpg("--trust-model", "always", "--no-encrypt-to", "--encrypt", "--recipient-file", pub,
        "--output", path + ".tmp", stdin=_sheet_text().encode())
    os.replace(path + ".tmp", path)
    with open(note, "w", encoding="utf-8") as fh:
        fh.write(rfpr + "\n")
    git(store, "add", os.path.relpath(path, store), os.path.relpath(note, store))
    _commit(store, f"agent {login()}: recovery copy, encrypted to the recovery key {rfpr[-16:]}")
    _after_commit(store)
    return {"path": path, "changed": True, "recipient": rfpr}


def _stores() -> dict[str, str]:
    """This agent's own store and every child mirror it holds: agent id -> dir."""
    mine = own_agent_id()
    if not mine:
        raise StoreError("this store has no agent id yet (store-enroll.sh --self)")
    out = {mine: store_dir()}
    try:
        for child in sorted(os.listdir(children_dir())):
            d = os.path.join(children_dir(), child)
            if os.path.isdir(os.path.join(d, ".git")) and AGENT_ID_RE.match(child):
                out[child] = d
    except FileNotFoundError:
        pass
    return out


def backup() -> dict:
    """Every store this login holds — its own and its children's mirrors,
    each brought up to its remote first — as a git bundle (the whole
    history, ciphertext only), with a manifest of each bundle's sha256
    and head, uploaded to Proton Drive as new revisions."""
    folder = _proton_folder(f"{PROTON_ROOT}/secrets")
    import datetime
    manifest = {"written_by": login(), "stores": {}}
    manifest["at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with tempfile.TemporaryDirectory() as tmp:
        for who, d in _stores().items():
            _before_write(d)
            bundle = os.path.join(tmp, f"{REPO_PREFIX}{who}.bundle")
            git(d, "bundle", "create", bundle, "--all")
            name = ((lineage().get(who) or {}).get("login")) or (login() if d == store_dir() else None)
            manifest["stores"][who] = {"bundle": os.path.basename(bundle), "sha256": _sha256_file(bundle), "login": name,
                                       "head": git(d, "rev-parse", "HEAD").stdout.decode().strip()}
            # Each store's recovery copy, already encrypted to the owner's
            # recovery key, also stands alone in keys/ for a restore.
            rdir = os.path.join(d, "recovery")
            for f in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
                if f.endswith(".key.gpg"):
                    manifest.setdefault("recovery_copies", {})[f] = _sha256_file(os.path.join(rdir, f))
                    _upload(os.path.join(rdir, f), _proton_folder(f"{PROTON_ROOT}/keys"))
        mpath = os.path.join(tmp, "manifest.json")
        with open(mpath, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        for name in sorted(os.listdir(tmp)):
            _upload(os.path.join(tmp, name), folder)
    return manifest


def verify_backup() -> list[str]:
    """Download the manifest, every bundle and every recovery copy it
    names, and check each against its sha256 (and a bundle with `git
    bundle verify`). Findings; [] is clean."""
    folder = f"{PROTON_ROOT}/secrets"
    findings = []
    with tempfile.TemporaryDirectory() as tmp:
        # `git bundle verify` needs a repository around it: run from one
        # that is not, it failed every good bundle. An empty one of its own,
        # never the caller's cwd, which could be any repository or none.
        empty = os.path.join(tmp, ".verify-repo")
        os.makedirs(empty)
        git(empty, "init", "-q")
        _proton("filesystem", "download", "-f", "remove", f"{folder}/manifest.json", tmp)
        manifest = json.load(open(os.path.join(tmp, "manifest.json"), encoding="utf-8"))
        for who, rec in sorted(manifest.get("stores", {}).items()):
            _proton("filesystem", "download", "-f", "remove", f"{folder}/{rec['bundle']}", tmp)
            local = os.path.join(tmp, rec["bundle"])
            if _sha256_file(local) != rec["sha256"]:
                findings.append(f"{rec['bundle']}: its sha256 is not the manifest's")
                continue
            if _run(["git", "bundle", "verify", local], cwd=empty, check=False).returncode != 0:
                findings.append(f"{rec['bundle']}: git bundle verify fails")
        # The recovery copies stand alone in keys/ for a restore: each is
        # checked against the hash the manifest took when it went up.
        for f, sha in sorted((manifest.get("recovery_copies") or {}).items()):
            got = _proton("filesystem", "download", "-f", "remove", f"{PROTON_ROOT}/keys/{f}", tmp, check=False)
            local = os.path.join(tmp, f)
            if got.returncode != 0 or not os.path.exists(local):
                findings.append(f"keys/{f}: could not be downloaded")
            elif _sha256_file(local) != sha:
                findings.append(f"keys/{f}: its sha256 is not the manifest's")
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabric-secrets store", description="this agent's encrypted secrets (ADR-038)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--remote")
    i.add_argument("--agent-id", help="the id the parent minted at enrolment (store-enroll.sh)")
    s = sub.add_parser("set")
    s.add_argument("name")
    s.add_argument("--empty", action="store_true", help="store an empty value on purpose")
    n = sub.add_parser("names")
    n.add_argument("--json", action="store_true")
    p = sub.add_parser("put")
    p.add_argument("login")
    p.add_argument("name")
    p.add_argument("--store")
    p.add_argument("--empty", action="store_true", help="store an empty value on purpose")
    mi = sub.add_parser("mint-id", help="a new agent id whose time is the birth given")
    mi.add_argument("born", help='the birth: "now", ISO 8601, or as `stat -c %%w` prints it')
    sub.add_parser("id", help="this store's agent id")
    io = sub.add_parser("id-of", help="the agent id lineage.json records for a login")
    io.add_argument("login")
    rn = sub.add_parser("rename", help="a login renamed: its lineage entry, nothing else")
    rn.add_argument("old")
    rn.add_argument("new")
    c = sub.add_parser("certify")
    c.add_argument("login", nargs="?")
    c.add_argument("key_file", nargs="?")
    c.add_argument("--root", action="store_true")
    sub.add_parser("verify")
    tb = sub.add_parser("trust-base", help="the commit up to which this store's history is trusted unsigned (ADR-042)")
    tb.add_argument("commit", nargs="?")
    tb.add_argument("--store", help="a store other than this agent's own (a child's mirror)")
    sub.add_parser("export-key")
    sub.add_parser("push")
    sub.add_parser("bundle", help="this store, armored, for its parent (a new account's first contact)")
    sub.add_parser("take-bundle", help="fast-forward this store from its parent's bundle on stdin")
    sc = sub.add_parser("seed-child", help="a new child's bundle (stdin) becomes its mirror, pushed")
    sc.add_argument("agent_id")
    sc.add_argument("--remote", required=True)
    rm = sub.add_parser("refresh-mirror", help="a child's mirror brought up to its remote, every commit verified")
    rm.add_argument("login")
    cb = sub.add_parser("child-bundle", help="a child's store as its mirror holds it, armored")
    cb.add_argument("login")
    pa = sub.add_parser("paper")
    pa.add_argument("--out")
    rc = sub.add_parser("recovery-copy")
    rc.add_argument("--force", action="store_true", help="re-make it even when it is encrypted to the current recovery key")
    rk = sub.add_parser("recovery-key")
    rk.add_argument("action", choices=["init"])
    rk.add_argument("--force", action="store_true", help="rotate: a new recovery key; every copy is then re-made")
    bk = sub.add_parser("backup")
    bk.add_argument("--verify", action="store_true", help="download the backup and check it against its manifest")
    ts = sub.add_parser("template-set")
    ts.add_argument("slug")
    tl = sub.add_parser("templates")
    tl.add_argument("--json", action="store_true")
    asg = sub.add_parser("assign")
    asg.add_argument("slug")
    asg.add_argument("logins", nargs="+")
    asg.add_argument("--json", action="store_true")
    asg.add_argument("--force", action="store_true", help="write even when this store's record says unchanged")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "init":
            r = init(args.remote, args.agent_id)
            print(f"store: {r['store']}  agent: {r['agent_id']}  key: {r['fingerprint']}{' (made)' if r['key_made'] else ''}"
                  + (f"  subkeys added: {', '.join(r['subkeys_added'])}" if r['subkeys_added'] and not r['key_made'] else ""))
        elif args.cmd == "mint-id":
            print(mint_agent_id(born_ms_of(args.born)))
        elif args.cmd == "id":
            # 3 is "no id yet", the one answer that lets a parent mint; any
            # other failure (no store read, a malformed .agent-id) is 1.
            aid = own_agent_id()
            if not aid:
                print("fabric-secrets store: this store has no agent id yet", file=sys.stderr)
                return 3
            print(aid)
        elif args.cmd == "id-of":
            # 3, as `id` answers "no id yet": no agent with that login. A
            # lineage that cannot be read is 1, never a reason to mint.
            try:
                print(resolve(args.login)[0])
            except NotInLineage as e:
                print(f"fabric-secrets store: {e}", file=sys.stderr)
                return 3
        elif args.cmd == "rename":
            r = rename(args.old, args.new)
            print(f"agent {r['agent_id']}: now {r['login']}")
        elif args.cmd == "set":
            r = set_entry(args.name, stdin_value(args.empty))
            print(f"{args.name}: {'set' if r['changed'] else 'unchanged'}")
        elif args.cmd == "names":
            ns = names()
            print(json.dumps(ns) if args.json else "\n".join(ns) or "(no entries)")
        elif args.cmd == "put":
            r = put(args.login, args.name, stdin_value(args.empty), store=args.store)
            print(f"{args.login} {args.name}: {'written' if r['changed'] else 'unchanged'}")
        elif args.cmd == "certify":
            if args.root == bool(args.login):
                raise StoreError("certify takes LOGIN KEYFILE, or --root for this login's own key")
            if args.login and not args.key_file:
                raise StoreError("certify LOGIN needs the child's exported public key file")
            r = certify(None if args.root else args.login, args.key_file)
            print(f"{r['login']} ({r['agent_id']}): {r['fingerprint']}, parent {r['parent'] or '(root)'}")
        elif args.cmd == "export-key":
            sys.stdout.write(export_key())
        elif args.cmd == "refresh-mirror":
            print(f"mirror up to date: {refresh_mirror(args.login)}")
        elif args.cmd == "trust-base":
            r = trust_base(args.commit, args.store)
            print(f"trusted base: {r['trusted_base']}" + (f" (was {r['was']})" if r["was"] and r["was"] != r["trusted_base"] else ""))
        elif args.cmd == "push":
            store = store_dir()
            key_of_store(store)
            if not git(store, "remote", check=False).stdout.strip():
                raise StoreError("the store has no remote (fabric-secrets store init --remote URL)")
            # What the parent put since is taken first, only as a fast-forward:
            # a re-enrolment after a put pushed the account's older head and
            # was refused as non-fast-forward. A new repository has no main.
            git(store, "fetch", "-q", "origin")
            if git(store, "rev-parse", "-q", "--verify", "refs/remotes/origin/main", check=False).returncode == 0:
                _take_verified(store, "refs/remotes/origin/main")
            git(store, "push", "-q", "-u", "origin", "HEAD:main")
            print("pushed")
        elif args.cmd == "bundle":
            sys.stdout.write(bundle_own())
        elif args.cmd == "take-bundle":
            r = take_bundle(sys.stdin.read())
            print(f"taken: agent {r['agent_id']} at {r['head']}, {r['names']} entries")
        elif args.cmd == "seed-child":
            r = seed_child(args.agent_id, args.remote, sys.stdin.read())
            print(f"seeded: agent {r['agent_id']}, mirror {r['mirror']}, pushed to {r['remote']}")
        elif args.cmd == "child-bundle":
            sys.stdout.write(child_bundle(args.login))
        elif args.cmd == "verify":
            f = verify()
            print("\n".join(f) if f else "keys: clean")
            return 1 if f else 0
        elif args.cmd == "paper":
            paper(args.out)
        elif args.cmd == "recovery-copy":
            r = recovery_copy(args.force)
            print(f"{r['path']}: {'written' if r['changed'] else 'unchanged'}, encrypted to the recovery key {r['recipient'][-16:]}")
        elif args.cmd == "recovery-key":
            r = recovery_key_init(args.force)
            print(f"recovery key {r['fingerprint']}: public half {r['public']} (commit it), protected private half {r['private']}")
        elif args.cmd == "backup":
            if args.verify:
                f = verify_backup()
                print("\n".join(f) if f else "backup: every bundle and recovery copy matches its manifest")
                return 1 if f else 0
            m = backup()
            for who, rec in sorted(m["stores"].items()):
                print(f"{PROTON_ROOT}/secrets/{rec['bundle']}  sha256 {rec['sha256'][:16]}…  head {rec['head'][:12]}")
        elif args.cmd == "template-set":
            r = template_set(args.slug, sys.stdin.buffer.read())
            print(f"template {args.slug}: {'set' if r['changed'] else 'unchanged'}")
        elif args.cmd == "templates":
            t = templates()
            if args.json:
                print(json.dumps(t))
            else:
                print("\n".join(f"{x['account']:<34} setup-token {x['token_sha256_12']}" for x in t) or "(no templates)")
        elif args.cmd == "assign":
            rows = assign(args.slug, args.logins, force=args.force)
            if args.json:
                print(json.dumps(rows))
            else:
                for r in rows:
                    print(f"{r['login']:<22} {r['from']:<30} -> {r.get('to', '-'):<30} {r['status']}{('  ' + r['reason']) if r.get('reason') else ''}")
            return 0 if all(r["status"] != "failed" for r in rows) else 1
    except StoreError as e:
        print(f"fabric-secrets store: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
