#!/usr/bin/env python3
"""Tests for runtime/provisioning/moveto/moveto.py's internals; the
behaviour is runtime/provisioning/moveto/test_moveto.sh's, run unchanged
against the moveto shim (ADR-040 §5 rule 5). What is here is what that
suite does not reach: the exec into the entering shell, a directory
service that hangs, the shim run from an installed copy, and the details
of what reaches the terminal (control characters, padding, order). Plain
script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "runtime", "provisioning", "moveto")
sys.path.insert(0, SRC)
import moveto as mv  # noqa: E402


def clean_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_"))}
    env.update(extra)
    return env


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        def put(path: str, text: str, mode: int = 0o644) -> str:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(path, mode)
            return path

        print("what reaches the terminal")
        check("C0, DEL and C1 controls are stripped; the printable rest stays",
              mv.display_safe("a\x1b]0;X\x07b\x7fc\x9bd") == "a]0;Xbcd")
        check("…and the line and paragraph separators a UTF-8 terminal breaks on",
              mv.display_safe("x\u2028y\u2029z") == "xyz")
        check("non-ASCII text that is not a control is kept", mv.display_safe("rôle ✓") == "rôle ✓")
        check("columns are padded by bytes, as bash's printf counts",
              mv.pad("ab", 5) == "ab   " and mv.pad("é", 4) == "é  " and mv.pad("longer-than", 4) == "longer-than")

        print("the role from the binding")
        bin_ = f"{tmp}/bin"
        put(f"{bin_}/getent", f"#!/usr/bin/env bash\necho \"$2:x:2000:2000::{tmp}/home/$2:/bin/bash\"\n", 0o755)
        put(f"{bin_}/sudo", "#!/usr/bin/env bash\nwhile [[ $1 == -* ]]; do [[ $1 == -u ]] && shift; shift; done\nexec \"$@\"\n",
            0o755)
        saved_path = os.environ["PATH"]
        os.environ["PATH"] = f"{bin_}:{saved_path}"
        try:
            b = f"{tmp}/home/acct/.local/state/agent-fabric/agents/acct/binding.json"
            put(b, '{"agent": "acct", "role": "first"}\n{"role": "second", "x": "y", "role": "last-on-line"}\n')
            check("the first line that names one, its last occurrence (sed's greedy .*)", mv.role_of("acct") == "first")
            put(b, '{"agent": "acct", "role": ""}\n')
            check("an empty role is -", mv.role_of("acct") == "-")
            put(b, "not json at all\n")
            check("no role at all is -", mv.role_of("acct") == "-")
        finally:
            os.environ["PATH"] = saved_path

        print("order")
        # In a locale whose collation is not byte order: under C.UTF-8 the
        # two agree, and the check would prove nothing.
        names = [b"web-dev-01", b"webdev-02", b"Alpha", b"alpha"]
        locales = subprocess.run(["locale", "-a"], capture_output=True, text=True, timeout=30).stdout.split()
        collating = next((loc for loc in ("en_US.utf8", "en_US.UTF-8", "C.utf8") if loc in locales), None)
        saved_lc = os.environ.get("LC_ALL")
        os.environ["LC_ALL"] = collating or "C"
        try:
            r = subprocess.run(["sort", "-z"], input=b"\0".join(names) + b"\0", capture_output=True, timeout=30)
            expected = [n for n in r.stdout.split(b"\0") if n]
            got = mv.sort_z(names)
        finally:
            if saved_lc is None:
                os.environ.pop("LC_ALL", None)
            else:
                os.environ["LC_ALL"] = saved_lc
        if collating and collating.startswith("en_US"):
            check(f"accounts and clones come in `sort`'s order under {collating}, which is not Python's bytes",
                  got == expected and expected != sorted(names), f"{got} vs {expected}")
        else:
            check(f"accounts and clones come in `sort`'s order (no collating locale here: {collating})", got == expected)
        check("…and nothing to sort is nothing", mv.sort_z([]) == [])

        print("the exec into the shell")
        calls = []
        saved = (mv.os.execv, mv.os.execvp, mv.me, mv.command, mv.run_as, mv.home_of, mv.list_clones)
        mv.os.execv = lambda path, argv: calls.append(("execv", path, argv)) or (_ for _ in ()).throw(SystemExit(0))
        mv.os.execvp = lambda path, argv: calls.append(("execvp", path, argv)) or (_ for _ in ()).throw(SystemExit(0))
        mv.home_of = lambda a: f"/h/{a}"
        mv.command = lambda args, stdin=None: (0, b"")
        mv.run_as = lambda a, *args: (0, b"")
        mv.list_clones = lambda a: (["c1"], "")
        try:
            mv.me = lambda: "op"
            try:
                with redirect_stdout(io.StringIO()), open(os.devnull, "w") as null:
                    sys.stderr, saved_err = null, sys.stderr
                    try:
                        mv.moveto(["acct"])
                    finally:
                        sys.stderr = saved_err
            except SystemExit:
                pass
            check("another account: sudo -n -u <it> -H enter <dir> <title>, nothing else",
                  calls == [("execvp", "sudo", ["sudo", "-n", "-u", "acct", "-H", mv.MOVETO_ENTER, "/h/acct/projects", "acct"])],
                  str(calls))
            calls.clear()
            mv.me = lambda: "acct"
            try:
                with redirect_stdout(io.StringIO()), open(os.devnull, "w") as null:
                    sys.stderr, saved_err = null, sys.stderr
                    try:
                        mv.moveto(["acct", "c1"])
                    finally:
                        sys.stderr = saved_err
            except SystemExit:
                pass
            check("this account: enter itself, no sudo", calls == [("execv", mv.MOVETO_ENTER, [mv.MOVETO_ENTER,
                                                                                               "/h/acct/projects/c1", "acct"])],
                  str(calls))
        finally:
            mv.os.execv, mv.os.execvp, mv.me, mv.command, mv.run_as, mv.home_of, mv.list_clones = saved

        print("a directory service that hangs")
        put(f"{bin_}/getent", "#!/usr/bin/env bash\nexec sleep 60\n", 0o755)
        saved_timeout = mv.TIMEOUT_S
        mv.TIMEOUT_S = 1
        os.environ["PATH"] = f"{bin_}:{saved_path}"
        try:
            t0 = time.monotonic()
            home = mv.home_of("acct")
            took = time.monotonic() - t0
            check("reads as the command failing within its bound: no home, not a hung prompt",
                  home == "" and took < 10, f"took {took:.1f} s")
        finally:
            os.environ["PATH"] = saved_path
            mv.TIMEOUT_S = saved_timeout

        print("the command line")
        fx = f"{tmp}/fx"
        put(f"{fx}/bin/getent", f"""#!/usr/bin/env bash
