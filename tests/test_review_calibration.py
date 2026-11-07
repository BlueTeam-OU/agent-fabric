#!/usr/bin/env python3
"""Tests for tools/fabric/review_calibration.py (ADR-066): each rate against a hand-computed value (gavel's README
table among them), the four behaviours that differ from gavel, the ledger's chain, the floor, the blind view and the
real entry points. No network: gh is a planted function; every file is under a private temporary directory."""
from __future__ import annotations

import contextlib
import fractions
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import review_calibration as rc  # noqa: E402

TOOL = os.path.join(ROOT, "tools", "fabric", "review_calibration.py")
SHIM = os.path.join(ROOT, "bin", "fabric-review-calibration")
INSTRUCTIONS_TEXT = "Judge each finding by its hunk. Nothing about any labelled finding is quoted here.\n"
CONF = {"engine": "code-review", "model": "m-1", "effort": "high",
        "config": hashlib.sha256(INSTRUCTIONS_TEXT.encode()).hexdigest()}
BASE, HEAD = "b" * 40, "c" * 40


def coords_in(half: str, count: int, repo: str = "o/r", start: int = 1) -> list[rc.Coordinates]:
    out, n = [], start
    while len(out) < count:
        c = rc.Coordinates(repo, 7, 1000 + n, f"F{n}")
        if c.half() == half:
            out.append(c)
        n += 1
    return out


def write_ledger(path: str, labels: list[tuple[rc.Coordinates, str]]) -> None:
    for c, verdict in labels:
        rc.append_label(path, c, verdict, "owner", "2026-11-07")


def run_main(argv, **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err):
        try:
            rc_ = rc.main(argv, out=out, **kw)
        except SystemExit as e:      # argparse's usage error
            rc_ = e.code
    return rc_, out.getvalue(), err.getvalue()


def fake_gh(directory: str) -> str:
    """A `gh` that answers a review read with one v2 review holding F1..F3000, the only call a report makes."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "gh")
    with open(path, "w") as f:
        f.write(f"""#!{sys.executable}
