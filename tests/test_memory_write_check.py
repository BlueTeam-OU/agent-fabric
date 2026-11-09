#!/usr/bin/env python3
"""runtime/claude-code/hooks/memory-write-check.py: a session writing one
of its own drain-bound memories is told what the drain would do with it;
everything else is silent, and nothing ever blocks."""
from __future__ import annotations

import json
import os
import pwd
import subprocess
import sys
import tempfile
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree, write_operator_projects  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import layout  # noqa: E402 — memory_slug, the one rule for a memory directory's name
HOOK = os.path.join(ROOT, "runtime", "claude-code", "hooks", "memory-write-check.py")


ANCHORS = "  anchors: [tools/fabric/harvest_memory.py::parse_memory]\n"
ANCHORED = "  roles_class: solution\n" + ANCHORS


def memory(dirpath: str, name: str, description: str, meta: str, body: str) -> str:
    path = os.path.join(dirpath, f"{name}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f'---\nname: {name}\ndescription: "{description}"\nmetadata:\n  type: project\n{meta}---\n{body}\n')
    return path


def run(path: str, raw: str | None = None, env: dict | None = None, cwd: str | None = None) -> tuple[int, str]:
    data = raw if raw is not None else json.dumps({"tool_name": "Write", "tool_input": {"file_path": path}})
    p = subprocess.run([sys.executable, HOOK], input=data, capture_output=True, text=True, env=env, cwd=cwd)
    if env is not None and p.stderr.strip():
        return 1, "stderr: " + p.stderr.strip()
    if not p.stdout.strip():
        return p.returncode, ""
    doc = json.loads(p.stdout)
    assert doc["hookSpecificOutput"]["hookEventName"] == "PostToolUse", doc
    return p.returncode, doc["hookSpecificOutput"]["additionalContext"]


def merge_target_cases() -> int:
    """ADR-050 rule 9, against a fixture corpus: the role's solution slice holds one section, and the writer is
    bound to that role and project through a state directory of its own, so nothing of the live corpus is read."""
    fails = 0
    with tempfile.TemporaryDirectory() as tmp:
        wc = os.path.join(tmp, "wc")
        slices = os.path.join(wc, ".agent-fabric", "memory", "fixture-role", "solution")
        os.makedirs(slices)
        with open(os.path.join(slices, "topic.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nrole: fixture-role\n---\n\n## The held section\n\ntext\n\n## Another section\n\ntext\n")
        state = os.path.join(tmp, "state")
        os.makedirs(os.path.join(state, "agents", pwd.getpwuid(os.geteuid()).pw_name))
        binding = os.path.join(state, "agents", pwd.getpwuid(os.geteuid()).pw_name, "binding.json")
        with open(binding, "w", encoding="utf-8") as fh:
            json.dump({"role": "fixture-role", "project": "fixture-proj", "working_copy": wc}, fh)
        # The live registry is instance data and a stripped copy has none: every case reads the operator tree this builds.
        env = {**os.environ, "AGENT_FABRIC_STATE_DIR": state,
               "AGENT_FABRIC_OPERATOR": write_operator_projects(
                   os.path.join(tmp, "operator"), {"fixture-proj": ["git@example.org:o/fixture-proj.git"]})}
        env.pop("AGENT_FABRIC_WORKING_COPY", None)
        # The drain reads a memory directory as the one of the working copy whose slug names it, so the fixture's is.
        home = os.path.join(tmp, ".claude", "projects", layout.memory_slug(wc), "memory")
        os.makedirs(home)
        elsewhere = os.path.join(tmp, "elsewhere")      # not a git checkout: the project comes from the binding
        os.makedirs(elsewhere)

        def target(name: str, heading: str, extra: str = "", klass: str = "solution") -> str:
            return memory(home, name, "a correction", f"  roles_class: {klass}\n{ANCHORS}  merge_target: \"{heading}\"\n{extra}",
                          "body")

        cases = [
            ("a target naming a section of the role's slice", target("t1", "The held section"), None),
            ("a target naming a second section of it", target("t2", "Another section"), None),
            ("a target naming nothing of it, no shared_with", target("t3", "A shared section"), "no shared_with"),
            ("the same, with shared_with", target("t4", "A shared section", "  shared_with: other-role\n"), None),
            ("a target in a class the role has no slice of", target("t5", "The held section", klass="workflow"), None),
            ("a retire (no body) of a missing section", memory(home, "t6", "retire", f"  roles_class: solution\n{ANCHORS}  merge_target: \"Gone\"\n", ""),
             "no shared_with"),
            ("no merge_target at all", memory(home, "t7", "plain", ANCHORED, "body"), None),
        ]
        for label, path, expect in cases:
            rc, out = run(path, env=env, cwd=elsewhere)
            good = rc == 0 and ((not out) if expect is None else expect in out)
            print(f"  {'ok  ' if good else 'FAIL'} merge_target: {label}" + ("" if good else f": {out!r}"))
            fails += not good
        # Unreadable slices say nothing: no binding, no working copy, a slice no one can parse.
        os.remove(binding)
        rc, out = run(target("t8", "A shared section"), env=env, cwd=elsewhere)
        good = rc == 0 and not out
        print(f"  {'ok  ' if good else 'FAIL'} merge_target: no binding, so no role: silent" + ("" if good else f": {out!r}"))
        fails += not good
        with open(binding, "w", encoding="utf-8") as fh:
            json.dump({"role": "fixture-role", "project": "fixture-proj", "working_copy": os.path.join(tmp, "no-such")}, fh)
        rc, out = run(target("t9", "A shared section"), env=env, cwd=elsewhere)
        good = rc == 0 and not out
        print(f"  {'ok  ' if good else 'FAIL'} merge_target: a working copy that is gone: silent" + ("" if good else f": {out!r}"))
        fails += not good
        fails += other_project_cases(tmp, binding, env)
    return fails


def other_project_cases(tmp: str, binding: str, env: dict) -> int:
    """j567: the memory is judged by the project of the working copy that owns its memory directory, as the
    drain does, not by the session's cwd: cwd in A (project gzapp), the memory in B's slug directory (gzapi.ge)."""
    fails = 0
    copies = {}
    for name, project, heading in (("wc-a", "gzapp", "Only in a"), ("wc-b", "gzapi.ge", "Only in b")):
        top = os.path.join(tmp, name)
        slices = os.path.join(top, ".agent-fabric", "memory", "fixture-role", "solution")
        os.makedirs(slices)
        with open(os.path.join(top, ".agent-fabric-project"), "w", encoding="utf-8") as fh:
            fh.write(project + "\n")
        with open(os.path.join(slices, "topic.md"), "w", encoding="utf-8") as fh:
            fh.write(f"---\nrole: fixture-role\n---\n\n## {heading}\n\ntext\n")
        subprocess.run(["git", "init", "-q", top], check=True, env=git_env())
        copies[name] = top
    with open(binding, "w", encoding="utf-8") as fh:
        json.dump({"role": "fixture-role", "project": "gzapp", "working_copy": copies["wc-a"]}, fh)
    # Both projects are registered in the operator's tree the case builds: the live registry is instance data,
    # and a stripped copy without it resolves no project, so the hook stays silent and "only A's slice" fails.
    env = {**env, "AGENT_FABRIC_OPERATOR": write_operator_projects(
        os.path.join(tmp, "operator"), {"gzapp": ["git@example.org:o/gzapp.git"],
                                        "gzapi.ge": ["git@example.org:o/gzapi.ge.git"]})}
    home_b = os.path.join(tmp, ".claude", "projects", layout.memory_slug(copies["wc-b"]), "memory")
    os.makedirs(home_b)
    cases = [
        ("cwd in A, memory of B naming a heading of B's slice", "Only in b", None),
        ("cwd in A, memory of B naming a heading only A's slice has", "Only in a", "no shared_with"),
    ]
    for i, (label, heading, expect) in enumerate(cases):
        path = memory(home_b, f"o{i}", "a correction",
                      f'  roles_class: solution\n{ANCHORS}  merge_target: "{heading}"\n', "body")
        rc, out = run(path, env={**env, "AGENT_FABRIC_WORKING_COPY": copies["wc-b"]}, cwd=copies["wc-a"])
        good = rc == 0 and ((not out) if expect is None else expect in out)
        print(f"  {'ok  ' if good else 'FAIL'} merge_target: {label}" + ("" if good else f": {out!r}"))
        fails += not good
    # The slug is lossy: one matching no known working copy names no project, so nothing is said.
    home_x = os.path.join(tmp, ".claude", "projects", "-no-such-copy", "memory")
    os.makedirs(home_x)
    path = memory(home_x, "o9", "a correction",
                  f'  roles_class: solution\n{ANCHORS}  merge_target: "Only in b"\n', "body")
    rc, out = run(path, env=env, cwd=copies["wc-a"])
    good = rc == 0 and not out
    print(f"  {'ok  ' if good else 'FAIL'} merge_target: a slug matching no working copy: silent"
          + ("" if good else f": {out!r}"))
    return fails + (not good)


def binding_record_case() -> int:
    """owning_working_copy asks identity.binding_record for the binding's working copy, never a raw read_binding.
    <- the candidate list back on identity.read_binding. Positive control: the record's working copy is the one found."""
    import importlib.util
    import types
    spec = importlib.util.spec_from_file_location("memory_write_check_hook", HOOK)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)

    def raw_read(*a, **k):
        raise AssertionError("a raw read of the binding")
    wc = "/work/the-bound-copy"
    wcmod = types.SimpleNamespace(toplevel=lambda cwd: None, sibling_working_copies=lambda root: {})
    hm = types.SimpleNamespace(
        identity=types.SimpleNamespace(
            _workingcopy=lambda: wcmod, read_binding=raw_read,
            binding_record=lambda: types.SimpleNamespace(working_copy=wc),
            resolve_context=lambda cwd: {"project": "bound-project"}),
        layout=types.SimpleNamespace(
            FABRIC_ROOT="/work/root", explicit_working_copies=dict, project_ids=list, working_copy_for=lambda pid: None,
            memory_slug=lambda path: "the-slug" if path == wc else "other"))
    found = hook.owning_working_copy(hm, "/h/.claude/projects/the-slug/memory/m.md")
    good = found == ("bound-project", wc)
    print(f"  {'ok  ' if good else 'FAIL'} owning_working_copy: the binding's working copy comes from binding_record"
          + ("" if good else f": {found!r}"))
    return not good


def main() -> int:
    fails = binding_record_case()
    with tempfile.TemporaryDirectory() as tmp:
        mem = os.path.join(tmp, ".claude", "projects", "slug", "memory")
        os.makedirs(mem)
        cases = [
            ("private: no roles_class", memory(mem, "p", "a note", "", "body"), None),
            ("clean: the drain takes it", memory(mem, "g", "a fact", ANCHORED, "body"), None),
            ("an unknown class, and the whole harvest stops", memory(mem, "b", "x", "  roles_class: notaclass\n", "body"),
             ("is not a claim class", "whole harvest")),
            ("a hand-authored class", memory(mem, "h", "x", "  roles_class: charter\n", "body"), "hand-authored"),
            ("shared_with naming no role", memory(mem, "s", "x", "  roles_class: solution\n  shared_with: Web Dev!\n", "body"),
             "not role slugs"),
            ("over the slice budget", memory(mem, "big", "big", "  roles_class: threads\n", "word " * 2000), "slice budget"),
            ("a workflow memory has the larger budget", memory(mem, "wf", "wf", "  roles_class: workflow\n" + ANCHORS, "word " * 2000), None),
            ("a description in another script without description_en",
             memory(mem, "ru", "факт по-русски", "  roles_class: domain\n", "Это факт на русском языке без перевода."),
             "no description_en"),
            ("a body in another language without its rendering",
             memory(mem, "ru2", "a fact in Russian", "  roles_class: domain\n", "Это факт на русском языке без перевода."),
             "'## English' rendering"),
            ("a generated class", memory(mem, "ix", "x", "  roles_class: index\n", "body"), "generated by the"),
            ("a credential by shape", memory(mem, "c", "c", "  roles_class: solution\n", "token ghp_" + "A" * 36),
             "by shape"),
        ]
        # ADR-050 rule 7: warned, never refused; matched exactly and case-sensitively.
        events = [
            ("FIXED: starts the description", "FIXED: the cache bug", True),
            ("FIXED then a space", "FIXED the cache bug", True),
            ("MERGED, CLOSED and DONE", "DONE with the port", True),
            ("a #number", "#198 and its reader", True),
            ("a PR number", "PR 250 landed", True),
            ("a date and a colon", "2026-10-14: the drain ran", True),
            ("Fixed in lower case is prose", "Fixed paths are resolved first", False),
            ("a date with no colon", "2026-10-14 is the day the drain moved", False),
            ("FIXED glued to a word", "FIXEDPOINT arithmetic", False),
            ("a # with no digits", "# of retries is capped", False),
            ("PR with no number", "PR review is blind", False),
            ("an event word after the start", "the cache was FIXED: twice", False),
        ]
        for label, description, warns in events:
            path = memory(mem, "ev", description, "  roles_class: domain\n", "body")
            rc, out = run(path)
            good = rc == 0 and (("reads as an event" in out) if warns else not out)
            print(f"  {'ok  ' if good else 'FAIL'} event: {label}" + ("" if good else f": {out!r}"))
            fails += not good
        for label, path, expect in cases:
            rc, out = run(path)
            wants = (expect,) if isinstance(expect, str) else (expect or ())
            good = rc == 0 and ((not out) if expect is None else all(w in out for w in wants))
            if expect and "ghp_" in out:
                good = False                     # never the credential itself
            print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {out!r}"))
            fails += not good
        # ADR-050 rule 1: advice for a solution or workflow memory with no anchors, read as parse_memory reads them.
        anchor_cases = [
            ("a solution memory with no anchors", "  roles_class: solution\n", "no anchors"),
            ("a workflow memory with no anchors", "  roles_class: workflow\n", "no anchors"),
            ("a solution memory with anchors", ANCHORED, None),
            ("anchors at the top level of the frontmatter count", "  roles_class: solution\n", None),
            ("an anchor list that is no inline list", "  roles_class: solution\n  anchors: a/b.py\n", "no inline list"),
            ("an anchor that leaves the tree is no anchor", "  roles_class: solution\n  anchors: [/etc/passwd::x]\n", "no anchors"),
            ("a block list of anchors is read like the inline form", "  roles_class: solution\n  anchors:\n    - tools/fabric/anchors.py::problem\n    - gzapp:src/a.py\n", None),
            ("a block list whose only item is no anchor says so", "  roles_class: solution\n  anchors:\n    - /etc/passwd::x\n", "anchor '/etc/passwd::x'"),
            ("a domain memory needs none", "  roles_class: domain\n", None),
            ("a threads memory needs none", "  roles_class: threads\n", None),
        ]
        for label, meta, expect in anchor_cases:
            path = memory(mem, "an", "a fact", meta, "body")
            if label.startswith("anchors at the top level"):
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text.replace("metadata:\n", "anchors: [tools/fabric/anchors.py::problem]\nmetadata:\n", 1))
            rc, out = run(path)
            good = rc == 0 and ((not out) if expect is None else expect in out)
            print(f"  {'ok  ' if good else 'FAIL'} anchors: {label}" + ("" if good else f": {out!r}"))
            fails += not good
        with open(os.path.join(mem, "MEMORY.md"), "w", encoding="utf-8") as fh:
            fh.write("- [x](x.md)\n")
        for label, path, raw in (("MEMORY.md is the index, not a memory", os.path.join(mem, "MEMORY.md"), None),
                                 ("a path outside the memory directory", os.path.join(ROOT, "CLAUDE.md"), None),
                                 ("an unreadable payload never blocks", "", "not json")):
            rc, out = run(path, raw)
            good = rc == 0 and not out
            print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": rc={rc} {out!r}"))
            fails += not good
        # A fabric tree the harvester cannot load (its schema missing:
        # mid-checkout, a stale root) exits it at import with SystemExit;
        # the hook still says nothing and exits 0.
        # The whole committed tree but for the claims schema, so the import
        # reaches the harvester's own sys.exit and nothing earlier.
        broken = os.path.join(tmp, "broken-fabric")
        os.makedirs(broken)
        archive = subprocess.run(["git", "-C", ROOT, "archive", "HEAD"], capture_output=True, check=True, env=git_env()).stdout
        subprocess.run(["tar", "-x", "-C", broken], input=archive, check=True)
        os.remove(os.path.join(broken, "identities", "schemas", "claims.schema.json"))
        for f in ("runtime/claude-code/hooks/memory-write-check.py",):
            with open(os.path.join(ROOT, f), encoding="utf-8") as src, \
                 open(os.path.join(broken, f), "w", encoding="utf-8") as dst:
                dst.write(src.read())
        rc, out = run(memory(mem, "late", "x", ANCHORED, "body"),
                      env={**os.environ, "AGENT_FABRIC_ROOT": broken})
        good = rc == 0 and not out
        print(f"  {'ok  ' if good else 'FAIL'} a fabric the harvester cannot load: silent, exit 0"
              + ("" if good else f": rc={rc} {out!r}"))
        fails += not good
    fails += merge_target_cases()
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
