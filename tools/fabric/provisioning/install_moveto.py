#!/usr/bin/env python3
"""tools/fabric/provisioning/install_moveto.py — install moveto from
runtime/provisioning/moveto/ to /usr/local. Needs root. Ported from
runtime/provisioning/moveto/install.sh (agent-fabric ADR-040, off shell).

    sudo python3 tools/fabric/provisioning/install_moveto.py

That directory is the SOURCE; /usr/local holds a copy. The installer records
what it installed in /usr/local/share/moveto/installed.sha256 (sha256sum
format), and `bin/fabric-status` compares the repository, the manifest and
the installed files on every call: the source moved on and this was not
re-run, or a copy was edited in place, is one line there rather than
nothing (review, 2026-09-16). $MOVETO_PREFIX overrides /usr/local for a test.

CONTRACT, frozen from the shell
  installs  bin/moveto (755), share/moveto/enter (755), share/moveto/moveto.py
            (644; the work is Python, ADR-040 Wave 5, and the shim in bin/
            finds it here, beside enter and rc, when no checkout is behind the
            copy), share/moveto/rc (644), share/bash-completion/completions/
            moveto (644; where bash-completion loads it on first use,
            XDG_DATA_DIRS lists /usr/local/share before /usr/share: accounts
            from the host registry, clones from `moveto <account> --list`),
            under the prefix, directories 755
  manifest  share/moveto/installed.sha256: sha256sum lines for those five
            paths, in the shell's order (MANIFEST_ORDER), relative to the prefix so the same line
            checks the copy wherever the prefix is; swapped in whole (a
            .tmp beside it, then renamed), 644
  stdout    `moveto installed to <prefix> (manifest: <prefix>/share/moveto/
            installed.sha256). Try: moveto --list`
  exit      0 done; 1 any step failed (nothing after it ran), said on stderr
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping

HERE = os.path.dirname(os.path.realpath(__file__))
SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "runtime", "provisioning", "moveto")
# (source name, installed path under the prefix, mode): the manifest lists them in this order.
FILES = (("moveto", "bin/moveto", 0o755), ("enter", "share/moveto/enter", 0o755),
         ("moveto.py", "share/moveto/moveto.py", 0o644), ("rc", "share/moveto/rc", 0o644),
         ("completion.bash", "share/bash-completion/completions/moveto", 0o644))
MANIFEST = "share/moveto/installed.sha256"
# The manifest's own order, as the shell's sha256sum line gave it: the status check reads it by path, but a copy is byte-compared in a test.
MANIFEST_ORDER = ("bin/moveto", "share/moveto/moveto.py", "share/moveto/enter", "share/moveto/rc",
                  "share/bash-completion/completions/moveto")


def _install_dir(path: str, mode: int = 0o755) -> None:
    os.makedirs(path, exist_ok=True)
    os.chmod(path, mode)


def _install_file(src: str, dst: str, mode: int) -> None:
    """install -m MODE SRC DST, the file replaced whole."""
    fd, tmp = tempfile.mkstemp(prefix=".install-", dir=os.path.dirname(dst))
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as fh:
            shutil.copyfileobj(fh, out)
        os.chmod(tmp, mode)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def install(prefix: str, source: str = SOURCE) -> None:
    for sub in ("bin", "share/moveto", "share/bash-completion/completions"):
        _install_dir(os.path.join(prefix, sub))
    for name, rel, mode in FILES:
        _install_file(os.path.join(source, name), os.path.join(prefix, rel), mode)
    manifest = "".join(f"{_sha256(os.path.join(prefix, rel))}  {rel}\n" for rel in MANIFEST_ORDER)
    tmp = os.path.join(prefix, MANIFEST + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(manifest)
    os.replace(tmp, os.path.join(prefix, MANIFEST))
    os.chmod(os.path.join(prefix, MANIFEST), 0o644)


def main(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    env = os.environ if environ is None else environ
    prefix = env.get("MOVETO_PREFIX") or "/usr/local"
    try:
        install(prefix)
    except OSError as e:
        print(f"install_moveto: {e.strerror or e}{': ' + e.filename if e.filename else ''}; nothing after it ran", file=sys.stderr)
        return 1
    print(f"moveto installed to {prefix} (manifest: {prefix}/{MANIFEST}). Try: moveto --list")
    return 0


if __name__ == "__main__":
    sys.exit(main())
