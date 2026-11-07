#!/usr/bin/env python3
"""tools/fabric/review_calibration.py — the reader of agent-fabric ADR-066: the review class measured like a
classifier. Standard library only (gh through gh.py).

PORTED FROM gavel, https://github.com/TechTideOhio/gavel at 27ff6e1d9d7ea38c4adb44809a147f24fe008fdf, MIT
licence, Copyright (c) 2026 TechTide Ohio (the notice is kept through REUSE.toml and LICENSES/MIT.txt):
  src/classifier.rs  the confusion matrix, TPR, TNR, precision, Cohen's kappa, MCC, Youden's J, the Wilson interval
  src/debias.rs      the Rogan-Gladen estimator and its parametric bootstrap
  src/dataset.rs     SplitMix64, which seeds the bootstrap so a run reproduces
The exact McNemar and TOST tests are written from their formulas with math.comb; gavel has neither.

FOUR BEHAVIOURS DIFFER FROM GAVEL, each pinned by a test that fails on gavel's:
  1. A rate with no denominator is None, never 0.0 (gavel's tpr() of a matrix with no positives is 0.0, so a
     judge never shown a real finding reads as one that rejects them all). The same rule covers kappa, MCC,
     precision and the Wilson interval of an empty sample (gavel: kappa 0.0/1.0, MCC 0.0, interval (0, 1)).
  2. The bootstrap counts the draws it discards as degenerate (Youden J <= 0.001) and reports them with the
     number drawn; gavel drops them silently, which narrows the interval exactly when the judge is weak. The raw
     Rogan-Gladen value is reported beside the clamped one. With no draw left the interval is None, not the
     point value twice.
  3. The ledger fails closed: every line must carry `prev` and `hash` and both must verify. gavel verifies a
     record's hashes only when they are non-empty, so a ledger with its hashes stripped passes.

CONTRACT.
  fabric-review-calibration label  --repo OWNER/NAME [--pr N]... [--limit K] [--ledger F] [--labeller L]
  fabric-review-calibration report --runs F --instructions F... [--ledger F] [--json] [--iterations N]
  fabric-review-calibration split  OWNER/NAME PR REVIEW_ID FINDING

  label   Shows the next unlabelled finding blind (its summary, its path and line, its hunk and the range; never
          the engine, the model, the author's reply or a Judgement: line), reads real / not-real / unsure
          (skip leaves it unlabelled, quit stops) and appends one line to the ledger. The finding's text is
          read through gh at run time and never written. Candidates are the `Finding:` machine lines of the v2
          reviews (the range is the marker's) posted as PR reviews; a review whose lines do not parse is skipped.
  split   Prints `dev` or `held-out`: sha256 of the coordinates, mod 2 (ADR-066 §5 rule 4). The coordinates are
          joined as repo, PR, review id, finding label, one per line, no trailing newline; the digest's low bit
          is the half: 0 dev, 1 held-out. The record does not say which parity is which; fixing it here is a
          decision of this reader that the first label makes permanent.
  report  Per configuration (engine, model, effort, the review's v2 `config` fingerprint), from the ledger and
          the runs file: the held-out counts always, a rate only at or above the floor of §5 rule 6 (20 real and
          20 not-real held-out labels behind it), each with its interval. A configuration is never pooled with
          another. It names no author (§5 rule 11). Before anything is computed it reads, through gh, the summary
          of every held-out labelled finding and refuses the run when one appears (whitespace folded) in any
          --instructions text, the configuration's rendered reviewer instructions (§5 rule 4); a summary that
          cannot be read refuses too, since "not in the instructions" would then be unknown. The refusal names
          the finding's coordinates, never its text. --instructions is required: a check that can be left out is
          not a refusal.

LEDGER (docs/review-calibration/labels.jsonl): one JSON object per line, exactly the keys repo, pr, review,
finding, verdict, date, labeller, prev, hash. `prev` is the line before's `hash` ("genesis" for the first) and
`hash` the sha256 over prev and the other fields, each length-prefixed. No other key, no blank or comment line,
no second label for a finding. The chain cannot show that lines were cut from its end; git does.

RUNS FILE (`report --runs`): one JSON object per line, written by a calibration run; the reader never invents
what a run did not record. Every record holds `kind` and `configuration` {engine, model, effort, config}:
  adjudication  repo, pr, review, finding, verdict (real | not-real | partly): a fresh review-class (or Codex)
                judgement of a finding; `partly` counts as real for the binary rates and is reported apart.
  raised        repo, pr, review, finding, level (P1-P3): the configuration's own review raised that finding.
  seeded        defect, run (1-3), found (bool): a seeded-defect run (§5 rule 8).
A duplicate record, an unknown key or a malformed value refuses the whole file, naming the line.

EXIT STATUS. 0 done; 1 a refusal (ledger, runs file, gh), named on stderr, one line, no traceback; 2 usage.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import fcntl
import getpass
import hashlib
import json
import math
import os
import re
import sys
from typing import Callable, Iterable

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import errors  # noqa: E402
import gh  # noqa: E402
from github import review_coverage  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
LEDGER = os.path.join(ROOT, "docs", "review-calibration", "labels.jsonl")
GENESIS = "genesis"
LABELS = ("real", "not-real", "unsure")
ADJUDICATIONS = ("real", "not-real", "partly")
FLOOR = 20                       # ADR-066 §5 rule 6: real and not-real labels each
Z95 = 1.959963984540054          # gavel's constant
MIN_YOUDEN = 0.001               # gavel: a judge at or below this cannot be inverted
ITERATIONS = 1000
U64 = (1 << 64) - 1


class Refused(Exception):
    """Input the reader will not read; the message names where and why."""


# ---------------------------------------------------------------- arithmetic (gavel classifier.rs, debias.rs)

def ratio(num: float, den: float) -> float | None:
    return None if den == 0 else num / den


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval; None for n == 0 (gavel returns (0, 1): a vacuous interval is not an interval)."""
    if n == 0:
        return None
    z2 = z * z
    tilde = n + z2
    centre = (k + 0.5 * z2) / tilde
    margin = (z / tilde) * math.sqrt(k * (n - k) / n + 0.25 * z2)
    return max(centre - margin, 0.0), min(centre + margin, 1.0)


