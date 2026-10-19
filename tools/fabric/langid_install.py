"""tools/fabric/langid_install.py — the language detector for THIS account,
under ~/.cache/agent-fabric/langid/venv/: a Python venv with the package
runtime/langid/detector.json pins (pycld2 — CLD2's tables are compiled into
the binding, so there is no model file to fetch; the binding builds from
source and needs a C++ compiler). Ported from runtime/langid/install.sh
(Wave 9, ADR-040 §7); tests/test_langid_install.py is the oracle.

Idempotent; --dry-run says what it would do. Best effort from bootstrap: a
host without the network or a compiler keeps what it has and says so, and
the control agent's `script` op reports `language` as unavailable rather
than failing. Nothing here names an agent or reads a secret.

CONTRACT:
  argv      only a FIRST argument of exactly --dry-run means a dry run;
            anything else is ignored, as the shell ignored it.
  env       AGENT_FABRIC_LANGID_DIR (the target; empty counts as unset,
            default $HOME/.cache/agent-fabric/langid); AGENT_FABRIC_LANGID_PIP
            (a command, split on whitespace, run in place of
            `<venv>/bin/pip install -q`, the package appended last).
            PATH finds `python3`, the interpreter that makes the venv (the
            host's, not the fabric's pin: the venv outlives the checkout).
            The children inherit the environment.
  stdout    one line per step: "  -  <model> (removed|would remove: the
            detector is CLD2 now)" for an earlier version's lid.176.ftz,
            then one of "  =  <venv> (<pkg>)" present and importing,
            "  +  <venv> (would create and install <pkg>)" on a dry run,
            "  +  <venv> (<pkg>)" installed, or "  !  <venv>: …" failed.
  stderr    nothing of its own but the interrupt line; the children's output
            is discarded.
  exit      0 done, present or dry run; 1 a said failure (venv, install,
            import check, an unusable target); 130 interrupted, the child
            killed with its group. Never a traceback.
  files     on the install branch the target directory is created, or
            chmod'ed, to 0700; a venv already importing pycld2 leaves it as
            it is; a dry run creates and removes nothing.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
DETECTOR = os.path.join(ROOT, "runtime", "langid", "detector.json")

IMPORT_TIMEOUT_S = 60
VENV_TIMEOUT_S = 300
# pycld2 compiles C++ from source; a slow host needs minutes, a hung one must not hold bootstrap forever.
PIP_TIMEOUT_S = 1800


def say(line: str) -> None:
    print(line, flush=True)


def quiet(argv: list[str], timeout: int) -> bool:
    """True when argv ran and exited 0. A missing command, a timeout and a
    non-zero exit are all "no": the caller says one failure line for each.
    The child leads its own process group so a timeout takes pip's compiler
    children with it, not only pip."""
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    try:
        return proc.wait(timeout=timeout) == 0
    except BaseException as exc:
        # An interrupt reaches only the foreground group, and the child left it:
        # without this kill, Ctrl-C would strand a pip still building into the venv.
        with contextlib.suppress(OSError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        if isinstance(exc, subprocess.TimeoutExpired):
            return False
        raise


def has_detector(venv_python: str) -> bool:
    return (os.path.isfile(venv_python) and os.access(venv_python, os.X_OK)
            and quiet([venv_python, "-c", "import pycld2"], IMPORT_TIMEOUT_S))


def run(argv: list[str]) -> int:
    dry_run = bool(argv) and argv[0] == "--dry-run"
    try:
        with open(DETECTOR, encoding="utf-8") as fh:
            package = json.load(fh)["package"]
        if not isinstance(package, str) or not package:
            raise ValueError("package is not a non-empty string")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        say(f"  !  {DETECTOR}: unreadable ({type(exc).__name__}); the language section stays unavailable")
        return 1
    home = os.environ.get("HOME", "")
    target = os.environ.get("AGENT_FABRIC_LANGID_DIR") or (
        os.path.join(home, ".cache", "agent-fabric", "langid") if home else "")
    if not target:
        say("  !  HOME is unset and AGENT_FABRIC_LANGID_DIR is not given; the language section stays unavailable")
        return 1
    rc = 0
    # The fastText model an earlier version fetched here is not read any more.
    model = os.path.join(target, "lid.176.ftz")
    if os.path.isfile(model):
        if dry_run:
            say(f"  -  {model} (would remove: the detector is CLD2 now)")
        else:
            try:
                os.unlink(model)
                say(f"  -  {model} (removed: the detector is CLD2 now)")
            except OSError as exc:
                say(f"  !  {model}: not removed ({type(exc).__name__})")
                rc = 1
    venv = os.path.join(target, "venv")
    venv_python = os.path.join(venv, "bin", "python")
    if has_detector(venv_python):
        say(f"  =  {venv} ({package})")
    elif dry_run:
        say(f"  +  {venv} (would create and install {package})")
    else:
        try:
            os.makedirs(target, exist_ok=True)
            os.chmod(target, 0o700)
        except OSError as exc:
            say(f"  !  {target}: cannot be prepared ({type(exc).__name__}); the language section stays unavailable")
            return 1
        executable = os.path.isfile(venv_python) and os.access(venv_python, os.X_OK)
        made = False
        if not executable:
            # venv writes bin/python before bin/pip: a half-made one would pass the
            # `executable` test on the next run and fail there for the wrong reason.
            try:
                made = quiet(["python3", "-m", "venv", venv], VENV_TIMEOUT_S)
            finally:
                if not made:
                    shutil.rmtree(venv, ignore_errors=True)
        if not executable and not made:
            say(f"  !  {venv}: python3 -m venv failed; the language section stays unavailable")
            rc = 1
        else:
            override = os.environ.get("AGENT_FABRIC_LANGID_PIP", "")
            pip = override.split() if override else [os.path.join(venv, "bin", "pip"), "install", "-q"]
            if quiet([*pip, package], PIP_TIMEOUT_S) and quiet([venv_python, "-c", "import pycld2"], IMPORT_TIMEOUT_S):
                say(f"  +  {venv} ({package})")
            else:
                say(f"  !  {venv}: could not install {package} (offline, or no C++ compiler on this host); "
                    "the language section stays unavailable")
                rc = 1
    return rc


def main(argv: list[str]) -> int:
    try:
        return run(argv)
    except KeyboardInterrupt:
        print("  !  interrupted; the language section stays as it was", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
