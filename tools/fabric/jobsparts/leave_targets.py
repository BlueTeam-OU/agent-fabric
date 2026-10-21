"""tools/fabric/jobsparts/leave_targets.py — the cargo targets `switch` clears from the worktree of the job it leaves (j75, the owner
2026-10-21: /home filled twice in a day, one project's target is 60 to 75 GB and every job worktree builds its own).
A part of tools/fabric/jobs.py, whose docstring is the contract.

Contract. Only the old job's `worktree` field is read: never its `working copy` or another job's (a main checkout other jobs share:
a field at, above or below one is refused), only a linked worktree, nothing outside the login's home, nothing when the field is unset or the directory is
gone. In it, each directory named `target` beside a Cargo.toml, at most 4 levels below the worktree, is removed — links are
never followed (a `target` that is one is kept), and a filesystem boundary is never crossed (a `target` holding another mount
is kept whole). One is kept, with the reason, when a process of this uid stands in it, when its `.cargo-lock` is held (a build
is running), or when a cargo configuration at or above it points the target directory outside the worktree. Whatever cannot
be told is kept: unknown is never "free to remove". One line per directory; a failure is a warning line, never a refusal:
the job's settlement already happened. One shared CARGO_TARGET_DIR per login is not an alternative (binaries bake in
CARGO_MANIFEST_DIR, so a build shared between worktrees runs stale paths)."""
from __future__ import annotations

import fcntl
import os
import shutil
import tomllib

MAX_DEPTH = 4
CONFIGS = (os.path.join(".cargo", "config.toml"), os.path.join(".cargo", "config"))
LOCK_DEPTH = 3      # target/<triple>/<profile>/.cargo-lock is the deepest place cargo puts it


class Unknown(Exception):
    """A fact about a target that could not be read: the target is kept."""


def human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def inside(path: str, root: str) -> bool:
    return path != root and path.startswith(root.rstrip(os.sep) + os.sep)


def find_targets(worktree: str) -> tuple[list[str], list[str]]:
    """(the `target` directories beside a Cargo.toml, the `target` links beside one), below the worktree and not below another."""
    found: list[str] = []
    links: list[str] = []
    base = worktree.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(worktree, followlinks=False):
        depth = dirpath.count(os.sep) - base
        dirnames[:] = [d for d in dirnames if d not in (".git", "target") and not os.path.islink(os.path.join(dirpath, d))] if depth < MAX_DEPTH - 1 else []
        if "Cargo.toml" in filenames and depth + 1 <= MAX_DEPTH:
            t = os.path.join(dirpath, "target")
            if os.path.islink(t):
                links.append(t)
            elif os.path.isdir(t):
                found.append(t)
    return found, links


def live_cwds() -> list[str]:
    """The directories processes of this uid stand in. A /proc that cannot be listed is Unknown, not "nobody"."""
    uid = os.getuid()
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError as e:
        raise Unknown(f"processes cannot be listed ({e.strerror or e})") from None
    cwds = []
    for pid in pids:
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            cwds.append(os.readlink(f"/proc/{pid}/cwd").removesuffix(" (deleted)"))
        except OSError:
            continue      # gone since the listing, or a kernel thread: not a process standing anywhere
    if not cwds:
        raise Unknown("no process of this uid shows its directory, not even this one")
    return cwds


def scan(target: str, dev: int) -> tuple[int, list[str]]:
    """(the bytes the tree holds, the `.cargo-lock` files in it); Unknown when another filesystem is mounted in it or a directory
    cannot be read."""
    total = 0
    seen: set[tuple[int, int]] = set()      # cargo hard-links its artifacts out of deps/: one inode is freed once
    locks: list[str] = []
    errors: list[OSError] = []
    base = target.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(target, followlinks=False, onerror=errors.append):
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                st = os.lstat(path)
            except OSError:
                continue
            if (st.st_dev, st.st_ino) not in seen:
                seen.add((st.st_dev, st.st_ino))
                total += st.st_blocks * 512
            if name == ".cargo-lock" and dirpath.count(os.sep) - base <= LOCK_DEPTH:
                locks.append(path)
        for d in dirnames:
            path = os.path.join(dirpath, d)
            if os.path.islink(path):
                continue
            if os.lstat(path).st_dev != dev:
                raise Unknown("another filesystem is mounted in it")
    if errors:
        raise Unknown(f"{errors[0].filename} cannot be read ({errors[0].strerror})")
    return total, locks


def config_dirs(target: str, worktree: str) -> list[str]:
    """The directories whose `.cargo/` cargo reads for a build in `target`'s directory: it and every parent up to the root (above
    the worktree too), then $CARGO_HOME, whose files are `config.toml` directly."""
    dirs = []
    here = os.path.dirname(target)
    while True:
        dirs.append(here)
        up = os.path.dirname(here)
        if up == here:
            break
        here = up
    return dirs


def config_files(target: str, worktree: str) -> list[tuple[str, str]]:
    """(file, directory its relative paths are taken from), nearest first."""
    files = [(os.path.join(d, name), d) for d in config_dirs(target, worktree) for name in CONFIGS]
    home = os.environ.get("CARGO_HOME") or os.path.join(os.path.expanduser("~"), ".cargo")
    files += [(os.path.join(home, name), os.path.dirname(home)) for name in ("config.toml", "config")]
    return files


