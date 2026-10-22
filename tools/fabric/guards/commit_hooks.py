#!/usr/bin/env python3
"""tools/fabric/guards/commit_hooks.py — what git's commit-time hooks decide (ADR-040 Wave 9 batch 4). One module for
policies/githooks/pre-commit, commit-msg, post-commit, guarded-change.sh and locale-carve-out.sh; the first three keep their
paths as forwarders because git runs a hook by path, the two libraries as sourced shims (ADR-040 §5 rule 4) that the oracle
tests still source.

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      pre-commit <fabric-root>                  git passes the hook nothing
            commit-msg <fabric-root> <message-file>
            post-commit <fabric-root>
            guarded <fabric-root>                     the library's `guarded_change`: stdout is the label
                                                      (`agent-fabric itself` or `.agent-fabric/`), then one guarded path
                                                      per line; exit 0
            locale-role <path>...                     stdout `<role>|<suffix>` (both empty when not a carve-out); exit 0
                                                      when every path is one locale's translation file, 1 otherwise
            locale-paths                              the staged paths to judge, one per line; exit 0
            <fabric-root> is where the hook file lives (the forwarder works it out from its own real path), which is
            NOT where this module lives: a test, or a checkout the hooks serve, holds its own policies/authority.json.
  itself    "agent-fabric itself" is ONE predicate, same_repository(<fabric-root>), for every decision that asks it (the
            guard's scope and label, the contributor carve-out, the decision-record check, the hidden-text scope): the
            repository's toplevel is <fabric-root>, or its git common directory is <fabric-root>'s, so a linked worktree of
            the fabric is the fabric. Every other repository is a managed project, whose guarded set is .agent-fabric/.
  hidden    pre-commit also refuses, for EVERY committer (the coordinator, both carve-outs, an unbound session), a staged
            file that tools/fabric/agent_text.py calls text an agent reads (in agent-fabric itself: any *.md, *.md/*.json
            under identities/ and .agent-fabric/; in a managed project: .agent-fabric/ only) whose STAGED blob holds
            a character tools/fabric/hidden_unicode.py refuses. Exit 1, one `<path>:<line>:<col>: U+XXXX NAME (kind)` per
            character.
  env       AGENT_FABRIC_STATE_DIR etc. are read by runtime/identity.py, which runs for the binding's role;
            AGENT_FABRIC_PYTHON is read by the forwarders only. The login is `id -un`, never the password database.
  stdout    only the three library verbs print on stdout; the hooks speak on stderr (and the decision-record check's
            own report, which goes there too).
  stderr    every refusal, in the words the bash used; they are pinned by tests/test_githook_*.py.
  exit      0 admitted; 1 refused or could not judge. A hook that cannot run its decision REFUSES (exit 1 or, from the
            forwarder, 127): the harness reads a hook's silence as no objection. post-commit exits 0 in every path.
  mutations on disk: commit-msg writes the `Kind:` stamp (commit_kind.py) and the `Fabric-Role:` trailer into the message
            file, and only into it; pre-commit makes a scratch tree for the decision-record check and removes it.

Departure from the bash, none observable by the oracles: a path list that `sort -u` ordered by the caller's locale is
ordered by code point (the same in C and UTF-8 locales for the paths git prints); a message file that cannot be read
refuses the commit (the bash read it as empty and let the Kind check fail it).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
# A hook runs in any repository's checkout, whose tools/fabric/guards/ may be tracked or scanned by `git add -A`: no
# __pycache__ is written beside the sibling it imports (the bash ran commit_kind.py as a script, which writes none).
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.dirname(HERE))
import agent_text  # noqa: E402  the one predicate for text an agent reads (lint judges the same files)
import commit_kind  # noqa: E402
import hidden_unicode  # noqa: E402  the one definition of what such text may not hide
import roots  # noqa: E402  the hook's own checkout is the root it is given; roots spells the policy's path (test_roots_seam)

ITSELF = "agent-fabric itself"
AGENT_FABRIC_DIR = ".agent-fabric/"
AMEND_PLACEHOLDER = "(amend or empty commit: the whole repository)"
DEFAULT_OWNER = "fabric-coordinator"
# The carve-out's pattern, verbatim what tools/fabric/guards/agent_fabric_dir_authority.py (CI's tripwire) holds too;
# tests/test_agent_fabric_dir_authority.py fails if the two drift.
LOCALE_PATH = re.compile(r"identities/(roles/([a-z][a-z0-9-]*)|prompt)/locale/([a-z][a-z0-9-]*)/[^/]+")
# grep's [[:space:]] in a UTF-8 locale takes Unicode spaces too (an em space), so these take any whitespace but the
# line break, as CI's ban_generated_by_attribution.py does: an ASCII-only class admitted " Co-authored-by:" spaced with
# an em space at the keyboard while CI refused it (review of #329, F2).
TRAILER_RE = re.compile(r"^[^\S\n]*(Co-authored-by|Claude-Session):", re.I)
FOOTER_RE = re.compile(r"Generated with\s+\[Claude Code|claude\.ai/code/session_", re.I)
# The stamp's question is the bash's exactly: wider here is not stricter, it skips the stamp on a line git does not read
# as a trailer (an NBSP before it). glibc's [[:space:]] under C.UTF-8, measured with grep on 2026-10-19: it leaves out
# U+001C-001F, U+0085, U+00A0, U+2007 and U+202F (review of #329, round 2).
GREP_SPACE = "\t\v\f\r \u1680\u2000-\u2006\u2008-\u200a\u2028\u2029\u205f\u3000"
FABRIC_ROLE_RE = re.compile(rf"^[{GREP_SPACE}]*Fabric-Role:", re.I | re.ASCII)
HEX_TREE = re.compile(r"[0-9a-f]{40,64}")
ADR_CHECK_TIMEOUT_S = 600
SHORT_TIMEOUT_S = 30


class Refuse(Exception):
    """A refusal with its words; the hook prints them and exits 1."""


def say(text: str = "") -> None:
    print(text, file=sys.stderr)


GIT_TIMEOUT_S = 120


def _git(*args: str) -> subprocess.CompletedProcess:
    # Plain `git <verb>`, not `git -C .` (tools/fabric/git.py): the oracle stands a `git` first on PATH that answers by
    # its first argument, as an older git would, and a verb behind -C is invisible to it. A failure is an exit status
    # the caller reads, never an exception: a hook decides what each failed question means.
    return subprocess.run(["git", *args], capture_output=True, text=True, errors="surrogateescape", timeout=GIT_TIMEOUT_S,
                          stdin=subprocess.DEVNULL)


def lines_of(text: str) -> list[str]:
    """What bash's `mapfile -t` makes of command output: split on newlines only (str.splitlines would split on \\x0b,
    \\x1c, U+2028 too), none for empty output."""
    parts = text.split("\n") if text else []
    if parts and parts[-1] == "":
        parts.pop()
    return parts


def _real(path: str) -> str:
    # readlink -f of nothing is nothing; realpath("") would be the cwd, which would make an absent toplevel equal a root.
    return os.path.realpath(path) if path else ""


def toplevel() -> str:
    r = _git("rev-parse", "--show-toplevel")
    return r.stdout.strip() if r.returncode == 0 else ""


def _common_dir_of(checkout: str) -> str:
    """The git common directory of the checkout at `checkout` as git lays it out on disk, "" when it has none: its own
    .git directory, or, for a linked worktree, what its gitdir's `commondir` names. Read from the files, because a hook
    asks git of its cwd only (`_git`) and the root is not where it runs."""
    dot_git = os.path.join(checkout, ".git")
    if os.path.isdir(dot_git):
        return _real(dot_git)
    try:
        with open(dot_git, encoding="utf-8") as f:
            first = f.readline().strip()
    except (OSError, UnicodeDecodeError):
        return ""
    if not first.startswith("gitdir:"):
        return ""
    gitdir = os.path.join(checkout, first[len("gitdir:"):].strip())
    try:
        with open(os.path.join(gitdir, "commondir"), encoding="utf-8") as f:
            return _real(os.path.join(gitdir, f.read().strip()))
    except (OSError, UnicodeDecodeError):
        return _real(gitdir)


def same_repository(root: str) -> bool:
    """The commit is made in agent-fabric itself: its toplevel is the root, or it shares the root's git common directory
    (a linked worktree of the root's repository, or the root a worktree of the clone being committed in). Most fabric work
    is committed in a worktree, whose toplevel is never the root while it inherits the root's hooks path; asked of the
    toplevel alone, the fence took such a commit for a managed project's and guarded only .agent-fabric/ (j320)."""
    top = toplevel()
    if not top:
        # Not in a work tree: nothing is committed here, and the library answers a project's empty set outside a repository.
        return False
    if _real(top) == _real(root):
        return True
    fabric = _common_dir_of(root)
    if not fabric:
        return False  # the root is no git checkout (an installed copy): nothing can be a worktree of it
    # git's own answer first, since GIT_DIR/GIT_COMMON_DIR outrank the layout. Not --path-format=absolute (git 2.31): an
    # older git echoes an option it does not know and exits 0, and so does a git older than 2.5 for --git-common-dir,
    # which is why an answer that is an option is no answer. Without one the toplevel's own layout is read: it names this
    # commit's repository whichever it is, so neither side of the question is guessed. A fence that fails open when it
    # cannot tell is the defect this predicate exists for, and taking a project for the fabric would lock the fleet out
    # of its projects: when neither source answers, the hook cannot judge and refuses.
    r = _git("rev-parse", "--git-common-dir")
    answer = r.stdout.strip() if r.returncode == 0 else ""
    here = _real(answer) if answer and "\n" not in answer and not answer.startswith("-") else _common_dir_of(top)
    if not here:
        raise Refuse("commit hooks: cannot tell whether this commit is made in agent-fabric (no git common directory for "
                     f"{top}) — not committed")
    return here == fabric


def merge_head() -> str:
    r = _git("rev-parse", "-q", "--verify", "MERGE_HEAD")
    return r.stdout.strip() if r.returncode == 0 else ""


def identity_role(root: str) -> str:
    """The role the live binding holds, "" when none or when it cannot be read."""
    try:
        r = subprocess.run([sys.executable, os.path.join(root, "runtime", "identity.py"), "--role"], capture_output=True,
                           text=True, timeout=SHORT_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.rstrip("\n") if r.returncode == 0 else ""


def owner_role(root: str) -> str:
    try:
        with open(roots.policy("authority.json", root=root), encoding="utf-8") as f:
            return str(json.load(f)["role_definitions"]["role"]).rstrip("\n")
    except Exception:  # noqa: BLE001 - any unreadable shape is the default owner, as the bash's `except Exception`
        return DEFAULT_OWNER


def login() -> str:
    """`id -un` through PATH, as the bash asked it (a test stands in for it)."""
    try:
        return subprocess.run(["id", "-un"], capture_output=True, text=True, timeout=SHORT_TIMEOUT_S).stdout.rstrip("\n")
    except (OSError, subprocess.SubprocessError):
        return ""


def _names(*args: str) -> list[str]:
    r = _git(*args)
    return lines_of(r.stdout) if r.returncode == 0 else []


def guarded_change(fabric_root: str) -> tuple[str, list[str]]:
    """(label, guarded paths) of the commit being made: what the staged tree changes of its OWN under the fabric-coordinator
    role's guard. A merge changes only what differs from the clean three-way merge of its parents."""
    itself = same_repository(fabric_root)
    what, prefix = (ITSELF, "") if itself else (AGENT_FABRIC_DIR, AGENT_FABRIC_DIR)
    scope = ["--", prefix] if prefix else []
    guarded = _names("diff", "--cached", "--no-renames", "--name-only", "--diff-filter=ACDMRT", *scope)
    head_of_merge = merge_head()
    if not head_of_merge:
        # Nothing staged against HEAD: an --amend or an empty commit. In agent-fabric itself every commit is the
        # coordinator's, an amend included, so it must carry the trailer.
        if not guarded and not prefix:
            guarded = [AMEND_PLACEHOLDER]
        return what, guarded
    # A merge in progress is judged even when nothing differs from HEAD: keeping HEAD's guarded tree while the other
    # side moved it drops landed changes.
    wrote = _git("write-tree")
    if wrote.returncode != 0:
        return what, guarded
    staged_tree = wrote.stdout.strip()
    heads_path = _git("rev-parse", "--git-path", "MERGE_HEAD").stdout.strip()
    try:
        with open(heads_path, encoding="utf-8") as f:
            heads_text = f.read()
    except OSError:
        heads_text = ""
    against: list[str] = []
    if sum(1 for line in heads_text.split("\n") if line) == 1:
        clean = _git("merge-tree", "--write-tree", "HEAD", head_of_merge)
        first = clean.stdout.split("\n", 1)[0]
        if clean.returncode in (0, 1) and HEX_TREE.fullmatch(first):
            against = [first]
    if not against:
        # Without a usable clean merge (an octopus, a git older than 2.38) the merge is judged against EVERY parent, so
        # an `-s ours` merge is not waved through.
        for rev in ["HEAD", *heads_text.split()]:
            r = _git("rev-parse", rev)
            if r.returncode == 0:
                against += lines_of(r.stdout)
    changed: set[str] = set()
    for a in against:
        changed.update(_names("diff", "--no-renames", "--name-only", a, staged_tree, *scope))
    return what, sorted(changed)


def locale_paths() -> list[str]:
    """The staged paths the locale carve-out judges: for a merge, what the result adds over the merged-in side."""
    against = [merge_head()] if merge_head() else []
    return _names("diff", "--cached", "--no-renames", "--name-only", "--diff-filter=ACDMRT", *against)


def locale_role(paths: list[str]) -> tuple[str, str] | None:
    """(role, suffix) when every path is a file directly inside ONE locale directory of one role, else None."""
    found: tuple[str, str] | None = None
    for p in paths:
        m = LOCALE_PATH.fullmatch(p)
        if not m:
            return None
        here = (m.group(2) or "language-culture", m.group(3))
        if found is not None and here != found:
            return None
        found = here
    return found


def _holds_locale(login_name: str, suffix: str) -> bool:
    return login_name.endswith("-" + suffix) or login_name == suffix


def _contributor_exit(root: str, role: str, quiet: bool) -> int | None:
    """contributors.py hook's exit status (0 admits, 1 refuses, saying why unless quiet, anything else is not a
    contributor), None when there is no role or the fabric has no such module (a fabric older than it)."""
    module = os.path.join(root, "tools", "fabric", "guards", "contributors.py")
    if not role or not os.path.isfile(module):
        return None
    r = subprocess.run([sys.executable, module, "hook", root, role], timeout=SHORT_TIMEOUT_S * 4, stdin=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL if quiet else None)
    return r.returncode


def _check_decision_records(root: str) -> None:
    """In agent-fabric itself, a commit staging anything under docs/adr/ leaves the records consistent in what it
    COMMITS: the staged tree is checked, not the working tree."""
    if not same_repository(root) or _git("diff", "--cached", "--quiet", "--no-renames", "--", "docs/adr/").returncode == 0:
        return
    try:
        scratch = tempfile.mkdtemp(prefix="pre-commit-adr.")
    except OSError:
        raise Refuse("pre-commit: cannot make a scratch directory to check the decision records") from None
    try:
        # The whole staged tree: a record's Evidence may cite any path in it.
        if _git("checkout-index", "-a", f"--prefix={scratch}/").returncode != 0:
            raise Refuse("pre-commit: cannot materialize the staged tree to check the decision records")
        r = subprocess.run([sys.executable, os.path.join(root, "tools", "fabric", "adr.py"), "--root", scratch, "check"],
                           capture_output=True, text=True, errors="replace", timeout=ADR_CHECK_TIMEOUT_S, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise Refuse("pre-commit: the decision records in this commit are not consistent — not committed:\n"
                         + (r.stdout + r.stderr).rstrip("\n"))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _check_hidden_unicode(root: str) -> None:
    """Before any carve-out is consulted: hidden text is refused whoever commits it, the coordinator included. The staged
    blob is judged, not the work tree. Every staged path that differs from HEAD is judged, a merge included: the authority
    fence may take a merged-in commit as judged when it was made, a content check cannot (a --no-verify commit, a web
    edit, a branch from before this hook). Names are read NUL-separated: git's default output quotes and octal-escapes a non-ASCII
    name, which then no longer ends in .md and was never judged (review of #346, F1). A question git does
    not answer refuses: judging nothing would admit."""
    itself = same_repository(root)
    r = _git("diff", "--cached", "-z", "--no-renames", "--name-only", "--diff-filter=ACMRT")
    if r.returncode != 0:
        raise Refuse("pre-commit: cannot list the staged files to check them for hidden Unicode — not committed")
    judged = [p for p in r.stdout.split("\0") if p and agent_text.is_agent_text(p, itself=itself)]
    # Each blob by the object id the index holds for the path, never by `:<path>`: that is revision syntax, and a file
    # named `0:README.md` read as `:0:README.md` is README.md's stage-0 blob (re-review of #346).
    oids: dict[str, str] = {}
    if judged:
        idx = _git("ls-files", "-s", "-z", "--full-name")
        if idx.returncode != 0:
            raise Refuse("pre-commit: cannot read the index to check staged files for hidden Unicode — not committed")
        for entry in (e for e in idx.stdout.split("\0") if e):
            meta, _, name = entry.partition("\t")
            fields = meta.split()
            if len(fields) == 3 and fields[2] == "0":
                oids[name] = fields[1]
    lines: list[str] = []
    for path in judged:
        if path not in oids:
            raise Refuse(f"pre-commit: {path} is staged but has no stage-0 entry in the index — not committed")
        blob = subprocess.run(["git", "cat-file", "blob", oids[path]], capture_output=True, timeout=GIT_TIMEOUT_S,
                              stdin=subprocess.DEVNULL)
        if blob.returncode != 0:
            raise Refuse(f"pre-commit: cannot read the staged {path} to check it for hidden Unicode — not committed")
        try:
            text = blob.stdout.decode("utf-8")
        except UnicodeDecodeError:
            lines.append(f"{path}: not UTF-8")
            continue
        lines += [f"{path}:{f.line}:{f.column}: U+{f.codepoint:04X} {f.name} ({f.kind})" for f in hidden_unicode.scan(text)]
    if lines:
        raise Refuse("\n".join(lines) + "\npre-commit: staged text an agent reads holds characters the reader does not see "
                     "— not committed. What is refused, and what is allowed, is defined in tools/fabric/hidden_unicode.py.")


def pre_commit(root: str) -> int:
    _check_decision_records(root)
    _check_hidden_unicode(root)
    what, staged = guarded_change(root)
    if not staged:
        return 0
    owner = owner_role(root)
    held = identity_role(root)
    if held == owner:
        return 0
    # THE LOCALE CARVE-OUT (policies/AUTHORITY.md): a commit staging nothing but one locale's translations, from the
    # session bound to that role on the login named for that suffix.
    own = locale_role(locale_paths())
    if own:
        loc_role, suffix = own
        if held == loc_role and _holds_locale(login(), suffix):
            return 0
        raise Refuse(f"pre-commit: this commit changes only {loc_role}'s locale/{suffix}/ translations,\n"
                     f"  which the holder of {loc_role} named for {suffix} may commit — this session's\n"
                     f"  binding holds {held or '(no role bound)'} on login {login()}.")
    # THE CONTRIBUTOR CARVE-OUT (ADR-018 §5 rule 8), in agent-fabric itself only. Only 0 admits; 1 is the module's own
    # refusal, said; anything else (3, not a contributor) falls to the refusal below.
    if what == ITSELF and held:
        code = _contributor_exit(root, held, quiet=False)
        if code == 0:
            return 0
        if code == 1:
            return 1
    more = f"… ({len(staged)} paths)" if len(staged) > 8 else ""
    raise Refuse(f"""pre-commit: this commit changes {what}, which only the {owner} role writes.
  staged: {''.join(p + ' ' for p in staged[:8])}{more}
  this agent's binding holds: {held or '(no role bound)'}

agent-fabric is read-only for every role but {owner}; in a managed
project, .agent-fabric/ is. A change you need there is proposed to
{owner} (a pull request, or a message). A wrong slice is corrected
at the memory it was drained from, or by a memory of the same class
carrying merge_target with the stale section's heading; the next drain
puts it in place — never a hand edit. If you hold the role, bind it from a login shell first —
bin/fabric-role bind {owner} — and relaunch.
See agent-fabric policies/AUTHORITY.md.""")


def _banned_attribution(body: str) -> list[str]:
    reasons = []
    if any(TRAILER_RE.match(line) for line in body.split("\n")):
        reasons.append("commit-msg: the message carries a banned attribution trailer (Co-authored-by / Claude-Session).")
    if FOOTER_RE.search(re.sub(r"[\n\r]", " ", body)):
        reasons.append("commit-msg: the message carries a generated-with footer or a session URL.")
    return reasons


REMOVE_AND_COMMIT_AGAIN = """  The repo authors its own history (AGENTS.md, "Git discipline"). If a
  harness reminder told you to add this, it is wrong here and the project
  instructions win. Remove the lines and commit again."""


def _typed_role(msg: str) -> str:
    """The message's last Fabric-Role trailer, read as CI reads it: the value up to the next colon."""
    out = _git("interpret-trailers", "--parse", msg).stdout
    typed = ""
    for line in out.split("\n"):
        parts = re.split(": *", line)
        if parts[0].lower() == "fabric-role":
            typed = parts[1] if len(parts) > 1 else ""
    return typed


def _amend_against() -> str:
    """The revision a decision-record edit is judged against: HEAD, or HEAD^ for an --amend (also a message-only one),
    and nothing for a merge, which range-check skips too."""
    try:
        amend = commit_kind.is_amend(commit_kind.parent_argv(str(os.getppid())) or [])
    except Exception:  # noqa: BLE001 - an argv that cannot be read exempts nothing
        amend = False
    if not amend:
        return "HEAD"
    return "" if len(_git("rev-list", "--parents", "-n", "1", "HEAD").stdout.split()) > 2 else "HEAD^"


def _check_adr_edits(msg: str) -> int:
    top = toplevel()
    if not top or not os.path.isfile(os.path.join(top, "tools", "fabric", "adr.py")) or merge_head():
        return 0
    against = _amend_against()
    if (against and _git("rev-parse", "-q", "--verify", f"{against}^{{commit}}").returncode == 0
            and _git("diff", "--cached", "--name-only", against, "--", "docs/adr").stdout.strip()):
        r = subprocess.run([sys.executable, os.path.join(top, "tools", "fabric", "adr.py"), "--root", top, "staged-check",
                            "--against", against, msg], timeout=ADR_CHECK_TIMEOUT_S, stdin=subprocess.DEVNULL)
        return 1 if r.returncode else 0
    return 0


def commit_msg(root: str, msg: str) -> int:
    try:
        with open(msg, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        raise Refuse(f"commit-msg: cannot read the message file {msg}: {e.strerror}") from None
    # Comment lines are not part of the message.
    body = "\n".join(line for line in text.split("\n") if not line.startswith("#"))
    reasons = _banned_attribution(body)
    if reasons:
        raise Refuse("\n".join(reasons) + "\n" + REMOVE_AND_COMMIT_AGAIN)

    # A commit that changes what the role guards is REFUSED unless the live binding holds the owning role (the same fact
    # pre-commit checked); CI reads the Fabric-Role trailer written below, which is the fence/tripwire split.
    what, guarded = guarded_change(root)
    role = ""
    if guarded:
        role = identity_role(root)
        owner = owner_role(root)
        if role != owner:
            contributor = _contributor_exit(root, role, quiet=True) if what == ITSELF else None
            own = locale_role(locale_paths())
            if contributor != 0 and not (own and role == own[0] and _holds_locale(login(), own[1])):
                raise Refuse(f"commit-msg: a guarded change, but this agent's binding holds '{role or 'no role'}', not {owner}.")
        # A guarded commit declares the binding the fence just checked, never a role typed into the message: CI reads the
        # trailer, so a typed `Fabric-Role: <owner>` would pass there as the owner's (review of #75).
        typed = _typed_role(msg)
        if typed and typed != role:
            raise Refuse(f"commit-msg: the message declares Fabric-Role: {typed}, but this agent's binding holds "
                         f"'{role or 'no role'}' — remove the line; the hook writes the binding.")
    # EVERY commit declares its KIND (ADR-019 §5 rule 3); an amended merge is told by the argv of the git that runs
    # this hook, its parent.
    if commit_kind.main(["commit_kind.py", msg, str(os.getppid())]) != 0:
        return 1
    # A decision record's body edit is recorded in the commit that makes it (agent-fabric ADR-001), judged by the
    # repository's OWN tools/fabric/adr.py.
    if _check_adr_edits(msg):
        return 1
    # EVERY commit records the role the account held (every account commits under one git author); a session with no
    # binding records nothing: the trailer states a fact about the account, never a claim it cannot make.
    with open(msg, encoding="utf-8", errors="replace") as f:
        has_role = any(FABRIC_ROLE_RE.match(line) for line in f.read().split("\n"))
    if not has_role:
        role = role or identity_role(root)
        if role:
            _git("interpret-trailers", "--in-place", "--if-exists", "addIfDifferent", "--trailer", f"Fabric-Role: {role}", msg)
    return 0


def post_commit() -> int:
    """File the commit's timestamp proof as its note (ADR-057 §5 rule 4), where git signs through fabric-sign. A post-commit
    hook cannot refuse a commit, and this one never fails: a failure is said, and left to the pre-push hook."""
    try:
        programs = "".join(_git("config", "--get", key).stdout.strip().rsplit("/", 1)[-1] for key in ("gpg.program", "gpg.ssh.program"))
        if "fabric-sign" not in programs:
            return 0
        try:
            ok = subprocess.run(["fabric-sign", "note", "HEAD"], timeout=300, stdin=subprocess.DEVNULL).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        if not ok:
            say("post-commit: no proof note yet for HEAD; the pre-push hook attaches it")
    except Exception:  # noqa: BLE001 - nothing here may fail a commit
        pass
    return 0


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(errors="surrogateescape")
    sys.stderr.reconfigure(errors="surrogateescape")
    verb, args = (argv[0], argv[1:]) if argv else ("", [])
    if verb == "post-commit":
        return post_commit()
    try:
        if verb == "pre-commit" and len(args) == 1:
            return pre_commit(args[0])
        if verb == "commit-msg" and len(args) == 2:
            return commit_msg(*args)
        if verb == "guarded" and len(args) == 1:
            what, paths = guarded_change(args[0])
            print("\n".join([what, *paths]))
            return 0
        if verb == "locale-role":
            found = locale_role(args) if args else None
            print("|".join(found or ("", "")))
            return 0 if found else 1
        if verb == "locale-paths" and not args:
            paths = locale_paths()
            if paths:
                print("\n".join(paths))
            return 0
        say("usage: commit_hooks.py pre-commit <root> | commit-msg <root> <file> | post-commit | guarded <root> | locale-role <path>... | locale-paths")
        return 2
    except Refuse as e:
        say(str(e))
        return 1
    except Exception as e:  # noqa: BLE001 - a hook that cannot judge refuses, and says why
        say(f"{verb}: could not judge ({type(e).__name__}: {e}); not committed")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