accounts="solo:2000 sys:999 mult:2001"
if [[ $1 == passwd && $# -eq 2 ]]; then
  for a in $accounts; do [[ ${{a%%:*}} == "$2" ]] && {{ echo "$2:x:${{a#*:}}:${{a#*:}}::{fx}/home/$2:/bin/bash"; exit 0; }}; done; exit 2
fi
for a in $accounts; do echo "${{a%%:*}}:x:${{a#*:}}:${{a#*:}}::{fx}/home/${{a%%:*}}:/bin/bash"; done
""", 0o755)
        put(f"{fx}/bin/sudo", "#!/usr/bin/env bash\nwhile [[ $1 == -* ]]; do [[ $1 == -u ]] && shift; shift; done\nexec \"$@\"\n",
            0o755)
        for acct, clone in (("solo", "one"), ("sys", "sysclone"), ("mult", "a"), ("mult", "b\x1b]0;X\x07c")):
            os.makedirs(f"{fx}/home/{acct}/projects/{clone}", exist_ok=True)

        def cli(*args):
            return subprocess.run(["bash", os.path.join(SRC, "moveto"), *args], capture_output=True, text=True,
                                  timeout=60, env=clean_env(AGENT_FABRIC_PYTHON=sys.executable,
                                                            PATH=f"{fx}/bin:{os.environ['PATH']}"))
        r = cli()
        check("no arguments: the usage on stdout, exit 0", r.returncode == 0 and r.stdout == mv.USAGE)
        r = cli("--list")
        check("--list leaves out accounts below uid 1000 (system accounts)",
              r.returncode == 0 and "solo" in r.stdout and "sys" not in r.stdout.split(), r.stdout)
        r = cli("nobody", "--list")
        check("<account> --list for an account that does not exist is refused by name",
              r.returncode == 1 and r.stderr == "moveto: no such account: nobody\n", r.stderr)
        r = cli("mult", "--list")
        check("<account> --list prints its clones with no control character",
              r.returncode == 0 and r.stdout == "a\nb]0;Xc\n", repr(r.stdout))
        r = cli("solo", "--bogus")
        check("an unknown option is refused, with where to look",
              r.returncode == 1 and r.stderr == "moveto: unknown option '--bogus' (try --help)\n", r.stderr)
        r = cli("mult", "a", "b")
        check("two clones are refused: one at a time", r.returncode == 1 and r.stderr == "moveto: one clone at a time\n")

        print("an installed copy")
        prefix = f"{tmp}/usr-local"
        r = subprocess.run(["sh", os.path.join(SRC, "install.sh")], env=clean_env(MOVETO_PREFIX=prefix),
                           capture_output=True, text=True, timeout=60)
        check("install.sh puts the module beside enter and rc, and records it",
              r.returncode == 0 and os.path.isfile(f"{prefix}/share/moveto/moveto.py")
              and "share/moveto/moveto.py" in open(f"{prefix}/share/moveto/installed.sha256").read(), r.stderr)
        sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
        import hosttools
        check("fabric-status reads a fresh install as in sync", hosttools.moveto_drift(prefix, root=HERE)["status"] == "in sync")
        with open(f"{prefix}/share/moveto/moveto.py", "a", encoding="utf-8") as fh:
            fh.write("# an older copy\n")
        drift = hosttools.moveto_drift(prefix, root=HERE)
        check("…and an installed module behind the repository as drift, naming it",
              drift["status"] == "drift" and "share/moveto/moveto.py" in drift["detail"], str(drift))
        moved = f"{tmp}/elsewhere"
        shutil.copytree(prefix, moved)
        r = subprocess.run([f"{moved}/bin/moveto", "--help"], env=clean_env(AGENT_FABRIC_PYTHON=sys.executable),
                           capture_output=True, text=True, timeout=60)
        check("the installed shim runs its own copy of the module, with no checkout behind it",
              r.returncode == 0 and r.stdout == mv.USAGE, r.stderr)
        r = subprocess.run([f"{moved}/bin/moveto", "--help"], env=clean_env(AGENT_FABRIC_PYTHON=f"{tmp}/no-python"),
                           capture_output=True, text=True, timeout=60)
        check("no pinned interpreter: exit 127, one line", r.returncode == 127 and r.stderr.count("\n") == 1
              and "python_pin.py install" in r.stderr)

    print("test_moveto.py: OK" if not fails else f"test_moveto.py: {fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