import json, sys
rid = int(sys.argv[2].rsplit("/", 1)[1])
head = "<!-- agent-fabric-review v2 base={BASE} head={HEAD} card={'d' * 40} config={'e' * 64} -->"
lines = [f"Finding: F{{n}} | P3 | likely | a.py:1 | summary {{n}}" for n in range(1, 3001)]
print(json.dumps({{"id": rid, "body": "\\n".join([head] + lines)}}))
""")
    os.chmod(path, 0o755)
    return directory


def child(argv: list[str], home: str) -> subprocess.CompletedProcess:
    env = {"PATH": fake_gh(os.path.join(home, "fake-bin")) + ":/usr/bin:/bin", "HOME": home, "LC_ALL": "C.UTF-8",
           "TMPDIR": home, "GH_TOKEN": "x"}
    return subprocess.run([sys.executable, *argv], env=env, capture_output=True, text=True, timeout=120, check=False)


def main() -> int:
    fails = 0

    def check(label, good, detail=""):
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    def near(a, b, tol=5e-4):
        return a is not None and abs(a - b) <= tol

    holder = tempfile.TemporaryDirectory(prefix="rc-")
    tmp = holder.name
    instructions = os.path.join(tmp, "code-review.md")
    with open(instructions, "w") as f:
        f.write(INSTRUCTIONS_TEXT)
    real_fetch = rc.fetch_summary
    rc.fetch_summary = lambda c: f"summary of {c.finding} in review {c.review}"
    real_levels = rc.Levels
    known_levels: dict = {}

    class FakeLevels:
        unreadable: set = set()
        asked: list = []

        def __call__(self, coords):
            self.asked.append(coords)
            return known_levels.get(coords)
    rc.Levels = FakeLevels

    # --- the rates, by hand: 17 of 20 real found, 15 of 20 not-real found
    m = rc.Confusion(tp=17, fn=3, tn=15, fp=5)
    check("TPR 17/20 = 0.85, TNR 15/20 = 0.75", near(m.tpr(), 0.85) and near(m.tnr(), 0.75), (m.tpr(), m.tnr()))
    check("precision 17/22", near(m.precision(), 17 / 22), m.precision())
    check("Youden J = 0.85 + 0.75 - 1 = 0.6", near(m.youden_j(), 0.6), m.youden_j())
    check("kappa: po 0.8, pe 0.5 -> 0.6", near(m.kappa(), 0.6), m.kappa())
    check("MCC 240 / sqrt(22*20*20*18)", near(m.mcc(), 240 / math.sqrt(22 * 20 * 20 * 18)), m.mcc())
    lo, hi = rc.wilson(40, 50)
    check("Wilson 40/50 -> [0.670, 0.888]", near(lo, 0.670, 6e-4) and near(hi, 0.888, 6e-4), (lo, hi))
    check("the matrix's own Wilson intervals are the function's", m.tpr_wilson() == rc.wilson(17, 20)
          and m.tnr_wilson() == rc.wilson(15, 20))

    # --- gavel's README table: TPR 0.85, TNR 0.75, true 0.20 -> observed 0.37 -> corrected 0.20
    observed = 0.20 * 0.85 + 0.80 * (1 - 0.75)
    rg = rc.rogan_gladen(observed, 0.85, 0.75)
    check("observed 0.37 from true 0.20, corrected back to 0.20", near(observed, 0.37) and near(rg.corrected, 0.20)
          and near(rg.raw, 0.20), (observed, rg))
    check("a judge with J <= 0.001 cannot be inverted", rc.rogan_gladen(0.5, 0.5, 0.5) is None
          and rc.rogan_gladen(0.5, 0.6, 0.401) is None)
    raw = rc.rogan_gladen(0.99, 0.85, 0.75)
    check("the raw value is kept beside the clamped one", raw.raw > 1.0 and raw.corrected == 1.0, raw)
    check("SplitMix64 seed 0 starts as the reference generator", rc.SplitMix64(0).next_u64() == 0xE220A8397B1DCDAF)

    # --- McNemar exact and TOST
    check("McNemar 15 vs 12 -> p 0.701", near(rc.mcnemar_exact(15, 12), 0.701, 6e-4), rc.mcnemar_exact(15, 12))
    check("McNemar 6 vs 0 -> p 0.031", near(rc.mcnemar_exact(6, 0), 0.03125, 1e-9), rc.mcnemar_exact(6, 0))
    check("McNemar with no discordant pair is p 1 (formula), symmetric in b and c",
          rc.mcnemar_exact(0, 0) == 1.0 and rc.mcnemar_exact(3, 9) == rc.mcnemar_exact(9, 3))
    # b = c = 10 of 100 pairs, margin 5 points: theta bounds 0.375 / 0.625 on n = 20
    th = fractions.Fraction(5, 8)
    want = float(sum(math.comb(20, i) * th ** i * (1 - th) ** (20 - i) for i in range(11)))
    got = rc.tost_paired(10, 10, 100)
    check("TOST 10 vs 10 of 100: the one-sided tail at the bound, and not equivalent (> 0.05)",
          near(got, want, 1e-9) and got > 0.05, (got, want))
    asym = rc.tost_paired(2, 18, 100)
    mirror = rc.tost_paired(18, 2, 100)
    want_asym = float(sum(math.comb(20, i) * fractions.Fraction(3, 8) ** i * fractions.Fraction(5, 8) ** (20 - i)
                          for i in range(2, 21)))
    check("TOST 2 vs 18 of 100: the lower bound's tail decides (~1), the same mirrored",
          near(asym, want_asym, 1e-9) and asym > 0.99 and near(mirror, asym, 1e-9), (asym, mirror, want_asym))
    check("TOST where every possible difference is inside the margin is 0", rc.tost_paired(1, 1, 100) == 0.0)
    check("TOST with no discordant pair or no pair is undefined, not 0 or 1",
          rc.tost_paired(0, 0, 100) is None and rc.tost_paired(0, 0, 0) is None)

    # --- changed behaviour 1: a rate with no denominator is None (gavel answers 0.0, 0.0, 0.0, 1.0/0.0, (0, 1))
    none_pos = rc.Confusion(tn=5, fp=2)
    check("no real label: TPR is None, not 0.0", none_pos.tpr() is None and none_pos.youden_j() is None)
    none_neg = rc.Confusion(tp=5, fn=2)
    check("no not-real label: TNR is None, not 0.0", none_neg.tnr() is None and none_neg.youden_j() is None)
    check("no positive verdict: precision is None", rc.Confusion(tn=3, fn=2).precision() is None)
    empty = rc.Confusion()
    check("an empty matrix has no kappa, MCC, rates or interval", empty.kappa() is None and empty.mcc() is None
          and empty.tpr() is None and empty.tpr_wilson() is None and rc.wilson(0, 0) is None)
    check("kappa is undefined, not 1.0, when both only ever say real", rc.Confusion(tp=5).kappa() is None)

    # --- changed behaviour 2: discarded draws are counted and the raw value is beside the clamped one
    weak = rc.Confusion(tp=11, fn=9, tn=23, fp=27)             # TPR 0.55, TNR 0.46: J 0.01, inverts but barely
    d = rc.debias(weak, 25, 50, 400, 1)
    check("a weak judge discards bootstrap draws, and the report counts them", d.discarded > 0 and d.draws == 400
          and 0 < d.discarded < 400, (d.discarded, d.draws))
    check("the raw Rogan-Gladen value is beside the clamped one: raw -4.0 -> corrected 0.0",
          d.raw == rc.rogan_gladen(25 / 50, 11 / 20, 23 / 50).raw and d.raw < 0.0 and d.corrected == 0.0, d)
    check("the same seed reproduces the draws", rc.debias(weak, 25, 50, 400, 1) == d
          and rc.debias(weak, 25, 50, 400, 2) != d)
    exact = rc.debias(rc.Confusion(tp=10, tn=10), 0, 20, 50, 3)
    check("a perfect judge and no passes: corrected 0, interval (0, 0), nothing discarded",
          exact.corrected == 0.0 and exact.interval == (0.0, 0.0) and exact.discarded == 0, exact)
    saved = rc.rogan_gladen
    calls = []

    def first_only(p, a, b):
        calls.append(1)
        return saved(p, a, b) if len(calls) == 1 else None
    rc.rogan_gladen = first_only
    try:
        every = rc.debias(rc.Confusion(tp=17, fn=3, tn=15, fp=5), 10, 50, 30, 1)
    finally:
        rc.rogan_gladen = saved
    check("with every draw discarded the interval is None, not the point value twice",
          every.interval is None and every.discarded == 30, every)
    for bad, why in ((rc.Confusion(tn=5, fp=1), "no real"), (rc.Confusion(tp=5, fn=1), "no not-real")):
        try:
            rc.debias(bad, 1, 4, 10, 1)
            raised = False
        except rc.Undefined:
            raised = True
        check(f"a matrix with {why} labels has no corrected value", raised)

    # --- changed behaviour 3: the ledger fails closed
    ledger = os.path.join(tmp, "docs", "labels.jsonl")
    cs = coords_in("held-out", 3)
    write_ledger(ledger, [(cs[0], "real"), (cs[1], "not-real"), (cs[2], "unsure")])
    good = open(ledger).read().splitlines()
    check("three labels chain from genesis and carry no finding text",
          [r["prev"] for r in rc.read_ledger(ledger)][0] == "genesis" and len(good) == 3
          and all(set(json.loads(x)) == set(rc.LEDGER_KEYS) for x in good))

    def refused(lines, text=None):
        path = os.path.join(tmp, "case.jsonl")
        with open(path, "w") as f:
            f.write(text if text is not None else "".join(x + "\n" for x in lines))
        try:
            rc.read_ledger(path)
        except rc.Refused as e:
            return str(e)
        return None

    def edit(i, **changes):
        rec = json.loads(good[i])
        rec.update(changes)
        return json.dumps(rec)
    stripped = json.loads(good[1])
    del stripped["hash"]
    blank = dict(json.loads(good[1]), hash="")
    check("a stripped hash is refused, naming the line", "line 2" in (refused([good[0], json.dumps(stripped), good[2]]) or ""))
    check("an empty hash is refused (gavel passes it)", "line 2" in (refused([good[0], json.dumps(blank), good[2]]) or ""))
    gavel = json.loads(good[1])
    gavel["prev"] = gavel["hash"] = ""
    check("both chain fields emptied on a line (gavel's accepted shape) is refused",
          "line 2" in (refused([good[0], json.dumps(gavel), good[2]]) or ""))
    check("an empty prev is refused", "line 2" in (refused([good[0], edit(1, prev=""), good[2]]) or ""))
    check("a changed verdict is refused", "hash does not match" in (refused([good[0], edit(1, verdict="real"), good[2]]) or ""))
    check("a line dropped from the middle breaks the chain", "line 2" in (refused([good[0], good[2]]) or "")
          and "broken chain" in (refused([good[0], good[2]]) or ""))
    check("a line with finding text is refused", "keys" in (refused([good[0], edit(1, text="the bug")]) or ""))
    check("a blank line is refused, not skipped", "line 2" in (refused([good[0], "", good[1], good[2]]) or ""))
    check("a comment line is refused, not skipped", "line 1" in (refused(["# note", good[0]]) or ""))
    check("a last line without its newline is refused", "newline" in (refused([], "\n".join(good)) or ""))
    twice = json.loads(good[0])
    twice.update(prev=twice["hash"], verdict="not-real")
    twice["hash"] = rc.chain_hash(twice)
    check("a finding labelled twice, properly chained, is refused by the reader", "already labelled" in
          (refused([good[0], json.dumps(twice)]) or ""), refused([good[0], json.dumps(twice)]))
    check("a whole good ledger is accepted (positive control)", refused(good) is None)
    rcode, out, err = run_main(["report", "--instructions", instructions, "--runs", os.path.join(tmp, "none"), "--ledger", ledger])
    check("a missing runs file is a refusal, one line", rcode == 1 and len(err.splitlines()) == 1, err)
    check("labelling the same finding again is refused and leaves the ledger as it was",
          _again(ledger, cs[0]) and open(ledger).read().splitlines() == good)

    # --- the half of a finding
    halves = [c.half() for c in coords_in("dev", 3)] + [c.half() for c in coords_in("held-out", 3)]
    check("the half is fixed by the coordinates", halves == ["dev"] * 3 + ["held-out"] * 3)
    check("the split is pinned: sha256 of 'o/r\\n7\\n1001\\nF1' ends in 0x30 (dev), of ...1004\\nF4 in 0xb1 (held-out)",
          rc.Coordinates("o/r", 7, 1001, "F1").half() == "dev" and rc.Coordinates("o/r", 7, 1004, "F4").half() == "held-out")
    c0 = coords_in("dev", 1)[0]
    rcode, out, _ = run_main(["split", c0.repo, str(c0.pr), str(c0.review), c0.finding])
    check("split prints the half", rcode == 0 and out == "dev\n", out)
    rcode, _, err = run_main(["split", "Mixed/Case", "1", "2", "F1"])
    check("split refuses a repository that is not lowercase (one spelling per finding)", rcode == 1 and "lowercase" in err, err)
    rcode, _, err = run_main(["split", "nonsense", "1", "2", "F1"])
    check("split refuses malformed coordinates", rcode == 1 and "coordinates" in err, err)

    # --- report: below the floor counts only, at it the rates
    labels_path = os.path.join(tmp, "report", "labels.jsonl")
    few = coords_in("held-out", 5)
    write_ledger(labels_path, [(c, "real") for c in few[:3]] + [(c, "not-real") for c in few[3:]])
    runs_path = os.path.join(tmp, "runs-few.jsonl")
    with open(runs_path, "w") as f:
        for c in few:
            f.write(json.dumps({"kind": "adjudication", "configuration": CONF, "repo": c.repo, "pr": c.pr,
                                "review": c.review, "finding": c.finding, "verdict": "real"}) + "\n")
        z = coords_in("held-out", 1, repo="o/zz")[0]           # unlabelled, so a level lookup would happen if asked
        f.write(json.dumps({"kind": "adjudication", "configuration": CONF, "repo": z.repo, "pr": z.pr,
                            "review": z.review, "finding": z.finding, "verdict": "real"}) + "\n")
    rcode, out, err = run_main(["report", "--instructions", instructions, "--runs", runs_path, "--ledger", labels_path])
    check("below the floor the report prints counts and no rate",
          rcode == 0 and "counts only, no rate" in out and "true-positive rate" not in out and "kappa" not in out
          and "real 3, not-real 2" in out, out)
    check("below the floor no level is looked up (each lookup may be a gh call)", FakeLevels.asked == [], FakeLevels.asked)
    rcode, out, _ = run_main(["report", "--instructions", instructions, "--runs", runs_path, "--ledger", labels_path, "--json"])
    js = json.loads(out)
    adj = js["configurations"][0]["adjudication"]
    check("the json below the floor holds the matrix and no rate key", adj["published"] is False and "tpr" not in adj
          and adj["matrix"] == {"tp": 3, "fn": 0, "tn": 0, "fp": 2}, adj)

    big_path = os.path.join(tmp, "report", "big.jsonl")
    reals, nots, other = coords_in("held-out", 25), coords_in("held-out", 25, start=500), coords_in("dev", 2, start=900)
    unsure_c = coords_in("held-out", 1, start=700)[0]
    write_ledger(big_path, [(c, "real") for c in reals] + [(c, "not-real") for c in nots] + [(other[0], "real"),
                                                                                              (unsure_c, "unsure")])
    runs_big = os.path.join(tmp, "runs-big.jsonl")

    def adjudication(c, verdict, conf=CONF):
        return json.dumps({"kind": "adjudication", "configuration": conf, "repo": c.repo, "pr": c.pr,
                           "review": c.review, "finding": c.finding, "verdict": verdict})
    unlabelled = coords_in("held-out", 40, repo="o/other")
    with open(runs_big, "w") as f:
        for i, c in enumerate(reals):
            f.write(adjudication(c, "real" if i < 20 else ("partly" if i < 21 else "not-real")) + "\n")   # 21 of 25
        for i, c in enumerate(nots):
            f.write(adjudication(c, "real" if i < 6 else "not-real") + "\n")                             # TNR 19/25
        f.write(adjudication(other[0], "not-real") + "\n")                                                # dev: unused
        f.write(adjudication(unsure_c, "real") + "\n")                                                   # unsure: out of every denominator
        for i, c in enumerate(unlabelled):
            f.write(adjudication(c, "real" if i % 2 == 0 else "not-real") + "\n")
        for i, c in enumerate(unlabelled[:20]):                       # P1: the ten the judge passed; P2: the ten it did not
            known_levels[c] = "P1" if i % 2 == 0 else "P2"            # the level is the finding's own, not a raised record
        f.write(json.dumps({"kind": "raised", "configuration": CONF, "repo": reals[0].repo, "pr": reals[0].pr,
                            "review": reals[0].review, "finding": reals[0].finding, "level": "P2"}) + "\n")
    rcode, out, err = run_main(["report", "--instructions", instructions, "--runs", runs_big, "--ledger", big_path, "--json", "--iterations", "300"])
    a = json.loads(out)["configurations"][0]["adjudication"]
    check("at the floor the rates are published with Wilson intervals (hand: TPR 21/25, TNR 19/25)",
          rcode == 0 and a["published"] and near(a["tpr"]["rate"], 0.84) and near(a["tnr"]["rate"], 0.76)
          and a["tpr"]["wilson95"] == [round(x, 3) for x in rc.wilson(21, 25)], (rcode, err, a))
    check("kappa and J by hand: po 0.8, pe 0.5", near(a["kappa"], 0.6, 1e-3) and near(a["youden_j"], 0.6, 1e-3), a)
    check("the dev-half label is counted apart and used by no rate", a["dev_labelled_not_used"] == 1
          and a["matrix"] == {"tp": 21, "fn": 4, "tn": 19, "fp": 6}, a["matrix"])
    check("`partly` is reported apart", a["held_out"]["judged_partly"] == 1)
    check("an unsure label is counted and kept out of every denominator, the unlabelled population too",
          a["held_out"]["unsure"] == 1 and a["unlabelled"]["adjudicated"] == 40, a)
    cp = a["corrected_precision"]
    check("corrected precision shows raw, corrected, interval, draws and the discarded", cp["draws"] == 300
          and "rogan_gladen_raw" in cp and "discarded" in cp and cp["bootstrap95"] is not None, cp)
    by = a["corrected_precision_by_level"]
    check("corrected precision per level (hand: P1 passed 10/10 -> (1 + 0.76 - 1) / 0.6 = 1.267, clamped 1.0; "
          "P2 passed 0/10 -> (0 + 0.76 - 1) / 0.6 = -0.4, clamped 0.0)",
          by["P1"]["observed"] == 1.0 and near(by["P1"]["rogan_gladen_raw"], 1.267, 1e-3) and by["P1"]["corrected"] == 1.0
          and by["P2"]["observed"] == 0.0 and near(by["P2"]["rogan_gladen_raw"], -0.4, 1e-3) and by["P2"]["corrected"] == 0.0
          and by["P1"]["draws"] == 300, by)
    check("a level with no adjudicated finding is undefined, and 20 findings whose review gives no level belong to no level",
          "undefined" in by["P3"] and a["unlevelled"] == 20, (by["P3"], a["unlevelled"]))
    # equal counts at two levels: the levels draw from their own streams, so their intervals are not copies
    labels_big = {rc.coordinates_of(r): r["verdict"] for r in rc.read_ledger(big_path)}
    twin = [json.loads(line) for line in open(runs_big).read().splitlines() if '"adjudication"' in line]
    twin_levels = {rc.coordinates_of(r): "P1" if i % 20 < 10 else "P2" for i, r in enumerate(twin[-20:])}
    for i, r in enumerate(twin[-20:]):
        r["verdict"] = "real" if i % 2 == 0 else "not-real"
    twin_by = rc.judge_section(tuple(CONF.values()), twin, labels_big, 400, twin_levels.get)["corrected_precision_by_level"]
    check("two levels with the same counts get different bootstrap intervals",
          twin_by["P1"]["observed"] == twin_by["P2"]["observed"] == 0.5
          and twin_by["P1"]["bootstrap95"] != twin_by["P2"]["bootstrap95"], twin_by)
    check("every review was readable for its levels", json.loads(run_main(
        ["report", "--instructions", instructions, "--runs", runs_big, "--ledger", big_path, "--json", "--iterations", "20"]
    )[1])["level_reviews_unreadable"] == 0)
    FakeLevels.unreadable = {("o/r", 9, 556)}
    try:
        counted = json.loads(run_main(["report", "--instructions", instructions, "--runs", runs_big, "--ledger", big_path,
                                       "--json", "--iterations", "20"])[1])["level_reviews_unreadable"]
        shown = run_main(["report", "--instructions", instructions, "--runs", runs_big, "--ledger", big_path,
                          "--iterations", "20"])[1]
    finally:
        FakeLevels.unreadable = set()
    check("unreadable reviews are counted in the json and named in the text", counted == 1
          and "1 review(s) could not be read for their findings' levels" in shown, (counted, shown[-200:]))
    check("the level assumption is stated", "does not depend on a finding's level" in a["level_assumption"], a)
    rcode, out, _ = run_main(["report", "--instructions", instructions, "--runs", runs_big, "--ledger", big_path, "--iterations", "300"])
    check("the per-level lines and the assumption are printed", "corrected precision P1 1.0" in out
          and "corrected precision P3 undefined" in out and "does not depend on a finding's level" in out, out)
    check("the text names the discarded draws and the configuration, never an author",
          "draws discarded as degenerate" in out and "model m-1" in out and "author" not in out.lower(), out)
    two = os.path.join(tmp, "runs-two.jsonl")
    other_conf = dict(CONF, model="m-2")
    with open(two, "w") as f:
        for line in open(runs_big).read().splitlines()[:50]:
            f.write(line + "\n")
        f.write(adjudication(reals[0], "real", other_conf) + "\n")
    instructions2 = os.path.join(tmp, "code-review-2.md")
    with open(instructions2, "w") as f:
        f.write(INSTRUCTIONS_TEXT + "A second version.\n")
    fp_conf = dict(CONF, config=hashlib.sha256(open(instructions2, "rb").read()).hexdigest())
    with open(two, "a") as f:
        f.write(adjudication(reals[0], "real", fp_conf) + "\n")
    rcode, out, _ = run_main(["report", "--instructions", instructions, instructions2, "--runs", two, "--ledger", big_path, "--json", "--iterations", "50"])
    confs = json.loads(out)["configurations"]
    check("configurations differing only in their instructions' sha256 are never pooled", rcode == 0
          and sorted(c["config"] for c in confs if c["model"] == "m-1") == sorted([CONF["config"], fp_conf["config"]]), confs)
    check("two configurations are never pooled", rcode == 0 and sorted({c["model"] for c in confs}) == ["m-1", "m-2"]
          and all(c["adjudication"]["published"] is False for c in confs if c["config"] != CONF["config"] or c["model"] == "m-2"), confs)
    one_sided = os.path.join(tmp, "report", "one-sided.jsonl")
    write_ledger(one_sided, [(c, "real") for c in reals])
    only_real = os.path.join(tmp, "runs-only-real.jsonl")
    with open(only_real, "w") as f:
        for c in reals:
            f.write(adjudication(c, "real") + "\n")
    ad = json.loads(run_main(["report", "--instructions", instructions, "--runs", only_real, "--ledger", one_sided, "--json"])[1])["configurations"][0]["adjudication"]
    check("25 real labels and no not-real label: below the floor on one side is below the floor",
          ad["published"] is False and "tpr" not in ad, ad)
    check("raised findings: P2 counted held-out, below its floor", json.loads(
        run_main(["report", "--instructions", instructions, "--runs", runs_big, "--ledger", big_path, "--json", "--iterations", "50"])[1]
    )["configurations"][0]["raised"]["P2"] == {"real": 1, "not_real": 0, "unsure": 0, "floor": 20, "published": False})

    bad_runs = os.path.join(tmp, "runs-bad.jsonl")
    for label, line in (("an unknown key", dict(json.loads(adjudication(reals[0], "real")), extra=1)),
                        ("a bad verdict", dict(json.loads(adjudication(reals[0], "real")), verdict="yes")),
                        ("a config that is not a 64-hex fingerprint", dict(json.loads(adjudication(reals[0], "real")),
                                                                           configuration=dict(CONF, config="x")))):
        with open(bad_runs, "w") as f:
            f.write(json.dumps(line) + "\n")
        r_, _, e_ = run_main(["report", "--instructions", instructions, "--runs", bad_runs, "--ledger", big_path])
        check(f"a runs file with {label} is refused, naming its line", r_ == 1 and "line 1" in e_, e_)
    for kind in ("[]", "{}", "5"):
        with open(bad_runs, "w") as f:
            f.write('{"kind": ' + kind + '}\n')
        r_, _, e_ = run_main(["report", "--instructions", instructions, "--runs", bad_runs, "--ledger", big_path])
        check(f"a runs-file kind of {kind} is a one-line refusal, no traceback", r_ == 1 and "line 1" in e_
              and len(e_.splitlines()) == 1, e_)
    with open(bad_runs, "w") as f:
        f.write(adjudication(reals[0], "real") + "\n" + adjudication(reals[0], "not-real") + "\n")
    r_, _, e_ = run_main(["report", "--instructions", instructions, "--runs", bad_runs, "--ledger", big_path])
    check("a duplicate record is refused", r_ == 1 and "line 2" in e_ and "duplicate" in e_, e_)

    seeded_path = os.path.join(tmp, "runs-seeded.jsonl")
    held = [d for d in (f"d{i}" for i in range(40)) if rc.half_of(d) == "held-out"][:2]
    with open(seeded_path, "w") as f:
        for defect, outcomes in ((held[0], (True, True, True)), (held[1], (True, False, True))):
            for n, found in enumerate(outcomes, 1):
                f.write(json.dumps({"kind": "seeded", "configuration": CONF, "defect": defect, "run": n,
                                    "found": found}) + "\n")
    s = json.loads(run_main(["report", "--instructions", instructions, "--runs", seeded_path, "--ledger", big_path, "--json"])[1])["configurations"][0]["seeded"]
    check("seeded recall: pass@1 5/6, pass^3 1/2", s["pass_at_1"]["k"] == 5 and s["pass_at_1"]["n"] == 6
          and s["pass_hat_3"]["k"] == 1 and s["pass_hat_3"]["n"] == 2, s)

    # --- rule 4: a held-out finding's summary in the instructions refuses the run
    held_c, dev_c = reals[0], other[0]
    quoting = os.path.join(tmp, "quoting.md")
    with open(quoting, "w") as f:
        f.write("Example:\n  summary of  " + held_c.finding + "\nin review " + str(held_c.review) + "\n\nend\n")
    def runs_of(extra_file, only=False):
        """runs_big with the configuration of extra_file added, or rebound to it when only."""
        path = os.path.join(tmp, "runs-rebound.jsonl")
        sha = hashlib.sha256(open(extra_file, "rb").read()).hexdigest()
        with open(path, "w") as f:
            for line in open(runs_big).read().splitlines():
                rec = json.loads(line)
                if only:
                    rec["configuration"] = dict(rec["configuration"], config=sha)
                    f.write(json.dumps(rec) + "\n")
                else:
                    f.write(line + "\n")
            if not only:
                f.write(adjudication(reals[0], "real", dict(CONF, config=sha)) + "\n")
        return path
    tail = ["--ledger", big_path, "--iterations", "20"]
    r_, o_, e_ = run_main(["report", "--runs", runs_of(quoting), *tail, "--instructions", instructions, quoting])
    check("a held-out summary in any instructions text refuses the run, naming the finding and not its text",
          r_ == 1 and o_ == "" and held_c.finding in e_ and str(held_c.review) in e_ and "summary of F4" not in e_, e_)
    r_, o_, _ = run_main(["report", "--runs", runs_big, *tail, "--instructions", instructions])
    check("the same run without the quotation is accepted (positive control)", r_ == 0 and o_ != "")
    with open(quoting, "w") as f:
        f.write(f"summary of {dev_c.finding} in review {dev_c.review}\n")
    r_, _, e_ = run_main(["report", "--runs", runs_of(quoting, only=True), *tail, "--instructions", quoting])
    check("a dev-half finding's summary in the instructions is allowed", r_ == 0, e_)
    # rule 4's binding: the file is the instructions the configuration was measured with
    stray = os.path.join(tmp, "stray.md")
    with open(stray, "w") as f:
        f.write("some other instructions\n")
    r_, o_, e_ = run_main(["report", "--runs", runs_big, *tail, "--instructions", instructions, stray])
    check("a file whose sha256 is the config of no configuration is refused, naming the file",
          r_ == 1 and o_ == "" and "stray.md" in e_ and "no configuration" in e_, (r_, e_))
    edited = os.path.join(tmp, "edited.md")
    with open(edited, "w") as f:
        f.write(INSTRUCTIONS_TEXT + "\n")
    r_, o_, e_ = run_main(["report", "--runs", runs_big, *tail, "--instructions", edited])
    check("one added newline changes the sha256 and the run is refused", r_ == 1 and o_ == "" and "edited.md" in e_, e_)
    r_, o_, e_ = run_main(["report", "--runs", runs_of(stray), *tail, "--instructions", instructions])
    check("a configuration with no instructions file is refused, naming its config",
          r_ == 1 and o_ == "" and hashlib.sha256(b"some other instructions\n").hexdigest() in e_ and "no --instructions" in e_, (r_, e_))
    r_, _, e_ = run_main(["report", "--runs", runs_big, "--ledger", big_path])
    check("the instructions are required, not optional", r_ == 2)
    r_, _, e_ = run_main(["report", "--runs", runs_big, *tail, "--instructions", os.path.join(tmp, "absent.md")])
    check("an unreadable instructions file is a refusal", r_ == 1 and "absent.md" in e_, e_)
    rc.fetch_summary = real_fetch
    rc.Levels = real_levels
    seen = []

    def review_api(path, **kw):
        seen.append(path)
        if path.endswith("/reviews/555"):
            return {"id": 555, "body": body_for_rule4}
        raise rc.gh.GhError("gh api GET", "HTTP 404", status=404)
    body_for_rule4 = "\n".join([f"<!-- agent-fabric-review v2 base={BASE} head={HEAD} card={'d' * 40} config={'e' * 64} -->",
                                "Finding: F1 | P2 | certain | src/a.py:12 | the loop never ends"])
    real_api = rc.gh.api
    rc.gh.api = review_api
    try:
        c555 = rc.Coordinates("o/r", 9, 555, "F1")
        got = rc.fetch_summary(c555)
        lone = {"repo": "o/r", "pr": 9, "review": 555, "finding": "F1"}
        outcomes = []
        for coords in (rc.Coordinates("o/r", 9, 556, "F1"), rc.Coordinates("o/r", 9, 555, "F2")):
            try:
                rc.fetch_summary(coords)
                outcomes.append("read")
            except rc.Refused as e:
                outcomes.append(str(e))
    finally:
        rc.gh.api = real_api
    check("fetch_summary reads the summary from the review; a missing review or finding refuses rather than passes",
          got == "the loop never ends" and "cannot be read" in outcomes[0] and "no longer readable" in outcomes[1],
          (got, outcomes, lone))

    # --- a finding's level is read from its own Finding: line, one gh read per review
    gets = []

    def levels_api(path, **kw):
        gets.append(path)
        if path.endswith("/reviews/555"):
            return {"id": 555, "body": body_for_rule4}
        if path.endswith("/reviews/557"):       # edited: its Finding: line has lost the marker that makes it readable
            return {"id": 557, "body": "Finding: F1 | P2 | certain | src/a.py:12 | the loop never ends"}
        raise rc.gh.GhError("gh api GET", "HTTP 502", status=502)
    rc.gh.api = levels_api
    try:
        lv = rc.Levels()
        got_levels = [lv(rc.Coordinates("o/r", 9, 555, "F1")), lv(rc.Coordinates("o/r", 9, 555, "F2")),
                      lv(rc.Coordinates("o/r", 9, 556, "F1")), lv(rc.Coordinates("o/r", 9, 556, "F2")),
                      lv(rc.Coordinates("o/r", 9, 557, "F1"))]
    finally:
        rc.gh.api = real_api
    check("Levels: the level on the finding's own line; a missing finding or an unreadable review is None",
          got_levels == ["P2", None, None, None, None], got_levels)
    odd_bodies = {1: 5, 2: 0, 3: [], 4: False}
    rc.gh.api = lambda path, **kw: {"id": int(path.rsplit("/", 1)[1]), "body": odd_bodies[int(path.rsplit("/", 1)[1])]}
    try:
        odd = rc.Levels()
        odd_levels = [odd(rc.Coordinates("o/r", 9, n, "F1")) for n in odd_bodies]
        odd_level = None if odd_levels == [None] * 4 else odd_levels
        try:
            rc.fetch_summary(rc.Coordinates("o/r", 9, 1, "F1"))
            odd_summary = "read"
        except rc.Refused as e:
            odd_summary = str(e)
    finally:
        rc.gh.api = real_api
    absent = {5: {"id": 5}, 6: {"id": 6, "body": None}}         # an absent body is a review without findings, not a malformed one
    rc.gh.api = lambda path, **kw: absent[int(path.rsplit("/", 1)[1])]
    try:
        none_lv = rc.Levels()
        none_levels = [none_lv(rc.Coordinates("o/r", 9, n, "F1")) for n in absent]
        try:
            rc.fetch_summary(rc.Coordinates("o/r", 9, 5, "F1"))
            none_summary = "read"
        except rc.Refused as e:
            none_summary = str(e)
    finally:
        rc.gh.api = real_api
    check("a review with no body or a null body stays readable: no level, not unreadable, a refused summary",
          none_levels == [None, None] and none_lv.unreadable == set() and "no longer readable" in none_summary,
          (none_levels, none_lv.unreadable, none_summary))
    check("a review body that is no text is an unreadable review and a one-line refusal, not a traceback",
          odd_level is None and odd.unreadable == {("o/r", 9, n) for n in odd_bodies} and "no longer readable" in odd_summary, (odd.unreadable, odd_summary))
    check("Levels: one read per review, and the unreadable review is counted apart",
          len(gets) == 3 and lv.unreadable == {("o/r", 9, 556), ("o/r", 9, 557)}, (gets, lv.unreadable))

    # --- the real entry points, with a minimal environment
    stripped_ledger = os.path.join(tmp, "stripped.jsonl")
    with open(stripped_ledger, "w") as f:
        f.write(good[0] + "\n" + json.dumps(stripped) + "\n")
    for name, argv in (("module", [TOOL]), ("shim", [SHIM])):
        r = child([*argv, "report", "--instructions", instructions, "--runs", runs_path, "--ledger", stripped_ledger], tmp)
        check(f"{name}: a ledger with a stripped hash is refused, exit 1, named, no traceback",
              r.returncode == 1 and "line 2" in r.stderr and "Traceback" not in r.stderr and r.stdout == "",
              (r.returncode, r.stderr))
        r = child([*argv, "report", "--instructions", instructions, "--runs", runs_path, "--ledger", labels_path], tmp)
        check(f"{name}: below the floor, exit 0 and counts only", r.returncode == 0 and "counts only" in r.stdout
              and "true-positive rate" not in r.stdout, (r.returncode, r.stderr, r.stdout))
        r = child([*argv, "bogus"], tmp)
        check(f"{name}: a usage error is exit 2", r.returncode == 2, r.returncode)
    r = child([TOOL, "split", c0.repo, str(c0.pr), str(c0.review), c0.finding], tmp)
    check("split through the module agrees with the library", r.stdout == "dev\n", r.stdout)

    # --- label: the blind view
    summary = "the loop never ends when the list is empty"
    body = "\n".join([
        f"<!-- agent-fabric-review v2 base={BASE} head={HEAD} card={'d' * 40} config={'e' * 64} -->", "prose by engine codex",
        f"Finding: F1 | P2 | certain | src/a.py:12 | {summary}", "Finding: F2 | P3 | likely | src/gone.py:3 | second finding",
        "Judgement: F1 | real | the author fixed it, code-review judged real"])
    patch = "@@ -1,3 +1,4 @@\n a\n+b\n c\n@@ -10,3 +10,5 @@ def f():\n x\n+y: the changed line\n z\n"
    calls = []

    def fake_api(path, **kw):
        calls.append(path)
        if "/reviews" in path:
            return [{"id": 555, "body": body}, {"id": 556, "body": "<!-- agent-fabric-review v1 -->\nFinding: F1 | P1 | certain | x | y"}]
        if "/compare/" in path:
            return {"files": [{"filename": "src/a.py", "patch": patch}]}
        raise AssertionError(path)
    real_api = rc.gh.api
    rc.gh.api = fake_api
    try:
        lp = os.path.join(tmp, "label", "labels.jsonl")
        answers = iter(["maybe", "unsure", "skip"])
        rcode, out, _ = run_main(["label", "--repo", "O/R", "--pr", "9", "--ledger", lp, "--labeller", "owner"],
                                 ask=lambda prompt: next(answers), today=lambda: "2026-11-08")
        recs = rc.read_ledger(lp)
        check("label: --repo is lowercased into the coordinates, whatever its spelling",
              all(r["repo"] == "o/r" for r in recs))
        check("label: the summary, place, range and hunk are shown; a bad answer asks again", rcode == 0
              and summary in out and "src/a.py:12" in out and "+y: the changed line" in out
              and f"{BASE[:12]}..{HEAD[:12]}" in out and "@@ -1,3" not in out, out)
        check("label: never the engine, the model, the reply or a Judgement", "Judgement" not in out
              and "codex" not in out and "author fixed" not in out and "code-review" not in out and "certain" not in out
              and "P2" not in out, out)
        check("label: a v1 review (no range) is not offered", out.count("range ") == 2, out)
        check("label: unsure is recorded; skip leaves the finding unlabelled; the line holds no finding text",
              len(recs) == 1 and recs[0]["verdict"] == "unsure" and recs[0]["finding"] == "F1" and recs[0]["review"] == 555
              and recs[0]["date"] == "2026-11-08" and recs[0]["labeller"] == "owner"
              and summary not in open(lp).read(), recs)
        r_, _, e_ = run_main(["label", "--repo", "o/r", "--limit", "200", "--ledger", lp])
        check("label: --limit above 100 is a usage error, not a silent cap", r_ == 2)
        again = io.StringIO()
        with contextlib.redirect_stderr(io.StringIO()):
            rc.main(["label", "--repo", "o/r", "--pr", "9", "--ledger", lp], ask=lambda p: "quit", out=again)
        check("label: the next unlabelled finding is the second, the labelled one is not offered again",
              "second finding" in again.getvalue() and summary not in again.getvalue(), again.getvalue())
        with open(lp, "a") as f:
            f.write("garbage\n")
        r_, _, e_ = run_main(["label", "--repo", "o/r", "--pr", "9", "--ledger", lp], ask=lambda p: "quit")
        check("label: a ledger that does not verify is refused before anything is shown", r_ == 1 and "line 2" in e_, e_)
    finally:
        rc.gh.api = real_api
    check("hunk_of picks the hunk holding the line, None for a line outside every hunk",
          rc.hunk_of(patch, 12).startswith("@@ -10,3") and rc.hunk_of(patch, 99) is None
          and rc.hunk_of(patch, None).startswith("@@ -1,3"))

    holder.cleanup()
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


def _again(ledger: str, coords: rc.Coordinates) -> bool:
    try:
        rc.append_label(ledger, coords, "real", "owner", "2026-11-08")
    except rc.Refused:
        return True
    return False


if __name__ == "__main__":
    sys.exit(main())
