#!/usr/bin/env python3
"""tools/fabric/managed_settings.py (agent-fabric ADR-043 rules 1-2) against scratch git repositories and a scratch
prefix, as a non-root login with the test overrides: the render byte-stable with every @ENTRY@ filled; the
template carrying every guard and no convenience, the workspace's moved entries each made a no-op by the managed
file; an install read from the object store, with its MANIFEST, modes, `current` swapped, the managed file and the
boot script written, a second install of the same sha changing nothing and another sha swapping; a planted object
that does not hash to its name refused; the refusals (a sha that is not hex, unknown, not a commit, older than the
template, a non-root caller without the overrides); check's five states; restore. Ownership cannot be root in a
test, so check is handed the expected owner (this uid).
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from instance_fixtures import own_instance_tree  # noqa: E402
from git_env import git_env, scrub_process_env  # noqa: E402
own_instance_tree()
scrub_process_env()

ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "runtime", "claude-code", "managed"))
import managed_settings as ms  # noqa: E402
import hook_entry  # noqa: E402
import fabric_settings  # noqa: E402

TOOL = os.path.join(ROOT, "tools", "fabric", "managed_settings.py")
TEMPLATE = os.path.join(ROOT, ms.TEMPLATE)
WORKSPACE = os.path.join(ROOT, "runtime", "claude-code", "workspace", "settings.json")
GATE = "[ -e /etc/claude-code/managed-settings.json ] && exit 0; "
# The workspace scripts whose entries moved, and the managed guard each became.
MOVED = {"agent-dispatch-guard.sh": "agent-dispatch-guard", "subagent-clone-guard.sh": "subagent-clone-guard",
         "pipe-status-guard.sh": "pipe-status-guard", "self-kill-guard.py": "self-kill-guard",
         "job-copy-guard.sh": "job-copy-guard", "plan-hold.sh": "plan-hold", "model-switch-guard.sh": "model-switch-guard"}
CONVENIENCES = ("statusline", "session-start", "tab-title", "model-fallback-note", "gzcoord-inbox")


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], env=git_env(), check=True, capture_output=True,
                          text=True).stdout.strip()


def write(path: str, text: str, mode: int = 0o644) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, mode)


def commit(repo: str, msg: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def hooks_of(doc: dict):
    for event, groups in doc.get("hooks", {}).items():
        for g in groups:
            for h in g["hooks"]:
                yield event, g.get("matcher"), h


def cli(*args: str, env_extra: dict | None = None, overrides: bool = True) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ms.OVERRIDES}
    env.update(env_extra or {})
    if not overrides:
        for k in ms.OVERRIDES:
            env.pop(k, None)
    return subprocess.run([sys.executable, TOOL, *args], env=env, capture_output=True, text=True, timeout=300)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    tpl_text = open(TEMPLATE, encoding="utf-8").read()
    tpl = json.loads(tpl_text)

    print("managed settings: the render")
    a, b = ms.render(tpl_text, "/p"), ms.render(tpl_text, "/p")
    doc = json.loads(a)
    check("byte-stable: two renders are equal, sorted, indented by two, one trailing newline",
          a == b and a == json.dumps(doc, sort_keys=True, indent=2) + "\n" and not a.endswith("\n\n"))
    entry = "/p/managed/current/runtime/claude-code/managed/hook_entry.py"
    managed_hooks = list(hooks_of(doc))
    check("every @ENTRY@ filled: no placeholder left, each hook's args name the entry under the prefix",
          ms.PLACEHOLDER not in a and managed_hooks and all(h["args"][2] == entry for _e, _m, h in managed_hooks),
          a[:400])
    check("the comment is dropped", "_comment" not in doc)
    check("rule 1's keys: allowManagedModsOnly under cc-plugin-sec-default@builtin, disableSideloadFlags",
          doc.get("pluginConfigs", {}).get("cc-plugin-sec-default@builtin", {}).get("options") ==
          {"allowManagedModsOnly": True} and doc.get("disableSideloadFlags") is True)
    r = cli("render", "--prefix", "/p")
    check("the CLI's render is the module's", r.returncode == 0 and r.stdout == a, r.stderr)

    print("managed settings: the template and the workspace")
    names = {h["args"][3] for _e, _m, h in hooks_of(tpl)}
    check("each hook is exec form: the pinned interpreter by path, -I -S, the entry, one guard name",
          all(h["type"] == "command" and h["command"] == "/usr/local/bin/fabric-python"
              and h["args"][:3] == ["-I", "-S", "@ENTRY@"] and len(h["args"]) == 4 for _e, _m, h in hooks_of(tpl)))
    check("the template's guards are exactly hook_entry's table", names == set(hook_entry.GUARDS),
          names ^ set(hook_entry.GUARDS))
    check("each guard's module is in the tree",
          all(os.path.isfile(os.path.join(ROOT, rel)) for rel, _e, _a in hook_entry.GUARDS.values()))
    check("no convenience in the template: no status line, no SessionStart or Post* event, none of their scripts",
          "statusLine" not in tpl and set(tpl["hooks"]) <= {"PreToolUse", "PreModelSwitch", "UserPromptSubmit",
                                                            "SessionEnd"}
          and not any(c in json.dumps(tpl["hooks"]) for c in CONVENIENCES))
    ws = json.load(open(WORKSPACE, encoding="utf-8"))
    moved, gated_wrong, sentinel = [], [], None
    for event, matcher, h in hooks_of(ws):
        script = next((s for s in MOVED if f"/runtime/claude-code/hooks/{s}" in h["command"]), None)
        if script:
            moved.append((event, matcher or "", h["timeout"], MOVED[script]))
            if not h["command"].startswith(GATE):
                gated_wrong.append(h["command"][:80])
        elif h["command"].startswith(GATE):
            gated_wrong.append("a convenience is gated: " + h["command"][:80])
        if event == "SessionStart" and "ADR-043" in h["command"]:
            sentinel = h["command"]
    theirs = sorted((e, m or "", h["timeout"], h["args"][3]) for e, m, h in hooks_of(tpl) if h["args"][3] != "review-fence")
    check("matchers, events and timeouts are the workspace's, guard for guard", sorted(moved) == theirs,
          (sorted(moved), theirs))
    check("every moved workspace entry, and only those, starts with the managed-file test", not gated_wrong,
          gated_wrong)
    check("review-fence is the one new entry: PreToolUse on Bash and the writing tools",
          [(e, m) for e, m, h in hooks_of(tpl) if h["args"][3] == "review-fence"] ==
          [("PreToolUse", "Bash|Write|Edit|MultiEdit|NotebookEdit")])
    check(".claude/settings.json is the workspace template re-rendered",
          open(os.path.join(ROOT, ".claude", "settings.json"), encoding="utf-8").read() == fabric_settings.render(ROOT))

    with tempfile.TemporaryDirectory() as tmp:
        # The gate and the sentinel as the harness runs them (sh -c), with the managed file's path aimed at
        # a scratch one: present, the guard does not run; absent, it runs, and the sentinel speaks.
        flag = os.path.join(tmp, "managed-settings.json")
        fake_root = os.path.join(tmp, "fr")
        write(os.path.join(fake_root, "runtime", "claude-code", "hooks", "pipe-status-guard.sh"),
              f"touch {tmp}/guard-ran\n")
        gated = next(h["command"] for _e, _m, h in hooks_of(ws) if "pipe-status-guard.sh" in h["command"])
        gated = gated.replace("/etc/claude-code/managed-settings.json", flag)
        sentinel_cmd = (sentinel or "").replace("/etc/claude-code/managed-settings.json", flag)
        env = {"PATH": "/usr/bin:/bin", "AGENT_FABRIC_ROOT": fake_root}
        r1 = subprocess.run(["sh", "-c", gated], env=env, capture_output=True, timeout=30)
        r2 = subprocess.run(["sh", "-c", sentinel_cmd], env=env, capture_output=True, text=True, timeout=30)
        ran_absent = os.path.exists(os.path.join(tmp, "guard-ran"))
        write(flag, "{}")
        os.remove(os.path.join(tmp, "guard-ran")) if ran_absent else None
        r3 = subprocess.run(["sh", "-c", gated], env=env, capture_output=True, timeout=30)
        r4 = subprocess.run(["sh", "-c", sentinel_cmd], env=env, capture_output=True, text=True, timeout=30)
        try:
            said = json.loads(r2.stdout)["hookSpecificOutput"]
        except (ValueError, KeyError):
            said = {}
        check("managed file absent: the workspace guard runs as before", r1.returncode == 0 and ran_absent)
        check("managed file present: the workspace entry exits 0 at once, the guard not run",
              r3.returncode == 0 and not os.path.exists(os.path.join(tmp, "guard-ran")))
        check("the sentinel: absent, one SessionStart context line naming ADR-043 and the operator's command",
              r2.returncode == 0 and said.get("hookEventName") == "SessionStart"
              and "ADR-043" in said.get("additionalContext", "") and "sudo fabric-managed install" in said["additionalContext"],
              r2.stdout)
        check("…present, nothing", r4.returncode == 0 and r4.stdout == "", r4.stdout)

        print("managed settings: install")
        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)
        git(repo, "init", "-q", "-b", "main")
        write(os.path.join(repo, "README.md"), "no template yet\n")
        write(os.path.join(repo, "runtime", "claude-code", "hooks", "x.sh"), "#!/bin/sh\n", 0o755)
        old = commit(repo, "before the template")
        write(os.path.join(repo, ms.TEMPLATE), tpl_text)
        shutil.copy(os.path.join(ROOT, ms.ENTRY), os.path.join(repo, ms.ENTRY))
        write(os.path.join(repo, "tools", "fabric", "a.py"), "A = 1\n")
        write(os.path.join(repo, "routing", "r.json"), "{}\n")
        write(os.path.join(repo, "policies", "p.json"), "{}\n")
        write(os.path.join(repo, "projects", "registry.json"), "{}\n")
        write(os.path.join(repo, "identities", "roles", "r.md"), "role\n")
        write(os.path.join(repo, "identities", "other.md"), "not in a snapshot\n")
        write(os.path.join(repo, "docs", "d.md"), "doc\n")
        sha_a = commit(repo, "A")
        write(os.path.join(repo, "docs", "d.md"), "doc, changed\n")
        sha_d = commit(repo, "D: docs only")
        write(os.path.join(repo, "tools", "fabric", "a.py"), "A = 2\n")
        sha_c = commit(repo, "C: a snapshot path")
        write(os.path.join(repo, ms.TEMPLATE), tpl_text.replace('"timeout": 5', '"timeout": 6', 1))
        sha_b = commit(repo, "B: the template")
        blob = git(repo, "rev-parse", f"{sha_a}:README.md")

        prefix, etc = os.path.join(tmp, "usr", "agent-fabric"), os.path.join(tmp, "etc", "claude-code")
        rcdir = os.path.join(tmp, "rw", "config", "rc.local.d")
        os.makedirs(rcdir)
        rc = os.path.join(rcdir, "agent-fabric-managed.rc")
        managed = os.path.join(prefix, "managed")
        me = os.getuid()
        lines: list[str] = []

        def inst(sha: str, rc_path: str = rc, into: str = prefix, from_repo: str = repo) -> list[str]:
            lines.clear()
            ms.install(sha, from_repo, into, etc, rc_path, say=lines.append)
            return list(lines)

        def state(ref: str, **kw) -> dict:
            return ms.check(repo, ref, prefix, etc, owner=me, **kw)

        out = inst(sha_a)
        snap_a = os.path.join(managed, f"fabric-{sha_a}")
        listed = git(repo, "ls-tree", "-r", "--full-tree", sha_a, "--", *ms.SNAPSHOT)
        want_manifest = f"sha {sha_a}\n" + "".join(line.replace(" blob ", " ", 1) + "\n" for line in listed.split("\n"))
        manifest = open(os.path.join(snap_a, ms.MANIFEST), encoding="utf-8").read()
        check("MANIFEST: the sha, then each snapshot file's mode, blob and path as git lists them",
              manifest == want_manifest, (manifest, want_manifest))
        check("only the snapshot paths: identities/roles/ in, identities/other.md, docs/ and README.md out",
              os.path.isfile(os.path.join(snap_a, "identities", "roles", "r.md"))
              and not os.path.exists(os.path.join(snap_a, "identities", "other.md"))
              and not os.path.exists(os.path.join(snap_a, "docs")) and not os.path.exists(os.path.join(snap_a, "README.md")))
        modes = {os.path.relpath(os.path.join(d, n), snap_a): stat.S_IMODE(os.lstat(os.path.join(d, n)).st_mode)
                 for d, _ds, fs in os.walk(snap_a) for n in fs}
        dmodes = {stat.S_IMODE(os.lstat(d).st_mode) for d, _ds, _fs in os.walk(snap_a)}
        check("modes: 0755 where git says 100755, 0644 otherwise, every directory 0755",
              modes["runtime/claude-code/hooks/x.sh"] == 0o755 and modes["tools/fabric/a.py"] == 0o644
              and modes[ms.ENTRY] == 0o644 and dmodes == {0o755}, (modes, dmodes))
        check("current -> fabric-<sha>, by a relative link", os.readlink(os.path.join(managed, "current")) == f"fabric-{sha_a}")
        rendered = ms.render(tpl_text, prefix)
        check("the managed file and its kept copy are the template rendered for the prefix, 0644",
              open(os.path.join(etc, "managed-settings.json")).read() == rendered
              and open(os.path.join(managed, "managed-settings.json")).read() == rendered
              and stat.S_IMODE(os.stat(os.path.join(etc, "managed-settings.json")).st_mode) == 0o644)
        rc_text = open(rc).read() if os.path.exists(rc) else ""
        check("the boot script, where rc.local.d exists: sh, install -D of the kept copy to /etc",
              rc_text.startswith("#!/bin/sh\n") and
              f"install -D -m 0644 {os.path.join(managed, 'managed-settings.json')} /etc/claude-code/managed-settings.json\n"
              in rc_text, rc_text)
        check("one line per step, the last saying installed", len(out) >= 5 and out[-1].startswith("installed:"), out)
        if os.access(ms.FABRIC_PYTHON, os.X_OK):
            check("compiled by the pinned interpreter: a __pycache__ beside tools/fabric/a.py",
                  any(n.startswith("a.") for n in os.listdir(os.path.join(snap_a, "tools", "fabric", "__pycache__"))))
        ino = os.stat(snap_a).st_ino
        out = inst(sha_a)
        check("a second install of the same sha: the snapshot reused, unchanged", os.stat(snap_a).st_ino == ino
              and any("already in place" in line for line in out), out)
        inst(sha_b)
        check("another sha: current swapped, the previous snapshot kept",
              os.readlink(os.path.join(managed, "current")) == f"fabric-{sha_b}" and os.path.isdir(snap_a)
              and open(os.path.join(etc, "managed-settings.json")).read() != rendered)
        inst(sha_c)
        check("a third: the one before the previous removed, the previous kept",
              not os.path.exists(snap_a) and os.path.isdir(os.path.join(managed, f"fabric-{sha_b}"))
              and os.readlink(os.path.join(managed, "current")) == f"fabric-{sha_c}")
        out = inst(sha_c, rc_path=os.path.join(tmp, "no-rw", "x.rc"))
        check("no rc.local.d (not a Qubes AppVM): no boot script", not os.path.exists(os.path.join(tmp, "no-rw")))

        print("managed settings: check")
        check("in force at the installed sha", state(sha_c)["state"] == "in force", state(sha_c))
        inst(sha_a)
        st = state(sha_a)
        check("in force at A, naming its snapshot", st["state"] == "in force" and st["snapshot"] == sha_a, st)
        st = state(sha_d)
        check("…and at D, which changes only docs/: a commit elsewhere on main is not drift", st["state"] == "in force", st)
        st = state(sha_c)
        check("drifted at C, a snapshot path changed, naming it", st["state"] == "drifted"
              and any("tools/fabric/a.py" in w for w in st["reasons"]), st)
        st = state(sha_b)
        check("drifted at B, the template changed: the managed file is not its render",
              st["state"] == "drifted" and any("is not the template at" in w for w in st["reasons"]), st)
        st = ms.check(repo, sha_a, os.path.join(tmp, "none"), os.path.join(tmp, "none-etc"), owner=me)
        check("missing: no managed file, no snapshot", st["state"] == "missing"
              and any("is absent" in w for w in st["reasons"]), st)
        st = state(sha_a, fabric_python="/nonexistent/fabric-python")
        check("missing: the pinned interpreter absent", st["state"] == "missing"
              and any("fabric-python is absent" in w for w in st["reasons"]), st)
        st = state(sha_a, jq_dirs=(os.path.join(tmp, "nowhere"),))
        check("missing: no jq", st["state"] == "missing" and any("no jq" in w for w in st["reasons"]), st)
        st = ms.check(repo, sha_a, prefix, etc, owner=me + 1)
        check("tampered: owned by another uid than the expected one", st["state"] == "tampered"
              and any("not %d" % (me + 1) in w for w in st["reasons"]), st)
        victim = os.path.join(snap_a, "tools", "fabric", "a.py")
        with open(victim, "a") as f:
            f.write("EVIL = 1\n")
        st = state(sha_a)
        check("tampered: a snapshot file edited", st["state"] == "tampered"
              and any("a.py: content is not its MANIFEST blob" in w for w in st["reasons"]), st)
        out = inst(sha_a)
        check("…and an install of that sha replaces the altered snapshot", state(sha_a)["state"] == "in force"
              and any("replaced" in line for line in out), out)
        os.chmod(victim, 0o664)
        st = state(sha_a)
        check("tampered: a snapshot file group-writable", st["state"] == "tampered"
              and any("group- or other-writable" in w for w in st["reasons"]), st)
        os.chmod(victim, 0o644)
        write(os.path.join(snap_a, "tools", "fabric", "planted.py"), "x = 1\n")
        st = state(sha_a)
        check("tampered: a file the MANIFEST does not hold", st["state"] == "tampered"
              and any("planted.py: in the snapshot, not in its MANIFEST" in w for w in st["reasons"]), st)
        os.remove(os.path.join(snap_a, "tools", "fabric", "planted.py"))
        etc_file = os.path.join(etc, "managed-settings.json")
        os.chmod(etc_file, 0o666)
        st = state(sha_a)
        check("tampered: the managed file other-writable", st["state"] == "tampered", st)
        os.chmod(etc_file, 0o644)
        if os.geteuid() != 0:
            os.chmod(etc_file, 0)
            st = state(sha_a)
            os.chmod(etc_file, 0o644)
            check("unreadable: the managed file cannot be read", st["state"] == "unreadable", st)
        st = state("refs/heads/no-such-branch")
        check("unreadable: the ref cannot be read", st["state"] == "unreadable", st)
        check("in force again once all is put back", state(sha_a)["state"] == "in force", state(sha_a))
        kept_copy = os.path.join(managed, "managed-settings.json")
        saved = open(kept_copy).read()
        write(kept_copy, "{}\n")
        st = state(sha_a)
        write(kept_copy, saved)
        check("drifted: the kept copy the boot restore uses is not the managed file", st["state"] == "drifted"
              and any("restore would bring back another file" in w for w in st["reasons"]), st)
        env = {ms.OVERRIDES[0]: prefix, ms.OVERRIDES[1]: etc, ms.OVERRIDES[2]: rc}
        r = cli("check", "--repo", repo, "--ref", sha_a, "--json", env_extra=env)
        try:
            j = json.loads(r.stdout)
        except ValueError:
            j = {}
        check("the CLI's check --json: one object, exit 1 unless in force (here: not root's files, so tampered)",
              r.returncode == 1 and j.get("state") == "tampered" and j.get("snapshot") == sha_a
              and isinstance(j.get("reasons"), list), (r.stdout, r.stderr))

        print("managed settings: restore and the CLI's install")
        os.remove(etc_file)
        r = cli("restore", env_extra=env)
        check("restore puts the kept copy back", r.returncode == 0 and
              open(etc_file).read() == open(os.path.join(managed, "managed-settings.json")).read(), r.stderr)
        r = cli("install", "--sha", sha_d, "--repo", repo, env_extra=env)
        check("install through the CLI under the overrides", r.returncode == 0
              and os.readlink(os.path.join(managed, "current")) == f"fabric-{sha_d}", r.stdout + r.stderr)

        print("managed settings: refusals")
        r = cli("install", "--sha", "xyz", "--repo", repo, env_extra=env)
        check("a sha that is not 40 hex: usage, exit 2", r.returncode == 2 and "not a 40-hex" in r.stderr, r.stderr)
        r = cli("install", "--sha", sha_a.upper(), "--repo", repo, env_extra=env)
        check("…upper case included", r.returncode == 2, r.stderr)
        r = cli("install", "--sha", "0" * 40, "--repo", repo, env_extra=env)
        check("an unknown sha: exit 1, one line", r.returncode == 1 and "not in the repository" in r.stderr
              and len(r.stderr.strip().splitlines()) == 1, r.stderr)
        r = cli("install", "--sha", blob, "--repo", repo, env_extra=env)
        check("a sha that names a blob, not a commit", r.returncode == 1 and "not a commit" in r.stderr, r.stderr)
        r = cli("install", "--sha", old, "--repo", repo, env_extra=env)
        check("a commit older than the template", r.returncode == 1 and "predates" in r.stderr, r.stderr)
        if os.geteuid() != 0:
            r = cli("install", "--sha", sha_a, "--repo", repo, overrides=False)
            check("a non-root caller without the overrides: refused, naming sudo", r.returncode == 1
                  and "run it as root" in r.stderr and "sudo fabric-managed install" in r.stderr, r.stderr)
            r = cli("restore", overrides=False)
            check("…restore too", r.returncode == 1 and "run it as root" in r.stderr, r.stderr)
        r = cli()
        check("no subcommand: usage, exit 2, naming git ls-remote", r.returncode == 2 and "git ls-remote origin" in r.stderr)

        # A login owns its object store and can plant a loose object under the name of one the operator's sha
        # reaches; git reads it without re-hashing. The install hashes every object it reads.
        evil = os.path.join(tmp, "evil-repo")
        shutil.copytree(repo, evil)
        oid = git(evil, "rev-parse", f"{sha_a}:tools/fabric/a.py")
        obj = os.path.join(evil, ".git", "objects", oid[:2], oid[2:])
        os.chmod(obj, 0o644)
        with open(obj, "wb") as f:
            f.write(zlib.compress(b"blob 9\0EVIL = 1\n"))
        try:
            inst(sha_a, into=os.path.join(tmp, "evil-prefix"), from_repo=evil)
            check("a planted object that does not hash to its name is refused", False)
        except ms.Failed as e:
            check("a planted object that does not hash to its name is refused, nothing installed",
                  "does not hash to its name" in str(e)
                  and not os.path.exists(os.path.join(tmp, "evil-prefix", "managed", "current")), e)

    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