@dataclasses.dataclass(frozen=True)
class Confusion:
    """Human label against judge verdict; positive is `real`."""
    tp: int = 0
    fn: int = 0
    tn: int = 0
    fp: int = 0

    @property
    def total(self) -> int:
        return self.tp + self.fn + self.tn + self.fp

    @property
    def positives(self) -> int:
        return self.tp + self.fn

    @property
    def negatives(self) -> int:
        return self.tn + self.fp

    def tpr(self) -> float | None:
        return ratio(self.tp, self.positives)

    def tnr(self) -> float | None:
        return ratio(self.tn, self.negatives)

    def precision(self) -> float | None:
        return ratio(self.tp, self.tp + self.fp)

    def youden_j(self) -> float | None:
        tpr, tnr = self.tpr(), self.tnr()
        return None if tpr is None or tnr is None else tpr + tnr - 1.0

    def kappa(self) -> float | None:
        if self.total == 0:
            return None
        t = float(self.total)
        po = (self.tp + self.tn) / t
        pe = ((self.tp + self.fn) / t) * ((self.tp + self.fp) / t) + ((self.tn + self.fp) / t) * ((self.tn + self.fn) / t)
        # gavel answers 1.0 or 0.0 when chance agreement is certain; the quotient is 0/0 there, so it is undefined.
        return None if abs(1.0 - pe) < 1e-9 else (po - pe) / (1.0 - pe)

    def mcc(self) -> float | None:
        denominator = math.sqrt(float(self.tp + self.fp) * (self.tp + self.fn) * (self.tn + self.fp) * (self.tn + self.fn))
        return None if denominator < 1e-9 else (self.tp * self.tn - self.fp * self.fn) / denominator

    def tpr_wilson(self) -> tuple[float, float] | None:
        return wilson(self.tp, self.positives)

    def tnr_wilson(self) -> tuple[float, float] | None:
        return wilson(self.tn, self.negatives)


class SplitMix64:
    """gavel's generator. It seeds the bootstrap only; nothing of the ledger or the split depends on it."""

    def __init__(self, seed: int):
        self.state = seed & U64

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & U64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & U64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & U64
        return z ^ (z >> 31)


@dataclasses.dataclass(frozen=True)
class RoganGladen:
    raw: float          # (p_obs + tnr - 1) / J, unclamped: a value outside [0, 1] says the inputs disagree
    corrected: float    # raw clamped to [0, 1]


def rogan_gladen(p_obs: float, tpr: float, tnr: float) -> RoganGladen | None:
    """None for a judge that cannot be inverted (J <= 0.001)."""
    j = tpr + tnr - 1.0
    if j <= MIN_YOUDEN:
        return None
    raw = (p_obs + tnr - 1.0) / j
    return RoganGladen(raw, min(max(raw, 0.0), 1.0))


