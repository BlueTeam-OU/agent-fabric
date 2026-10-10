#!/usr/bin/env python3
"""tools/fabric/github/semantic_collisions.py, through the module. The
behaviour's oracle is two managed projects' tools/checks/
test_scan_semantic_collisions.sh, run unchanged against the module with
each project's collisions.json (ADR-040 §5 rule 5). Those suites check
exit codes and a few names; this file pins the lines whole, and what the
port changed or added: numbers compared as text, every member of a
number listed in bytewise order, headings joined by " | " and compared as
bytes, the footer and the wording from the config, the config's lookup
and its refusals, the shared argv. Plain script: prints ok/FAIL, exit 1
on any failure."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = [sys.executable, os.path.join(ROOT, "tools", "fabric", "github", "semantic_collisions.py")]
GZAPP = os.path.join(ROOT, "tests", "fixtures", "gzapp-gh", "collisions.json")
FOOTER = ("Semantic collision(s): {n} — a textually-clean merge does NOT clear these.\n"
          "These are parallel-session numbering races (CLAUDE.md §Concurrent contributors):\n"
          "renumber the entry that has NOT yet reached origin/main; never rewrite landed work.\n")
OK = "scan_semantic_collisions: OK — no numbering collisions in the merged tree.\n"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as sandbox:
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_", "GH_", "GIT_"))}
        base.update(HOME=sandbox, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_CEILING_DIRECTORIES=sandbox)
        if os.environ.get("AGENT_FABRIC_PYTHON"):
            base["AGENT_FABRIC_PYTHON"] = os.environ["AGENT_FABRIC_PYTHON"]
        n = [0]

        def tree(files: dict[str, bytes | str], dirs=("docs/adr/history", "docs/architecture", "infra/db/migrations")):
            n[0] += 1
            root = os.path.join(sandbox, f"t{n[0]}")
            for d in dirs:
                os.makedirs(os.path.join(root, d), exist_ok=True)
            os.makedirs(os.path.join(root, "docs", "adr"), exist_ok=True)
            for rel, body in files.items():
                path = os.path.join(root, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(body.encode() if isinstance(body, str) else body)
            return root

        def run(*args: str, cwd: str = sandbox, config: str | None = GZAPP, **env: str):
            e = dict(base, **env)
            if config is not None:
                e["AGENT_FABRIC_COLLISIONS_CONFIG"] = config
            r = subprocess.run([*TOOL, *args], env=e, cwd=cwd, capture_output=True, timeout=60)
            return r.returncode, r.stdout.decode("utf-8", "surrogateescape"), r.stderr.decode("utf-8", "surrogateescape")

        print("semantic_collisions: the lines, whole")
        root = tree({"docs/adr/ADR-001-a.md": "# a\n", "infra/db/migrations/0001_a.sql": "",
                     "infra/db/migrations/0002_b.sql": ""})
        rc, out, err = run("--root", root)
        check("a clean tree: the OK line, exit 0", (rc, out, err) == (0, OK, ""), f"{rc} {out!r} {err!r}")

        root = tree({"docs/adr/ADR-001-a.md": "# a\n", "infra/db/migrations/0014_z.sql": "",
                     "infra/db/migrations/0014.sql": "", "infra/db/migrations/0014_b.sql": "",
                     "infra/db/migrations/014_c.sql": ""})
        rc, out, err = run("--root", root)
        want = ("FAIL: duplicate migration number prefix 0014 — relative apply order is undefined.\n"
                "   0014.sql 0014_b.sql 0014_z.sql\n"
                "   Renumber YOUR migration past the highest on origin (update any doc references).\n\n"
                + FOOTER.format(n=1))
        check("every member of a number listed, bytewise, the bash's 0014.sql too", (rc, out) == (1, want),
              f"{rc}\n{out}")
        check("and 014 is another number: compared as text", "014_c.sql" not in out)

        root = tree({"docs/adr/ADR-002-b.md": "# b\n", "docs/adr/ADR-002-a.md": "# a\n",
                     "docs/architecture/ARCH-001-X.md": "", "docs/architecture/ARCH-001-Y.md": "",
                     "infra/db/migrations/0001_a.sql": ""})
        rc, out, err = run("--root", root)
        want = ("FAIL: duplicate ADR number 002 — two files claim it.\n"
                "   ADR-002-a.md ADR-002-b.md\n"
                "   Renumber YOUR document to the next free number (and re-propagate indexes).\n\n"
                "FAIL: duplicate ARCH number 001 — two files claim it.\n"
                "   ARCH-001-X.md ARCH-001-Y.md\n"
                "   Renumber YOUR document to the next free number (and re-propagate indexes).\n\n"
                + FOOTER.format(n=2))
        check("two families, in the config's order, counted in the footer", (rc, out) == (1, want), f"{rc}\n{out}")

        heads = "".join(f"### Amendment {d} — x\n" for d in ("D", "B", "C", "A")) * 2
        root = tree({"docs/adr/ADR-001-a.md": heads, "infra/db/migrations/0001_a.sql": "",
                     "docs/adr/history/ADR-001-amendments.md": b"### Amendment \xff\n### Amendment \xff\n"})
        rc, out, err = run("--root", root)
        want = ("FAIL: identical amendment headings in ADR-001-a.md — cross-references are ambiguous.\n"
                "   ### Amendment A — x | ### Amendment B — x | ### Amendment C — x\n"
                "   Suffix the newer one '(ii)' per the existing same-day-amendment convention.\n\n"
                "FAIL: identical amendment headings in ADR-001-amendments.md — cross-references are ambiguous.\n"
                "   ### Amendment \udcff\n"
                "   Suffix the newer one '(ii)' per the existing same-day-amendment convention.\n\n"
                + FOOTER.format(n=2))
        check("headings: sorted, the first three, joined by ' | '; history files too", (rc, out) == (1, want),
              f"{rc}\n{out}")
        check("a heading that is not UTF-8 is compared and printed as its bytes", "\udcff" in out)

        root = tree({"docs/adr/ADR-001-a.md": "### Amendment X\n### Amendment X (ii)\n",
                     "docs/adr/ADR-002-b.md": "### Amendment X\n", "infra/db/migrations/0001_a.sql": ""},
                    dirs=("infra/db/migrations",))
        rc, out, err = run("--root", root)
        check("no history/ and no ARCH dir: both optional; one heading per file is no collision", rc == 0, out + err)

        print("semantic_collisions: refusals")
        root = tree({}, dirs=())
        shutil.rmtree(os.path.join(root, "docs"))
        rc, out, err = run("--root", root)
        check("the first required path missing is named, exit 2",
              (rc, out, err) == (2, "", f"scan_semantic_collisions: expected path not found: {root}/docs/adr\n"), err)
        rc, out, err = run("--root", root, config=os.path.join(sandbox, "none.json"))
        check("a config that cannot be read is exit 2, named", rc == 2 and "cannot read " in err and not out, err)
        bad = os.path.join(sandbox, "bad.json")
        with open(GZAPP, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["families"][0]["pattern"] = "^[0-9]+.*\\.sql$"
        with open(bad, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        rc, out, err = run("--root", root, config=bad)
        check("a family pattern without its one group is refused", rc == 2 and "exactly one group" in err, err)
        doc = json.load(open(GZAPP, encoding="utf-8"))
        doc["required"] = []
        with open(bad, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        rc, out, err = run("--root", root, config=bad)
        check("an amendment directory not marked optional, missing, is exit 2, never a silent pass",
              (rc, out, err) == (2, "", f"scan_semantic_collisions: expected path not found: {root}/docs/adr\n"), err)
        plain = tree({}, dirs=())
        rc, out, err = run("--root", plain, config=None)
        check("outside any project and with no setting, no config: exit 2",
              rc == 2 and err.startswith(f"scan_semantic_collisions: no collisions config for {plain} "), err)

        print("semantic_collisions: the project's config, found from --root")
        # The operator a working copy's project is found in: a fixture registry
        # holding gzapp's remote, and gzapp's collisions.json at its place (instance data).
        operator = os.path.join(sandbox, "operator")
        os.makedirs(os.path.join(operator, "projects", "gzapp", "integration", "gh"))
        with open(os.path.join(operator, "projects", "registry.json"), "w", encoding="utf-8") as fh:
            json.dump({"projects": {"gzapp": {"remotes": ["git@github.com:gzapi-org/gzapp.git"]}}}, fh)
        shutil.copy(GZAPP, os.path.join(operator, "projects", "gzapp", "integration", "gh", "collisions.json"))
        gz = tree({"docs/adr/ADR-001-a.md": "", "infra/db/migrations/0001_a.sql": "",
                   "infra/db/migrations/0001_b.sql": ""})
        for args in (["init", "-q", gz], ["-C", gz, "remote", "add", "origin", "git@github.com:gzapi-org/gzapp.git"]):
            subprocess.run(["git", *args], env=base, check=True, capture_output=True, timeout=30)
        rc, out, err = run("--root", gz, config=None, AGENT_FABRIC_OPERATOR=operator)
        check("a gzapp working copy reads gzapp's collisions.json", rc == 1 and "migration number prefix 0001" in out
              and "§Concurrent contributors" in out, f"{rc} {out} {err}")
        os.makedirs(os.path.join(gz, "sub"))
        rc, out, err = run(cwd=os.path.join(gz, "sub"), config=None, AGENT_FABRIC_OPERATOR=operator)
        check("without --root, the working directory's toplevel", rc == 1 and "0001_a.sql 0001_b.sql" in out, err)

        print("semantic_collisions: argv")
        rc, out, err = run("-h")
        check("--help is the module's text", rc == 0 and "SEMANTIC collisions" in out and not err)
        for args, want in ((("--root",), "scan_semantic_collisions: --root needs a value\n"),
                           (("x",), "scan_semantic_collisions: unexpected argument: x\n")):
            rc, out, err = run(*args)
            check(f"{args}: exit 2, stderr only", (rc, out, err) == (2, "", want), f"{rc} {out!r} {err!r}")

    print("ok" if not fails else f"{fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
