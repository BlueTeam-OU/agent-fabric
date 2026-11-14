"""tools/fabric/assembler/intake.py — the arguments, the layout, and the drain's claims read, screened and bucketed.
A part of tools/fabric/assemble.py, whose docstring is the contract."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
import anchors
import memory_horizons
from assembler.core import layout, workingcopy, DEFAULT_SLICE_BUDGET_TOKENS, BANNED_PATTERNS, PROJECT_PATTERNS, patterns_for, store_error, slugify, origin_of_row, REDACTED, hygiene_check, hygiene_substitute, role_id_error, bound_role_ids, one_line, LINE_BREAK_RE, Run
from assembler.slices import cited_outside_code
from assembler.bundle import open_bundle


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Assemble knowledge slices from claims.")
    ap.add_argument("--claims", default=None, help="directory of <role>.json claim files")
    ap.add_argument("--drain", default=None, help="harvest output directory")
    ap.add_argument("--bundle", default=None, metavar="FILE|-",
                    help="a drain bundle (harvest_memory.py --bundle) in place of --claims/--drain; - reads stdin")
    ap.add_argument("--project", required=True,
                    help="logical project id the project-scoped classes are filed under")
    ap.add_argument("--fabric", default=None,
                    help="agent-fabric root (default: this checkout; an exported AGENT_FABRIC_ROOT or AGENT_FABRIC_OPERATOR naming another tree is refused)")
    ap.add_argument("--working-copy", action="append", default=[], metavar="[PROJECT=]DIR",
                    help="the project's checkout; its .agent-fabric/memory/ receives the "
                         "project-scoped classes (default: the agent's binding, or this checkout "
                         "for agent-fabric itself; <the --project's id>=DIR is the same). PROJECT=DIR, repeatable as lint takes it, tells the anchor guard "
                         "where another project's checkout is, so it judges an anchor there and not only in a "
                         "checkout beside the tree")
    ap.add_argument("--allow-missing-hygiene", action="store_true",
                    help="assemble although a registered project's working copy, and so its .agent-fabric/hygiene.json, "
                         "is not found; without it such a run is refused. The report names each project assembled "
                         "without its list")
    ap.add_argument("--stamp", required=True, help="distillation date (YYYY-MM-DD)")
    ap.add_argument("--budget", type=int, default=DEFAULT_SLICE_BUDGET_TOKENS)
    ap.add_argument("--hold", default=None, metavar="FILE",
                    help="slices held back from this drain: a JSON list of \"<role>/<class>:<topic>\" "
                         "(\"shared/<class>:<topic>\" for a shared one); their claims are not written, the "
                         "report lists them as held_back and drops what an earlier run of the stamp said of them")
    ap.add_argument("--collision-decisions", default=None, metavar="FILE",
                    help="the owner's decision per collision the previous run refused on: "
                         "{\"<role>/<class>:<topic>#<heading>\": \"supersede\"|\"keep-both\"|\"drop\"}")
    ap.add_argument("--reads-state", default=None, metavar="FILE",
                    help="where the drain keeps when each section was last read (ADR-050 rule 8); "
                         "default: memory-drain-reads.json in this login's agent state directory")
    ap.add_argument("--commit-message", default=None, metavar="FILE",
                    help="write the commit body for this project's drain to FILE, built only from the drain report "
                         "(not written when the run fails); commit with -F")
    ap.add_argument("--flags", action="store_true",
                    help="after the drain, route the sections a check or a reader flagged to the agents that own them "
                         "(ADR-050 rules 3 and 6; tools/fabric/memory_flagrun.py): a dry run that prints the plan")
    ap.add_argument("--send", action="store_true", help="with --flags: send the REQUESTs, and ask the model for hints")
    args = ap.parse_args()
    if args.send and not args.flags:
        ap.error("--send goes with --flags")
    given, args.working_copy, args.checkouts = args.working_copy, None, {}
    for wc in given:
        project, sep, path = wc.partition("=")
        if not sep:
            project, path = args.project, wc
        elif not project or not os.path.isdir(path):
            ap.error(f"--working-copy {wc!r}: {'no project named' if not project else path + ' is no directory'}")
        if project == args.project:
            # lint's own-project form: the corpus is written there, so it is the bare flag. Not put in the map: for a
            # project corpus memory_check has no own project, so a `<project>:` anchor of it is judged beside the tree by
            # its id, map or not (as with the bare flag). Two different checkouts cannot both receive the corpus.
            if args.working_copy and os.path.abspath(args.working_copy) != os.path.abspath(path):
                ap.error(f"--working-copy {wc!r}: the checkout of --project {project} is already {args.working_copy!r}")
            args.working_copy = path
        else:
            args.checkouts[project] = os.path.abspath(path)
    if memory_horizons.day(args.stamp) is None:
        ap.error(f"--stamp {args.stamp!r} is no YYYY-MM-DD date")       # before anything is written: the horizons need it
    if args.bundle:
        if args.claims or args.drain:
            ap.error("--bundle replaces --claims and --drain")
        args.drain = open_bundle(args.bundle)
        args.claims = os.path.join(args.drain, "claims")
    elif not (args.claims and args.drain):
        ap.error("--claims and --drain, or --bundle")
    return args


def refuse_foreign_root() -> None:
    """Without --fabric the drain's tree is the checkout this assemble.py is in. An exported AGENT_FABRIC_ROOT or
    AGENT_FABRIC_OPERATOR naming another tree (a source account's checkout, in the 2026-10-31 incident: only the
    domain slices went there, the project ones followed --working-copy) would take the domain and shared slices
    to it unasked, so the run stops before it writes. --fabric is how a run names a tree on purpose."""
    here = os.path.realpath(layout.roots.code_root())
    for name, value in (("AGENT_FABRIC_ROOT", layout.FABRIC_ROOT), ("AGENT_FABRIC_OPERATOR", os.environ.get(layout.roots.ENV_OPERATOR))):
        if value and os.path.realpath(value) != here:
            sys.exit(f"assemble: {name} names {value}, not the checkout this assemble.py is in ({here}); "
                     f"the drain would write its domain and shared slices there. Unset it, or pass --fabric {value} "
                     "to write there on purpose")


def open_layout(args: argparse.Namespace) -> str:
    """The project, with the layout told where the fabric and every
    working copy are, and the hygiene lists of all of them loaded."""
    if args.fabric:
        layout.FABRIC_ROOT = os.path.abspath(args.fabric)
        # roots.operator_root() lets an exported AGENT_FABRIC_OPERATOR outrank the engine tree a caller was
        # handed, so a run that named its tree wrote the domain and shared slices into the operator's instead
        # (found 2026-11-02, j88). --fabric is the one tree this run reads and writes; the flag phase's
        # children (fabric-ctl, gzcoord-send) inherit it, so they read the fleet from --fabric too.
        os.environ[layout.roots.ENV_OPERATOR] = layout.FABRIC_ROOT
    else:
        refuse_foreign_root()
    project = args.project
    if args.working_copy:
        layout.set_working_copy(project, args.working_copy)
    try:
        layout.project_memory_root(project)
    except LookupError as exc:
        sys.exit(f"assemble: {exc}")
    # Every project's list, not the target's alone: a slice travels into
    # every repository through the fabric's domains, and lint holds it to
    # every list — a name one project keeps out (a city, a deployment) is
    # out of the corpus everywhere (found 2026-09-18: a slice admitted here
    # carried a city name another project bans). The working copies
    # beside the fabric are found the way lint finds them, so each list is
    # actually read, not skipped for want of a known checkout.
    for pid, path in workingcopy.sibling_working_copies(layout.FABRIC_ROOT).items():
        if pid not in layout.explicit_working_copies():
            layout.set_working_copy(pid, path)
    listed = sorted(set(layout.project_ids()) | set(layout.explicit_working_copies()))
    # A list that cannot be found withholds nothing, and the drain would go on as if it did: banned names reached
    # project corpora that way. The fabric's own project always has one: its working copy is the root.
    args.without_hygiene = [pid for pid in listed if not layout.working_copy_for(pid)]
    if args.without_hygiene and not args.allow_missing_hygiene:
        looked = (f"beside {os.path.dirname(layout.FABRIC_ROOT)} (a checkout of the project with .agent-fabric/memory/), "
                  "in $AGENT_FABRIC_WORKING_COPY and in this agent's binding")
        # PROJECT=DIR is the anchor guard's alone (args.checkouts); naming it here keeps the operator from trying it.
        guard_only = [pid for pid in args.without_hygiene if pid in args.checkouts]
        sys.exit("assemble: no hygiene list can be found for " + ", ".join(args.without_hygiene)
                 + f"; looked {looked}, and no working copy is known. Put the project's checkout beside the fabric, or pass "
                 "--allow-missing-hygiene to assemble without those lists"
                 + (f" (--working-copy PROJECT=DIR is read by the anchor guard only: {', '.join(guard_only)})" if guard_only else ""))
    args.hygiene_listed = listed
    load_hygiene(args, project)
    return project


def load_hygiene(args: argparse.Namespace, project: str) -> None:
    """The banned lists as `project` sees them: a name a project lists as its own is allowed in its own slices and out of every
    other's, so a claim re-homed to another project is screened by that project's view, not the one it was read under."""
    try:
        BANNED_PATTERNS[:] = layout.load_hygiene_patterns(args.hygiene_listed)
        PROJECT_PATTERNS[:] = layout.load_hygiene_patterns(args.hygiene_listed, for_project=project)
    except layout.HygieneError as exc:
        sys.exit(f"assemble: {exc}")


def screened(text: str) -> str:
    return hygiene_substitute(text, "", BANNED_PATTERNS)[0]


def shown(value: Any) -> str:
    """A distiller's text as a refusal may print it: held to every pattern, then repr'd. In that order: repr escapes a quote,
    a tab or a backslash, and a pattern screened against the escaped text misses what the raw text holds. A value that is
    no string is named by its type unless it is a scalar, since a list or dict has no text a pattern is told of. These messages go to the
    operator's terminal and any log of the run before screen_hygiene has judged the claim, so a banned name in a title,
    topic, anchor, class, role id or file name must not reach them. BANNED_PATTERNS, not the class's set: a name
    another project keeps out is out of every stream, and a refusal has no slice it is about to be written to."""
    if isinstance(value, str):
        return repr(screened(value))
    return repr(value) if value is None or isinstance(value, (bool, int, float)) else f"<{type(value).__name__}>"


def shown_why(value: Any, why: str) -> str:
    """role_id_error's text echoes the value; the echo is screened, the rule it names is not."""
    return why.replace(repr(value), shown(value), 1)


