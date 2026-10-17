"""tools/fabric/secretstore/roles.py — the parent installs a holder's addenda (agent-fabric ADR-060 §5 rule 3).
A part of secret_store.py's family; the CLI is secret_child.py.

Contract of `roles_put(child, role, src, approval, ...)`:
  input   a directory whose files become settings/roles/<role>/ in the
          child's store, whole: a file the store holds there and the directory
          does not is removed. An empty directory with retire=True removes the
          role's addenda (ADR-060 rule 11); an empty one without it is refused,
          and a retirement with files in it too.
  runs on the parent's mirror of the child, ~/.local/share/agent-fabric/
          children/<id>, as the child's parent: the lineage must name this
          account's agent id as the child's parent.
  refused before the mirror is touched, each saying "nothing written": a role,
          approval, reviewer or author that is not one line of the shape
          below; a source that settings._read_tree refuses; a file in a
          subdirectory or whose name starts with a dot; any finding of
          addenda_check.validate on any file; an addendum with no readable
          against_digest in its frontmatter.
  refused under the mirror's write lock, before anything is written: a mirror
          with uncommitted changes, with no remote, with no trusted base, whose
          .agent-id is not the child's, or whose HEAD is not the remote's main
          as just fetched (behind it, ahead of it, or diverged: refresh-mirror
          first); a link on the way to settings/roles/<role>.
  effect  ONE commit signed with the parent's own key ("parent <login>: roles-put <role>"
          or "roles-retire <role>"), pushed. Trailers, in this order: Addendum-Role,
          Authored-By (the child's login unless given: the holder drafts its own
          addendum, rule 9), one Reviewed-By per pass ("<login> pass-<n> <sha256>"),
          Owner-Approval, and one Against-Digest per addendum ("<file> <digest>").
          Nothing changed is no commit. A push that fails puts the mirror back
          to its remote, since the mirror is the parent's view and no record.
  result  {"child", "agent_id", "role", "files", "changed", "commit"}.
SIGKILL leaves the mirror dirty, which the next run refuses by name."""
from __future__ import annotations

import os
import re
import shutil

import addenda_check
from .core import LOGIN_RE, StoreError, children_dir, git, login, own_agent_id, _run
from .entries import _after_commit, _branch, _remote, _require_clean
from .keys import key_of_store
from .lock import write_lock
from .mirrors import resolve
from .settings import _destination, _put_file, _read_tree
from .trust import _commit, _full, _git_env, _is_ancestor, _no_base, _verify_incoming, trusted_base

ROLE_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
# One line, no whitespace inside a decision reference or a MESSAGE-ID; a trailer value is read by a parser.
APPROVAL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#@-]{0,199}$")
REVIEW_RE = re.compile(r"^([a-z][a-z0-9_-]{0,31}) (pass-[0-9]{1,2}) ([0-9a-f]{64})$")
DIGEST_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z:._-]{0,127}$")
ADDENDA = ("charter-addendum.md", "brief-addendum.md")


def against_digest(name: str, raw: bytes) -> str:
    """The `against_digest` of an addendum's frontmatter, or a StoreError:
    an install that cannot name what the text was written against records nothing."""
    lines = raw.decode("utf-8", "replace").replace("\r\n", "\n").split("\n")
    if lines[:1] != ["---"] or "---" not in lines[1:]:
        raise StoreError(f"{name}: no frontmatter, so no against_digest; nothing written")
    for line in lines[1:lines.index("---", 1)]:
        key, sep, value = line.partition(":")
        if sep and key.strip() == "against_digest":
            value = value.strip().strip("'\"")
            if not DIGEST_RE.fullmatch(value):
                raise StoreError(f"{name}: against_digest is not a digest; nothing written")
            return value
    raise StoreError(f"{name}: its frontmatter has no against_digest; nothing written")


def _checked_args(role: str, approval: str, reviewed_by: list[str], authored_by: str | None) -> None:
    if not ROLE_RE.fullmatch(role):
        raise StoreError(f"{role!r} is not a role slug; nothing written")
    if not APPROVAL_RE.fullmatch(approval):
        raise StoreError("--approval is one token (a decision or a MESSAGE-ID), no spaces; nothing written")
    for r in reviewed_by:
        if not REVIEW_RE.fullmatch(r):
            raise StoreError("--reviewed-by is 'login pass-N sha256' (the sha256 of the text read, 64 hex); nothing written")
    if authored_by is not None and not LOGIN_RE.fullmatch(authored_by):
        raise StoreError(f"--authored-by {authored_by!r} is not a login; nothing written")


def _checked_files(role: str, aid: str, files: dict[str, bytes], retire: bool) -> None:
    if retire and files:
        raise StoreError("--retire takes an empty directory: a retirement installs nothing; nothing written")
    if not retire and not files:
        raise StoreError("the directory holds no file; a retirement is an empty directory with --retire; nothing written")
    found = []
    for name, raw in sorted(files.items()):
        if os.sep in name or name.startswith("."):
            found.append(f"{name}: addenda are plain files directly in settings/roles/{role}/")
            continue
        found += [f"{name}: {f}" for f in addenda_check.validate(role, aid, name, raw)]
    if found:
        raise StoreError("the addenda are refused, nothing written: " + "; ".join(found))


