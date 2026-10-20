#!/usr/bin/env python3
"""tools/fabric/guards/ban_unsigned_commits.py -- every commit a push or a
branch adds carries a signature git can read; and, once a repository is cut
over (policies/signing.json `since`), every commit a branch adds that `since`
does not reach is signed by its own agent, for a role that agent may hold,
with its timestamp proof beside it (agent-fabric ADR-057 §5 rule 5) -- or is
one of the two kinds of commit the forge makes that rule 8 admits.

WHY. The GitHub ruleset blocks an unsigned commit from merging, but only
after the push. A history rewrite made with git plumbing (commit-tree,
filter-branch) ignores commit.gpgsign: on 2026-10-11 one pushed 36 unsigned
commits that the ruleset then refused to merge. The guard is three things
(policies/AUTHORITY.md): the pre-push hook (githooks_prepush.py calls
`unsigned` for the refs pushed), this entry point for CI (the commits the
branch adds, the range found as ban_generated_by_attribution finds it), and
tests/test_ban_unsigned_commits.py, tests/test_signing_rule5.py.

"SIGNED" IS A SIGNATURE HEADER IN THE COMMIT OBJECT, not git's `%G?`.
Whether the signer's key is known is not asked by `unsigned`: CI has no
keyring, so a good OpenPGP signature reads `E` there; and an SSH signature
reads `N` (no signature) wherever gpg.ssh.allowedSignersFile is unset, which
is every clone, so `%G?` would refuse every SSH-signed commit as unsigned.
This part applies before and after a cut-over.

RULE 5, after `since`. Until ADR-057 every fleet commit was signed by one
shared key, so a signature said nothing about which agent made a commit. For
each commit the branch adds that `since` does not reach, `judge` refuses it
unless ALL of:
  - it carries a signature, in the format the policy gives the repository;
  - that signature verifies against a signing subkey (OpenPGP) or that
    subkey's SSH form (SSH, principal = the agent id) of an agent key under
    identities/keys/, in a keyring built here from those files alone;
  - that agent's chain in identities/keys/lineage.json verifies to the root
    (secretstore/lineage.py verify(): no finding names it or an ancestor,
    and none names no one), and neither its key nor an ancestor's is revoked
    in its committed file;
  - its last `Fabric-Role:` trailer names a role (identities/roles/<role>/)
    the agent may hold: a role authority.json lists is held by its holders
    alone; any other role by a login that is the role's name alone, with
    `-<n>`, or with `-<suffix>` of one of the role's locales;
  - its note under refs/notes/fabric-ots is ONE OpenTimestamps proof whose
    stamped digest is sha256 of this commit's own signature.
A COMMIT THE FORGE MAKES (rule 8) is judged before all of that, the format
included -- the forge signs OpenPGP whatever the repository's format: a good
OpenPGP signature (G or U) by a key policies/signing.json lists under
`forge_keys`, its primary the one in policies/forge-keys/<fingerprint>.asc,
names no agent, no role and no proof, and passes only as
  - a merge of exactly two parents whose tree is `git merge-tree
    --write-tree` of them (exit 0), with no merge attributes from the
    checkout: "Update branch", whose content is its parents', each judged
    here where the branch adds it; or
  - a commit, not a merge, authored `dependabot[bot]`, whose diff against
    its parent is not empty and lies wholly under .github/workflows/: the
    action-pin carve-out of policies/AUTHORITY.md.
Anything else the forge signed is refused and re-made in a working copy.

THREAT MODEL. Each line is refused, and each has a case in
tests/test_signing_rule5.py that fails when its check is taken out:
  - a commit signed by another account's key, or by the shared owner key
    (6E760A4C55CBA02F) or any key outside the lineage, after `since`;
  - a role trailer the signer may not hold (another agent's role, a role
    with no definition, no trailer at all);
  - a commit with no signature, or in a format the policy does not admit;
  - a key not in the lineage, a key whose certification chain does not
    verify, a revoked key (or a key under a revoked ancestor);
  - a missing proof note, a note holding another signature's proof (a
    forged or carried-over note), a note of two proofs;
  - a range that cannot be resolved (a shallow clone, no base, a `since`
    this clone does not have): a refusal, never a pass;
  - a forge-signed merge that changes something itself (its tree is not
    the clean merge, or its parents conflict: a conflict resolved on the
    web), an octopus, a root commit; a forge-signed commit that is neither
    a merge nor Dependabot's (a web edit, a committed suggestion, a
    squash); Dependabot's commit touching a path outside
    .github/workflows/, or changing nothing, or a merge authored by
    Dependabot that changes something itself;
  - a clean merge signed by an OpenPGP key forge_keys does not list (one
    this keyring verifies included), and one by a listed key whose file is
    missing or is another key: that key's commits alone are refused, an
    agent's still pass.
  Commits reachable from `since` pass as they did. With `since` null nothing
  is refused under rule 5, and an unresolvable range is NOT ENFORCED as it
  always was.
NOT DEFENDED: a forge signature says GitHub made the commit, never who
asked -- any account pushing through the shared GitHub account can have it
made -- so rule 8 admits only what carries nothing of its own; the author
`dependabot[bot]` is text anyone can write, a tripwire bounded by the
.github/workflows/ fence, check_actions_pinned_by_sha and review, as under
the trailer guard; the proof is matched to the signature by the digest it
stamps, not checked against a calendar or Bitcoin (no network, ADR-057 §7); a
private key that leaked signs as its agent until the key is revoked in its
committed file; the data judged by (keys, lineage, holders, the policy) is
the operator root's, so CI must run this from main's tree, never the
branch's (.github/workflows/ci.yml does).

Contract: no arguments; cwd is the repository; env as in
ban_generated_by_attribution (GITHUB_EVENT_PATH, GITHUB_BASE_REF), with
AGENT_FABRIC_SIGNATURES_BASE naming the base ref of a hand run; the
repository the policy is read for is AGENT_FABRIC_SIGNING_REPOSITORY, else
GITHUB_REPOSITORY, else origin's owner/name; the keys, the lineage, the
roles, the holders, the policy and its forge keys are the operator root's
(roots.py: AGENT_FABRIC_OPERATOR, else AGENT_FABRIC_ROOT, else this
checkout). Exit 0
every commit passes (or, `since` null, no range could be shown: said as NOT
ENFORCED, never as OK), 1 a commit refused or, `since` set, no range, with
one line per refusal on stderr."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import common  # noqa: E402
import git  # noqa: E402
import roots  # noqa: E402
import signing_policy  # noqa: E402

SHOWN = 8
WORKFLOWS = ".github/workflows/"
NOTES_REF = "refs/notes/fabric-ots"
GPG_TIMEOUT_S = 60
# The proof file's head, as tools/fabric/signing/proof.py writes it: magic, a
# version byte, the sha256 op, then the stamped digest. Said again here and
# not imported: that package is a contributor's to change and this guard is
# not (lint.py CONTRIBUTOR_NEVER); tests/test_signing_rule5.py holds the two
# to the same answer.
OTS_MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
OTS_HEAD = OTS_MAGIC + b"\x01" + b"\x08"
AGENT_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
ROLE_RE = re.compile(r"^[a-z][a-z0-9-]*\Z")
ROOTS_FINDING_RE = re.compile(r"lineage\.json: [0-9]+ roots \(")


def unsigned(repo: str, *rev_args: str) -> list[tuple[str, str]]:
    """(short sha, subject) of every commit `git log <rev_args>` lists whose
    object carries no signature header. Merges are listed too. Raises
    git.GitError."""
    out = git.run(repo, "log", "--no-show-signature", "--format=%H%x09%s", *rev_args, errors="replace").stdout
    listed = [(sha, subject) for sha, _, subject in (line.partition("\t") for line in out.splitlines() if line)]
    if not listed:
        return []
    # One cat-file for the whole list: a branch of hundreds of commits is
    # one process, not hundreds.
    try:
        p = subprocess.run(["git", "-C", repo, "cat-file", "--batch"], capture_output=True, timeout=git.TIMEOUT_S,
                           input="".join(sha + "\n" for sha, _ in listed).encode())
    except (OSError, subprocess.SubprocessError) as e:
        raise git.GitError("git cat-file", str(e)) from None
    if p.returncode != 0:
        raise git.GitError("git cat-file", p.stderr.decode(errors="replace").strip() or f"exit {p.returncode}")
    data, at, found = p.stdout, 0, []
    for sha, subject in listed:
        nl = data.find(b"\n", at)
        header = data[at:nl].split() if nl >= 0 else []
        if len(header) != 3 or header[1] != b"commit":
            raise git.GitError("git cat-file", f"{sha} is not a readable commit")
        size = int(header[2])
        if commit_signature(data[nl + 1:nl + 1 + size]) is None:
            found.append((sha[:10], subject))
        at = nl + 1 + size + 1
    return found


def refusal(found: list[tuple[str, str]]) -> str:
    names = ", ".join(f"{sha} {subject[:50]}" for sha, subject in found[:SHOWN])
    more = f" and {len(found) - SHOWN} more" if len(found) > SHOWN else ""
    return (f"{len(found)} unsigned commit(s): {names}{more} -- re-sign with "
            "`git rebase --exec 'git commit --amend --no-edit -S' <base>` "
            "(history rewritten by git plumbing ignores commit.gpgsign)")


# --- rule 5 -----------------------------------------------------------------

def commit_signature(raw: bytes) -> bytes | None:
    """The signature in a commit object's header, unfolded (continuation
    lines lose their one leading space), as signing/notes.py reads it."""
    lines: list[bytes] = []
    inside = False
    for line in raw.split(b"\n\n", 1)[0].split(b"\n"):
        if inside and line.startswith(b" "):
            lines.append(line[1:])
            continue
        inside = line.startswith((b"gpgsig ", b"gpgsig-sha256 ")) and not lines
        if inside:
            lines.append(line.split(b" ", 1)[1])
    return b"\n".join(lines) if lines else None


def format_of(signature: bytes) -> str | None:
    if signature.startswith(b"-----BEGIN PGP SIGNATURE-----"):
        return "openpgp"
    if signature.startswith(b"-----BEGIN SSH SIGNATURE-----"):
        return "ssh"
    return None


def proof_matches(signature: bytes, proof: bytes) -> bool:
    """ONE proof, of this signature: git's note carry-over concatenates the
    old note behind the new, and a second proof is not a proof file."""
    head = len(OTS_HEAD)
    if not proof.startswith(OTS_HEAD) or len(proof) < head + 32 or proof.find(OTS_MAGIC, 1) != -1:
        return False
    return proof[head:head + 32] == hashlib.sha256(signature.strip()).digest()


def may_hold(login: str, role: str, holders: list[str] | None, locales: list[str]) -> bool:
    """A role that authority.json lists (`holders` not None) is held by its list
    alone, as charter_authority.is_holder has it -- a login merely NAMED
    fabric-coordinator-N, or fabric-coordinator-<locale>, is whatever a
    provisioner called it. Any other role is held by the convention name,
    name-<n>, or a locale's holder (ADR-057 §5 rule 5)."""
    if holders is not None:
        return login in holders  # not the locales either: a listed role's list is complete
    if re.fullmatch(re.escape(role) + r"(-[0-9]+)?", login):
        return True
    return any(login == f"{role}-{suffix}" for suffix in locales)


