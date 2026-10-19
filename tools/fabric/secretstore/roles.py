"""tools/fabric/secretstore/roles.py — the parent installs a holder's addenda (ADR-060 §5 rule 3).
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
          addenda_check.validate_set on the files (the gloss rules among them);
          an addendum with no readable against_digest in its frontmatter; an
          addendum not in English without both review passes by language-culture-<key> (<key> the locale whose locale.json tag has the addendum's lang: ka-GE, ge),
          pass-1 naming the sha256 of the addendum, pass-2 that or its gloss's; any other Reviewed-By is refused, so a set
          with no such addendum, a retirement included, takes none (an install-time gate: the render does not check it).
  refused under the mirror's write lock, before anything is written: a mirror
          with uncommitted changes, with no remote, with no trusted base, whose
          .agent-id is not the child's, or whose HEAD is not the remote's main
          as just fetched (behind it: refresh-mirror first; ahead or diverged: reset
          the mirror to its remote); a link on the way to settings/roles/<role>, or a
          file where a directory belongs.
  effect  ONE commit signed with the parent's own key ("parent <login>: roles-put <role>"
          or "roles-retire <role>"), pushed. Trailers, in this order: Addendum-Role,
          Authored-By (the child's login unless given: the holder drafts its own
          addendum, rule 9), one Reviewed-By per pass ("<login> pass-<n> <sha256>"),
          Owner-Approval, and one Against-Digest per addendum ("<file> <digest>").
          Nothing changed is no commit. A push that fails puts the mirror back
          to its remote, since the mirror is the parent's view and no record.
  result  {"child", "agent_id", "role", "files", "changed", "commit"}.
  staged  what git staged below settings/roles/<role> is read back and must be the files given, byte for byte
          (an ignore rule or a filter would otherwise commit less or other than was validated).
  signals Ctrl-C, SIGTERM and SIGHUP undo the write (to HEAD before the commit, to the remote's main after it) and
          end as a one-line refusal; SIGKILL leaves the mirror dirty, which the next run refuses by name."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal

import addenda_check
from .core import LOGIN_RE, StoreError, children_dir, git, login, own_agent_id, roots, _run
from .entries import _after_commit, _branch, _remote, _require_clean
from .keys import key_of_store
from .lock import write_lock
from .mirrors import resolve
from .settings import _destination, _put_file, _read_blobs, _read_tree, _terminate
from .trust import _commit, _full, _git_env, _is_ancestor, _no_base, trusted_base

ROLE_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
# One line, no whitespace inside a decision reference or a MESSAGE-ID; a trailer value is read by a parser.
APPROVAL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#@-]{0,199}$")
REVIEW_RE = re.compile(r"^([a-z][a-z0-9_-]{0,31}) (pass-[0-9]{1,2}) ([0-9a-f]{64})$")
ADDENDA = ("charter-addendum.md", "brief-addendum.md")


def against_digest(name: str, raw: bytes) -> str:
    """The `against_digest` of an addendum's frontmatter, or a StoreError: an install that cannot name what the
    text was written against records nothing. Read by the validator's own frontmatter parser, the one the launch
    reads it with too: what install accepts, render accepts."""
    try:
        value = addenda_check.frontmatter(raw.decode("utf-8")).get("against_digest")
    except UnicodeDecodeError:
        raise StoreError(f"{name}: not UTF-8, so no against_digest; nothing written") from None
    if value is None:
        raise StoreError(f"{name}: no against_digest in its frontmatter (or no frontmatter); nothing written")
    if not addenda_check.DIGEST_RE.fullmatch(value):
        raise StoreError(f"{name}: against_digest is not a digest; nothing written")
    return value


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


def _locale_keys(lang: str, fabric: str | None) -> list[str]:
    """The keys of the language-culture locales whose locale.json `tag` is in `lang`: the tag ka-GE is in ka, so ka's
    key is ge (ADR-060 §5 rule 6).
    A locale.json that cannot be read is a refusal naming it, never a locale that is skipped: skipping it would
    answer "no reviewer for this language" for a reason the operator cannot see."""
    base = os.path.join(roots.role_dir("language-culture", root=fabric), "locale")
    keys = []
    try:
        names = sorted(os.listdir(base))
    except OSError as e:
        raise StoreError(f"the language-culture locales cannot be listed ({base}: {e.strerror}); nothing written") from None
    for key in names:
        path = os.path.join(base, key, "locale.json")
        if not os.path.isdir(os.path.join(base, key)):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                tag = json.load(fh)["tag"]
            if not isinstance(tag, str) or not tag:
                raise ValueError("tag is not a string")
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise StoreError(f"{path} has no readable tag ({e}); nothing written") from None
        if tag.split("-")[0].lower() == lang.lower():
            keys.append(key)
    return keys


def _unreviewed(plain: dict[str, bytes], reviewed_by: list[str], fabric: str | None) -> list[str]:
    """Rule 9: a text in another language is read in both passes of ADR-027 §5 rule 3 by language-culture-<key>
    (the role's login, with an instance number if it has one), <key> the locale whose tag has the text's `lang`. Pass one read the text alone, so it names the sha256 of
    that addendum; pass two read it against its English gloss, so it names the sha256 of the addendum or of the gloss.
    A set with such a text records no pass over anything else: a Reviewed-By line is a statement of what was read.
    An install-time gate only: the render never sees the passes, so a commit signed without roles-put renders
    unreviewed; the signing parent is what rule 3 trusts for that.
    A set that validated has a lang to read; a file without one never gets here with the real validator."""
    sha = lambda name: hashlib.sha256(plain[name]).hexdigest()  # noqa: E731
    reviews = [r.split() for r in reviewed_by]
    findings = []
    judges = []   # (reviewer login pattern, the digests each pass may name) per non-English addendum
    for name in ADDENDA:
        lang = addenda_check.frontmatter(plain[name].decode("utf-8")).get("lang", "en") if name in plain else "en"
        if lang == "en":
            continue
        gloss = name.replace(".md", ".gloss.en.md")
        allowed = {"pass-1": {sha(name)}, "pass-2": {sha(name)} | ({sha(gloss)} if gloss in plain else set())}
        keys = _locale_keys(lang, fabric)
        if not keys:
            findings.append(f"{name}: its lang is carried by no language-culture locale (no locale.json tag has it), "
                            "so no reviewer can be named (ADR-060 rule 6)")
            continue
        who = "|".join(re.escape(k) for k in keys)
        reviewer = re.compile(rf"language-culture-(?:{who})(-[0-9]+)?")
        judges.append((reviewer, allowed))
        for n in ("pass-1", "pass-2"):
            if not any(reviewer.fullmatch(login) and which == n and digest in allowed[n] for login, which, digest in reviews):
                findings.append(f"{name}: not in English, so it needs --reviewed-by 'language-culture-{'|'.join(keys)} {n} <sha256 of "
                                f"{'the addendum' if n == 'pass-1' else 'the addendum or its gloss'}>' (ADR-060 rule 9)")
    # A Reviewed-By line becomes a trailer in the parent-signed commit and says that this login read this text in this
    # pass: so each line is a pass-1 or pass-2 by the reviewer of some non-English addendum over a digest that pass may
    # name, and nothing else. A set with no such addendum (English only, or a holder.json beside it, or a retirement)
    # records no pass at all.
    findings += [f"--reviewed-by {r[0]} {r[1]}: not a pass by its language's reviewer over a non-English addendum or its English gloss"
                 + ("" if judges else " (this install has none, so it records no pass)") for r in reviews
                 if not any(rev.fullmatch(r[0]) and r[2] in allowed.get(r[1], ()) for rev, allowed in judges)]
    return findings


def _checked_files(role: str, aid: str, files: dict[str, bytes], retire: bool, reviewed_by: list[str],
                   fabric: str | None = None) -> None:
    if retire and files:
        raise StoreError("--retire takes an empty directory: a retirement installs nothing; nothing written")
    if not retire and not files:
        raise StoreError("the directory holds no file; a retirement is an empty directory with --retire; nothing written")
    plain = {n: raw for n, raw in files.items() if os.sep not in n and not n.startswith(".")}
    found = [f"{n}: addenda are plain files directly in settings/roles/{role}/" for n in sorted(set(files) - set(plain))]
    # The set, not each file: a stale gloss, a gloss with no addendum and a non-English addendum with no gloss
    # are only visible together (ADR-060 rules 1 and 9).
    found += [f"{n}: {f}" for n, fs in sorted(addenda_check.validate_set(role, aid, plain).items()) for f in fs]
    if not found:
        found += _unreviewed(plain, reviewed_by, fabric)
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
        fix = (f"fabric-secrets store refresh-mirror {aid} first" if how.startswith("is behind") else
               f"a mirror is the parent's view and no record: git -C {mirror} reset --hard origin/{branch}, then again")
        raise StoreError(f"the mirror {how}; nothing written — {fix}")
    if not _is_ancestor(mirror, base, head):
        raise StoreError(f"the mirror's head {head[:12]} does not descend from its trusted base {base[:12]}; nothing written — "
                         "the owner, after checking the head against the remote, records it again: "
                         f"fabric-secrets store trust-base --replace-orphaned --store {mirror}")
    # HEAD is the remote's tip, which the last refresh-mirror (or the last install here) verified: a
    # _verify_incoming of it would find no commit it neither holds nor trusts, and prove nothing.


def _staged_as_given(mirror: str, rel: str, files: dict[str, bytes]) -> None:
    """What git staged below settings/roles/<role> is the files given, byte for byte: an ignore rule in the
    child's store (or the parent's own excludes) drops a file from `git add` with exit 0, and a filter
    (.gitattributes) changes the bytes — either way the commit would not hold what was validated while its
    trailers say it did."""
    out = git(mirror, "ls-files", "-s", "-z", "--", os.path.join("settings", rel)).stdout.decode("utf-8", "surrogateescape")
    staged = {}
    for entry in filter(None, out.split("\0")):
        meta, _, path = entry.partition("\t")
        staged[os.path.basename(path)] = meta.split()[1]
    if sorted(staged) != sorted(files):
        raise StoreError(f"git staged {sorted(staged) or 'nothing'} of settings/{rel}, not {sorted(files) or 'nothing'} "
                         "(an ignore rule in the store?); nothing written")
    blobs = _read_blobs(mirror, {name: oid for name, oid in staged.items()}) if staged else {}
    for name, data in files.items():
        if blobs[name] != data:
            raise StoreError(f"settings/{rel}/{name} was changed by a git filter on its way into the commit; nothing written")


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
    _checked_files(role, aid, files, retire, reviewed_by, fabric)
    for n in ADDENDA:   # an addendum that names no digest is refused before the mirror is looked at
        if n in files:
            against_digest(n, files[n])
    mirror = mirror or os.path.join(children_dir(), aid)
    if not os.path.isdir(os.path.join(mirror, ".git")):
        raise StoreError(f"no mirror of {rec.get('login')} here (store_enroll.py first); nothing written")
    key_of_store()   # a parent that cannot sign stops here, before the mirror is touched
    rel = os.path.join("roles", role)
    previous = {sig: signal.signal(sig, _terminate) for sig in (signal.SIGTERM, signal.SIGHUP)
                if signal.getsignal(sig) != signal.SIG_IGN}
    try:
        with write_lock(mirror):
            return _install(mirror, aid, rec, role, rel, files, approval, reviewed_by, authored_by, retire)
    except KeyboardInterrupt as e:
        raise StoreError(f"interrupted ({str(e) or 'Ctrl-C'}); the mirror was put back to its remote — nothing is installed") from None
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def _install(mirror: str, aid: str, rec: dict, role: str, rel: str, files: dict[str, bytes], approval: str,
             reviewed_by: list[str], authored_by: str | None, retire: bool) -> dict:
    digests = [(n, against_digest(n, files[n])) for n in ADDENDA if n in files]
    _require_clean(mirror)
    _synced(mirror, aid)
    here = _destination(mirror, rel)   # a link on the way to settings/roles/<role> would carry the write out of it
    for part in (os.path.join(mirror, "settings"), os.path.join(mirror, "settings", "roles"), here):
        if os.path.lexists(part) and not os.path.isdir(part):
            raise StoreError(f"{os.path.relpath(part, mirror)} is a file in the mirror, not a directory; nothing written")
    dests = {name: _destination(mirror, os.path.join(rel, name)) for name in files}
    head = git(mirror, "rev-parse", "HEAD").stdout
    committed = False
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
        _staged_as_given(mirror, rel, files)
        changed = git(mirror, "diff", "--cached", "--quiet", check=False).returncode != 0
        if changed:
            _commit(mirror, _message(rec["login"], role, retire, authored_by or rec["login"], reviewed_by,
                                     approval, digests))
            committed = True
        # After the commit, a failed or interrupted push is undone to the remote: the mirror is the parent's
        # view of the child's store, never a record of its own (as put).
        if changed:
            _after_commit(mirror)
    except BaseException as e:
        _put_back(mirror, rel, head if not committed and git(mirror, "rev-parse", "HEAD").stdout == head else None)
        if isinstance(e, OSError):
            raise StoreError(f"{e.filename or 'settings'}: {e.strerror or e}; nothing written") from None
        raise
    commit = git(mirror, "rev-parse", "--short", "HEAD").stdout.decode().strip() if changed else None
    return {"child": rec.get("login"), "agent_id": aid, "role": role, "files": sorted(files),
            "changed": changed, "commit": commit}


def _put_back(mirror: str, rel: str, unmoved: bytes | None) -> None:
    """The mirror as it was: to HEAD when no commit was made, else to the remote's main (the commit was never
    pushed, or the push did not finish). Ignored files this run wrote are removed too (clean -x)."""
    old = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGHUP, signal.SIGINT})
    try:
        target = "HEAD" if unmoved is not None else f"origin/{_branch(mirror)}"
        r = git(mirror, "reset", "-q", "--hard", target, check=False)
        git(mirror, "clean", "-fdxq", "--", os.path.join("settings", rel), check=False)
        if r.returncode != 0:
            raise StoreError(f"the install failed, and the mirror could not be reset ({mirror}) — reset it to its remote "
                             "before the next install")
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, old)
