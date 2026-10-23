"""The five read tools over git (agent-fabric ADR-065 §2 A): a fixed argv per tool, typed fields, no shell, no verb that writes.

What makes the argv safe is spelled out where it is built (`git_argv`): every config key that can name a program is overridden on the
command line, the system and global config are not read, attributes come from an empty tree so a pull request's .gitattributes names
no driver, and a revision reaches a command only as the commit id git resolved it to.
"""
from __future__ import annotations

import os

from review_mcp import runner, scope
from review_mcp.scope import ToolError

CAP_BYTES = 100_000
BUDGET_S = 30.0
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"       # git knows this object without it being stored; sha-256 repositories are refused below
# A key that can run a program, or a setting that changes what a verb prints, pinned on the command line: a -c outranks the repository's
# config, which a pull request cannot write but a hostile clone-local key might name (core.fsmonitor, diff.external, a pager).
PINNED = ("core.fsmonitor=false", "core.hooksPath=/dev/null", "core.pager=cat", "core.attributesFile=/dev/null", "diff.external=",
          "protocol.allow=never", "log.showSignature=false", "gc.auto=0", "core.warnAmbiguousRefs=true", "color.ui=never")
GIT = "git"


def git_argv(repository: str, *args: str) -> list[str]:
    return [GIT, "--no-pager", f"--attr-source={EMPTY_TREE}", *[x for key in PINNED for x in ("-c", key)], "-C", repository, *args]


def run_git(repository: str, *args: str, env: dict[str, str] | None = None) -> runner.Ran:
    try:
        return runner.run_bounded(git_argv(repository, *args), env if env is not None else scope.git_env(), repository, BUDGET_S, CAP_BYTES)
    except OSError as e:
        raise ToolError(f"git cannot be started: {e.strerror or e}") from None


def first_line(ran: runner.Ran) -> str:
    return (ran.err.decode("utf-8", "replace").strip().splitlines() or ["no message"])[0][:300]


def _checked(ran: runner.Ran, what: str, ok: tuple[int, ...] = (0,)) -> runner.Ran:
    if ran.timed_out:
        raise ToolError(f"{what} did not finish within {BUDGET_S:.0f} s and was ended")
    if not ran.cut and ran.returncode not in ok:
        raise ToolError(f"{what} failed (exit {ran.returncode}): {first_line(ran)}")
    return ran


def allowed_repositories(env: dict[str, str] | None = None, project_dir: str | None = None) -> list[str]:
    """The session clone's toplevel and its worktrees, as real paths. The narrowest input is the clone Claude Code was started in
    (CLAUDE_PROJECT_DIR); without it nothing is allowed, since a default would be a guess about which repository the reviewer may read."""
    project_dir = project_dir if project_dir is not None else os.environ.get("CLAUDE_PROJECT_DIR", "")
    if not project_dir or not os.path.isdir(project_dir):
        raise ToolError("CLAUDE_PROJECT_DIR does not name the session's clone; no repository is allowed")
    env = env if env is not None else scope.git_env()
    top = _checked(run_git(project_dir, "rev-parse", "--show-toplevel", env=env), "finding the session clone")
    clone = os.path.realpath(top.out.decode("utf-8", "replace").strip())
    listing = _checked(run_git(clone, "worktree", "list", "--porcelain", "-z", env=env), "listing the clone's worktrees")
    found = [clone]
    for record in listing.out.split(b"\0"):
        if record.startswith(b"worktree "):
            found.append(os.path.realpath(os.fsdecode(record[len(b"worktree "):])))
    return list(dict.fromkeys(found))


def repository_of(args: dict) -> str:
    """The repository a call names (default: the session clone), if it is the clone or one of its worktrees; its real path."""
    allowed = allowed_repositories()
    named = scope.field("repository", args.get("repository"), required=False)
    if not named:
        return allowed[0]
    real = os.path.realpath(named)
    if real not in allowed:
        raise ToolError("repository is not the session's clone or one of its worktrees")
    return real


