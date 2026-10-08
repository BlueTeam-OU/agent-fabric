#!/usr/bin/env python3
"""tools/fabric/github/trial_merge.py — do these branches combine? (ADR-040
Wave 1; runtime/github/trial-merge.sh is its shim.)

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      <PR number | branch>... [--base <ref>] [--check] [--json] [-h|--help]
            options and refs may be mixed; `--base` takes the next argument
            whatever it looks like, and refuses an empty one
  env       AGENT_FABRIC_OPERATOR (where projects/ is, default AGENT_FABRIC_ROOT),
            AGENT_FABRIC_ROOT (where bin/fabric-lease is),
            TMPDIR (where the worktree goes, /tmp when unset or empty),
            AGENT_FABRIC_TRIAL_CONFIG (a trial.json used instead of the
            project's), AGENT_FABRIC_TRIAL_MIN_FREE_KB (default 1048576)
  stdin     not read (the check gets /dev/null)
  stdout    the report (text, or one JSON object with --json); --help
  stderr    every refusal, prefixed `trial-merge: `
  exit      0 combines (and, with --check, the check passed); 1 conflicts,
            or the check failed; 2 could not try — a failed fetch, a ref not
            on origin, no room, bad usage, a merge that failed without a
            conflict — or the check was unavailable

The caller's clone is never touched: HEAD, index, working tree and branches
are as they were, and the worktree, its pid file and its output file are gone
when this returns, however it returns (signals included: INT exits 130, TERM
143, HUP 129, each after the cleanup).

WHY (carried from the bash, where each of these was an incident or a review
finding; the help text says what the tool answers and why).

What differs from the bash, on purpose: jq is not needed; a pid file whose
process exists but belongs to another login (EPERM) is a live run, where
`kill -0` called it dead and the sweep then tried to delete a stranger's
worktree; a check argv element that holds a newline stays one argument (mapfile made
it two); a trial.json that is not JSON is said once on stderr, where jq said
it three times, and the result reads "none declared" either way; an
AGENT_FABRIC_TRIAL_MIN_FREE_KB that is not a number is a refusal, exit 2,
where bash died on an unbound variable with 1; git's own `error:` line for a
ref such as `x^{tree}` is not echoed. A declared `verdict` is an extended
regular expression for grep -E: Python's re reads it, with the POSIX bracket
classes translated, so a construct the two dialects spell differently
(a word-boundary `<`, a leading `{`) can differ.
"""
from __future__ import annotations

import glob
import json
import os
import random
import re
import shutil
import signal
import string
import subprocess
import sys
import time
import warnings

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import git  # noqa: E402
import gh  # noqa: E402
import roots  # noqa: E402