def read_claims(run: Run) -> int | None:
    """The drain's references, origins and claims; 1 when a claim is out of its scope."""
    # The harvest's record is judged before anything is written: the store
    # it names becomes a committed watermark (core.store_error).
    harvest_report = os.path.join(run.args.drain, "harvest-report.json")
    if os.path.exists(harvest_report):
        try:
            with open(harvest_report, encoding="utf-8") as fh:
                hr = json.load(fh)
        except (OSError, ValueError) as exc:
            sys.exit(f"assemble: {harvest_report}: cannot be read ({exc})")
        why = store_error(hr) if isinstance(hr, dict) else "harvest-report.json is not an object"
        if why:
            sys.exit(f"assemble: {why}")
    with open(os.path.join(run.args.drain, "references.json"), encoding="utf-8") as fh:
        run.references = json.load(fh)
    obs_path = os.path.join(run.args.drain, "observations.final.jsonl")
    if not os.path.exists(obs_path):
        obs_path = os.path.join(run.args.drain, "observations.jsonl")
    with open(obs_path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                run.origins[row["content_hash"]] = origin_of_row(row)
                run.evidence_epoch[row["content_hash"]] = row.get("created_at_epoch")

    claim_files = sorted(
        f for f in os.listdir(run.args.claims) if f.endswith(".json") and not f.startswith(".")
    )
    scope_violations: list[str] = []
    anchor_violations: list[str] = []
    for name in claim_files:
        with open(os.path.join(run.args.claims, name), encoding="utf-8") as fh:
            payload = json.load(fh)
        role = payload.get("role") if isinstance(payload, dict) else None
        why = role_id_error(role)
        if why:
            sys.exit(f"assemble: {shown(name)}: the claims file's role {shown_why(role, why)}")
        run.all_claims[role] = payload.get("claims", [])
        for claim in run.all_claims[role]:
            claim["_role"] = role   # for the section's dated tail; never written to disk
            if isinstance(claim.get("title"), str):
                lined = one_line(claim["title"])
                if lined != claim["title"]:
                    claim["_title_before_one_line"] = claim["title"]   # told by bucket_claims, once hygiene has judged the claim
                claim["title"] = lined
            cites = claim.get("citations")
            if isinstance(cites, dict) and isinstance(cites.get("memories"), list) and isinstance(claim.get("body"), str):
                kept = cited_outside_code(claim["body"], cites["memories"])
                if kept != cites["memories"]:
                    claim["citations"] = {**cites, **({"memories": kept} if kept else {})}
                    if not kept:
                        del claim["citations"]["memories"]
            # A co-owner is a role id too: it gets a project directory and
            # an index (writer.write_shared, assemble.py's owning roles).
            for owner in claim.get("shared_with") or []:
                why = role_id_error(owner)
                if why:
                    sys.exit(f"assemble: {shown(name)}: a claim's shared_with names {shown_why(owner, why)}")
        run.telemetry[role] = payload.get("telemetry", {})

        # DOMAIN-ONLY EVIDENCE MAY SUPPORT ONLY A DOMAIN CLAIM.
        #
        # Evidence carried over from a sibling project is transferable
        # knowledge about a FIELD, not a statement about this repository.
        # Filed as `solution` it becomes an as-of-dated claim about what this
        # system implements; as `workflow` or `rationale` it becomes a claim
        # about how this team works. Both are false in the same way, and the
        # in-body disclaimer the assembler adds is prose a reader may skim,
        # not a boundary.
        #
        # Checked here in code, not left to the schema alone: this is the
        # only consumer of a claims file, and lint's fallback validator
        # cannot evaluate a conditional when jsonschema is absent.
        for index, claim in enumerate(run.all_claims[role]):
            if (claim.get("knowledge_scope") == "domain-only"
                    and claim.get("class") != "domain"):
                scope_violations.append(
                    f"{shown(name)}: claim {index} {shown(claim.get('title') or claim.get('topic'))} is "
                    f"domain-only evidence filed as {shown(claim.get('class'))} — "
                    "sibling-project evidence may support only a domain claim"
                )

    # ADR-050 rule 1: a claim's anchors come from a distiller's file, which is untrusted, and are rendered into a
    # slice as a line a later reader trusts and opens files by. They are refused here, before anything is written:
    # only a solution or workflow claim has them, as a list of strings that are anchors (anchors.problem).
    for role, claims in run.all_claims.items():
        for index, claim in enumerate(claims):
            if "anchors" not in claim:
                continue
            listed = claim["anchors"]
            who = f"{shown(role)}: claim {index} {shown(claim.get('title') or claim.get('topic'))}"
            if not (isinstance(listed, list) and all(isinstance(a, str) for a in listed)):
                anchor_violations.append(f"{who}: anchors is not a list of strings")
            elif claim.get("class") not in anchors.ANCHOR_CLASSES:
                anchor_violations.append(f"{who}: anchors on a {shown(claim.get('class'))} claim; only {sorted(anchors.ANCHOR_CLASSES)} have them")
            elif len(listed) > anchors.ANCHORS_MAX:
                anchor_violations.append(f"{who}: {len(listed)} anchors, at most {anchors.ANCHORS_MAX}")
            else:
                known_projects = frozenset(layout.project_ids())
                for a in listed:
                    bad = anchors.problem(a) or anchors.registry_problem(a, known_projects)
                    if bad:
                        anchor_violations.append(f"{who}: anchor {shown(screened(a)[:60])}: {screened(bad)}")
    if anchor_violations:
        print("CLAIM ANCHOR VIOLATIONS:", file=sys.stderr)
        for problem in anchor_violations:
            print(f"  {problem}", file=sys.stderr)
        return 1

    # Refuse BEFORE writing anything. A scope violation is an input defect,
    # so assembling and reporting afterwards would leave a tree that has to
    # be reverted rather than simply re-run.
    if scope_violations:
        print("CLAIM SCOPE VIOLATIONS:", file=sys.stderr)
        for problem in scope_violations:
            print(f"  {problem}", file=sys.stderr)
        return 1


def screen_hygiene(run: Run) -> None:
    # A claim whose body fails the hygiene check (RUBRIC.md: deployment
    # specifics, secrets, session-local detail) is REJECTED here, before any
    # bucket, and named in the report. Writing it and warning afterwards put
    # the text in the tree first and asked for a fix second — and lint then
    # failed the drain's branch on exactly that text. The author fixes the
    # memory; the corpus never receives the claim.
    # Banned text is SUBSTITUTED in every text field of the claim — title,
    # description, body, and the topic that names the file — and each
    # substitution is reported; only non-English prose is still refused.
    for role, claims in list(run.all_claims.items()):
        kept = []
        for claim in claims:
            # The topic first: every note below names the claim by it, and a
            # note must never carry what it says was withheld.
            # A note names the slice its claim lands in: a claim another role
            # shares lands in shared/, so --hold matches the one it held.
            label = "shared" if set(claim.get("shared_with") or []) - {role} else role
            if isinstance(claim.get("topic"), str):
                topic, notes = hygiene_substitute(claim["topic"], "", patterns_for(claim["class"]))
                if notes:
                    claim["topic"] = slugify(topic.replace(REDACTED, "redacted")) or "redacted"
                    run.redactions.extend(f"{label}/{claim['class']}:{claim['topic']} topic{n}" for n in notes)
            where = f"{label}/{claim['class']}:{claim['topic']}"
            for field in ("title", "description", "body"):
                if isinstance(claim.get(field), str):
                    claim[field], notes = hygiene_substitute(claim[field], f"{where} {field}", patterns_for(claim["class"]))
                    run.redactions.extend(notes)
            # An anchor the hygiene lists would change is dropped, not rewritten: a rewritten one names no file.
            if claim.get("anchors"):
                kept_anchors = []
                for anchor in claim["anchors"]:
                    _text, notes = hygiene_substitute(anchor, f"{where} anchor", patterns_for(claim["class"]))
                    if notes:
                        run.redactions.extend(f"{n} (the anchor was dropped)" for n in notes)
                    else:
                        kept_anchors.append(anchor)
                claim["anchors"] = kept_anchors
                if not kept_anchors:
                    del claim["anchors"]
            issues = hygiene_check(claim.get("body") or "", where, patterns_for(claim["class"]))
            if issues:
                run.rejected_hygiene.extend(issues)
                run.telemetry.setdefault(role, {}).setdefault("rejected_hygiene", 0)
                run.telemetry[role]["rejected_hygiene"] += 1
            else:
                kept.append(claim)
        run.all_claims[role] = kept


def bucket_claims(run: Run) -> None:
    """A claim owned by several roles lives once, in shared/, and every owner's
    index points at it. Copies would drift."""
    for role, claims in run.all_claims.items():
        for claim in claims:
            key = (claim["class"], claim["topic"])
            owners = set(claim.get("shared_with") or [])
            owners.discard(role)
            before = claim.pop("_title_before_one_line", None)
            if before is not None:
                # After screen_hygiene: a claim it rejected is told of nowhere. Named as the claim is filed, so holding that slice
                # drops the entry. The old title is not copied: the report is committed, and a pattern that needs the space
                # one_line made (a lookbehind such as "gh repo clone ") does not match across the break, so the old text could
                # carry what hygiene replaced in the new one. The breaks are counted; the title shown is the one hygiene screened.
                breaks = len(LINE_BREAK_RE.findall(before))
                run.titles_one_lined.append({"slice": f"{'shared' if owners else role}/{claim['class']}:{claim['topic']}",
                                             "breaks": breaks, "title": claim["title"]})
            if owners:
                owners.add(role)
                run.shared[key].append(claim)
                run.shared_owners[key] |= owners
            else:
                run.per_role[role][key].append(claim)


def hold_back(run: Run) -> None:
    """--hold: the claims of each held slice leave the drain before anything
    is planned, so nothing of them is written, decided or clipped. A key
    that names no slice of this drain is refused: a typo would otherwise
    let the slice through, held by nobody."""
    if not run.args.hold:
        return
    try:
        with open(run.args.hold, encoding="utf-8") as fh:
            keys = json.load(fh)
    except OSError as exc:
        sys.exit(f"assemble: --hold: {run.args.hold} cannot be read ({exc.strerror or exc})")
    except ValueError as exc:
        sys.exit(f"assemble: --hold: {run.args.hold} does not parse ({exc})")
    if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
        sys.exit("assemble: --hold: a JSON list of \"<role>/<class>:<topic>\" keys")
    unmatched = []
    for key in keys:
        label, _, rest = key.partition("/")
        klass, _, topic = rest.partition(":")
        if label == "shared" and (klass, topic) in run.shared:
            run.held_evidence.update(h for c in run.shared[(klass, topic)] for h in c.get("evidence") or [])
            del run.shared[(klass, topic)]
            run.shared_owners.pop((klass, topic), None)
        elif label != "shared" and (klass, topic) in run.per_role.get(label, {}):
            run.held_evidence.update(h for c in run.per_role[label][(klass, topic)] for h in c.get("evidence") or [])
            del run.per_role[label][(klass, topic)]
        else:
            unmatched.append(key)
            continue
        run.held_back.append(key)
    if unmatched:
        sys.exit(f"assemble: --hold names no slice of this drain: {', '.join(unmatched)}")


# The one role whose remit is the control plane wherever it learned a lesson (the owner, 2026-11-11): its claim of a project that
# does not bind it is the control plane's knowledge, and goes to agent-fabric's own corpus.
REHOME_ROLE = "fabric-coordinator"


def rehome_unbound(run: Run) -> list[dict[str, Any]]:
    """A project-scoped claim whose role the project's taxonomy does not bind is not admitted to that project's corpus (drain of
    2026-11-08: a bundle wrote fabric-coordinator claims into a project that binds three other roles). fabric-coordinator's
    claim is taken out of this run and returned, for agent-fabric's own corpus (assemble.main writes it there); a claim of any
    other role refuses the run, naming the claim, its role and the project, before anything is written: there is no
    fallback, because a role's knowledge written under another role's remit is wrong in a way no later run notices.

    Judged per claim, by its owners: its author and everyone it is shared with. A claim some bound role co-owns is that role's
    knowledge too and stays (note_unbound_owners). Not judged: a project with no taxonomy (nothing says which roles it binds),
    the fabric's own project (its taxonomy binds the roles that own the control plane's paths, while its project memory is every
    role's), and domain claims, which live in the fabric and belong to no project's roles."""
    bound = bound_role_ids(run.project)
    if bound is None or run.project == layout.FABRIC_PROJECT_ID:
        return []
    moved: dict[str, list[dict[str, Any]]] = {}
    refused: list[str] = []
    for role in sorted(run.all_claims):
        kept = []
        for claim in run.all_claims[role]:
            owners = {role} | set(claim.get("shared_with") or [])
            if claim.get("class") not in layout.PROJECT_CLASSES or owners & bound:
                kept.append(claim)
            elif owners == {REHOME_ROLE}:
                moved.setdefault(role, []).append(claim)
            else:
                # Screened as screen_hygiene would, which has not run: this line goes to stderr, and the topic and title are text
                # the hygiene lists may ban (nothing is committed from it, but a log is read and kept too).
                topic, title = (hygiene_substitute(v, "", patterns_for(claim["class"]))[0] if isinstance(v, str) else v
                                for v in (claim.get("topic"), claim.get("title")))
                refused.append(f"{shown(claim['class'])[1:-1]}:{topic} ({title!r}) of role {shown(role)[1:-1]}"
                               + (f" shared with {', '.join(shown(o)[1:-1] for o in sorted(owners - {role}))}" if len(owners) > 1 else "")
                               + f", project {run.project}")
        run.all_claims[role] = kept
    if refused:
        sys.exit(f"assemble: not admitted: the project's taxonomy binds {', '.join(sorted(bound)) or 'no role'} and no owner of these "
                 f"claims; only {REHOME_ROLE}'s claim is re-homed (to {layout.FABRIC_PROJECT_ID}), any other refuses the run. "
                 "Bind the role in the project's taxonomy, or file the memory where its role's remit is:\n  " + "\n  ".join(refused))
    for role in moved:
        if not run.all_claims[role]:
            # A role with no claim left owns nothing here: not a project directory, index or crossref (assemble.main owning_roles).
            del run.all_claims[role]
    return [c for claims in moved.values() for c in claims]


def rehomed_row(run: Run, claim: dict[str, Any]) -> dict[str, Any]:
    """The report's record of a claim re-homed to the control plane. Built from the claim as the control plane's pass left it, never
    from the one read: that pass screens the topic and the title, and a row from before it would carry to the report, the commit
    body and stderr what hygiene withheld from the corpus. `claim` is one of that pass's own, so a claim it rejected has no row."""
    origins = (run.origins.get(h) for h in claim.get("evidence") or [])
    role = claim["_role"]
    return {"slice": f"{role}/{claim['class']}:{claim['topic']}", "role": role, "class": claim["class"], "topic": claim["topic"],
            "title": claim.get("title"), "from_project": run.project, "to_project": layout.FABRIC_PROJECT_ID,
            "source": sorted({f"{o.get('agent') or o.get('clone_id')}@{o.get('host')}" for o in origins if o})}


def note_unbound_owners(run: Run) -> None:
    """A shared slice some bound role co-owns is written with every owner in its shared_with (a corpus fact, not a binding
    question; drain of 2026-11-08: a slice shared by an unbound and a bound role). Only the unbound owners are left out of the
    indexes, and an unbound author gets no project directory of its own. A slice with no bound owner never reaches here
    (rehome_unbound judged its claims)."""
    bound = bound_role_ids(run.project)
    if bound is None or run.project == layout.FABRIC_PROJECT_ID:
        return
    for (klass, topic) in sorted(k for k in run.shared if k[0] in layout.PROJECT_CLASSES):
        unbound = sorted(run.shared_owners[(klass, topic)] - bound)
        if unbound:
            run.unbound_held_roles.update(c["_role"] for c in run.shared[(klass, topic)] if c.get("_role") in unbound)
            run.unindexed_owners.update(unbound)


def load_decisions(run: Run) -> None:
    # A CLAIM THAT DISAGREES WITH THE CORPUS STOPS THE DRAIN (the owner,
    # 2026-09-20). A new claim under a heading the slice already has, with
    # different text, is a potential supersession — a workflow that
    # changed, or a memory that is wrong — and the assembler cannot tell
    # which: it used to write both as "X" and "X (2)" and report a
    # collision nobody read. Now nothing is written and the run exits 1
    # naming each pair, both texts, both dates; the owner decides, and
    # the re-run carries the decisions: supersede (the new text replaces
    # the section and retires its siblings — merge_target, the author's
    # instrument, applied by the coordinator on the owner's word),
    # keep-both (the old shape), or drop (the new claim is wrong). Two
    # claims of one drain under one heading collide the same way. Every
    # applied decision is recorded in the drain report.
    if run.args.collision_decisions:
        with open(run.args.collision_decisions, encoding="utf-8") as fh:
            run.decisions = json.load(fh)
        bad = {k: v for k, v in run.decisions.items() if v not in ("supersede", "keep-both", "drop")}
        if bad:
            sys.exit(f"assemble: --collision-decisions: a decision is supersede, keep-both or drop; got {bad}")