def _load_lineage_module():
    # By path, as lint loads it: the module is fenced from contributors and
    # standard-library only, so nothing a branch adds beside it answers here.
    path = os.path.join(os.path.dirname(HERE), "secretstore", "lineage.py")
    spec = importlib.util.spec_from_file_location("fabric_guard_lineage", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Judge:
    """The agents a signature may belong to, built once from the operator
    root's committed keys; `refusals` judges commits against them."""

    def __init__(self, environ: dict[str, str], fmt: str) -> None:
        self.environ, self.format = environ, fmt
        self.fabric = roots.operator_root(environ)
        self.keys = roots.keys_dir(environ=environ)
        self.home = tempfile.mkdtemp(prefix="sig5-")
        self.allowed = os.path.join(self.home, "allowed_signers")
        self.by_subkey: dict[str, str] = {}      # OpenPGP signing subkey fingerprint -> agent id
        self.forge: set[str] = set()             # listed forge key fingerprints whose file loaded as that key
        self.forge_unloaded: dict[str, str] = {}  # listed forge key fingerprint -> why it did not load
        self.excluded: dict[str, str] = {}       # agent id -> why its signatures are refused
        self._build()

    def close(self) -> None:
        try:
            subprocess.run(["gpgconf", "--homedir", self.home, "--kill", "all"], capture_output=True, timeout=GPG_TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired):
            pass
        shutil.rmtree(self.home, ignore_errors=True)

    def _gpg(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["gpg", "--homedir", self.home, "--batch", "--no-tty", *args], capture_output=True,
                              timeout=GPG_TIMEOUT_S, stdin=subprocess.DEVNULL)

    def _load_forge_keys(self) -> None:
        """Into this keyring, each forge key whose file holds that key alone.
        A key that does not load is recorded, not made a global problem: its
        commits are refused and an agent's are judged as ever."""
        try:
            listed = signing_policy.load(roots.policy("signing.json", environ=self.environ)).get("forge_keys") or {}
        except signing_policy.PolicyError as e:
            # main() has refused already; a Judge used alone admits no forge key.
            self.forge_unloaded["*"] = str(e)
            return
        for fpr in sorted(listed):
            path = roots.policy(os.path.join(signing_policy.FORGE_KEYS_DIR, f"{fpr}.asc"), environ=self.environ)
            if not os.path.isfile(path):
                self.forge_unloaded[fpr] = f"policies/{signing_policy.FORGE_KEYS_DIR}/{fpr}.asc is missing"
                continue
            # Read before imported: a file that is another key, or carries a
            # second one, would put a key in this keyring under the listed name.
            try:
                held = signing_policy.key_file_primaries(path, self.home, GPG_TIMEOUT_S)
            except (OSError, subprocess.SubprocessError) as e:
                self.forge_unloaded[fpr] = f"gpg could not read its file ({e})"
                continue
            if held != [fpr]:
                self.forge_unloaded[fpr] = f"its file holds {', '.join(held) or 'no key'}, not that key alone"
                continue
            if self._gpg("--import", path).returncode != 0 or self._gpg("--list-keys", fpr).returncode != 0:
                self.forge_unloaded[fpr] = "its file does not import"
                continue
            self.forge.add(fpr)

    def _build(self) -> None:
        os.chmod(self.home, 0o700)
        # First, and whatever becomes of the lineage below: a forge commit
        # names no agent, so a lineage that cannot be read does not decide it.
        self._load_forge_keys()
        lineage_mod = _load_lineage_module()
        try:
            self.lineage = lineage_mod.lineage(self.fabric)
        except lineage_mod.StoreError as e:
            self.lineage, self.global_problem = {}, str(e)
            return
        if not isinstance(self.lineage, dict):
            self.lineage, self.global_problem = {}, "identities/keys/lineage.json is not an object"
            return
        self.global_problem = ""
        try:
            findings = lineage_mod.verify(self.fabric)
        except lineage_mod.StoreError as e:
            findings = [f"the lineage could not be verified ({e})"]
        named: dict[str, str] = {}
        for line in findings:
            ids = AGENT_ID_RE.findall(line)
            if not ids or ROOTS_FINDING_RE.search(line):
                # A finding about the whole chain (no root, two roots) leaves
                # no agent certified.
                self.global_problem = line
                continue
            # The first id is the finding's subject; a later one is context
            # ("not certified by its parent <id>'s key" says nothing against
            # the parent, and must not exclude its every other child).
            named.setdefault(ids[0], line)
        ssh_lines, revoked = [], set()
        for aid, rec in sorted(self.lineage.items()):
            if not isinstance(rec, dict):
                continue
            path = os.path.join(self.keys, f"{aid}.asc")
            if not os.path.isfile(path):
                continue
            self._gpg("--import", path)
            fpr = rec.get("fingerprint") or ""
            listing = self._gpg("--with-colons", "--list-keys", fpr).stdout.decode(errors="replace") if fpr else ""
            is_revoked, subs, current = False, [], None
            for line in listing.splitlines():
                f = line.split(":")
                if f[0] == "pub":
                    is_revoked = f[1] == "r"
                    current = None
                elif f[0] == "sub":
                    current = f if "s" in f[11] else None
                elif f[0] == "fpr" and current is not None:
                    subs.append((f[9], current[1] not in ("r", "e", "i", "d")))
                    current = None
            if is_revoked:
                revoked.add(aid)
            # A revoked agent's subkeys stay known, so its signature is named
            # as its and refused as revoked; an agent's own revoked or expired
            # subkey is simply not one of its keys.
            subs = [s for s, usable in subs if usable or is_revoked]
            for sub in subs:
                self.by_subkey[sub] = aid
                exported = self._gpg("--export-ssh-key", sub + "!").stdout.decode(errors="replace").split()
                if len(exported) >= 2:
                    ssh_lines.append(f'{aid} namespaces="git" {exported[0]} {exported[1]}')
        # A chain is as good as its weakest link: a finding on, or the
        # revocation of, the agent or any ancestor refuses its signatures.
        for aid in self.lineage:
            seen, at = set(), aid
            while isinstance(at, str) and at not in seen:
                seen.add(at)
                # Revocation first: a revoked key's user id is no longer valid,
                # so verify() names it too, in words that do not say why.
                if at in revoked:
                    self.excluded[aid] = (f"the key of {aid} is revoked" if at == aid
                                          else f"the key of {aid}'s ancestor {at} is revoked")
                    break
                if at in named:
                    self.excluded[aid] = f"the lineage does not certify {aid}: {named[at]}"
                    break
                rec = self.lineage.get(at)
                at = rec.get("parent") if isinstance(rec, dict) else None
        with open(self.allowed, "w", encoding="utf-8") as f:
            f.write("".join(l + "\n" for l in ssh_lines))
        try:
            with open(roots.policy("authority.json", environ=self.environ), encoding="utf-8") as f:
                definitions = json.load(f).get("role_definitions")
        except (OSError, ValueError) as e:  # a missing file too: no holders is not "no one is listed"
            self.global_problem = f"policies/authority.json cannot be read ({type(e).__name__}: {e})"
            definitions = None
        # The charter guard refuses a file with no role_definitions dict, and
        # reads a definition with no role as DEFAULT_ROLE's (common.role_of);
        # the same here, so the owner role is always listed and never falls back
        # to the name convention.
        if not isinstance(definitions, (dict, list)) or definitions == []:
            self.global_problem = self.global_problem or "policies/authority.json has no role_definitions -- no holder can be named"
            definitions = []
        self.holders: dict[str, list[str]] = {common.DEFAULT_ROLE: []}
        for d in definitions if isinstance(definitions, list) else [definitions]:
            if isinstance(d, dict):
                role = d.get("role")
                role = role if isinstance(role, str) and role else common.DEFAULT_ROLE
                listed = d.get("holders")
                # A role it names is listed even with no usable holders list:
                # held by nobody, never by the name convention.
                names = self.holders.setdefault(role, [])
                if isinstance(listed, list):
                    names.extend(h for h in listed if isinstance(h, str))

    def _locales(self, role: str) -> list[str]:
        try:
            return sorted(os.listdir(os.path.join(roots.role_dir(role, environ=self.environ), "locale")))
        except OSError:
            return []

    def _verdicts(self, repo: str, shas: list[str]) -> dict[str, tuple[str, str, str, str]]:
        """sha -> (%G?, %GF, %GS, %GK) from git, verifying against this keyring
        and allowed-signers file alone, whatever the clone's config says."""
        cfg = ["-c", "gpg.program=gpg", "-c", "gpg.openpgp.program=gpg", "-c", "gpg.ssh.program=ssh-keygen",
               "-c", f"gpg.ssh.allowedSignersFile={self.allowed}", "-c", "gpg.ssh.revocationFile=",
               "-c", "gpg.minTrustLevel=undefined"]
        env = {**os.environ, "GNUPGHOME": self.home}
        out = git.run(repo, *cfg, "log", "--no-show-signature", "--no-walk=unsorted", "--stdin", "--format=%H%x1f%G?%x1f%GF%x1f%GS%x1f%GK%x1e",
                      input="".join(s + "\n" for s in shas), env=env, errors="replace").stdout
        verdicts = {}
        for rec in out.split("\x1e"):
            fields = rec.strip("\n").split("\x1f")
            if len(fields) == 5:
                verdicts[fields[0]] = (fields[1], fields[2], fields[3], fields[4])
        return verdicts

    def refusals(self, repo: str, shas: list[str]) -> list[str]:
        """One line per refused commit; [] when every one passes. Raises
        git.GitError when a commit cannot be read: unread is not passed."""
        if not shas:
            return []
        verdicts = self._verdicts(repo, shas)
        notes = {}
        listed = git.run(repo, "notes", f"--ref={NOTES_REF}", "list", check=False)
        if listed.returncode == 0:
            for line in listed.stdout.splitlines():
                blob, _, commit = line.partition(" ")
                notes[commit.strip()] = blob
        out = []
        for sha in shas:
            why = self._why(repo, sha, verdicts.get(sha), notes.get(sha))
            if why:
                subject = git.run(repo, "log", "--no-show-signature", "-1", "--format=%s", sha, errors="replace").stdout.strip()
                out.append(f"{sha[:10]} {subject[:50]}: {why}")
        return out

    def _forge_why(self, repo: str, sha: str, raw: bytes, fpr: str) -> str:
        """Rule 8: "" for the two kinds of forge commit that carry nothing of
        their own, else why it is refused."""
        who = f"signed by the forge's key {fpr[-16:]}"
        remake = "re-make it in a working copy, signed by its agent"
        header = raw.split(b"\n\n", 1)[0].decode(errors="replace").split("\n")
        tree = next((l[len("tree "):] for l in header if l.startswith("tree ")), "")
        parents = [l[len("parent "):] for l in header if l.startswith("parent ")]
        author = git.run(repo, "log", "--no-show-signature", "-1", "--format=%an", sha, errors="replace").stdout.strip()
        dependabot = author == "dependabot[bot]"
        if not parents:
            return f"{who}, a root commit: the forge begins no history here; {remake}"
        if len(parents) > 2:
            return f"{who}, an octopus merge of {len(parents)} parents: only a clean merge of two is the forge's; {remake}"
        if len(parents) == 2:
            but = " (Dependabot's carve-out is for a commit that is not a merge)" if dependabot else ""
            # Exit 1 is a conflict: whatever tree the forge wrote, a person
            # chose it in the web editor, and that choice is what rule 5 judges.
            # Merge attributes are read from the empty tree, never the
            # checkout: in CI the checkout is the branch being judged, and its
            # `.gitattributes` (`merge=union`, say) could turn that conflict
            # into a "clean" merge (review of #341). A repository whose own
            # attributes GitHub honours is refused here, which fails closed.
            empty = git.run(repo, "hash-object", "-t", "tree", "--stdin", input="").stdout.strip()
            r = git.run(repo, "-c", "core.attributesFile=/dev/null", f"--attr-source={empty}", "merge-tree",
                        "--write-tree", parents[0], parents[1], check=False)
            clean = (r.stdout.splitlines() or [""])[0].strip() if r.returncode == 0 else ""
            if not clean:
                return (f"{who}, a merge whose parents do not merge cleanly (git merge-tree exit {r.returncode}): "
                        f"a conflict resolved on the web?{but} {remake}")
            if clean != tree:
                return (f"{who}, a merge that changes something itself (its tree is not the clean merge of its "
                        f"parents: a conflict resolved on the web?){but}; {remake}")
            return ""
        if dependabot:
            # --no-renames: a move out of the workflows shows its source path.
            paths = [p for p in git.run(repo, "diff-tree", "--no-commit-id", "-r", "--no-renames", "--name-only",
                                        parents[0], sha, errors="replace").stdout.split("\n") if p]
            outside = [p for p in paths if not p.startswith(WORKFLOWS)]
            if not paths:
                return f"{who}, authored dependabot[bot] and changing nothing: no action pin was bumped; {remake}"
            if outside:
                more = f" and {len(outside) - 1} more" if len(outside) > 1 else ""
                return (f"{who}, authored dependabot[bot] but changing {outside[0]}{more}, outside {WORKFLOWS}: "
                        f"the forge's Dependabot commit bumps action pins only; {remake}")
            return ""
        return f"{who}: made on the forge (a web edit, a committed suggestion, a squash): {remake}"

    def _why(self, repo: str, sha: str, verdict: tuple[str, str, str, str] | None, note_blob: str | None) -> str:
        raw = subprocess.run(["git", "-C", repo, "cat-file", "commit", sha], capture_output=True, timeout=git.TIMEOUT_S)
        if raw.returncode != 0:
            raise git.GitError("git cat-file", f"cannot read commit {sha}")
        signature = commit_signature(raw.stdout)
        if signature is None:
            return "no signature"
        fmt = format_of(signature)
        status, key, signer, keyid = verdict or ("", "", "", "")
        # Before the format: the forge signs OpenPGP in a repository that
        # signs SSH, and its commit is judged by rule 8, never as an agent's.
        # %GF is the key that signed. web-flow's primary signs itself; a forge
        # key that signed with a subkey would not match its listed primary
        # and is refused, the closed side to fail on.
        if fmt == "openpgp" and status in ("G", "U") and key.upper() in self.forge:
            return self._forge_why(repo, sha, raw.stdout, key.upper())
        if fmt == "openpgp" and status == "E" and keyid:
            # Not in this keyring: when that is a listed forge key whose file
            # did not load, say so rather than "not an agent's".
            for fpr, why in sorted(self.forge_unloaded.items()):
                if fpr.endswith(keyid.upper()):
                    return f"signed by the forge's key {fpr}, listed in forge_keys but not loaded ({why}): refused until it loads"
        if fmt != self.format:
            return f"signed as {fmt or 'an unknown format'}; the policy admits {self.format} here"
        if self.global_problem:
            return f"no agent is certified: {self.global_problem}"
        if fmt == "openpgp":
            # U as well as G: a good signature whose validity gpg's own trust
            # model leaves unknown; validity here is the lineage's, judged above.
            agent = self.by_subkey.get(key) if status in ("G", "U") else None
            if agent is None:
                return (f"not signed by an agent's signing subkey in identities/keys/ "
                        f"(git: {status or '?'} {key or 'no key'})")
        else:
            agent = signer if status == "G" and signer in self.lineage else None
            if agent is None:
                return f"not signed by the SSH form of an agent's signing subkey in identities/keys/ (git: {status or '?'})"
        if agent in self.excluded:
            return self.excluded[agent]
        login = (self.lineage.get(agent) or {}).get("login") or ""
        trailers = git.run(repo, "log", "--no-show-signature", "-1", "--format=%(trailers:key=Fabric-Role,valueonly,unfold)", sha,
                           errors="replace").stdout.strip().splitlines()
        role = trailers[-1].strip() if trailers else ""
        if not role:
            return f"signed by {login} ({agent}) but names no Fabric-Role"
        if not ROLE_RE.match(role) or not os.path.isdir(roots.role_dir(role, environ=self.environ)):
            return f"Fabric-Role: {role} is no role defined in identities/roles/"
        if not may_hold(login, role, self.holders.get(role), self._locales(role)):
            return f"signed by {login} ({agent}), who may not hold the role it names (Fabric-Role: {role})"
        if note_blob is None:
            return f"no timestamp proof in {NOTES_REF} (fetch it, or `fabric-sign note {sha[:10]}` and push)"
        proof = subprocess.run(["git", "-C", repo, "cat-file", "blob", note_blob], capture_output=True, timeout=git.TIMEOUT_S)
        if proof.returncode != 0 or not proof_matches(signature, proof.stdout):
            return f"its {NOTES_REF} note is not the timestamp proof of this commit's signature"
        return ""


# --- the CI entry point ------------------------------------------------------

def repository(env: dict[str, str]) -> str | None:
    import workingcopy
    explicit = env.get("AGENT_FABRIC_SIGNING_REPOSITORY") or env.get("GITHUB_REPOSITORY")
    if explicit:
        return explicit if signing_policy.SLUG_RE.match(explicit) else None
    r = git.run(".", "config", "--get", "remote.origin.url", check=False)
    return signing_policy.slug_of(r.stdout.strip(), workingcopy.parse_remote) if r.returncode == 0 else None


def policy_entry(env: dict[str, str]) -> tuple[str | None, dict]:
    """(the repository, its entry). Raises PolicyError."""
    import workingcopy
    policy = signing_policy.load(roots.policy("signing.json", environ=env))
    slug = repository(env)
    try:
        registry = workingcopy.load_registry(roots.projects_registry(environ=env))
    except (OSError, ValueError) as e:
        raise signing_policy.PolicyError(f"projects/registry.json cannot be read ({type(e).__name__}: {e})") from None
    return slug, signing_policy.entry_for(policy, slug, registry, workingcopy.parse_remote)[1]


def require_since_on(base: str, since: str) -> None:
    """Raises git.GitError unless `since` is in this clone and an ancestor of
    `base` (the default branch's tip): a since on a side branch would exempt
    every commit it reaches."""
    if git.run(".", "cat-file", "-e", f"{since}^{{commit}}", check=False).returncode != 0:
        raise git.GitError("git cat-file", f"the policy's since {since[:12]} is not in this clone (shallow? fetch it)")
    if not git.ok(".", "merge-base", "--is-ancestor", since, base):
        raise git.GitError("git merge-base", f"the policy's since {since} is not an ancestor of {base}: "
                           "it must be a commit on the default branch (or "
                           f"{base} is stale and predates it: fetch the remote first)")


def judged_commits(base: str, head: str, since: str) -> list[str]:
    """The commits base..head adds that `since` does not reach. Raises
    git.GitError (see require_since_on)."""
    require_since_on(base, since)
    return git.run(".", "rev-list", head, f"^{base}", f"^{since}").stdout.split()


def main(env: dict[str, str]) -> int:
    import ban_generated_by_attribution as attribution
    env = dict(env)
    env["AGENT_FABRIC_ATTRIBUTION_BASE"] = env.get("AGENT_FABRIC_SIGNATURES_BASE", "")
    try:
        slug, entry = policy_entry(env)
    except signing_policy.PolicyError as e:
        print(f"ban_unsigned_commits: FAIL the signing policy cannot be read: {e}", file=sys.stderr)
        return 1
    since = entry.get("since")
    try:
        rng = attribution.resolve_range(env)
    except git.GitError as e:
        rng, problem = None, str(e)
    else:
        problem = "no usable range (a shallow checkout with no event payload)"
    if rng is None:
        if since:
            print(f"ban_unsigned_commits: FAIL {slug} is cut over (since {since[:12]}) and the commits the branch "
                  f"adds cannot be resolved: {problem}", file=sys.stderr)
            return 1
        print(f"signatures: NOT ENFORCED -- {problem}")
        return 0
    try:
        found = unsigned(".", f"{rng[0]}..{rng[1]}")
        judged = judged_commits(rng[0], rng[1], since) if since else []
    except git.GitError as e:
        if since:
            print(f"ban_unsigned_commits: FAIL {slug} is cut over and the range cannot be read: {e}", file=sys.stderr)
            return 1
        print(f"signatures: NOT ENFORCED -- {e}")
        return 0
    if found:
        print(f"ban_unsigned_commits: FAIL {refusal(found)}", file=sys.stderr)
        return 1
    if not since:
        print(f"signatures: OK -- every commit the branch adds is signed (rule 5 not applied: "
              f"{slug or 'this repository'} has no since in policies/signing.json)")
        return 0
    judge = None
    try:
        judge = Judge(env, entry["format"])
        refused = judge.refusals(".", judged)
    except (git.GitError, OSError, subprocess.SubprocessError) as e:
        print(f"ban_unsigned_commits: FAIL the signatures could not be judged: {e}", file=sys.stderr)
        return 1
    finally:
        if judge is not None:
            judge.close()
    if refused:
        for line in refused:
            print(f"ban_unsigned_commits: FAIL {line}", file=sys.stderr)
        print(f"ban_unsigned_commits: {len(refused)} of {len(judged)} commit(s) refused under agent-fabric ADR-057 "
              f"§5 rule 5 ({slug}, since {since[:12]})", file=sys.stderr)
        return 1
    print(f"signatures: OK -- every commit the branch adds is signed; {len(judged)} judged under ADR-057 rule 5 "
          f"({slug}, since {since[:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main(dict(os.environ)))