def _synced(mirror: str, aid: str) -> None:
    """The mirror is exactly the remote's verified main, or nothing is installed on it (rule 3): a commit
    on a stale head would be refused at the push, or worse, rebuilt on history nobody has verified."""
    if own_agent_id(mirror) != aid:
        raise StoreError(f"{mirror} is not the mirror of agent {aid}; nothing written")
    if not _remote(mirror):
        raise StoreError(f"{mirror} has no remote to push its commit to; nothing written")
    base = trusted_base(mirror)
    if not base:
        raise _no_base(mirror)
    branch = _branch(mirror)
    r = _run(["git", "-C", mirror, "fetch", "-q", "origin", f"+{branch}:refs/remotes/origin/{branch}"], env=_git_env(), check=False)
    if r.returncode != 0:
        lines = [l for l in r.stderr.decode(errors="replace").splitlines() if l.strip()]
        raise StoreError("the mirror could not be compared with its remote; nothing written: " + (lines or ["?"])[-1])
    tip, head = _full(mirror, f"refs/remotes/origin/{branch}"), _full(mirror, "HEAD")
    if tip != head:
        how = ("is behind its remote" if _is_ancestor(mirror, head, tip)
               else "is ahead of its remote" if _is_ancestor(mirror, tip, head) else "has diverged from its remote")
        raise StoreError(f"the mirror {how}; nothing written — fabric-secrets store refresh-mirror {aid} first")
    if not _is_ancestor(mirror, base, head):
        raise StoreError(f"the mirror's head does not descend from its trusted base {base[:12]}; nothing written")
    _verify_incoming(mirror, tip, aid)


def _message(child: str, role: str, retire: bool, authored_by: str, reviewed_by: list[str], approval: str,
             digests: list[tuple[str, str]]) -> str:
    trailers = [f"Addendum-Role: {role}", f"Authored-By: {authored_by}",
                *(f"Reviewed-By: {r}" for r in reviewed_by), f"Owner-Approval: {approval}",
                *(f"Against-Digest: {name} {digest}" for name, digest in digests)]
    return f"parent {login()}: {'roles-retire' if retire else 'roles-put'} {role} of {child}\n\n" + "\n".join(trailers)


def roles_put(child: str, role: str, src: str, approval: str, *, reviewed_by: list[str] = (),
              authored_by: str | None = None, retire: bool = False, fabric: str | None = None,
              mirror: str | None = None) -> dict:
    reviewed_by = list(reviewed_by)
    _checked_args(role, approval, reviewed_by, authored_by)
    aid, rec = resolve(child, fabric=fabric)
    me = own_agent_id()
    if not me or rec.get("parent") != me:
        raise StoreError(f"{rec.get('login')} is not this account's child in identities/keys/lineage.json; "
                         "only an agent's parent installs its addenda (ADR-060); nothing written")
    files = _read_tree(src, allow_empty=True)   # _checked_files says what an empty one means
    _checked_files(role, aid, files, retire)
    digests = [(n, against_digest(n, files[n])) for n in ADDENDA if n in files]
    mirror = mirror or os.path.join(children_dir(), aid)
    if not os.path.isdir(os.path.join(mirror, ".git")):
        raise StoreError(f"no mirror of {rec.get('login')} here (store-enroll.sh first); nothing written")
    key_of_store()   # a parent that cannot sign stops here, before the mirror is touched
    rel = os.path.join("roles", role)
    with write_lock(mirror):
        _require_clean(mirror)
        _synced(mirror, aid)
        here = _destination(mirror, rel)   # a link on the way to settings/roles/<role> would carry the write out of it
        dests = {name: _destination(mirror, os.path.join(rel, name)) for name in files}
        head = git(mirror, "rev-parse", "HEAD").stdout
        try:
            if os.path.isdir(here):
                shutil.rmtree(here)
            for name, data in sorted(files.items()):
                _put_file(dests[name], data)
            # Deletions staged first, then what exists: `git add -A` refuses a pathspec nothing matches, and a
            # retirement of what is already gone is "unchanged", not an error.
            git(mirror, "rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", os.path.join("settings", rel))
            if files:
                git(mirror, "add", "--", os.path.join("settings", rel))
            changed = git(mirror, "diff", "--cached", "--quiet", check=False).returncode != 0
            if changed:
                _commit(mirror, _message(rec["login"], role, retire, authored_by or rec["login"], reviewed_by,
                                         approval, digests))
        except BaseException:
            if git(mirror, "rev-parse", "HEAD").stdout == head:
                git(mirror, "reset", "-q", "--hard", "HEAD", check=False)
                git(mirror, "clean", "-fdq", "--", os.path.join("settings", rel), check=False)
            raise
        commit = None
        if changed:
            commit = git(mirror, "rev-parse", "--short", "HEAD").stdout.decode().strip()
            try:
                _after_commit(mirror)
            except StoreError as pushed:
                # As put: the mirror is the parent's view of the child's store, never a record of its own.
                r = git(mirror, "reset", "-q", "--hard", f"origin/{_branch(mirror)}", check=False)
                if r.returncode != 0:
                    raise StoreError(f"{pushed}; and the mirror could not be reset to its remote ({mirror}) — "
                                     "reset it before the next install") from pushed
                raise
        return {"child": rec.get("login"), "agent_id": aid, "role": role, "files": sorted(files),
                "changed": changed, "commit": commit}
