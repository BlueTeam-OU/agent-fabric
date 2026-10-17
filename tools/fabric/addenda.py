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
          but plain files; a file addendum_check.validate has a finding on.
          Tamper is never read as absence (rule 7).
  reads   git objects at HEAD only (ls-tree, cat-file blob): never the
          working tree, never env/, never a decryption. The one gpg call is
          verify-commit in a temporary GNUPGHOME that holds the parent's
          public key alone (trust.verify_signed_by).
  writes  nothing.

Why HEAD and not the working tree: the rendered text must be the text the
parent installed and signed; a file edited in the checkout, or left
untracked, is neither. Why the last commit on the directory and not every
commit: the store's other writes are the agent's own (rule 3 of ADR-042),
and only this path is the parent's alone.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass

# The launcher runs this as a script under -I, which puts no directory on
# sys.path; secret_store.py does the same for the parts it loads.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re  # noqa: E402

import addenda_check as check  # noqa: E402
from secretstore import mirrors, trust  # noqa: E402
from secretstore.core import StoreError, _run, git, store_dir, own_agent_id

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


def _directory(store: str, role: str) -> str | None:
    """The oid of settings/roles/<role> at HEAD; None when the store has no
    commit or no such path. A path that is not a directory, or a git that
    fails, is no absence."""
    rel = f"HEAD:settings/roles/{role}"
    r = git(store, "rev-parse", "-q", "--verify", rel, check=False)
    if r.returncode == 1:
        return None
    if r.returncode != 0:
        raise _refuse(role, f"the store could not be read (git exit {r.returncode})")
    kind = git(store, "cat-file", "-t", rel).stdout.decode().strip()
    if kind != "tree":
        raise _refuse(role, f"settings/roles/{role} is a {kind}, not a directory")
    return r.stdout.decode().strip()


def _entries(store: str, role: str) -> list[tuple[str, str, str, str]]:
    out = git(store, "ls-tree", "-z", f"HEAD:settings/roles/{role}").stdout.decode("utf-8", "surrogateescape")
    rows = []
    for rec in filter(None, out.split("\0")):
        meta, _, name = rec.partition("\t")
        mode, kind, oid = meta.split()
        rows.append((mode, kind, oid, name))
    return rows


def _blob(store: str, role: str, name: str, oid: str) -> bytes:
    size = int(git(store, "cat-file", "-s", oid).stdout.decode())
    if size > _MAX_BLOB:
        raise _refuse(role, f"{name} is {size} bytes, over the limit")
    return git(store, "cat-file", "blob", oid).stdout


def load(login: str, role: str, policy: str = "optional", *, store: str | None = None,
         fabric: str | None = None) -> Holder | None:
    if policy not in POLICIES:
        raise StoreError(f"holders_specialize of role {role} is {policy!r}, not one of {', '.join(POLICIES)}")
    if not _ROLE_RE.fullmatch(role):
        raise StoreError(f"{role!r} is no role name")
    store = store or store_dir()
    if not os.path.isdir(os.path.join(store, ".git")):
        return _absent(role, policy, "this account has no store")
    if _directory(store, role) is None:
        return _absent(role, policy, "the store has no settings/roles/" + role)

    aid, _ = mirrors.resolve(login, fabric=fabric)
    if own_agent_id(store) != aid:
        raise _refuse(role, f"the store's .agent-id is not the id lineage gives {login}")
    head = git(store, "rev-parse", "HEAD").stdout.decode().strip()
    base = trust.trusted_base(store)
    if not base:
        raise _refuse(role, "the store has no trusted base (ADR-042)", head)
    if not trust._is_ancestor(store, base, head):
        raise _refuse(role, "the store's HEAD does not descend from its trusted base", head)

    commit = git(store, "log", "-1", "--format=%H", "HEAD", "--", f"settings/roles/{role}/").stdout.decode().strip()
    if not commit:
        raise _refuse(role, "no commit touched the directory", head)
    # `git log -1 -- <path>` follows history simplification: the commit it
    # names has the path exactly as HEAD does, so its signature is evidence
    # about the bytes read below (a merge shows only when it changed the path).
    try:
        trust.verify_signed_by(store, commit, trust.parent_writer(aid, fabric))
    except StoreError as e:
        raise _refuse(role, f"the last commit on the directory is not the parent's ({e})", commit) from None

    rows = _entries(store, role)
    for mode, kind, _, name in rows:
        if (mode, kind) != ("100644", "blob"):
            raise _refuse(role, f"{name} is not a plain file (mode {mode}, {kind}): no link, no subdirectory, no executable", commit)
    files = {name: _blob(store, role, name, oid) for _, _, oid, name in rows}
    findings = [f for name in sorted(files) for f in check.validate(role, aid, name, files[name])]
    if findings:
        raise _refuse(role, "; ".join(findings[:5]) + ("; and more" if len(findings) > 5 else ""), commit)

    def text(name: str) -> tuple[str | None, str | None]:
        """(body, against_digest) of an addendum; validate has accepted it,
        so a frontmatter this cannot read is a validator that disagrees with
        the reader, which stops the launch rather than render a guess."""
        if name not in files:
            return None, None
        full = files[name].decode("utf-8")
        m = _FRONTMATTER_RE.match(full)
        d = _AGAINST_RE.search(m.group(1)) if m else None
        if not m or not d:
            raise _refuse(role, f"{name} passed validation but its frontmatter has no readable against_digest", commit)
        return full[m.end():], d.group(1)

    charter, c_against = text(CHARTER)
    brief, b_against = text(BRIEF)
    return Holder(role=role, agent_id=aid, charter=charter, brief=brief,
                  holder=json.loads(files[HOLDER]) if HOLDER in files else None,
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
