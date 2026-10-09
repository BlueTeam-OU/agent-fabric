#!/usr/bin/env python3
"""runtime/provisioning/rename_history.py — carry an account's Claude Code
history across a working-copy rename; the Python half of
rename_working_copy.py, run AS THE ACCOUNT.

    rename_history.py <home> <login> <old-path> <new-path> <dry:0|1> <identity.py>

Everything it writes goes through identity.atomic_write (a temporary
beside the target, fsync, os.replace) and the binding through
identity.update_binding under the agent lock — a crash, a full disk or a
kill leaves the previous file whole (review, 2026-09-16; before this,
transcripts, history.jsonl, ~/.claude.json and binding.json were
rewritten in place, the binding bypassing write_binding). A merge into
an existing history directory is planned before anything moves and
never overwrites: same name and bytes, one copy; same name and
different bytes, both kept, the incoming one suffixed .from-<old key>;
a directory on both sides is refused.
"""
import hashlib, importlib.util, json, os, re, sys


def main() -> int:
    if len(sys.argv) != 7:
        print(__doc__.split("\n")[5].strip(), file=sys.stderr); return 2
    home, login, oldp, newp, dry, identity_py = sys.argv[1:7]
    dry = dry == "1"
    # The account's own copy of runtime/identity.py: every state file goes
    # through its atomic_write, the binding through update_binding under the
    # agent lock — never a rewrite in place (review, 2026-09-16).
    spec = importlib.util.spec_from_file_location("fabric_identity", identity_py)
    identity = importlib.util.module_from_spec(spec); spec.loader.exec_module(identity)
    key = lambda p: p.replace("/", "-")
    pdir_old, pdir_new = os.path.join(home, ".claude", "projects", key(oldp)), os.path.join(home, ".claude", "projects", key(newp))
    def note(m): print("rename: " + m, file=sys.stderr)
    def field_re(name, value):
        # `"name":"value"` as the harness writes it (compact) and as any
        # re-serialisation with a space after the colon would.
        return re.compile(json.dumps(name).encode() + rb":\s*" + re.escape(json.dumps(value).encode()))
    def field(name, value):
        return json.dumps(name).encode() + b":" + json.dumps(value).encode()
    def digest(path):
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b""): h.update(chunk)
        return h.hexdigest()
    # 1. the project directory: transcripts and memory
    if os.path.isdir(pdir_old):
        if dry: note(f"would: mv {pdir_old} -> {pdir_new}")
        else:
            if os.path.isdir(pdir_new):
                # MERGE, collision-safe: an earlier session under the new key must
                # not be lost, and neither may the one moving in. Same name and
                # same bytes: one copy. Same name, different bytes: both stay —
                # the incoming file takes a deterministic suffix naming the key
                # it came from, so nothing is overwritten and the origin is
                # readable in the name. Planned before anything moves.
                plan = []
                for f in sorted(os.listdir(pdir_old)):
                    src, dst = os.path.join(pdir_old, f), os.path.join(pdir_new, f)
                    if os.path.isdir(src):
                        if os.path.exists(dst):
                            note(f"REFUSED: both {pdir_old} and {pdir_new} hold a directory {f!r}; merge it by hand"); return 1
                        plan.append((src, dst))
                    elif os.path.exists(dst):
                        if digest(src) == digest(dst):
                            plan.append((src, None))            # identical: drop the incoming copy
                        else:
                            stem, ext = os.path.splitext(f)
                            plan.append((src, os.path.join(pdir_new, f"{stem}.from-{key(oldp)}{ext}")))
                    else:
                        plan.append((src, dst))
                for src, dst in plan:
                    if dst is None: os.unlink(src)
                    elif os.path.exists(dst):
                        note(f"REFUSED: {dst} exists; nothing moved"); return 1
                    else: os.replace(src, dst)
                os.rmdir(pdir_old)
                kept = sum(1 for _, d in plan if d and ".from-" in os.path.basename(d))
                note(f"{login}: history merged into {os.path.basename(pdir_new)}" + (f" ({kept} name collision(s) kept with a .from- suffix)" if kept else ""))
            else:
                os.replace(pdir_old, pdir_new)
                note(f"{login}: history {os.path.basename(pdir_new)}")
    if os.path.isdir(pdir_new) and not dry:
        n = 0
        old_cwd = field_re("cwd", oldp)
        for f in os.listdir(pdir_new):
            if not f.endswith(".jsonl"): continue
            p = os.path.join(pdir_new, f)
            data = open(p, "rb").read()
            if old_cwd.search(data):
                identity.atomic_write(p, old_cwd.sub(lambda _: field("cwd", newp), data)); n += 1
        note(f"{login}: cwd field rewritten in {n} transcript(s)")
    # 2. ~/.claude.json project key
    cj = os.path.join(home, ".claude.json")
    try: d = json.load(open(cj))
    except (OSError, ValueError): d = None
    if d and isinstance(d.get("projects"), dict) and oldp in d["projects"]:
        if dry: note(f"would: rename projects[{oldp}] in ~/.claude.json")
        else:
            if newp in d["projects"]:
                merged = {**d["projects"][oldp], **d["projects"][newp]}
                for k in ("allowedTools",):
                    a, b = d["projects"][oldp].get(k) or [], d["projects"][newp].get(k) or []
                    merged[k] = list(dict.fromkeys(a + b))
                d["projects"][newp] = merged
            else:
                d["projects"][newp] = d["projects"][oldp]
            del d["projects"][oldp]
            identity.atomic_write(cj, json.dumps(d, indent=2) + "\n")
            note(f"{login}: ~/.claude.json project key renamed")
    # 3. prompt history
    hj = os.path.join(home, ".claude", "history.jsonl")
    if os.path.exists(hj):
        old_pf = field_re("project", oldp)
        data = open(hj, "rb").read()
        if old_pf.search(data):
            if dry: note("would: rewrite history.jsonl project field")
            else: identity.atomic_write(hj, old_pf.sub(lambda _: field("project", newp), data)); note(f"{login}: history.jsonl project field rewritten")
    # 4. the binding: identity's own read-modify-write, under the agent lock,
    #    stamped by the OS (this runs as the account, so agent and host are its own)
    b = identity.read_binding(login)
    if b and any(b.get(k) == oldp for k in ("working_copy", "workspace")):
        if dry: note("would: rewrite binding working_copy/workspace")
        else:
            identity.update_binding(lambda rec: {**rec, **{k: newp for k in ("working_copy", "workspace") if rec.get(k) == oldp}}, login)
            note(f"{login}: binding updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
