#!/usr/bin/env python3
"""tools/fabric/secretstore/lineage.py is what the corpus lint loads, by its
path, to check identities/keys/, and contributors may not change it. That
fence holds only if nothing the module runs lies outside it: it imports the
standard library alone, nothing package-relative, and loads with nothing of
the fabric on sys.path. And it is the one definition: the store's parts use
its names and its verify, so the lint and `fabric-secrets store verify`
cannot disagree."""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINEAGE = os.path.join(ROOT, "tools", "fabric", "secretstore", "lineage.py")
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import secret_store  # noqa: E402
from secretstore import core, keys, lineage, mirrors  # noqa: E402


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:400]}"))
        fails += not good

    tree = ast.parse(open(LINEAGE, encoding="utf-8").read())
    imported, relative = set(), []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                relative.append(n.module or ".")
            elif n.module:
                imported.add(n.module.split(".")[0])
    outside = sorted(m for m in imported - {"__future__"} if m not in sys.stdlib_module_names)
    check("lineage.py imports the standard library only", not outside, outside)
    check("…and nothing package-relative", not relative, relative)

    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "identities", "keys"))
        # As the lint loads it: by path, in an isolated interpreter, run from
        # a directory where no fabric module could be found.
        r = subprocess.run([sys.executable, "-I", "-c",
                            "import importlib.util, sys\n"
                            "s = importlib.util.spec_from_file_location('fabric_lineage', sys.argv[1])\n"
                            "m = importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
                            "print(m.verify(sys.argv[2]))", LINEAGE, tmp],
                           capture_output=True, text=True, cwd=tmp, timeout=120, env={"PATH": os.environ.get("PATH", "")})
        check("it loads alone by path and verifies an empty fabric clean", r.returncode == 0 and r.stdout.strip() == "[]",
              r.stdout + r.stderr)
        with open(os.path.join(tmp, "identities", "keys", "lineage.json"), "w") as fh:
            fh.write('{"not-an-id": {}}')
        check("…and its verify is the store's: one finding, the same from both",
              lineage.verify(tmp) == secret_store.verify(tmp) == mirrors.verify(tmp) != [], lineage.verify(tmp))

    for name, here in (("StoreError", core.StoreError), ("AGENT_ID_RE", core.AGENT_ID_RE), ("LOGIN_RE", core.LOGIN_RE),
                       ("UID_DOMAIN", core.UID_DOMAIN), ("born_of", core.born_of), ("fingerprints", keys.fingerprints),
                       ("KEY_USES", keys.KEY_USES), ("_key_caps", keys._key_caps)):
        check(f"{name} is lineage.py's, not a second definition", here is getattr(lineage, name))
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