HELP = """Do these branches combine? Merge them, in the order given, onto the
base in a throwaway worktree, optionally run the project's own check
on the result, say what happened, and remove the worktree.

THE QUESTION IT ANSWERS. A change that depends on another agent's
branch has to know the two combine before it is armed, or before "the
code is on a branch" is taken as enough of a dependency. CI and the
merge queue test a PR against main only, never with a sibling it
depends on, and folding the sibling into one's own clone froze that
clone for twenty minutes or left a hand-made worktree behind
(2026-09-26). This answers from the side, and touches nothing of the
caller's: its HEAD, index, working tree and branches are as they were.

WHAT IT SAYS
  combines           every ref merged; the resulting tree hash is given
  conflicts          <ref> did not merge, and the conflicted paths
  could not merge    <ref> failed for another reason (git's line is given):
                     unrelated histories, a missing object — never read
                     as a conflict. The clone's hooks are not run: this
                     merge is never committed anywhere.
  check passed       (--check) the project's check passed on the result
  check failed       (--check) it ran and failed; its last lines are shown
  check unavailable  (--check) it could not say: timed out, not found,
                     its lease still held, or its verdict line missing —
                     never read as a pass
  check not run      the refs did not combine, so there is nothing to check
  The shas tried are printed: a result is true for those shas only, and
  says nothing of branches not named or of the base after it moves.
  It reserves, pushes and decides nothing.

THE CHECK is the project's: projects/<id>/integration/gh/trial.json in
agent-fabric, found from this clone's remote —
  {"check": ["make", "trial-check"], "timeout_s": 600,
   "verdict": "^trial-check: (PASS|FAIL|UNAVAILABLE)", "lease": "..."}
check is an argv run in the worktree (never through a shell). verdict,
when set, is read from the output's last matching line and wins over the
exit code (make exits 2 for every kind of failure); a declared verdict
that never appears is unavailable, whatever the exit code. lease, when
set, runs it under that host lease (fabric-lease), so two agents' builds
queue instead of overloading the host — leave it unset when the check
takes a lease itself. A project that declares none gets merge-only
results, and --check says so. A fresh worktree has no build cache, so a
compiled check starts cold.

Usage:
  runtime/github/trial-merge.sh <PR number | branch>... [--base <ref>] [--check] [--json]

Exit codes:
  0  combines (and, with --check, the check passed)
  1  conflicts, or the check failed
  2  could not try (a failed fetch, a ref not on origin, no room, bad
     usage, a merge that failed without a conflict), or the check was
     unavailable

Environment (the self-test):
  AGENT_FABRIC_TRIAL_CONFIG   path of the trial.json to use instead of the project's
  AGENT_FABRIC_TRIAL_MIN_FREE_KB   free space the worktree needs beyond its size (default 1 GiB)"""

DEFAULT_MIN_FREE_KB = 1048576
DEFAULT_CHECK_TIMEOUT = "1800"
# A fetch is the one call that scales with the remote, not the clone.
FETCH_TIMEOUT_S = 600
# A fresh worktree of a large base is a checkout; a merge rewrites files.
WORKTREE_TIMEOUT_S = 600
# No hook of the clone runs on anything the trial does to its worktree.
# --no-verify skips only pre-merge-commit and commit-msg; measured, the add
# ran post-checkout and reference-transaction, the merge post-merge, and an
# abort reference-transaction (git-lfs and husky install such hooks;
# reviews of #71 and #73). The removals carry it too as a guard: none was
# seen to run a hook there.
NO_HOOKS = ("-c", "core.hooksPath=/dev/null")
# Two runs at once in one repository can make an add fail for a moment
# (another run's prune, git's config lock): one add lost that race in CI.
# A few tries, each clearing only its own half-made entry, then git's own
# last line if it still fails.
ADD_PAUSES = (0.2, 0.5, 1, 2)


class Refused(Exception):
    pass


def say(msg: str) -> None:
    print(f"trial-merge: {msg}", file=sys.stderr)


def tail(text: str, n: int) -> str:
    """`tail -n N <<<"$text"` inside a command substitution: the last N
    lines, trailing newlines gone; empty text stays empty."""
    return "\n".join(text.split("\n")[-n:]).rstrip("\n")


def jq_str(value) -> str:
    """What `jq -r` prints for a scalar."""
    return value if isinstance(value, str) else json.dumps(value)


def load_check(cfg: str) -> tuple[list[str], str, str, str]:
    """(argv, timeout_s, lease, verdict) of a trial.json. A file that is
    missing, is not JSON, or declares no `check` list declares no check
    (the bash read every such case as "none declared" too); `timeout_s`,
    `lease` and `verdict` read as jq's `// default`: null and false are
    unset. timeout_s stays text: `timeout` takes "90", "1.5" and "2m", and
    refuses the rest with 125, which is unavailable."""
    if not cfg or not os.path.isfile(cfg):
        return [], DEFAULT_CHECK_TIMEOUT, "", ""
    try:
        with open(cfg, encoding="utf-8", errors="surrogateescape") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as e:
        say(f"{cfg} is not readable JSON ({e}); no check declared")
        return [], DEFAULT_CHECK_TIMEOUT, "", ""
    if not isinstance(doc, dict):
        return [], DEFAULT_CHECK_TIMEOUT, "", ""

    def field(key: str, default: str) -> str:
        v = doc.get(key)
        return default if v is None or v is False else jq_str(v)

    check = doc.get("check")
    argv = [jq_str(a) for a in check] if isinstance(check, list) else []
    return argv, field("timeout_s", DEFAULT_CHECK_TIMEOUT), field("lease", ""), field("verdict", "")


