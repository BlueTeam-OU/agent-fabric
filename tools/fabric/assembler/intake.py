"""tools/fabric/assembler/intake.py — the arguments, the layout, and the drain's claims read, screened and bucketed.
A part of tools/fabric/assemble.py, whose docstring is the contract."""
from __future__ import annotations

import argparse
import json
import os
import sys
from assembler.core import layout, workingcopy, DEFAULT_SLICE_BUDGET_TOKENS, BANNED_PATTERNS, PROJECT_PATTERNS, patterns_for, slugify, origin_of_row, REDACTED, hygiene_check, hygiene_substitute, Run
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
                    help="agent-fabric root (default: this checkout, or $AGENT_FABRIC_ROOT)")
    ap.add_argument("--working-copy", default=None,
                    help="the project's checkout; its .agent-fabric/memory/ receives the "
                         "project-scoped classes (default: the agent's binding, or this checkout "
                         "for agent-fabric itself)")
    ap.add_argument("--stamp", required=True, help="distillation date (YYYY-MM-DD)")
    ap.add_argument("--budget", type=int, default=DEFAULT_SLICE_BUDGET_TOKENS)
    ap.add_argument("--collision-decisions", default=None, metavar="FILE",
                    help="the owner's decision per collision the previous run refused on: "
                         "{\"<role>/<class>:<topic>#<heading>\": \"supersede\"|\"keep-both\"|\"drop\"}")
    args = ap.parse_args()
    if args.bundle:
        if args.claims or args.drain:
            ap.error("--bundle replaces --claims and --drain")
        args.drain = open_bundle(args.bundle)
        args.claims = os.path.join(args.drain, "claims")
    elif not (args.claims and args.drain):
        ap.error("--claims and --drain, or --bundle")
    return args


def open_layout(args: argparse.Namespace) -> str:
    """The project, with the layout told where the fabric and every
    working copy are, and the hygiene lists of all of them loaded."""
    if args.fabric:
        layout.FABRIC_ROOT = os.path.abspath(args.fabric)
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
    try:
        listed = sorted(set(layout.project_ids()) | set(layout.explicit_working_copies()))
        BANNED_PATTERNS[:] = layout.load_hygiene_patterns(listed)
        PROJECT_PATTERNS[:] = layout.load_hygiene_patterns(listed, for_project=project)
    except layout.HygieneError as exc:
        sys.exit(f"assemble: {exc}")
    return project


def read_claims(run: Run) -> int | None:
    """The drain's references, origins and claims; 1 when a claim is out of its scope."""
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

    claim_files = sorted(
        f for f in os.listdir(run.args.claims) if f.endswith(".json") and not f.startswith(".")
    )
    scope_violations: list[str] = []
    for name in claim_files:
        with open(os.path.join(run.args.claims, name), encoding="utf-8") as fh:
            payload = json.load(fh)
        role = payload["role"]
        run.all_claims[role] = payload.get("claims", [])
        for claim in run.all_claims[role]:
            claim["_role"] = role   # for the section's dated tail; never written to disk
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
        for claim in run.all_claims[role]:
            if (claim.get("knowledge_scope") == "domain-only"
                    and claim.get("class") != "domain"):
                scope_violations.append(
                    f"{name}: {claim.get('title') or claim.get('topic')!r} is "
                    f"domain-only evidence filed as {claim.get('class')!r} — "
                    "sibling-project evidence may support only a domain claim"
                )

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
            where = f"{role}/{claim['class']}:{claim['topic']}"
            for field in ("title", "description", "body"):
                if isinstance(claim.get(field), str):
                    claim[field], notes = hygiene_substitute(claim[field], f"{where} {field}", patterns_for(claim["class"]))
                    run.redactions.extend(notes)
            if isinstance(claim.get("topic"), str):
                topic, notes = hygiene_substitute(claim["topic"], f"{where} topic", patterns_for(claim["class"]))
                if notes:
                    claim["topic"] = slugify(topic.replace(REDACTED, "redacted")) or "redacted"
                    run.redactions.extend(notes)
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
            if owners:
                owners.add(role)
                run.shared[key].append(claim)
                run.shared_owners[key] |= owners
            else:
                run.per_role[role][key].append(claim)


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