def resolve(repository: str, name: str, value: object, env: dict[str, str] | None = None) -> str:
    """The commit id `value` names, from git itself, refused when it names nothing or names two things (a branch and a tag of one name
    resolve with exit 0 and a warning, and which one a later command meant is not knowable). Only the id is used afterwards."""
    rev = scope.field(name, value)
    ran = _checked(run_git(repository, "rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}", env=env), f"resolving {name}", ok=(0, 128))
    sha = ran.out.decode("utf-8", "replace").strip()
    if ran.returncode != 0 or not scope.SHA.fullmatch(sha):
        raise ToolError(f"{name} does not name a commit of this repository")
    if b"ambiguous" in ran.err:
        raise ToolError(f"{name} is ambiguous in this repository; give the commit id")
    if len(sha) != 40:
        raise ToolError("a repository with sha-256 object names is not supported")
    return sha


def _result(ran: runner.Ran) -> str:
    return runner.text_of(ran.out, CAP_BYTES, ran.cut)


def review_diff(args: dict) -> str:
    repo = repository_of(args)
    base, head = resolve(repo, "base", args.get("base")), resolve(repo, "head", args.get("head"))
    shape = args.get("output") or "patch"
    form = {"patch": [], "stat": ["--stat"], "name-only": ["--name-only"], "name-status": ["--name-status"]}.get(shape)
    if form is None:
        raise ToolError("output must be patch, stat, name-only or name-status")
    context = scope.whole("context", args.get("context"), 0, 200, 3)
    paths = scope.pathspecs_field(args.get("pathspec"))
    return _result(_checked(run_git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-color", f"--unified={context}", *form, base, head,
                                    *(["--", *paths] if paths else [])), "git diff"))


def review_log(args: dict) -> str:
    repo = repository_of(args)
    head = resolve(repo, "head", args.get("head"))
    base = resolve(repo, "base", args["base"]) if args.get("base") else None
    count = scope.whole("max_count", args.get("max_count"), 1, 1000, 50)
    path = scope.pathspec_field("path", args.get("path")) if args.get("path") else None
    body = ["--patch", "--format=fuller"] if args.get("patch") else ["--format=%H %an %ad %s", "--date=short"]
    return _result(_checked(run_git(repo, "log", "--no-ext-diff", "--no-textconv", "--no-color", f"--max-count={count}", *body,
                                    f"{base}..{head}" if base else head, *(["--", path] if path else [])), "git log"))


def review_show(args: dict) -> str:
    repo = repository_of(args)
    rev = resolve(repo, "rev", args.get("rev"))
    if args.get("path"):
        path = scope.path_field("path", args.get("path"))
        return _result(_checked(run_git(repo, "show", "--no-textconv", "--no-color", f"{rev}:{path}"), "git show"))
    return _result(_checked(run_git(repo, "show", "--no-ext-diff", "--no-textconv", "--no-color", "--format=fuller", rev), "git show"))


def review_blame(args: dict) -> str:
    repo = repository_of(args)
    rev = resolve(repo, "rev", args.get("rev"))
    path = scope.path_field("path", args.get("path"))
    first = scope.whole("line_start", args.get("line_start"), 1, 10_000_000)
    last = scope.whole("line_end", args.get("line_end"), first, 10_000_000, first)
    return _result(_checked(run_git(repo, "blame", "--no-textconv", "--date=short", "-L", f"{first},{last}", rev, "--", path), "git blame"))


def review_grep(args: dict) -> str:
    repo = repository_of(args)
    rev = resolve(repo, "rev", args.get("rev"))
    pattern = scope.field("pattern", args.get("pattern"))
    paths = scope.pathspecs_field(args.get("pathspec"))
    count = scope.whole("max_count", args.get("max_count"), 1, 1000, 100)
    mode = "-F" if args.get("fixed") else "-E"       # explicit either way: grep.patternType in the repository's config does not choose
    case = ["-i"] if args.get("ignore_case") else []
    ran = _checked(run_git(repo, "grep", "-n", "-I", "--no-color", mode, *case, f"--max-count={count}", "-e", pattern, rev,
                           *(["--", *paths] if paths else [])), "git grep", ok=(0, 1))
    return _result(ran) if ran.out or ran.cut else "no match"