# grep -E's bracket classes, which Python's re does not know; a class is
# only valid inside a bracket expression, so the replacement never lands
# outside one.
POSIX_CLASSES = {"alpha": "a-zA-Z", "digit": "0-9", "alnum": "a-zA-Z0-9", "upper": "A-Z", "lower": "a-z",
                 "space": " \\t\\n\\r\\f\\v", "blank": " \\t", "punct": "!-/:-@\\[-`{-~", "xdigit": "0-9A-Fa-f",
                 "word": "A-Za-z0-9_", "cntrl": "\\x00-\\x1f\\x7f", "print": " -~", "graph": "!-~"}


def ere_to_re(pattern: str) -> str:
    return re.sub(r"\[:(\w+):\]", lambda m: POSIX_CLASSES.get(m.group(1), m.group(0)), pattern)


def verdict_in(pattern: str, out: str) -> str:
    """The last verdict word of the last line the pattern matches: the bash's
    `grep -oE pattern | tail -n 1 | grep -oE 'PASS|FAIL|UNAVAILABLE' | tail
    -n 1`, line by line. "" when none, or when the pattern is not a regex."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")   # "possible nested set": an ERE's own spelling
            rx = re.compile(ere_to_re(pattern))
    except re.error as e:
        say(f"the declared verdict {pattern!r} is not a regular expression ({e})")
        return ""
    last = ""
    for line in out.split("\n"):
        for m in rx.finditer(line):
            if m.group(0):   # grep -o never prints an empty match
                last = m.group(0)
    words = re.findall("PASS|FAIL|UNAVAILABLE", last)
    return words[-1] if words else ""


def classify(rc: int, verdict_pattern: str, out: str) -> str:
    """Only a pass reads as a pass: a timeout, a command that is not there,
    or a declared verdict line that never came is unavailable.
    124/137 timed out, 125 timeout itself failed, 126/127 no such command,
    75 the lease stayed held (fabric-lease's EX_TEMPFAIL)."""
    if rc in (124, 125, 137, 126, 127, 75):
        return "unavailable"
    if verdict_pattern:
        return {"PASS": "passed", "FAIL": "failed"}.get(verdict_in(verdict_pattern, out), "unavailable")
    return "passed" if rc == 0 else "failed"


def exit_code(result: str, check_state: str) -> int:
    rc = 0
    if result == "conflicts":
        rc = 1
    if result == "could not merge":
        rc = 2
    if check_state == "failed":
        rc = 1
    if check_state == "unavailable" and rc == 0:
        rc = 2
    return rc


def _json_text(obj) -> str:
    """jq's rendering: two-space indent, raw UTF-8, DEL escaped, bytes that
    are not UTF-8 replaced."""
    text = json.dumps(obj, indent=2, ensure_ascii=False).replace("\x7f", "\\u007f")
    return text.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def render_json(r: dict) -> str:
    doc = {"base": r["base"], "base_sha": r["base_sha"],
           "refs": [{"branch": n, "sha": s} for n, s in zip(r["names"], r["shas"])], "result": r["result"]}
    if r["result"] == "combines":
        doc["tree"] = r["tree"]
    else:
        doc.update(failed_ref=r["failed_ref"], conflicted=r["conflicted"], git=tail(r["merge_err"], 3))
    doc["check"] = r["check_state"]
    if r["check_rc"] is not None:
        doc.update(check_exit=r["check_rc"], check_tail=r["check_tail"])
    doc["seconds"] = r["seconds"]
    return _json_text(doc)


def render_text(r: dict) -> str:
    lines = [f"trial-merge onto {r['base']} ({r['base_sha'][:8]}):"]
    lines += [f"  {n} @ {s[:8]}" for n, s in zip(r["names"], r["shas"])]
    if r["result"] == "combines":
        lines.append(f"combines — tree {r['tree'][:12]}")
    elif r["result"] == "conflicts":
        lines.append(f"conflicts — {r['failed_ref']} did not merge:")
        lines += [f"    {p}" for p in r["conflicted"]]
    else:
        lines.append(f"could not merge {r['failed_ref']} (not a conflict):")
        lines += [f"    {l}" for l in tail(r["merge_err"], 3).split("\n")]
    state = r["check_state"]
    if state == "not asked":
        pass
    elif state == "not run: did not combine":
        lines.append("check: not run — the refs did not combine")
    elif state == "none declared":
        lines.append("check: none declared for this project (projects/<id>/integration/gh/trial.json); merge only")
    else:
        lines.append(f"check {state} (exit {r['check_rc']})")
        if state != "passed":
            lines += [f"    {l}" for l in r["check_tail"].split("\n")]
    return "\n".join(lines)


def pid_alive(pid_file: str) -> bool:
    try:
        with open(pid_file, encoding="ascii", errors="replace") as fh:
            pid = int(fh.read().strip())
        if pid <= 0:
            return False
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False
    return True


def sweep(top: str, scratch: str) -> None:
    """A worktree of a run that died is this tool's to clear, and only when
    its owner is gone: a concurrent run's is left alone.
    A run writes its pid right after making its worktree, so a worktree
    with none is from a run killed in that gap: dead within seconds. The
    hour is a generous margin, not a bound on how long a check may run."""
    for d in sorted(glob.glob(os.path.join(scratch, "trial-merge.*"))):
        if not os.path.isdir(d):
            continue
        if os.path.isfile(d + ".pid"):
            if pid_alive(d + ".pid"):
                continue
        else:
            try:
                if time.time() - os.stat(d).st_mtime <= 3600:
                    continue
            except OSError:
                continue
        git.run(top, *NO_HOOKS, "worktree", "remove", "--force", d, check=False)
        remove_tree(d)
        for suffix in (".pid", ".pid.tmp", ".out"):
            remove_file(d + suffix)


def remove_file(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def remove_tree(path: str) -> None:
    if os.path.islink(path):
        remove_file(path)
    else:
        shutil.rmtree(path, ignore_errors=True)


def make_worktree_dir(scratch: str) -> str:
    alphabet = string.ascii_letters + string.digits
    for _ in range(100):
        path = os.path.join(scratch, "trial-merge." + "".join(random.choices(alphabet, k=6)))
        try:
            os.mkdir(path, 0o700)
            return path
        except FileExistsError:
            continue
        except OSError:
            break
    raise Refused(f"cannot make a worktree directory under {scratch}")


def worktree_procs(wt: str, cpid: int | None) -> list[int]:
    """The group is not always the whole check: a declared lease runs it in a
    process group of its own (fabric-lease's set -m). It stays in the
    SESSION the check was given, though, wherever it moves, so every
    process of that session is the check's and is ended with it; anything
    of this login still working inside the worktree is too, as a backstop
    (a process can leave the session only by making its own, as a daemon
    does on purpose)."""
    me, mine = os.getuid(), os.getpid()
    found = []
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == mine:
            continue
        p = f"/proc/{name}"
        try:
            if os.stat(p).st_uid != me:
                continue
            if cpid is not None:
                with open(f"{p}/stat", encoding="utf-8", errors="replace") as fh:
                    # comm may hold ") ": the fields start after the last one.
                    if int(fh.read().rsplit(") ", 1)[1].split()[3]) == cpid:
                        found.append(int(name))
                        continue
            cwd = os.readlink(f"{p}/cwd")
        except (OSError, ValueError, IndexError):
            continue
        if cwd == wt or cwd.startswith(wt + "/"):
            found.append(int(name))
    return found


def terminate(pid: int, group: bool = False) -> None:
    try:
        (os.killpg if group else os.kill)(pid, signal.SIGTERM)
    except OSError:
        pass


def cleanup(top: str, wt: str, cpid: int | None) -> None:
    # The check runs in its own process group so that a killed run takes the
    # whole check with it; an orphaned build would outlive the worktree.
    # The group is killed at the end even when the check exited on its own:
    # whatever it started in the background (a server, a build daemon) would
    # otherwise outlive the worktree it runs in.
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, signal.SIG_IGN)
    if cpid is not None:
        terminate(cpid, group=True)
    for pid in worktree_procs(wt, cpid):
        terminate(pid)
    # Each step on its own: a git that times out (git.py's bound) must not
    # keep the scratch tree and the pid file from going (review of #71).
    for step in (lambda: git.run(top, *NO_HOOKS, "worktree", "remove", "--force", wt, check=False),
                 lambda: remove_tree(wt), lambda: remove_file(wt + ".pid"), lambda: remove_file(wt + ".out"),
                 lambda: git.run(top, "worktree", "prune", check=False)):
        try:
            step()
        except (git.GitError, OSError):
            pass


def add_worktree(top: str, wt: str, base_sha: str) -> None:
    err = ""
    for pause in ADD_PAUSES:
        r = git.run(top, *NO_HOOKS, "worktree", "add", "-q", "--detach", wt, base_sha, check=False, timeout=WORKTREE_TIMEOUT_S)
        if r.returncode == 0:
            return
        err = (r.stderr or r.stdout).strip()
        git.run(top, *NO_HOOKS, "worktree", "remove", "--force", wt, check=False)
        os.makedirs(wt, exist_ok=True)
        time.sleep(pause)
    raise Refused(f"git worktree add failed ({err.split(chr(10))[-1]}); nothing tried")


def merge_all(wt: str, shas: list[str], names: list[str]) -> tuple[str, str, list[str], str, str]:
    """(result, failed_ref, conflicted, tree, merge_err). The clone's hooks
    are not run: this merge is never committed anywhere (NO_HOOKS)."""
    for name, sha in zip(names, shas):
        r = git.run(wt, "-c", "user.name=trial-merge", "-c", "user.email=trial-merge@invalid",
                    "-c", "commit.gpgsign=false", *NO_HOOKS,
                    "merge", "-q", "--no-ff", "--no-edit", "--no-verify", sha,
                    check=False, timeout=WORKTREE_TIMEOUT_S)
        if r.returncode != 0:
            d = git.run(wt, "diff", "--name-only", "--diff-filter=U", check=False).stdout
            conflicted = [p for p in d.split("\n") if p]
            git.run(wt, *NO_HOOKS, "merge", "--abort", check=False)
            return ("conflicts" if conflicted else "could not merge"), name, conflicted, "", r.stderr.rstrip("\n")
    return "combines", "", [], git.run(wt, "rev-parse", "HEAD^{tree}", check=False).stdout.strip(), ""


def run_check(wt: str, argv: list[str], timeout: str, lease: str, fabric: str, started) -> tuple[int, str]:
    """(exit status, its combined output). The status is the shell's: 128+N
    for a runner killed by signal N. `started` is called with the check's
    pid, which is its session and its group, before the wait: a signal that
    ends the wait must still find it to end the group."""
    runner = ["timeout", "--kill-after=30", timeout]
    if lease:
        # A declared lease runs the check under that host lease
        # (fabric-lease), so two agents' builds queue instead of
        # overloading the host.
        runner = [shutil.which("fabric-lease") or os.path.join(fabric, "bin", "fabric-lease"), lease, "--", *runner]
    out_path = wt + ".out"
    with open(out_path, "wb") as out_fh:
        try:
            proc = subprocess.Popen([*runner, *argv], cwd=wt, stdin=subprocess.DEVNULL, stdout=out_fh,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        except PermissionError:
            return 126, ""
        except OSError:
            return 127, ""
        started(proc.pid)
        rc = proc.wait()
    with open(out_path, "rb") as fh:
        out = fh.read().replace(b"\0", b"").decode("utf-8", "surrogateescape").rstrip("\n")
    return (128 - rc if rc < 0 else rc), out


def need_kb_for(top: str, base_sha: str) -> int:
    """Room for a checkout of the base, plus a margin."""
    total = 0
    for line in git.run(top, "ls-tree", "-r", "-l", base_sha, check=False).stdout.split("\n"):
        meta = line.split("\t", 1)[0].split()
        if len(meta) >= 4 and meta[3] != "-":
            total += int(meta[3])
    raw = os.environ.get("AGENT_FABRIC_TRIAL_MIN_FREE_KB") or str(DEFAULT_MIN_FREE_KB)
    try:
        margin = int(raw)
    except ValueError:
        raise Refused(f"AGENT_FABRIC_TRIAL_MIN_FREE_KB is not a number ({raw!r}); nothing tried") from None
    return total // 1024 + margin


def free_kb_of(path: str) -> int:
    try:
        st = os.statvfs(path)
    except OSError:
        return 0
    return st.f_bavail * st.f_frsize // 1024


def resolve_refs(top: str, refs: list[str]) -> tuple[list[str], list[str]]:
    """Each ref as the sha on origin: a PR by its head branch, a branch by name."""
    names, shas = [], []
    for r in refs:
        b = r
        if re.fullmatch("[0-9]+", r):
            if not shutil.which("gh"):
                raise Refused(f"#{r} needs gh to find its branch; nothing tried")
            try:
                # The number as typed: "0007" is what the caller gave gh.
                b = json.loads(gh.run(["pr", "view", r, "--json", "headRefName"], what=f"gh pr view {r}")).get("headRefName") or ""
            except (gh.GhError, ValueError, AttributeError):
                b = ""
            if not b:
                raise Refused(f"#{r} is not a pull request gh can read; nothing tried")
        b = b[len("origin/"):] if b.startswith("origin/") else b
        s = git.out(top, "rev-parse", "-q", "--verify", f"refs/remotes/origin/{b}^{{commit}}", check=False)
        if not s:
            raise Refused(f"{b} is not a branch on origin; nothing tried")
        names.append(b)
        shas.append(s)
    return names, shas


def project_trial_config(top: str, fabric: str) -> str:
    """The project's trial.json, found from this clone's remote."""
    try:
        import workingcopy
        pid = workingcopy.resolve(top).get("project")
    except (Exception, SystemExit):   # a marker naming nothing the registry knows exits: no project, no check
        pid = None
    return roots.project_integration(pid, "gh", "trial.json", engine=fabric) if pid else ""


def run(argv: list[str]) -> int:
    json_out, want_check, base, refs = False, False, "", []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            json_out = True
        elif a == "--check":
            want_check = True
        elif a == "--base":
            if i + 1 >= len(argv) or not argv[i + 1]:
                raise Refused("--base takes a ref")
            base = argv[i + 1]
            i += 1
        elif a in ("-h", "--help"):
            print(HELP)
            return 0
        elif a.startswith("-"):
            raise Refused(f"unknown option '{a}' (try --help)")
        else:
            refs.append(a)
        i += 1
    if not refs:
        raise Refused("name at least one PR number or branch (try --help)")
    if not shutil.which("git"):
        raise Refused("git is required")
    top = git.toplevel(os.getcwd())
    if not top:
        raise Refused("not inside a git working copy")
    os.chdir(top)
    fabric = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

    if git.run(top, "fetch", "-q", "--prune", "origin", check=False, timeout=FETCH_TIMEOUT_S).returncode != 0:
        raise Refused("git fetch origin failed; nothing tried")
    if not base:
        base = git.out(top, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", check=False) or "origin/main"
    base_sha = git.out(top, "rev-parse", "-q", "--verify", f"{base}^{{commit}}", check=False)
    if not base_sha:
        raise Refused(f"the base {base} is not in this clone; nothing tried")
    names, shas = resolve_refs(top, refs)

    # The project's check, when asked for.
    check_argv, check_timeout, check_lease, check_verdict, check_state = [], DEFAULT_CHECK_TIMEOUT, "", "", "not asked"
    if want_check:
        cfg = os.environ.get("AGENT_FABRIC_TRIAL_CONFIG", "") or project_trial_config(top, fabric)
        check_argv, check_timeout, check_lease, check_verdict = load_check(cfg)
        check_state = "pending" if check_argv else "none declared"

    scratch = os.environ.get("TMPDIR") or "/tmp"
    need_kb, free_kb = need_kb_for(top, base_sha), free_kb_of(scratch)
    if free_kb < need_kb:
        raise Refused(f"{scratch} has {free_kb} KB free, the worktree needs {need_kb}; nothing tried")
    sweep(top, scratch)
    git.run(top, "worktree", "prune", check=False)

    wt = make_worktree_dir(scratch)
    started: list[int] = []
    # A signal is an exit, so that the cleanup below always runs.
    for sig, code in ((signal.SIGINT, 130), (signal.SIGTERM, 143), (signal.SIGHUP, 129)):
        signal.signal(sig, lambda _s, _f, code=code: sys.exit(code))
    try:
        # Written whole under another name, then moved: a concurrent run's
        # sweep never reads an empty pid and takes this live worktree for a
        # dead one.
        with open(wt + ".pid.tmp", "w", encoding="ascii") as fh:
            fh.write(f"{os.getpid()}\n")
        os.replace(wt + ".pid.tmp", wt + ".pid")
        add_worktree(top, wt, base_sha)

        start = int(time.time())
        result, failed_ref, conflicted, tree, merge_err = merge_all(wt, shas, names)

        check_rc, check_tail = None, ""
        if result != "combines" and check_state == "pending":
            check_state = "not run: did not combine"
        if result == "combines" and check_state == "pending":
            check_rc, out = run_check(wt, check_argv, check_timeout, check_lease, fabric, started.append)
            check_tail = tail(out, 20)
            check_state = classify(check_rc, check_verdict, out)
        seconds = int(time.time()) - start

        report = {"base": base, "base_sha": base_sha, "names": names, "shas": shas, "result": result,
                  "failed_ref": failed_ref, "conflicted": conflicted, "tree": tree, "merge_err": merge_err,
                  "check_state": check_state, "check_rc": check_rc, "check_tail": check_tail, "seconds": seconds}
        print(render_json(report) if json_out else render_text(report))
        sys.stdout.flush()
        return exit_code(result, check_state)
    finally:
        cleanup(top, wt, started[0] if started else None)


def main() -> int:
    # SIGPIPE stays ignored, as Python leaves it: a closed stdout raises
    # BrokenPipeError through run()'s finally, so the worktree, its pid
    # file and the check's processes are cleaned up before the run ends —
    # the default action killed it first and left them all (review of #71).
    # Bytes git or a check printed that are not UTF-8 go out as they came in.
    sys.stdout.reconfigure(errors="surrogateescape")
    sys.stderr.reconfigure(errors="surrogateescape")
    try:
        return run(sys.argv[1:])
    except Refused as e:
        say(str(e))
        return 2
    except git.GitError as e:
        say(str(e))
        return 2
    except BrokenPipeError:
        # The reader is gone and cleanup has run; end as a pipe-killed run
        # ends, quietly and 141, with stdout on /dev/null so the exit's own
        # flush does not raise again.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141


if __name__ == "__main__":
    sys.exit(main())
