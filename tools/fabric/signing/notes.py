"""tools/fabric/signing/notes.py — a commit's timestamp proof as a git note
under refs/notes/fabric-ots (ADR-057 §5 rule 4), and that ref kept level
with a remote's.

CONTRACT
  note      the blob is the proof file, byte for byte (`git notes --ref
            fabric-ots show <commit> | ots info -` reads it). Attached with
            `notes add -f -C <blob>`: -F/-m would strip and re-terminate
            lines, which corrupts a binary file.
  ensure    ensure_note() makes the commit's note the proof of ITS signature:
            one equal to the proof waiting in the spool is left alone (and
            the spool entry dropped); one that is not (git carried it over
            from the commit an amend or a rebase replaced, concatenated
            behind or instead of the new one) is replaced when the spool
            holds this commit's proof and reported STALE when it does not.
            With nothing waiting, a note that is one proof of this signature
            is PRESENT.
  sync      sync_and_push() fetches the remote's notes ref, merges it (notes
            of different commits never conflict; for one commit the local
            note wins) and pushes without force, again when another agent's
            push came first. Every agent pushes to the same ref, which is why
            a bare push of the local one would be refused by the second.
"""
from __future__ import annotations

import enum
import hashlib
import subprocess

from . import proof

REF = "refs/notes/fabric-ots"
GIT_TIMEOUT_S = 120
PUSH_ATTEMPTS = 3


class NotesError(Exception):
    """The message is the whole answer."""


class Status(enum.Enum):
    UNSIGNED = "the commit carries no signature"
    PRESENT = "the note already holds this signature's proof"
    ATTACHED = "the note now holds this signature's proof"
    MISSING = "no proof for this signature is waiting"
    STALE = "the note holds another signature's proof and no proof for this one is waiting"


def git(repo: str, *args: str, input: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess:
    try:
        p = subprocess.run(["git", "-C", repo, *args], capture_output=True, input=input, timeout=GIT_TIMEOUT_S,
                           stdin=None if input is not None else subprocess.DEVNULL)
    except FileNotFoundError:
        raise NotesError("git is not installed") from None
    except subprocess.TimeoutExpired:
        raise NotesError(f"git {args[0]} did not finish within {GIT_TIMEOUT_S} s") from None
    if check and p.returncode != 0:
        tail = [l for l in p.stderr.decode(errors="replace").strip().splitlines() if not l.startswith("hint:")]
        raise NotesError(f"git {' '.join(args[:2])} failed: {(tail or [f'exit {p.returncode}'])[-1]}")
    return p


def commit_signature(raw_commit: bytes) -> bytes | None:
    """The signature in a commit object, unfolded from its header: the
    continuation lines lose their one leading space."""
    head = raw_commit.split(b"\n\n", 1)[0].split(b"\n")
    lines: list[bytes] = []
    inside = False
    for line in head:
        if inside and line.startswith(b" "):
            lines.append(line[1:])
            continue
        inside = line.startswith((b"gpgsig ", b"gpgsig-sha256 ")) and not lines
        if inside:
            lines.append(line.split(b" ", 1)[1])
    return b"\n".join(lines) if lines else None


def _note_blob(repo: str, rev: str) -> str | None:
    p = git(repo, "notes", f"--ref={REF}", "list", rev, check=False)
    return p.stdout.decode().strip() or None if p.returncode == 0 else None


def ensure_note(repo: str, rev: str, spool: proof.Spool) -> tuple[Status, str]:
    """(status, the commit's full id)."""
    commit = git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}").stdout.decode().strip()
    signature = commit_signature(git(repo, "cat-file", "commit", commit).stdout)
    if signature is None:
        return Status.UNSIGNED, commit
    key = proof.key_of(signature)
    blob = _note_blob(repo, commit)
    held = git(repo, "cat-file", "blob", blob).stdout if blob else None
    waiting = spool.get(key)
    if waiting is not None and not proof.matches(signature, waiting):
        waiting = None
    # The spool entry is the clean copy and is dropped only once the note
    # is seen to equal it: git may still carry another note over onto the
    # commit after this one was attached (an amend), and a note that
    # merely starts with the right proof is not equal.
    if waiting is not None and held == waiting:
        spool.drop(key)
        return Status.PRESENT, commit
    if waiting is None:
        if held is not None and proof.matches(signature, held):
            return Status.PRESENT, commit
        return (Status.STALE if held is not None else Status.MISSING), commit
    new = git(repo, "hash-object", "-w", "--stdin", input=waiting).stdout.decode().strip()
    git(repo, "notes", f"--ref={REF}", "add", "-f", "-C", new, commit)
    return Status.ATTACHED, commit


def _remote_has_ref(repo: str, remote: str) -> bool:
    out = git(repo, "ls-remote", remote, REF).stdout.decode().strip()
    return bool(out)


def sync_and_push(repo: str, remote: str) -> bool:
    """False when there was nothing to push (no local notes ref)."""
    if git(repo, "rev-parse", "--verify", "--quiet", REF, check=False).returncode != 0:
        return False
    # A name of its own per remote, stable across runs: a leftover from a
    # killed sync is overwritten by the next, never accumulated.
    scratch = "refs/fabric-ots-sync/" + hashlib.sha1(remote.encode()).hexdigest()[:12]
    last = ""
    for _ in range(PUSH_ATTEMPTS):
        if _remote_has_ref(repo, remote):
            git(repo, "fetch", "--quiet", "--no-tags", remote, f"+{REF}:{scratch}")
            git(repo, "notes", f"--ref={REF}", "merge", "-s", "ours", "--quiet", scratch)
            git(repo, "update-ref", "-d", scratch)
        p = git(repo, "push", "--quiet", remote, f"{REF}:{REF}", check=False)
        if p.returncode == 0:
            return True
        last = (p.stderr.decode(errors="replace").strip().splitlines() or [f"exit {p.returncode}"])[-1]
    raise NotesError(f"{REF} was not pushed to {remote} after {PUSH_ATTEMPTS} attempts ({last})")