def binomial(rng: SplitMix64, n: int, p: float) -> int:
    if p <= 0.0:
        return 0
    if p >= 1.0:
        return n
    return sum(1 for _ in range(n) if rng.next_u64() / float(U64) < p)


@dataclasses.dataclass(frozen=True)
class Debiased:
    observed: float
    raw: float
    corrected: float
    interval: tuple[float, float] | None    # None when every draw was discarded
    draws: int
    discarded: int
    tpr: float
    tnr: float


class Undefined(Exception):
    """A corrected value that has no definition for these inputs; the message says why."""


def debias(matrix: Confusion, observed_passes: int, total: int, iterations: int, seed: int) -> Debiased:
    if total == 0:
        raise Undefined("no adjudicated findings outside the labels")
    tpr, tnr = matrix.tpr(), matrix.tnr()
    if tpr is None or tnr is None:
        raise Undefined("the judge's matrix lacks real or not-real labels")
    p_obs = observed_passes / total
    point = rogan_gladen(p_obs, tpr, tnr)
    if point is None:
        raise Undefined("the judge cannot be inverted: Youden's J <= 0.001")
    rng = SplitMix64(seed)
    estimates: list[float] = []
    for _ in range(iterations):
        tpr_star = binomial(rng, matrix.positives, tpr) / matrix.positives
        tnr_star = binomial(rng, matrix.negatives, tnr) / matrix.negatives
        p_star = binomial(rng, total, p_obs) / total
        draw = rogan_gladen(p_star, tpr_star, tnr_star)
        if draw is not None:
            estimates.append(draw.corrected)
    interval = None
    if estimates:
        estimates.sort()
        low = int(math.floor(len(estimates) * 0.025))
        high = min(int(math.ceil(len(estimates) * 0.975)), len(estimates) - 1)
        interval = (estimates[low], estimates[high])
    return Debiased(p_obs, point.raw, point.corrected, interval, iterations, iterations - len(estimates), tpr, tnr)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact p of b against c discordant pairs: min(1, 2 * P(X <= min(b, c))), X ~ Bin(b + c, 1/2)."""
    n = b + c
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def tost_paired(b: int, c: int, pairs: int, margin: float = 0.05) -> float | None:
    """Exact TOST of |P(A only) - P(B only)| < margin on `pairs` paired items, b of them A-only and c B-only.
    Conditional on the n = b + c discordant pairs, b ~ Bin(n, theta) and the difference is (2 theta - 1) n / pairs,
    so equivalence is theta in (1/2 -/+ margin * pairs / (2n)). The p-value is the larger of the two one-sided
    exact tail probabilities at the bounds. None when nothing is discordant (the conditional test has no data)
    or there are no pairs; a bound beyond [0, 1] is a null the data cannot be under, so its tail is 0."""
    n = b + c
    if pairs <= 0 or n == 0 or n > pairs:
        return None
    half = margin * pairs / (2 * n)
    upper, lower = 0.5 + half, 0.5 - half

    def tail(k_from: int, k_to: int, theta: float) -> float:
        return sum(math.comb(n, i) * theta ** i * (1 - theta) ** (n - i) for i in range(k_from, k_to + 1))

    p_upper = 0.0 if upper >= 1.0 else tail(0, b, upper)     # H0: theta >= upper
    p_lower = 0.0 if lower <= 0.0 else tail(b, n, lower)     # H0: theta <= lower
    return max(p_upper, p_lower)


# ---------------------------------------------------------------- the ledger

REPO = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+")
FINDING = re.compile(r"F[0-9]+")
LEDGER_KEYS = ("repo", "pr", "review", "finding", "verdict", "date", "labeller", "prev", "hash")
HEX64 = re.compile(r"[0-9a-f]{64}")


@dataclasses.dataclass(frozen=True)
class Coordinates:
    repo: str
    pr: int
    review: int
    finding: str

    def half(self) -> str:
        return half_of("\n".join((self.repo, str(self.pr), str(self.review), self.finding)))


def half_of(text: str) -> str:
    return "held-out" if hashlib.sha256(text.encode()).digest()[-1] & 1 else "dev"


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_coordinates(rec: dict) -> bool:
    return (isinstance(rec.get("repo"), str) and bool(REPO.fullmatch(rec["repo"])) and _count(rec.get("pr"))
            and _count(rec.get("review")) and isinstance(rec.get("finding"), str)
            and bool(FINDING.fullmatch(rec["finding"])))


def chain_hash(rec: dict) -> str:
    h = hashlib.sha256()
    for key in ("prev", "repo", "pr", "review", "finding", "verdict", "date", "labeller"):
        part = str(rec[key]).encode()
        h.update(str(len(part)).encode() + b":" + part)
    return h.hexdigest()


def read_ledger(path: str) -> list[dict]:
    """Every record, verified. A line that is blank, not an object of exactly LEDGER_KEYS, with a value of the
    wrong shape, with no prev or hash, with a prev that is not the line before's hash, with a hash that is not
    the line's, or that labels a finding already labelled, refuses the whole ledger (ADR-066 §5 rule 3)."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise Refused(f"{path}: cannot be read: {e.strerror or e}") from None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Refused(f"{path}: not UTF-8") from None
    records: list[dict] = []
    seen: set[tuple] = set()
    prev = GENESIS
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    elif lines:
        raise Refused(f"{path} line {len(lines)}: the last line has no newline")
    for number, line in enumerate(lines, 1):
        where = f"{path} line {number}"
        try:
            rec = json.loads(line, parse_constant=lambda name: (_ for _ in ()).throw(ValueError(name)))
        except ValueError:
            raise Refused(f"{where}: not a JSON object") from None
        if not isinstance(rec, dict):
            raise Refused(f"{where}: not a JSON object")
        if set(rec) != set(LEDGER_KEYS):
            raise Refused(f"{where}: keys {sorted(rec)} are not exactly {list(LEDGER_KEYS)}")
        if not _valid_coordinates(rec) or rec["verdict"] not in LABELS:
            raise Refused(f"{where}: coordinates or verdict malformed")
        if not (isinstance(rec["date"], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", rec["date"])
                and isinstance(rec["labeller"], str) and rec["labeller"].strip()):
            raise Refused(f"{where}: date or labeller malformed")
        try:
            dt.date.fromisoformat(rec["date"])
        except ValueError:
            raise Refused(f"{where}: date is not a calendar date") from None
        if not (isinstance(rec["prev"], str) and rec["prev"] and isinstance(rec["hash"], str) and rec["hash"]):
            raise Refused(f"{where}: no chain hash (prev and hash are required)")
        if rec["prev"] != prev:
            raise Refused(f"{where}: broken chain: prev is not the previous line's hash")
        if not HEX64.fullmatch(rec["hash"]) or rec["hash"] != chain_hash(rec):
            raise Refused(f"{where}: the line's hash does not match its content")
        key = (rec["repo"], rec["pr"], rec["review"], rec["finding"])
        if key in seen:
            raise Refused(f"{where}: finding already labelled")
        seen.add(key)
        records.append(rec)
        prev = rec["hash"]
    return records


def coordinates_of(rec: dict) -> Coordinates:
    return Coordinates(rec["repo"], rec["pr"], rec["review"], rec["finding"])


def append_label(path: str, coords: Coordinates, verdict: str, labeller: str, today: str) -> dict:
    """Appends one verified line. The ledger is re-read under an exclusive lock so two labellers cannot both
    chain to the same previous line; a ledger that does not verify is never appended to."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644)
    with os.fdopen(fd, "r+b") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        existing = read_ledger(path)
        if any(coordinates_of(r) == coords for r in existing):
            raise Refused(f"{path}: {coords.repo}#{coords.pr} review {coords.review} {coords.finding} is already labelled")
        rec = {"repo": coords.repo, "pr": coords.pr, "review": coords.review, "finding": coords.finding,
               "verdict": verdict, "date": today, "labeller": labeller,
               "prev": existing[-1]["hash"] if existing else GENESIS}
        rec["hash"] = chain_hash(rec)
        f.write((json.dumps(rec, sort_keys=True) + "\n").encode())
        f.flush()
        os.fsync(f.fileno())
    return rec


# ---------------------------------------------------------------- the runs file and the report

CONFIGURATION_KEYS = ("engine", "model", "effort", "config")
RUN_KINDS = {
    "adjudication": ("repo", "pr", "review", "finding", "verdict"),
    "raised": ("repo", "pr", "review", "finding", "level"),
    "seeded": ("defect", "run", "found"),
}
Configuration = tuple[str, str, str, str]


@dataclasses.dataclass(frozen=True)
class Run:
    kind: str
    configuration: Configuration
    rec: dict


def read_runs(path: str) -> list[Run]:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except (OSError, UnicodeDecodeError) as e:
        raise Refused(f"{path}: cannot be read: {getattr(e, 'strerror', None) or e}") from None
    if lines and lines[-1] == "":
        lines.pop()
    runs: list[Run] = []
    seen: set[tuple] = set()
    for number, line in enumerate(lines, 1):
        where = f"{path} line {number}"
        try:
            rec = json.loads(line, parse_constant=lambda name: (_ for _ in ()).throw(ValueError(name)))
        except ValueError:
            raise Refused(f"{where}: not a JSON object") from None
        kind = rec.get("kind") if isinstance(rec, dict) else None
        if kind not in RUN_KINDS:
            raise Refused(f"{where}: kind is not one of {sorted(RUN_KINDS)}")
        if set(rec) != {"kind", "configuration", *RUN_KINDS[kind]}:
            raise Refused(f"{where}: keys {sorted(rec)} do not fit a {kind} record")
        conf = rec["configuration"]
        if not (isinstance(conf, dict) and set(conf) == set(CONFIGURATION_KEYS)
                and all(isinstance(conf[k], str) and conf[k].strip() for k in CONFIGURATION_KEYS)
                and HEX64.fullmatch(conf["config"])):
            raise Refused(f"{where}: configuration must name engine, model, effort and a 64-hex config")
        configuration = tuple(conf[k] for k in CONFIGURATION_KEYS)
        if kind == "seeded":
            ok = (isinstance(rec["defect"], str) and rec["defect"].strip() and rec["run"] in (1, 2, 3)
                  and not isinstance(rec["run"], bool) and isinstance(rec["found"], bool))
            ident = (kind, configuration, rec.get("defect"), rec.get("run"))
        else:
            ok = _valid_coordinates(rec) and (rec.get("verdict") in ADJUDICATIONS if kind == "adjudication"
                                              else rec.get("level") in ("P1", "P2", "P3"))
            ident = (kind, configuration, rec.get("repo"), rec.get("pr"), rec.get("review"), rec.get("finding"))
        if not ok:
            raise Refused(f"{where}: a value does not fit a {kind} record")
        if ident in seen:
            raise Refused(f"{where}: duplicate {kind} record for this configuration")
        seen.add(ident)
        runs.append(Run(kind, configuration, rec))
    return runs


def seed_of(configuration: Configuration) -> int:
    return int.from_bytes(hashlib.sha256("\0".join(configuration).encode()).digest()[:8], "big")


def interval_view(iv: tuple[float, float] | None) -> list[float] | None:
    return None if iv is None else [round(iv[0], 3), round(iv[1], 3)]


def rate_view(k: int, n: int) -> dict:
    return {"k": k, "n": n, "rate": None if n == 0 else round(k / n, 3), "wilson95": interval_view(wilson(k, n))}


def judge_section(conf: Configuration, adjudications: list[dict], labels: dict[Coordinates, str],
                  iterations: int) -> dict:
    matrix = [0, 0, 0, 0]       # tp fn tn fp
    held = {"real": 0, "not-real": 0, "unsure": 0}
    partly = dev = 0
    unlabelled_pass = unlabelled_total = 0
    for rec in adjudications:
        coords = coordinates_of(rec)
        label = labels.get(coords)
        positive = rec["verdict"] in ("real", "partly")
        if label is None:
            unlabelled_total += 1
            unlabelled_pass += positive
        elif label == "unsure":
            held["unsure"] += coords.half() == "held-out"
        elif coords.half() == "dev":
            dev += 1
        else:
            held[label] += 1
            partly += rec["verdict"] == "partly"
            if label == "real":
                matrix[0 if positive else 1] += 1
            else:
                matrix[3 if positive else 2] += 1
    m = Confusion(*matrix)
    out: dict = {"held_out": {"real": m.positives, "not_real": m.negatives, "unsure": held["unsure"],
                              "judged_partly": partly},
                 "dev_labelled_not_used": dev, "floor": FLOOR,
                 "matrix": {"tp": m.tp, "fn": m.fn, "tn": m.tn, "fp": m.fp}}
    if m.positives < FLOOR or m.negatives < FLOOR:
        out["published"] = False
        return out
    out["published"] = True
    out["tpr"] = rate_view(m.tp, m.positives)
    out["tnr"] = rate_view(m.tn, m.negatives)
    for name, value in (("precision", m.precision()), ("kappa", m.kappa()), ("youden_j", m.youden_j()),
                        ("mcc", m.mcc())):
        out[name] = None if value is None else round(value, 3)
    out["unlabelled"] = {"adjudicated": unlabelled_total, "real_or_partly": unlabelled_pass}
    try:
        d = debias(m, unlabelled_pass, unlabelled_total, iterations, seed_of(conf))
        out["corrected_precision"] = {"observed": round(d.observed, 3), "rogan_gladen_raw": round(d.raw, 3),
                                      "corrected": round(d.corrected, 3), "bootstrap95": interval_view(d.interval),
                                      "draws": d.draws, "discarded": d.discarded}
    except Undefined as e:
        out["corrected_precision"] = {"undefined": str(e)}
    return out


def raised_section(raised: list[dict], labels: dict[Coordinates, str]) -> dict:
    levels: dict[str, dict] = {}
    for level in ("P1", "P2", "P3"):
        counts = {"real": 0, "not-real": 0, "unsure": 0}
        for rec in raised:
            coords = coordinates_of(rec)
            if rec["level"] == level and coords.half() == "held-out" and coords in labels:
                counts[labels[coords]] += 1
        entry: dict = {"real": counts["real"], "not_real": counts["not-real"], "unsure": counts["unsure"],
                       "floor": FLOOR, "published": counts["real"] >= FLOOR and counts["not-real"] >= FLOOR}
        if entry["published"]:
            entry["precision"] = rate_view(counts["real"], counts["real"] + counts["not-real"])
        levels[level] = entry
    return levels


def seeded_section(seeded: list[dict]) -> dict:
    """pass@1 over the held-out defects' runs and pass^3 over the held-out defects run exactly three times.
    ADR-066 sets no floor for rate 3, so counts and rate always appear together here, with the interval."""
    by_defect: dict[str, list[bool]] = {}
    for rec in seeded:
        if half_of(rec["defect"]) == "held-out":
            by_defect.setdefault(rec["defect"], []).append(rec["found"])
    runs = [f for outcomes in by_defect.values() for f in outcomes]
    complete = [o for o in by_defect.values() if len(o) == 3]
    return {"defects": len(by_defect), "pass_at_1": rate_view(sum(runs), len(runs)),
            "pass_hat_3": rate_view(sum(all(o) for o in complete), len(complete)),
            "incomplete_defects": len(by_defect) - len(complete)}


def fetch_summary(coords: Coordinates) -> str:
    """The finding's summary, read through gh from its review now; Refused when it cannot be."""
    try:
        review = gh.api(f"repos/{coords.repo}/pulls/{coords.pr}/reviews/{coords.review}")
    except gh.GhError as e:
        raise Refused(f"{coords.repo}#{coords.pr} review {coords.review} {coords.finding}: the review cannot be read "
                      f"to check the instructions against it: {e}") from None
    for c in findings_of(coords.repo, coords.pr, review if isinstance(review, dict) else {}):
        if c.coords == coords:
            return c.summary
    raise Refused(f"{coords.repo}#{coords.pr} review {coords.review} {coords.finding}: the finding is no longer "
                  "readable in its review, so the instructions cannot be checked against it")


def check_instructions(ledger: list[dict], texts: dict[str, str]) -> None:
    """ADR-066 §5 rule 4: no held-out labelled finding's summary appears in the instructions."""
    folded = {name: " ".join(text.split()) for name, text in texts.items()}
    for rec in ledger:
        coords = coordinates_of(rec)
        if coords.half() != "held-out":
            continue
        summary = " ".join(fetch_summary(coords).split())
        for name, text in folded.items():
            if summary in text:
                raise Refused(f"{name}: holds the summary of held-out finding {coords.repo}#{coords.pr} review "
                              f"{coords.review} {coords.finding}; a held-out finding is never quoted in the instructions")


def build_report(ledger: list[dict], runs: list[Run], iterations: int = ITERATIONS) -> dict:
    labels = {coordinates_of(r): r["verdict"] for r in ledger}
    halves = {"dev": 0, "held-out": 0}
    for coords in labels:
        halves[coords.half()] += 1
    report: dict = {"labels": {"total": len(labels), "dev": halves["dev"], "held_out": halves["held-out"],
                               "unsure": sum(v == "unsure" for v in labels.values())},
                    "configurations": []}
    for conf in sorted({r.configuration for r in runs}):
        mine = [r for r in runs if r.configuration == conf]
        entry: dict = {"engine": conf[0], "model": conf[1], "effort": conf[2], "config": conf[3]}
        adjudications = [r.rec for r in mine if r.kind == "adjudication"]
        raised = [r.rec for r in mine if r.kind == "raised"]
        seeded = [r.rec for r in mine if r.kind == "seeded"]
        if adjudications:
            entry["adjudication"] = judge_section(conf, adjudications, labels, iterations)
        if raised:
            entry["raised"] = raised_section(raised, labels)
        if seeded:
            entry["seeded"] = seeded_section(seeded)
        report["configurations"].append(entry)
    return report


def _fmt(rate: dict) -> str:
    iv = rate["wilson95"]
    return f"{rate['rate']:.3f} [{iv[0]:.3f}, {iv[1]:.3f}] ({rate['k']}/{rate['n']})" if iv else f"undefined ({rate['k']}/{rate['n']})"


def render(report: dict) -> str:
    lab = report["labels"]
    out = [f"labels: {lab['total']} (dev {lab['dev']}, held-out {lab['held_out']}, unsure {lab['unsure']})"]
    for c in report["configurations"]:
        out.append(f"\nconfiguration: engine {c['engine']}, model {c['model']}, effort {c['effort']}, config {c['config']}")
        if "adjudication" in c:
            a = c["adjudication"]
            h = a["held_out"]
            out.append(f"  adjudication (held-out): real {h['real']}, not-real {h['not_real']}, unsure {h['unsure']}, "
                       f"judged partly {h['judged_partly']}; matrix {a['matrix']}")
            if not a["published"]:
                out.append(f"  below the floor ({FLOOR} real and {FLOOR} not-real): counts only, no rate")
            else:
                out.append(f"  true-positive rate {_fmt(a['tpr'])}")
                out.append(f"  true-negative rate {_fmt(a['tnr'])}")
                for name in ("precision", "kappa", "youden_j", "mcc"):
                    out.append(f"  {name} {'undefined' if a[name] is None else a[name]} (no interval)")
                cp = a["corrected_precision"]
                if "undefined" in cp:
                    out.append(f"  corrected precision undefined: {cp['undefined']}")
                else:
                    iv = cp["bootstrap95"]
                    out.append(f"  corrected precision {cp['corrected']} (raw Rogan-Gladen {cp['rogan_gladen_raw']}, "
                               f"observed {cp['observed']}), bootstrap 95% "
                               f"{'undefined' if iv is None else f'[{iv[0]}, {iv[1]}]'}; "
                               f"{cp['discarded']} of {cp['draws']} draws discarded as degenerate")
        for level, e in c.get("raised", {}).items():
            line = f"  raised {level} (held-out): real {e['real']}, not-real {e['not_real']}, unsure {e['unsure']}"
            out.append(line + (f"; precision {_fmt(e['precision'])}" if e["published"] else "; below the floor: counts only"))
        if "seeded" in c:
            s = c["seeded"]
            out.append(f"  seeded (held-out defects {s['defects']}, {s['incomplete_defects']} without three runs; "
                       f"no floor set by ADR-066): pass@1 {_fmt(s['pass_at_1'])}, pass^3 {_fmt(s['pass_hat_3'])}")
    return "\n".join(out)


# ---------------------------------------------------------------- label: the blind view

@dataclasses.dataclass(frozen=True)
class Candidate:
    coords: Coordinates
    base: str
    head: str
    path: str
    line: int | None
    summary: str


def findings_of(repo: str, pr: int, review: dict) -> list[Candidate]:
    body = review.get("body") or ""
    marker = review_coverage.parse_marker(body)
    parsed = errors.parse_machine_lines(body)
    if marker is None or parsed is None or parsed.unparsed or not isinstance(review.get("id"), int):
        return []
    found = []
    for rest in errors.FINDING_LINE.findall(body):
        if rest.strip() == "none" or errors.parse_finding_line(rest) is None:
            continue
        label, _level, _confidence, where, summary = (f.strip() for f in rest.split("|", 4))
        path, _, line = where.rpartition(":") if re.fullmatch(r".+:\d+", where) else (where, "", "")
        found.append(Candidate(Coordinates(repo, pr, review["id"], label), marker.base, marker.head, path,
                               int(line) if line else None, summary))
    return found


def hunk_of(patch: str, line: int | None) -> str | None:
    """The hunk of a file's patch holding new-side `line`; the first when no line is named; None when none holds it."""
    hunks = re.split(r"(?m)^(?=@@ )", patch)
    hunks = [h for h in hunks if h.startswith("@@ ")]
    if line is None:
        return hunks[0] if hunks else None
    for h in hunks:
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", h)
        if m and int(m[1]) <= line < int(m[1]) + int(m[2] if m[2] is not None else 1):
            return h
    return None


def view(c: Candidate, hunk: str | None) -> str:
    """What the labeller sees: the range, the place, the summary, the hunk. Nothing else of the review."""
    where = c.path if c.line is None else f"{c.path}:{c.line}"
    return "\n".join([f"{c.coords.repo}#{c.coords.pr}  range {c.base[:12]}..{c.head[:12]}", f"at {where}", "",
                      c.summary, "", hunk if hunk is not None else "(no hunk available for this place)"])


def candidates(repo: str, prs: list[int], limit: int) -> Iterable[Candidate]:
    if not prs:
        newest = gh.api(f"repos/{repo}/pulls?state=all&per_page={limit}&sort=created&direction=desc")
        prs = sorted(p["number"] for p in newest)
    for pr in prs:
        for review in gh.api(f"repos/{repo}/pulls/{pr}/reviews", paginate=True):
            yield from findings_of(repo, pr, review)


def hunk_for(c: Candidate) -> str | None:
    if c.path == "-":
        return None
    compare = gh.api(f"repos/{c.coords.repo}/compare/{c.base}...{c.head}")
    for f in compare.get("files") or []:
        if f.get("filename") == c.path and isinstance(f.get("patch"), str):
            return hunk_of(f["patch"], c.line)
    return None


def run_label(args, ask: Callable[[str], str], out, today: Callable[[], str]) -> int:
    existing = read_ledger(args.ledger) if os.path.exists(args.ledger) else []
    done = {coordinates_of(r) for r in existing}
    for c in candidates(args.repo, args.pr, args.limit):
        if c.coords in done:
            continue
        print("\n" + view(c, hunk_for(c)), file=out)
        while True:
            answer = ask("real / not-real / unsure / skip / quit: ").strip().lower()
            if answer in LABELS:
                append_label(args.ledger, c.coords, answer, args.labeller, today())
                break
            if answer in ("skip", "quit"):
                break
        if answer == "quit":
            return 0
    print("no more unlabelled findings", file=out)
    return 0


def read_instructions(paths: list[str]) -> dict[str, str]:
    texts = {}
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                texts[path] = f.read()
        except (OSError, UnicodeDecodeError) as e:
            raise Refused(f"{path}: cannot be read: {getattr(e, 'strerror', None) or e}") from None
    return texts


def main(argv: list[str] | None = None, ask: Callable[[str], str] = input, out=None,
         today: Callable[[], str] = lambda: dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")) -> int:
    out = out or sys.stdout
    parser = argparse.ArgumentParser(prog="fabric-review-calibration", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("label", help="label the next unlabelled finding, blind")
    p.add_argument("--repo", required=True)
    p.add_argument("--pr", type=int, action="append", default=[])
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--ledger", default=LEDGER)
    p.add_argument("--labeller", default=None)
    p = sub.add_parser("split", help="the half of a finding: dev or held-out")
    p.add_argument("repo")
    p.add_argument("pr", type=int)
    p.add_argument("review", type=int)
    p.add_argument("finding")
    p = sub.add_parser("report", help="the rates per configuration, with intervals and the floor")
    p.add_argument("--runs", required=True)
    p.add_argument("--instructions", required=True, nargs="+", metavar="FILE")
    p.add_argument("--ledger", default=LEDGER)
    p.add_argument("--json", action="store_true")
    p.add_argument("--iterations", type=int, default=ITERATIONS)
    args = parser.parse_args(argv)
    try:
        if args.command == "split":
            rec = {"repo": args.repo, "pr": args.pr, "review": args.review, "finding": args.finding}
            if not _valid_coordinates(rec):
                raise Refused("coordinates are OWNER/NAME, a PR number, a review id and a label like F3")
            print(coordinates_of(rec).half(), file=out)
            return 0
        if args.command == "report":
            ledger = read_ledger(args.ledger)
            runs = read_runs(args.runs)
            check_instructions(ledger, read_instructions(args.instructions))
            report = build_report(ledger, runs, args.iterations)
            print(json.dumps(report, indent=2, sort_keys=True) if args.json else render(report), file=out)
            return 0
        args.labeller = args.labeller or getpass.getuser()
        return run_label(args, ask, out, today)
    except Refused as e:
        print(f"fabric-review-calibration: {e}", file=sys.stderr)
        return 1
    except gh.GhError as e:
        print(f"fabric-review-calibration: {e}", file=sys.stderr)
        return 1
    except EOFError:
        print("fabric-review-calibration: input ended", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
