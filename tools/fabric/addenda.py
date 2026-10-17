"""tools/fabric/addenda.py — a holder's addenda of a shared role, read for the launch (agent-fabric ADR-060 §5).

Contract of `load(login, role, policy=)`:
  input   the login being launched, the role it is bound to, and the role's
          policy from the catalogue ("optional" or "required"; anything
          else is refused). The store is the account's own (store_dir()).
  result  a Holder (the charter and brief addendum bodies, holder.json, the
          store's HEAD, the commit that last touched the role's directory), or None: the store has no settings/roles/<role>/ and the
          role's policy is "optional" — the prompt is today's, byte for byte.
  raises  StoreError, naming the role, the path and the commit and never a
          byte of content, for everything else: a required role with no
          addenda; a store whose .agent-id is not the id lineage gives the
          login; a trusted base missing or a HEAD that does not descend from
          it; a last commit on the directory not signed by the parent's key
          alone (the agent's own included); a directory holding anything
          but plain files; a set of files addendum_check.validate_set has a finding on.
          Tamper is never read as absence (rule 7).
  reads   git objects only, without replace refs or a commit-graph, those of
          the parent-signed last commit on the directory, each hashed against
          its name (the commit, the trees down to the directory, the blobs),
          and .agent-id as HEAD has it: never the working tree, never env/,
          never a decryption. Besides objects it reads the store's .git/config
          (the trusted base) and .git/info/grafts, to refuse the latter. The one gpg call is
          verify-commit in a temporary GNUPGHOME that holds the parent's
          public key alone (trust.verify_signed_by).
  writes  nothing.
  limit   the agent owns its .git (ADR-060 §6: a fence, not a wall). Not covered:
          a process of the agent's that swaps a loose object between the
          signature check and the hash check of the same commit.

Why HEAD and not the working tree: the rendered text must be the text the
parent installed and signed; a file edited in the checkout, or left
untracked, is neither. Why the last commit on the directory and not every
commit: the store's other writes are the agent's own (rule 3 of ADR-042),
and only this path is the parent's alone.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass

# The launcher runs this as a script under -I (launcher/holder.py), which puts
# no directory on sys.path; secret_store.py does the same for the parts it loads.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re  # noqa: E402

import addenda_check as check  # noqa: E402
from secretstore import mirrors, trust  # noqa: E402
from secretstore.core import AGENT_ID_RE, StoreError, _run, git, store_dir

POLICIES = ("optional", "required")
# Names of the files the reader takes the text of; whether any other name is
# allowed is addenda_check.validate's to say, and it is asked of every file.
CHARTER, BRIEF, HOLDER = "charter-addendum.md", "brief-addendum.md", "holder.json"
_ROLE_RE = re.compile(r"[a-z][a-z0-9-]*")
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_AGAINST_RE = re.compile(r"(?m)^against_digest: (sha256:[0-9a-f]{64})$")
# Far above any valid file (the cap is 4 000 characters), so a blob of this size
# is refused before it is read into memory, not by the validator.
_MAX_BLOB = 64 * 1024


@dataclass(frozen=True)
class Holder:
    role: str
    agent_id: str
    charter: str | None        # the body of charter-addendum.md, frontmatter stripped
    brief: str | None          # the body of brief-addendum.md
    holder: dict | None        # holder.json as parsed
    against: dict[str, str]    # name -> the against_digest it records, for the drift warning
    store_sha: str             # the store's HEAD when read
    addenda_commit: str        # the last commit on settings/roles/<role>/


def _refuse(role: str, why: str, commit: str | None = None) -> StoreError:
    return StoreError(f"holder addenda of role {role} refused: {why}"
                      + (f" (store commit {commit[:12]})" if commit else "") + "; the launch stops (ADR-060)")


# Every read of an object goes through --no-replace-objects: the agent owns
# its .git and refs/replace/<oid> would show other bytes under the name of one
# the parent signed. A loose object overwritten in place is caught by hashing
# what is read against the name it was read by (the commit whose signature is
# verified, the trees down to the directory, each blob).
# core.commitGraph off: an agent-written commit-graph file would feed merge-base
# and history walks other parents. Grafts cannot be switched off from here (core
# scrubs GIT_GRAFT_FILE from every git environment), so a grafts file is a refusal.
_NOREPLACE = "--no-replace-objects"


def _git(store: str, *args: str, check: bool = True):
    return git(store, _NOREPLACE, "-c", "core.commitGraph=false", *args, check=check)


def _committed_agent_id(store: str) -> str | None:
    """.agent-id as HEAD has it: the checkout's copy is an edit the parent
    never signed. None for a store that commits none."""
    r = _git(store, "show", "HEAD:.agent-id", check=False)
    if r.returncode != 0:
        return None
    aid = r.stdout.decode("utf-8", "replace").strip()
    return aid if AGENT_ID_RE.fullmatch(aid) else None


def _algo(store: str) -> str:
    return git(store, "rev-parse", "--show-object-format").stdout.decode().strip()


def _object(store: str, role: str, kind: str, oid: str, algo: str, limit: int | None = None, label: str = "") -> bytes:
    if limit is not None:
        size = int(_git(store, "cat-file", "-s", oid).stdout.decode())
        if size > limit:
            raise _refuse(role, f"{label or kind + ' ' + oid[:12]} is {size} bytes, over the limit")
    body = _git(store, "cat-file", kind, oid).stdout
    if hashlib.new(algo, f"{kind} {len(body)}\0".encode() + body).hexdigest() != oid:
        raise _refuse(role, f"{kind} {oid[:12]} does not hash to its name: the object database was altered")
    return body


def _descends(store: str, base: str) -> bool:
    return _git(store, "merge-base", "--is-ancestor", base, "HEAD", check=False).returncode == 0


def _tree_entries(body: bytes, width: int) -> list[tuple[str, str, str]]:
    """(mode, name, oid) of a tree object's entries; width is the raw oid's."""
    out, i = [], 0
    while i < len(body):
        head_end = body.index(b"\0", i)
        mode, _, name = body[i:head_end].partition(b" ")
        out.append((mode.decode(), name.decode("utf-8", "surrogateescape"), body[head_end + 1:head_end + 1 + width].hex()))
        i = head_end + 1 + width
    return out


def _directory(store: str, role: str) -> str | None:
    """The oid of settings/roles/<role> at HEAD; None when the store has no
    commit or no such path. A path that is not a directory, or a git that
    fails, is no absence."""
    r = _git(store, "rev-parse", "-q", "--verify", f"HEAD:settings/roles/{role}", check=False)
    if r.returncode == 1:
        return None
    if r.returncode != 0:
        raise _refuse(role, f"the store could not be read (git exit {r.returncode})")
    kind = _git(store, "cat-file", "-t", r.stdout.decode().strip()).stdout.decode().strip()
    if kind != "tree":
        raise _refuse(role, f"settings/roles/{role} is a {kind}, not a directory")
    return r.stdout.decode().strip()


def _verified_directory(store: str, role: str, commit: str, algo: str) -> list[tuple[str, str, str]]:
    """The entries of settings/roles/<role> as the verified commit's own tree
    holds them, every object between re-hashed, and that tree the one HEAD
    shows."""
    width = len(hashlib.new(algo).digest())
    body = _object(store, role, "commit", commit, algo)
    lines = body.split(b"\n", 1)[0].split()
    if len(lines) != 2 or lines[0] != b"tree":
        raise _refuse(role, "the commit has no tree header", commit)
    oid = lines[1].decode()
    for part in ("settings", "roles", role):
        hit = [e for e in _tree_entries(_object(store, role, "tree", oid, algo), width) if e[1] == part]
        if len(hit) != 1 or hit[0][0] != "40000":
            raise _refuse(role, f"{part} is not a directory of the commit's tree", commit)
        oid = hit[0][2]
    # `git log -1 -- <path>` names a commit whose version of the path is HEAD's
    # own, and no replace ref is honoured, so this tree is the one HEAD shows.
    return _tree_entries(_object(store, role, "tree", oid, algo), width)


def load(login: str, role: str, policy: str = "optional", *, store: str | None = None,
         fabric: str | None = None) -> Holder | None:
    if policy not in POLICIES:
        raise StoreError(f"holders_specialize of role {role} is {policy!r}, not one of {', '.join(POLICIES)}")
    if not _ROLE_RE.fullmatch(role):
        raise StoreError(f"{role!r} is no role name")
    store = store or store_dir()
    if not os.path.isdir(os.path.join(store, ".git")):
        return _absent(role, policy, "this account has no store")
    # A HEAD outside the trusted base is tamper whether or not the directory
    # is there: a store moved back to before the install must not read as
    # "no addenda" (rule 7). Without a base there is nothing to compare with.
    if os.path.exists(os.path.join(store, ".git", "info", "grafts")):
        raise _refuse(role, "the store carries .git/info/grafts, which rewrites history")
    base = trust.trusted_base(store)
    if base and _git(store, "rev-parse", "-q", "--verify", "HEAD", check=False).returncode == 0 \
            and not _descends(store, base):
        raise _refuse(role, "the store's HEAD does not descend from its trusted base")
    if _directory(store, role) is None:
        # Never there, or removed: a removal is the parent's too (rule 3), or an
        # unsigned deletion would turn any addendum into "no addenda".
        removed = _git(store, "log", "-1", "--format=%H", "HEAD", "--", f"settings/roles/{role}/", check=False).stdout.decode().strip()
        if not removed:
            return _absent(role, policy, "the store has no settings/roles/" + role)
        aid, _ = mirrors.resolve(login, fabric=fabric)
        try:
            trust.verify_signed_by(store, removed, trust.parent_writer(aid, fabric), unknown_key="not signed by the parent's key")
        except StoreError as e:
            raise _refuse(role, f"the commit that removed the directory is not the parent's ({e})", removed) from None
        return _absent(role, policy, "the parent removed settings/roles/" + role)

    aid, _ = mirrors.resolve(login, fabric=fabric)
    if _committed_agent_id(store) != aid:
        raise _refuse(role, f"the store's .agent-id is not the id lineage gives {login}")
    head = _git(store, "rev-parse", "HEAD").stdout.decode().strip()
    if not base:
        raise _refuse(role, "the store has no trusted base (ADR-042)", head)

    commit = _git(store, "log", "-1", "--format=%H", "HEAD", "--", f"settings/roles/{role}/").stdout.decode().strip()
    if not commit:
        raise _refuse(role, "no commit touched the directory", head)
    try:
        trust.verify_signed_by(store, commit, trust.parent_writer(aid, fabric), unknown_key="not signed by the parent's key")
    except StoreError as e:
        raise _refuse(role, f"the last commit on the directory is not the parent's ({e})", commit) from None

    algo = _algo(store)
    rows = _verified_directory(store, role, commit, algo)
    for mode, name, _ in rows:
        if mode != "100644":
            raise _refuse(role, f"{name} is not a plain file (mode {mode}): no link, no subdirectory, no executable", commit)
    files = {name: _object(store, role, "blob", oid, algo, _MAX_BLOB, name) for _, name, oid in rows}
    # The set, not each file: the gloss rules (a stale gloss, a gloss with no
    # addendum, a non-English addendum without its gloss) show only there.
    verdicts = check.validate_set(role, aid, files)
    findings = [f for name in sorted(verdicts) for f in verdicts[name]]
    if findings:
        raise _refuse(role, "; ".join(findings[:5]) + ("; and more" if len(findings) > 5 else ""), commit)

    def decoded(name: str) -> str:
        try:
            return files[name].decode("utf-8")
        except UnicodeDecodeError:
            # Not the exception's own text: it quotes a byte of the content.
            raise _refuse(role, f"{name} is not UTF-8", commit) from None

    def text(name: str) -> tuple[str | None, str | None]:
        """(body, against_digest) of an addendum; validate has accepted it,
        so a frontmatter this cannot read is a validator that disagrees with
        the reader, which stops the launch rather than render a guess."""
        if name not in files:
            return None, None
        full = decoded(name)
        m = _FRONTMATTER_RE.match(full)
        d = _AGAINST_RE.search(m.group(1)) if m else None
        if not m or not d:
            raise _refuse(role, f"{name} passed validation but its frontmatter has no readable against_digest", commit)
        return full[m.end():], d.group(1)

    charter, c_against = text(CHARTER)
    brief, b_against = text(BRIEF)
    try:
        holder = json.loads(decoded(HOLDER)) if HOLDER in files else None
    except ValueError:
        raise _refuse(role, f"{HOLDER} is not JSON", commit) from None
    return Holder(role=role, agent_id=aid, charter=charter, brief=brief, holder=holder,
                  against={n: d for n, d in ((CHARTER, c_against), (BRIEF, b_against)) if d},
                  store_sha=head, addenda_commit=commit)


def _absent(role: str, policy: str, why: str) -> None:
    if policy == "required":
        raise StoreError(f"role {role} is held only with addenda (holders_specialize: required) and {why}: "
                         "the agent's parent installs them (roles-put), then the launch is repeated")
    return None


def store_head(store: str | None = None) -> str | None:
    """The store's HEAD, for fabric-status to compare with the commit the
    launch recorded; None for a store with no commit. A git that fails is an
    error, not None: "unknown" must not read as "unchanged"."""
    store = store or store_dir()
    if not os.path.isdir(os.path.join(store, ".git")):
        return None
    r = _run(["git", "-C", store, "rev-parse", "-q", "--verify", "HEAD"], check=False)
    if r.returncode == 1:
        return None
    if r.returncode != 0:
        raise StoreError(f"{store}: git rev-parse failed (exit {r.returncode})")
    return r.stdout.decode().strip()


def main(argv: list[str] | None = None) -> int:
    """The launcher's entry (launcher/holder.py): `--login L --role R --policy P --out FILE`.
    Exit 0 and nothing written: no addenda, the prompt is today's. Exit 0 and
    FILE written (0600, atomically): the Holder as JSON, and "STORE_SHA
    ADDENDA_COMMIT" on stdout. Exit 1 and one line on stderr: a refusal."""
    ap = argparse.ArgumentParser(prog="addenda.py")
    ap.add_argument("--login", required=True)
    ap.add_argument("--role", required=True)
    ap.add_argument("--policy", default="optional")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    try:
        holder = load(args.login, args.role, args.policy)
    except StoreError as e:
        print(f"addenda: {e}", file=sys.stderr)
        return 1
    if holder is None:
        return 0
    tmp = f"{args.out}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(asdict(holder), fh, ensure_ascii=False)
        os.replace(tmp, args.out)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print(f"{holder.store_sha} {holder.addenda_commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
