#!/usr/bin/env python3
"""Tests for tools/fabric/project.py (`fabric-project import`), run through the
shim bin/fabric-project on a copy of this tree.

The acceptance imports a scratch project --like a REAL registered one and
runs lint on the result, so it reads the operator's own registry on purpose
(tests/test_tests_read_fixtures.py DELIBERATE); on a stripped copy there is
no sibling to import from and it says so and passes. The pure pieces (the id
replacement, the remote key) are exact cases that need no tree."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import project as pj  # noqa: E402

GIT = shutil.which("git") or "/usr/bin/git"
PY = sys.executable
LIKE = "interweave"      # no opt-in files: the plain case
LIKE_FULL = "gzapp"      # has gh/compliance.json, gh/trial.json and pr-tools.json
ARGS = ["--id", "scratch.proj", "--client", "blueteam", "--default-branch", "main", "--license", "Apache-2.0",
        "--remote", "git@github.com:BlueTeam-OU/scratch.proj.git", "--remote", "https://github.com/BlueTeam-OU/scratch.proj"]


def clean_env(home: str) -> dict:
    env = {"PATH": os.environ.get("PATH", ""), "HOME": home, "LC_ALL": "C.UTF-8",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "TMPDIR": home}
    return env


def sh(cwd: str, *argv: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(list(argv), cwd=cwd, env=env, capture_output=True, text=True, timeout=300, check=False)


def tree_state(root: str) -> dict:
    out = {}
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for n in names:
            p = os.path.join(base, n)
            out[os.path.relpath(p, root)] = os.stat(p).st_mtime_ns, os.path.getsize(p)
    return out


def make_tree(dest: str, env: dict) -> None:
    """The tree as git lists it, uncommitted work included, as a repository
    whose origin/main is its one commit (fabric-ref reads it)."""
    names = subprocess.run([GIT, "-C", HERE, "ls-files", "-co", "--exclude-standard", "-z"], capture_output=True,
                           check=True, timeout=60).stdout.split(b"\0")
    for raw in filter(None, names):
        rel = os.fsdecode(raw)
        src = os.path.join(HERE, rel)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst, follow_symlinks=False)
    for argv in ([GIT, "init", "-q", "-b", "main"], [GIT, "add", "-A"],
                 [GIT, "-c", "user.name=t", "-c", "user.email=t@e.invalid", "-c", "commit.gpgsign=false",
                  "commit", "-q", "-m", "tree"], [GIT, "update-ref", "refs/remotes/origin/main", "HEAD"]):
        r = sh(dest, *argv, env=env)
        assert r.returncode == 0, r.stderr


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print(f"       {detail}")
        fails += not good

    # --- pure pieces ---------------------------------------------------------
    r = pj.replace_id
    check("replace: a word and the directory under projects/",
          r("gzapp's rules; projects/gzapp/integration; gzapp.", "gzapp", "n.x") == "n.x's rules; projects/n.x/integration; n.x.")
    check("replace: not inside a repository name, a dotted or dashed identifier or a channel",
          r("gzapi-org/gzapp gzapp.decks gzapp-claude2 gzapp:gzcoord git@github.com:o/gzapp.git", "gzapp", "n")
          == "gzapi-org/gzapp gzapp.decks gzapp-claude2 gzapp:gzcoord git@github.com:o/gzapp.git")
    check("replace: positive control for the line above (the same words standing alone are replaced)",
          r("gzapp gzapp", "gzapp", "n") == "n n")
    ck = pj.workingcopy.canonical_remote
    check("remote key: the registry's comparison, so ssh, https, a default port and a case difference agree",
          len({ck(x) for x in ("git@github.com:BlueTeam-OU/InterWeave.git", "https://github.com/blueteam-ou/interweave/",
                               "ssh://git@github.com:22/BlueTeam-OU/InterWeave.git", "https://github.com:443/BlueTeam-OU/InterWeave")}) == 1
          and ck("git@github.com:org/other.git") != ck("git@github.com:org/interweave.git"))

    mini = '{\n  "projects": {\n    "a": {\n      "x": 1\n    }\n  }\n}\n'
    grown = pj.insert_entry(mini, "b", {"y": 2})
    check("insert_entry: appends one project after the last, the rest byte for byte",
          grown.startswith(mini[:-len("\n    }\n  }\n}\n")]) and json.loads(grown)["projects"] == {"a": {"x": 1}, "b": {"y": 2}})
    try:
        pj.insert_entry(mini, "a", {"y": 2})
        dup = False
    except pj.Refused:
        dup = True
    check("insert_entry: an id already in the file is refused, not merged over", dup)
    unit = tempfile.mkdtemp(prefix="test_project_import_unit.")
    try:
        taken = os.path.join(unit, "f")
        open(taken, "w").write("mine")
        try:
            pj.write_all([{"path": taken, "data": b"new", "mode": 0o644}], os.path.join(unit, "reg.json"), "{}")
            clobbered = True
        except OSError:
            clobbered = False
        check("write_all: a file that appeared after the plan is not overwritten", not clobbered and open(taken).read() == "mine")
    finally:
        shutil.rmtree(unit, ignore_errors=True)

    live = os.path.join(HERE, "projects", "registry.json")
    if not os.path.exists(live) or LIKE not in json.load(open(live, encoding="utf-8")).get("projects", {}):
        print(f"  skip: {LIKE} is not registered here (a stripped copy); the tree cases need the operator's registry")
        return 1 if fails else 0

    scratch = tempfile.mkdtemp(prefix="test_project_import.")
    try:
        env = clean_env(scratch)
        base = os.path.join(scratch, "tree")
        os.makedirs(base)
        make_tree(base, env)
        registry = json.load(open(os.path.join(base, "projects", "registry.json"), encoding="utf-8"))["projects"]
        assert LIKE in registry and LIKE_FULL in registry, "the cases need both siblings registered"

        shim = os.path.join(base, "bin", "fabric-project")
        fake_python = os.path.join(scratch, "python")
        os.symlink(PY, fake_python)
        env_run = {**env, "AGENT_FABRIC_PYTHON": fake_python}

        def imp(tree: str, *argv: str) -> subprocess.CompletedProcess:
            return sh(tree, os.path.join(tree, "bin", "fabric-project"), "import", *argv, env=env_run)

        def refuses(label: str, tree: str, argv: list[str], says: str, before: dict | None = None) -> None:
            before = before if before is not None else tree_state(tree)
            r = imp(tree, *argv)
            check(label, r.returncode == 2 and says in r.stderr and r.stderr.startswith("fabric-project: ")
                  and tree_state(tree) == before, f"exit {r.returncode}: {r.stderr.strip()[:200]}")

        wc = os.path.join(scratch, "wc")
        os.makedirs(wc)
        base_args = ARGS + ["--like", LIKE, "--role", "python-dev", "--role", "devex-tooling"]

        # --- dry run writes nothing, and says what it would --------------------
        before = tree_state(base)
        r = imp(base, *base_args, "--working-copy", wc)
        check("dry run: exit 0, names the registry, the integration files and the working-copy files, writes nothing",
              r.returncode == 0 and "dry run" in r.stdout and "projects/registry.json" in r.stdout
              and "projects/scratch.proj/integration/gh/arm.json" in r.stdout
              and "taxonomy.json" in r.stdout and "fabric-ref" in r.stdout
              and tree_state(base) == before and os.listdir(wc) == [], r.stdout[-400:] + r.stderr)
        check("dry run: the first line names the tree the paths are relative to",
              r.stdout.splitlines()[0].endswith(f"relative to {os.path.realpath(base)}:") or r.stdout.splitlines()[0].endswith(f"relative to {base}:"),
              r.stdout[:200])
        check("dry run: no working copy for the sibling found, so every remit is marked a stub and stderr says how to fix it",
              r.stdout.count("[stub remit]") == 2 and "stub remits for: python-dev, devex-tooling" in r.stderr
              and "was not found: pass --like-working-copy" in r.stderr, r.stdout[-300:] + r.stderr)
        check("dry run: a registry diff with the new entry and the date in its note",
              '+    "scratch.proj": {' in r.stdout and '+      "note": "imported 20' in r.stdout)

        plain = imp(base, *ARGS, "--like", LIKE_FULL, "--role", "python-dev").stdout
        asked = imp(base, *ARGS, "--like", LIKE_FULL, "--role", "python-dev", "--with-trial").stdout
        optins = ("gh/compliance.json", "gh/trial.json", "pr-tools.json")
        check("opt-in files: none planned without a flag, only the one asked for with it",
              not any(o in plain for o in optins) and "gh/trial.json" in asked
              and "gh/compliance.json" not in asked and "pr-tools.json" not in asked, plain[:300])

        # --- refusals, each leaving the tree untouched -------------------------
        refuses("refuses an id already registered", base, ["--like", LIKE, "--role", "python-dev"] + ARGS[:0]
                + ["--id", LIKE_FULL] + ARGS[2:], "already registered")
        refuses("refuses a remote already registered (the other spelling of a registered repository)", base,
                ["--like", LIKE, "--role", "python-dev", "--id", "scratch.proj", "--client", "blueteam",
                 "--default-branch", "main", "--license", "MIT", "--remote", "https://github.com/BlueTeam-OU/InterWeave.git"],
                "already registered to")
        refuses("refuses a registered repository spelled as its old owner's remote", base,
                ["--like", LIKE, "--role", "python-dev", "--id", "scratch.proj", "--client", "blueteam",
                 "--default-branch", "main", "--license", "MIT", "--remote", "git@github.com:gzapi-org/InterWeave.git"],
                "already registered to")
        refuses("refuses a registered repository spelled with an explicit port", base,
                ["--like", LIKE, "--role", "python-dev", "--id", "scratch.proj", "--client", "blueteam",
                 "--default-branch", "main", "--license", "MIT", "--remote", "ssh://git@github.com:22/BlueTeam-OU/InterWeave.git"],
                "already registered to")
        refuses("refuses a remote that is not a repository URL", base,
                ["--like", LIKE, "--role", "python-dev", "--id", "scratch.proj", "--client", "blueteam",
                 "--default-branch", "main", "--license", "MIT", "--remote", "foo"], "not a remote repository URL")
        for bad in ("schemas", "registry.json", "clients.json", "a-", "a..b", "-a"):
            refuses(f"refuses the id {bad!r}", base, ["--like", LIKE, "--role", "python-dev", "--id", bad] + ARGS[2:], "--id")
        refuses("refuses an empty licence", base, base_args[:base_args.index("--license") + 1] + [" "] + base_args[base_args.index("--license") + 2:], "--license is empty")
        refuses("refuses an unknown client", base, base_args[:2] + ["--client", "nobody"] + base_args[4:], "not in projects/clients.json")
        refuses("refuses an unknown sibling", base, ["--like", "no-such"] + ARGS + ["--role", "python-dev"], "not a registered project")
        refuses("refuses an unknown role", base, base_args + ["--role", "no-such-role"], "not in identities/roles/catalog.json")
        refuses("refuses a malformed id", base, ["--like", LIKE, "--role", "python-dev", "--id", "Bad_Id"] + ARGS[2:], "--id")
        refuses("refuses an opt-in file the sibling does not have", base, base_args + ["--with-trial"], "has no integration/gh/trial.json")

        existing = os.path.join(base, "projects", "scratch.proj", "integration", "gh", "arm.json")
        os.makedirs(os.path.dirname(existing))
        open(existing, "w").write("mine\n")
        refuses("refuses to overwrite an existing integration file", base, base_args, "exists; nothing is overwritten")
        check("  ...and the file is as it was", open(existing).read() == "mine\n")
        shutil.rmtree(os.path.join(base, "projects", "scratch.proj"))

        badwc = os.path.join(scratch, "badwc")
        outside = os.path.join(scratch, "outside")
        os.makedirs(os.path.join(outside, "integration"))
        held = os.path.join(base, "projects", "scratch.proj")
        os.symlink(outside, held)
        refuses("refuses a symlinked projects/<id>", base, base_args + ["--write"], "is not a registered project")
        check("  ...and nothing went through the link", os.listdir(os.path.join(outside, "integration")) == [])
        os.unlink(held)
        os.makedirs(held)
        os.symlink(os.path.join(scratch, "outside"), os.path.join(held, "integration"))
        refuses("refuses a symlinked projects/<id>/integration", base, base_args + ["--write"], "is not a registered project")
        check("  ...and nothing went through that link either", os.listdir(os.path.join(outside, "integration")) == []
              and sorted(os.listdir(outside)) == ["integration"])
        os.unlink(os.path.join(held, "integration"))
        os.rmdir(held)

        os.makedirs(os.path.join(held, "integration"))
        os.symlink(outside, os.path.join(held, "integration", "gh"))
        refuses("refuses a symlinked directory below projects/<id>/integration", base, base_args + ["--write"], "nothing is written through it")
        check("  ...and nothing went through that one", sorted(os.listdir(outside)) == ["integration"])
        shutil.rmtree(held)

        os.makedirs(os.path.join(badwc, ".agent-fabric", "roles"))
        open(os.path.join(badwc, ".agent-fabric", "roles", "python-dev.md"), "wb").write(b"---\nproject: x\n---\n\xff\xfe\n")
        refuses("refuses a sibling remit that is not UTF-8, with no traceback", base,
                base_args + ["--working-copy", wc, "--like-working-copy", badwc], "is not UTF-8")
        linked = os.path.join(base, "projects", LIKE, "integration", "linked")
        os.symlink(os.path.join(base, "projects", LIKE, "integration", "gh"), linked)
        refuses("refuses a symlinked directory in the sibling's integration", base, base_args, "is a symlink")
        os.unlink(linked)

        os.makedirs(os.path.join(wc, ".agent-fabric"))
        open(os.path.join(wc, ".agent-fabric", "taxonomy.json"), "w").write("mine\n")
        refuses("refuses to overwrite an existing working-copy file", base, base_args + ["--working-copy", wc], "exists; nothing is overwritten")
        os.unlink(os.path.join(wc, ".agent-fabric", "taxonomy.json"))
        os.rmdir(os.path.join(wc, ".agent-fabric"))

        # --- the acceptance: import, then lint --------------------------------
        for like, extra in ((LIKE, []), (LIKE_FULL, ["--with-compliance", "--with-trial", "--with-pr-tools"])):
            tree = os.path.join(scratch, f"tree-{like}")
            shutil.copytree(base, tree, symlinks=True)
            wcopy = os.path.join(scratch, f"wc-{like}")
            os.makedirs(wcopy)
            argv = ARGS + ["--like", like, "--role", "python-dev", "--role", "devex-tooling", "--working-copy", wcopy,
                           "--write", *extra]
            original = open(os.path.join(tree, "projects", "registry.json"), encoding="utf-8").read()
            reg_mode = os.stat(os.path.join(tree, "projects", "registry.json")).st_mode & 0o777
            old_umask = os.umask(0o077)   # a created file must still take the sibling's mode
            try:
                r = imp(tree, *argv)
            finally:
                os.umask(old_umask)
            check(f"--like {like} --write: exit 0, nothing committed", r.returncode == 0 and "nothing committed" in r.stdout, r.stderr)
            reg_text = open(os.path.join(tree, "projects", "registry.json"), encoding="utf-8").read()
            reg = json.loads(reg_text)["projects"]
            entry = reg.get("scratch.proj", {})
            like_entry = registry[like]
            check(f"--like {like}: the entry takes the sibling's keys in its order, its own values, and no moved_from",
                  list(entry) == [k for k in like_entry if k != "moved_from"] + ([] if "note" in like_entry else ["note"])
                  and entry["remotes"] == [ARGS[ARGS.index("--remote") + 1], ARGS[-1]]
                  and entry["integration"] == "projects/scratch.proj/integration" and entry["license"] == "Apache-2.0"
                  and entry["tools"] == [] and entry["note"].startswith("imported ") and entry["taxonomy"] == like_entry["taxonomy"],
                  json.dumps(entry)[:300])
            check(f"--like {like}: every other byte of the registry is as it was", reg_text.startswith(original[:-len("\n    }\n  }\n}\n")]))
            check(f"--like {like}: the sibling's integration files are all there, the opt-in ones only when asked",
                  all(os.path.exists(os.path.join(tree, "projects", "scratch.proj", "integration", os.path.relpath(p, os.path.join(tree, "projects", like, "integration"))))
                      for p in [os.path.join(b, n) for b, _, ns in os.walk(os.path.join(tree, "projects", like, "integration")) for n in ns]
                      if os.path.basename(p) not in ("compliance.json", "trial.json", "pr-tools.json") or extra))
            if like == LIKE_FULL:
                check("--like gzapp: the host-check script keeps its mode, whatever the umask",
                      os.stat(os.path.join(tree, "projects", "scratch.proj", "integration", "provisioning", "host-check.sh")).st_mode & 0o777
                      == os.stat(os.path.join(tree, "projects", like, "integration", "provisioning", "host-check.sh")).st_mode & 0o777)
            else:
                check("--like interweave: no opt-in file was written",
                      not any(n in ("compliance.json", "trial.json", "pr-tools.json")
                              for _, _, ns in os.walk(os.path.join(tree, "projects", "scratch.proj")) for n in ns))
            snippet = open(os.path.join(tree, "projects", "scratch.proj", "integration", "gzcoord", "CLAUDE.snippet.md"), encoding="utf-8").read()
            sibling_snippet = open(os.path.join(tree, "projects", like, "integration", "gzcoord", "CLAUDE.snippet.md"), encoding="utf-8").read()
            check(f"--like {like}: the id is replaced where it is the project (a file that names {like}'s directory now names the new one)",
                  f"projects/{like}/integration/gzcoord/" in sibling_snippet
                  and "projects/scratch.proj/integration/gzcoord/" in snippet and f"projects/{like}/" not in snippet)
            check(f"--like {like}: the registry keeps its mode under umask 077",
                  os.stat(os.path.join(tree, "projects", "registry.json")).st_mode & 0o777 == reg_mode)
            tax = json.load(open(os.path.join(wcopy, ".agent-fabric", "taxonomy.json")))
            check(f"--like {like}: a taxonomy of this project, one rule per role",
                  tax["project"] == "scratch.proj" and [x["id"] for x in tax["roles"]] == ["python-dev", "devex-tooling"])
            ref = open(os.path.join(wcopy, ".agent-fabric", "fabric-ref")).read()
            head = sh(tree, GIT, "rev-parse", "origin/main", env=env).stdout.strip()
            check(f"--like {like}: fabric-ref is origin/main's full commit id and one line", ref == head + "\n" and len(head) == 40)
            check(f"--like {like}: no charter was written", not os.path.exists(os.path.join(wcopy, ".agent-fabric", "charter.md"))
                  and sorted(os.listdir(os.path.join(wcopy, ".agent-fabric", "roles"))) == ["devex-tooling.md", "python-dev.md"])
            for role in ("python-dev", "devex-tooling"):
                text = open(os.path.join(wcopy, ".agent-fabric", "roles", f"{role}.md"), encoding="utf-8").read()
                check(f"--like {like}: the {role} remit is for scratch.proj and names fabric-coordinator as author (a stub)",
                      "project: scratch.proj\n" in text and "agent: fabric-coordinator" in text and "class: remit" in text)
            # lint reads what git tracks; the owner commits the import, the test only stages it.
            sh(tree, GIT, "add", "-A", env=env)
            lint = sh(tree, PY, "tools/fabric/lint.py", "--no-siblings", "--working-copy", f"scratch.proj={wcopy}", env=env)
            check(f"--like {like}: lint.py --no-siblings on the imported tree is clean", lint.returncode == 0 and "corpus lint: clean" in lint.stdout,
                  (lint.stdout + lint.stderr)[-600:])
            again = imp(tree, *argv)
            check(f"--like {like}: a second run is refused, nothing more written", again.returncode == 2 and "already registered" in again.stderr)

        # --- a remit the sibling has is copied, its project set ----------------
        tree = os.path.join(scratch, "tree-remit")
        shutil.copytree(base, tree, symlinks=True)
        like_wc = os.path.join(scratch, "like-wc")
        os.makedirs(os.path.join(like_wc, ".agent-fabric", "roles"))
        body = "---\nrole: python-dev\nclass: remit\nproject: interweave\ndescription: \"d\"\n---\n\n# python-dev — remit in interweave\n\ninterweave text\n"
        open(os.path.join(like_wc, ".agent-fabric", "roles", "python-dev.md"), "w").write(body)
        wcopy = os.path.join(scratch, "wc-remit")
        os.makedirs(wcopy)
        r = imp(tree, *ARGS, "--like", LIKE, "--role", "python-dev", "--role", "devex-tooling", "--working-copy", wcopy,
                "--like-working-copy", like_wc, "--write")
        got = open(os.path.join(wcopy, ".agent-fabric", "roles", "python-dev.md"), encoding="utf-8").read()
        check("a remit the sibling has is copied with only its frontmatter project set (the body is the sibling's)",
              r.returncode == 0 and got == body.replace("project: interweave\n", "project: scratch.proj\n"), got)
        check("only the role the sibling lacks is marked and named; the copied one is not",
              r.stdout.count("[stub remit]") == 1 and "stub remits for: devex-tooling (" in r.stderr
              and "has none of them" in r.stderr and "python-dev," not in r.stderr, r.stdout[-300:] + r.stderr)
        stub = open(os.path.join(wcopy, ".agent-fabric", "roles", "devex-tooling.md"), encoding="utf-8").read()
        check("a role the sibling lacks is a stub", "agent: fabric-coordinator" in stub and "not written yet" in stub.lower())

        # --- a write that fails part-way names what it made ---------------------
        tree = os.path.join(scratch, "tree-fail")
        shutil.copytree(base, tree, symlinks=True)
        os.makedirs(os.path.join(tree, "projects", "scratch.proj"))
        os.chmod(os.path.join(tree, "projects", "scratch.proj"), 0o500)
        try:
            r = imp(tree, *base_args, "--write")
            reg_now = json.load(open(os.path.join(tree, "projects", "registry.json"), encoding="utf-8"))["projects"]
            check("an unwritable directory: exit 1, a message, and no registry entry",
                  r.returncode == 1 and r.stderr.startswith("fabric-project: ") and "scratch.proj" not in reg_now and "Traceback" not in r.stderr,
                  f"exit {r.returncode}: {r.stderr[:300]}")
        finally:
            os.chmod(os.path.join(tree, "projects", "scratch.proj"), 0o700)

        # No live project keeps a moved_from the remotes lack, so the registry is edited to one that does.
        tree = os.path.join(scratch, "tree-moved")
        shutil.copytree(base, tree, symlinks=True)
        regp = os.path.join(tree, "projects", "registry.json")
        text = open(regp, encoding="utf-8").read()
        doc = json.loads(text)
        doc["projects"][LIKE]["moved_from"] = ["git@github.com:old-org/legacy-name.git"]
        open(regp, "w", encoding="utf-8").write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        refuses("refuses a remote only in a project's moved_from", tree,
                ["--like", LIKE, "--role", "python-dev", "--id", "scratch.proj", "--client", "blueteam",
                 "--default-branch", "main", "--license", "MIT", "--remote", "https://github.com/old-org/legacy-name"],
                "already registered to")

        open(regp, "wb").write(b"\xff\xfe")
        refuses("refuses a registry that is not UTF-8, with no traceback", tree, base_args, "is not UTF-8")
        r = sh(base, shim, "import", *base_args, "--working-copy", wc, env={**env_run, "GIT_DIR": os.path.join(scratch, "nowhere")})
        check("a GIT_DIR in the environment is dropped: the import still reads origin/main",
              r.returncode == 0 and "fabric-ref" in r.stdout, f"exit {r.returncode}: {r.stderr[:200]}")

        tree = os.path.join(scratch, "tree-link")
        shutil.copytree(base, tree, symlinks=True)
        real = os.path.join(scratch, "real-registry.json")
        shutil.move(os.path.join(tree, "projects", "registry.json"), real)
        os.symlink(real, os.path.join(tree, "projects", "registry.json"))
        r = imp(tree, *base_args, "--write")
        check("a symlinked registry stays a symlink and its target gets the entry",
              r.returncode == 0 and os.path.islink(os.path.join(tree, "projects", "registry.json"))
              and "scratch.proj" in json.load(open(real, encoding="utf-8"))["projects"], r.stderr)
        r = sh(base, PY, "-c", "import sys; sys.path.insert(0, %r); import project; project.run = lambda argv: (_ for _ in ()).throw(BrokenPipeError()); sys.exit(project.main())" % os.path.join(base, "tools", "fabric"),
               env=env_run)
        check("a broken pipe from the run exits 141, not 1", r.returncode == 141, f"exit {r.returncode}: {r.stderr[:200]}")
        r = sh(base, shim, "--help", env=env_run)
        check("--help: exit 0 and the contract on stdout", r.returncode == 0 and "CONTRACT" in r.stdout)
        r = sh(base, shim, "bogus", env=env_run)
        check("an unknown subcommand: exit 2, one line", r.returncode == 2 and r.stderr.count("\n") == 1)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    print(f"{'FAILED' if fails else 'ok'}: {fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
