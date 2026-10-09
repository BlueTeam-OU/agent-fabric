#!/usr/bin/env python3
"""The fabric's typed records are held to the values the code builds.

No type checker runs here (agent-fabric's typing is option (B): types only
where they carry behaviour, j28). An annotation nothing checks can drift
from the code and go on claiming a shape that is no longer there, so each
TypedDict is checked against real values: every required key present,
nothing undeclared. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback
from typing import Any, Callable

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from gzcoord import gzmsg  # noqa: E402
from secretstore import mirrors, trust  # noqa: E402
import jobs as jobs_mod  # noqa: E402
from assembler import core as asm_core  # noqa: E402
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

CASES: list[tuple[str, Callable[[], None]]] = []
SCRATCH: list[str] = []


class Failed(AssertionError):
    pass


def case(name: str) -> Callable:
    def add(fn: Callable[[], None]) -> Callable[[], None]:
        CASES.append((name, fn))
        return fn
    return add


def scratch() -> str:
    d = tempfile.mkdtemp(prefix="types-")
    SCRATCH.append(d)
    return d


def holds(value: Any, td: type, what: str) -> None:
    """`value` is a `td`: a dict, every required key, no key undeclared."""
    if not isinstance(value, dict):
        raise Failed(f"{what}: not a dict: {value!r}")
    keys = set(value)
    missing = set(td.__required_keys__) - keys
    extra = keys - set(td.__required_keys__) - set(td.__optional_keys__)
    if missing or extra:
        raise Failed(f"{what} is no {td.__name__}: missing {sorted(missing)}, undeclared {sorted(extra)}")


MESSAGE = ("[GZCOORD/1] INFO\nFROM: h/someone\nROLE: python-dev\nPROJECT: fixture\nBROADCAST: true\n"
           "MESSAGE-ID: 01a09fc1-0000-7000-8000-000000000001\nSUBJECT: s\n\nNOTES:\nn\n")


@case("gzmsg.parse and validate return a ParsedMessage and a Validation, either way validate goes")
def _():
    holds(gzmsg.parse(MESSAGE), gzmsg.ParsedMessage, "parse")
    good = gzmsg.validate(MESSAGE)
    holds(good, gzmsg.Validation, "validate (valid)")
    holds(good["message"], gzmsg.ParsedMessage, "validate's message")
    bad = gzmsg.validate("not a message\n")
    holds(bad, gzmsg.Validation, "validate (bad first line)")
    if bad["message"] is not None:
        raise Failed(f"a bad first line still carries a message: {bad}")


@case("gzmsg.whoami returns a Whoami, from identity and from the fallback")
def _():
    holds(gzmsg.whoami(), gzmsg.Whoami, "whoami")
    real = gzmsg._identity_module
    gzmsg._identity_module = lambda _root: (_ for _ in ()).throw(RuntimeError("identity cannot answer"))
    try:
        fallback = gzmsg.whoami()
    finally:
        gzmsg._identity_module = real
    holds(fallback, gzmsg.Whoami, "whoami (fallback)")
    if fallback.get("fallback") is not True:
        raise Failed(f"the fallback was not taken: {fallback}")


@case("gzmsg.recorded_role returns a RoleRecord in each of its four outcomes")
def _():
    d = scratch()
    tax = gzmsg.Taxonomy(os.path.join(d, "catalog.json"), {"python-dev": "Python developer"})
    binding = os.path.join(d, "binding.json")
    me = {"agent": "someone", "host": "h", "role": None, "project": None, "working_copy": None, "binding": binding}
    outcomes = {"no taxonomy": gzmsg.recorded_role(None, me), "no record": gzmsg.recorded_role(tax, me)}
    with open(binding, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    outcomes["unreadable"] = gzmsg.recorded_role(tax, me)
    outcomes["not in the catalogue"] = gzmsg.recorded_role(tax, dict(me, role="no-such-role"))
    outcomes["a catalogue role"] = gzmsg.recorded_role(tax, dict(me, role="python-dev"))
    for what, value in outcomes.items():
        holds(value, gzmsg.RoleRecord, f"recorded_role ({what})")
    keys = {what: sorted(set(v) - {"role"}) for what, v in outcomes.items()}
    if keys != {"no taxonomy": [], "no record": [], "unreadable": ["warning"],
                "not in the catalogue": ["error"], "a catalogue role": ["file"]}:
        raise Failed(f"the four outcomes are not told apart by their keys: {keys}")


def _env(**values: str):
    saved = {k: os.environ.get(k) for k in values}
    os.environ.update(values)

    def restore() -> None:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return restore


@case("secretstore: a refusal, written or unreadable, and every refusal listed, is a RefusalRecord")
def _():
    home = scratch()
    store = os.path.join(home, "store")
    os.makedirs(os.path.join(store, ".git"))
    restore = _env(HOME=home, AGENT_FABRIC_SECRET_STORE=store)
    try:
        trust._record_refusal(store, "0123abcd", "unsigned commit")
        holds(trust.refusal(store), trust.RefusalRecord, "refusal (written)")
        listed = trust.refusals()
        if [r.get("store") for r in listed] != ["own"]:
            raise Failed(f"the own store's refusal is not listed as own: {listed}")
        for r in listed:
            holds(r, trust.RefusalRecord, "refusals")
        with open(os.path.join(store, ".git", trust.REFUSAL_FILE), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        unreadable = trust.refusal(store)
        holds(unreadable, trust.RefusalRecord, "refusal (unreadable)")
        if unreadable.get("unreadable") is not True:
            raise Failed(f"an unreadable record reads as a refusal: {unreadable}")
    finally:
        restore()


@case("secretstore: a store with no trusted base is a BaseRecord in bases()")
def _():
    import subprocess
    listed = []
    # Both states base_state() gives: "unreadable" (no repository) and
    # "no base" (a repository that names none).
    for kind in ("unreadable", "no base"):
        home = scratch()
        store = os.path.join(home, "store")
        os.makedirs(os.path.join(store, "env"))
        if kind == "no base":
            subprocess.run(["git", "init", "-q", store], check=True, timeout=30,
                           env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull})
        restore = _env(HOME=home, AGENT_FABRIC_SECRET_STORE=store)
        try:
            listed += trust.bases()
        finally:
            restore()
    states = sorted(r.get("state") for r in listed)
    if states != ["no base", "unreadable"]:
        raise Failed(f"both states were not reached: {states}")
    for r in listed:
        holds(r, trust.BaseRecord, "bases")


@case("secretstore: every agent in a lineage file is a LineageEntry")
def _():
    # What certify() writes for a root and for a child, through the one
    # builder it uses, so an entry written tomorrow is held as well. The file
    # is a scratch fabric's: the committed one is the operator's, read by
    # lint's key-lineage rule, and absent from a checkout without its instance data.
    # Lint does not reject a key the type does not declare, so an undeclared key in the
    # committed file is no longer held anywhere; what certify() writes still is.
    root = "01a111d3-7e46-744b-8159-5131b5598f4d"
    child = "01a111d3-e2a5-7817-8019-35e185dcad48"
    fabric = scratch()
    mirrors._write_lineage({root: mirrors.lineage_entry(root, "user", "A" * 40, None),
                            child: mirrors.lineage_entry(child, "dev-01", "B" * 40, root)}, fabric)
    doc = mirrors.lineage(fabric)
    if set(doc) != {root, child}:
        raise Failed(f"the lineage file read back holds {sorted(doc)}")
    for aid, entry in doc.items():
        holds(entry, mirrors.LineageEntry, f"lineage[{aid}]")
    holds(mirrors.lineage_entry(root, "user", "A" * 40, None), mirrors.LineageEntry, "a root's entry")
    holds(mirrors.lineage_entry(child, "dev-01", "B" * 40, root), mirrors.LineageEntry, "a child's entry")


@case("every job fabric-jobs writes, through each state it can take, is a Job")
def _():
    import subprocess
    state = scratch()
    env = {**os.environ, "AGENT_FABRIC_STATE_DIR": state}
    jobs = os.path.join(HERE, "tools", "fabric", "jobs.py")

    def run(*args: str) -> None:
        r = subprocess.run([sys.executable, jobs, *args], env=env, cwd=HERE, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise Failed(f"fabric-jobs {' '.join(args)}: exit {r.returncode}\n{r.stderr}")
    run("add", "first", "--topic", "t")
    run("add", "second")
    run("add", "third")
    run("start", "j1")
    run("block", "j1", "--on-request", "01a111d3-7e46-744b-8159-5131b5598f4d", "a reply")
    run("start", "j2")
    run("deliver", "j2", "branch x@abc")
    run("drop", "j3", "not needed")
    run("add", "fourth", "--priority", "high")
    run("start", "j4")
    run("done", "j4")
    with open(os.path.join(state, "agents", jobs_login(), "jobs.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    states = sorted(j["state"] for j in doc["jobs"])
    if states != ["blocked", "delivered", "done", "dropped"]:
        raise Failed(f"the states were not all reached: {states}")
    # A job taken from a request (`add --request`): request_job() builds it
    # from the replayed message, as the command does, with no relay here.
    msg = {"type": "REQUEST", "seq": 7, "sender": "h/user",
           "metadata": {"MESSAGE-ID": "01a111d3-7e46-744b-8159-5131b5598f4d", "FROM": "h/user",
                        "SUBJECT": "a request"}}
    taken = jobs_mod.request_job({"jobs": list(doc["jobs"])}, msg, working_copy=HERE)
    if not taken or (taken.get("source") or {}).get("kind") != "request":
        raise Failed(f"no request job was built: {taken}")
    for j in [*doc["jobs"], taken]:
        holds(j, jobs_mod.Job, f"job {j.get('id')}")


# The drain, run through the real assemble.py in its own process, with its
# report phase wrapped to hand out the Run it was given: the claims, origins,
# class plan and index entries every phase built.
CAPTURE = r"""
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("assemble_capture", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
caught = {}
real = m.report
def capture(run):
    caught["run"] = run
    return real(run)
m.report = capture
sys.argv = ["assemble.py", *sys.argv[2:]]
rc = m.main()
run = caught["run"]
claims = [c for cs in run.all_claims.values() for c in cs]
claims += [c for buckets in run.per_role.values() for cs in buckets.values() for c in cs]
claims += [c for cs in run.shared.values() for c in cs]
print(json.dumps({"rc": rc, "claims": claims, "origins": list(run.origins.values()),
                  "plan": list(run.class_plan.values()),
                  "index": [e for es in run.index_entries.values() for e in es],
                  "shared_index": [e for es in run.shared_index.values() for e in es]}, default=sorted))
"""


# A role with one topic in its class, in both drains: the flat file the first
# writes is the one the second's plan names (flat_topic).
ONLY = {"class": "domain", "topic": "only", "title": "Only", "body": "One topic.", "evidence": ["a5"]}


@case("assemble: every claim, origin, class plan entry and index entry a drain builds is its type")
def _():
    import subprocess
    sys.path.insert(0, os.path.join(HERE, "tests"))
    import test_assemble as ta
    t = scratch()
    drain, claims_dir, out = ta.build(t, {"alpha": ta.claims("alpha", [
        {"class": "domain", "topic": "tracker", "title": "Issue is open", "body": "Waiting.", "evidence": ["a1"],
         "observed_at": "2026-09-20"},
        {"class": "domain", "topic": "same", "title": "Same", "body": "One.", "evidence": ["a2"]},
        {"class": "domain", "topic": "both", "title": "Both", "body": "Shared.", "evidence": ["a3"],
         "shared_with": ["beta"], "citations": {"memories": ["x"]}, "knowledge_scope": "full"},
    ]), "gamma": ta.claims("gamma", [ONLY])})
    ta.with_agents(drain, {h: "dev-01" for h in ("a1", "a2", "a3", "a4", "a5")})
    with open(os.path.join(drain, "observations.jsonl"), "a", encoding="utf-8") as fh:
        # An older row's clone, and a row naming its project and working copy.
        fh.write(json.dumps({"content_hash": "c9", "clone_id": "clone-z", "host": "hostB"}) + "\n")
        fh.write(json.dumps({"content_hash": "c8", "agent": "dev-01", "host": "hostA", "project": "demo",
                             "working_copy": "wc-demo"}) + "\n")
    first = ta.run_assemble(drain, claims_dir, out)
    if first.returncode != 0:
        raise Failed(f"the first drain failed: {first.stderr}")
    # The second: the tracker retitled (_retire) and a section rewritten
    # (merge_target), both by the agent that wrote them.
    ta.set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Issue is merged", "body": "Merged.", "evidence": ["a4"],
         "observed_at": "2026-09-24"},
        {"class": "domain", "topic": "same", "title": "Same", "body": "Two.", "evidence": ["a5"]},
        {"class": "domain", "topic": "both", "title": "Both", "body": "Shared.", "evidence": ["a3"],
         "shared_with": ["beta"], "citations": {"memories": ["x"]}, "knowledge_scope": "full"},
    ])
    r = subprocess.run([sys.executable, "-c", CAPTURE, ta.ASSEMBLE, "--claims", claims_dir, "--drain", drain,
                        "--fabric", out, "--project", ta.PROJECT, "--working-copy", ta.working_copy(out),
                        "--stamp", "2026-01-02"], capture_output=True, text=True, timeout=120)
    try:
        got = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise Failed(f"the second drain gave nothing to read: {r.stdout[-500:]}{r.stderr[-500:]}") from None
    if got["rc"] != 0:
        raise Failed(f"the second drain failed: {r.stderr[-800:]}")
    claims = got["claims"]
    # Every optional key of each type reached, so a type that drops one fails
    # here too; and one added to a type fails until the fixture reaches it.
    for td, values in ((asm_core.Claim, claims), (asm_core.Origin, got["origins"])):
        reached = {k for v in values for k in v} & set(td.__optional_keys__)
        if reached != set(td.__optional_keys__):
            raise Failed(f"no {td.__name__} built carried {sorted(set(td.__optional_keys__) - reached)}: "
                         "the fixture no longer reaches them")
    if not got["plan"] or not got["index"] or not got["shared_index"]:
        raise Failed(f"no plan, index or shared index entry was built: {got}")
    if not any(e.get("flat_topic") for e in got["plan"]):
        raise Failed(f"no plan entry named a flat topic: {got['plan']}")
    for c in claims:
        holds(c, asm_core.Claim, f"claim {c.get('topic')}")
    for o in got["origins"]:
        holds(o, asm_core.Origin, "origin")
    for e in got["plan"]:
        holds(e, asm_core.ClassPlanEntry, "class plan entry")
    for e in got["index"] + got["shared_index"]:
        holds(e, asm_core.IndexEntry, f"index entry {e.get('path')}")


def jobs_login() -> str:
    import pwd
    return pwd.getpwuid(os.geteuid()).pw_name


def main() -> int:
    fails = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as e:  # noqa: BLE001 — a case that raises is a failure, reported
            fails += 1
            print(f"  FAIL {name}: {e}")
            if not isinstance(e, Failed):
                traceback.print_exc()
    for d in SCRATCH:
        shutil.rmtree(d, ignore_errors=True)
    print(f"test_types: {'OK' if not fails else f'FAILED — {fails}'} ({len(CASES)} cases)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