def outside_config(target: str, worktree: str) -> str | None:
    """The path a cargo configuration that applies to `target` sends the target directory to when that is outside the worktree,
    else None. A configuration that exists and cannot be read is Unknown: only a file that is not there is absent."""
    for conf, base in config_files(target, worktree):
        try:
            os.lstat(conf)
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError as e:
            raise Unknown(f"{conf} cannot be looked at ({e.strerror})") from None
        try:
            with open(conf, "rb") as fh:
                doc = tomllib.load(fh)
        except (OSError, ValueError) as e:      # a TOML error and bytes that are not UTF-8 are both ValueErrors
            raise Unknown(f"{conf} cannot be read ({type(e).__name__})") from None
        named = []
        build = doc.get("build")
        if isinstance(build, dict) and isinstance(build.get("target-dir"), str):
            named.append(os.path.join(base, build["target-dir"]))      # relative to the directory holding .cargo
        env = doc.get("env")
        if isinstance(env, dict) and "CARGO_TARGET_DIR" in env:
            v = env["CARGO_TARGET_DIR"]
            value = v.get("value") if isinstance(v, dict) else v
            if not isinstance(value, str):
                raise Unknown(f"{conf} has a CARGO_TARGET_DIR that is not a path")
            relative = isinstance(v, dict) and v.get("relative") is True
            named.append(os.path.join(base, value) if relative else value)
        for p in named:
            p = os.path.expanduser(p)
            p = os.path.realpath(p if os.path.isabs(p) else os.path.join(worktree, p))
            if not (p == worktree or inside(p, worktree)):
                return p
    return None


def lock_held(locks: list[str]) -> tuple[bool, list[int]]:
    """Whether any of the lock files is held by a build (a non-blocking flock refused), and the descriptors that took the rest:
    they stay open through the removal, so a build cannot start under it. Unknown on a lock that can be neither opened nor tried."""
    fds: list[int] = []
    try:
        for path in locks:
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            except OSError as e:
                raise Unknown(f"{path} cannot be opened ({e.strerror})") from None
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                return True, fds
            except OSError as e:
                os.close(fd)
                raise Unknown(f"{path} cannot be tried ({e.strerror})") from None
            fds.append(fd)
    except BaseException:
        for fd in fds:
            os.close(fd)
        raise
    return False, fds


def overlaps(path: str, root: str) -> bool:
    """Whether `path` is the root, inside it or above it: a checkout that is any of these is not the job's to clear."""
    return path == root or inside(path, root) or inside(root, path)


def clean_targets(worktree: str | None, working_copy: str | None, others: tuple[str | None, ...] = ()) -> list[str]:
    """The lines the clearing says: one per `target`, removed or kept with the reason; a warning, not an exception, on a failure.
    `others` are the working copies and worktrees of the other jobs of the list: a worktree at, above or below one is shared."""
    if not worktree:
        return []
    lines: list[str] = []
    try:
        home = os.path.realpath(os.path.expanduser("~"))
        if not os.path.isdir(worktree):
            return []
        root = os.path.realpath(worktree)
        if not inside(root, home):
            return [f"cargo targets: {worktree} is not under {home}; left alone"]
        # A linked worktree has a `.git` file; a main checkout a directory. Whatever else the field names (a parent of several
        # checkouts, a directory inside one) is not the job's own worktree.
        if not os.path.isfile(os.path.join(root, ".git")):
            return [f"cargo targets: {worktree} is not a linked worktree; left alone"]
        for c in (working_copy, *others):
            if c and os.path.lexists(c) and overlaps(os.path.realpath(c), root):
                return [f"cargo targets: {worktree} is, holds or lies in a checkout of this or another job ({c}); left alone"]
        found, links = find_targets(root)
        lines = [f"kept {t}: a link, not followed" for t in links]
        if not found:
            return lines
        dev = os.lstat(root).st_dev
        try:
            cwds, why_blind = live_cwds(), ""
        except Unknown as e:
            cwds, why_blind = [], str(e)
        for t in found:
            try:
                lines.append(one(t, root, dev, cwds, why_blind))
            except Exception as e:      # one target's failure is its own line: the others are still judged
                lines.append(f"warning: {t} not cleared: {type(e).__name__}: {e}")
        return lines
    except Exception as e:      # the settlement already happened: nothing here refuses the switch
        return lines + [f"warning: cargo targets of {worktree} not cleared: {type(e).__name__}: {e}"]


def one(target: str, root: str, dev: int, cwds: list[str], why_blind: str) -> str:
    fds: list[int] = []
    try:
        if why_blind:
            raise Unknown(why_blind)
        if os.lstat(target).st_dev != dev:
            raise Unknown("another filesystem")
        real = os.path.realpath(target)
        if any(c == real or inside(c, real) for c in cwds):
            return f"kept {target}: a process of this uid stands in it"
        outside = outside_config(target, root)
        if outside:
            return f"kept {target}: a cargo configuration sends the target directory to {outside}"
        size, locks = scan(target, dev)
        held, fds = lock_held(locks)
        if held:
            return f"kept {target}: its .cargo-lock is held, a build is running"
        shutil.rmtree(target)
        return f"removed {target} ({human(size)})"
    except Unknown as e:
        return f"kept {target}: {e}"
    except OSError as e:
        return f"warning: {target} not removed: {e.strerror or e} ({e.filename})"
    finally:
        for fd in fds:
            os.close(fd)
