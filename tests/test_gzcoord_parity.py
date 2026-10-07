#!/usr/bin/env python3
"""The two validators agree on every message the GZCoord suites hold
(agent-fabric ADR-040 §7, Wave 7: "both validators run over every message
the suite holds and agree on every verdict" before the Node one goes).

communication/gzcoord/tests/parity/corpus.jsonl is what the Node validator
said, recorded while it existed: the protocol and i18n suites were run
with a module hook that wrapped gzmsg.mjs's validate, parse and normalize
and appended each call's input and the Node's own answer, under the
default printer — the commands those suites spawn included (the hook,
parity/record-hook.mjs and record-loader.mjs, is in commit 9e7b195, the
last tree where the Node validator ran). The last two lines, a WAIVE: and
a WAIVES: field, were recorded from main's gzmsg.mjs at 66aa491, when #92
added WAIVES to its known keys while this branch was open; the three after
them, ids in non-ASCII digits, from the same file in review of #93.
Each distinct call is one line. The checkout's path, which the catalogue
diagnostics quote, is written {FABRIC}. Outputs that repeat the input — a
parse result, a normalized text, a validate's message — are kept as the
sha256 of their JSON; the diagnostics themselves (ok, errors, warnings, a
parse's error) are kept whole, so a disagreement reads as text.

Once the Node validator is gone the corpus cannot be re-recorded: it is
the Node's verdict, frozen, and this test holds the Python to it. One edit
since: the MESSAGE-ID hint names `gzmsg new-id`, as the command is now
called, where the recording said `gzmsg.mjs new-id`; the lines that carry
it were rewritten in place and nothing else in them.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from gzcoord import gzmsg  # noqa: E402

CORPUS = os.path.join(HERE, "communication", "gzcoord", "tests", "parity", "corpus.jsonl")
ROOT = os.path.realpath(HERE)


def sha(v) -> str:
    return hashlib.sha256(json.dumps(v, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def here(s: str) -> str:
    return s.replace("{FABRIC}", ROOT)


def main() -> int:
    with open(CORPUS, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    fails: list[str] = []
    counts: dict[str, int] = {}
    for n, r in enumerate(rows, 1):
        counts[r["fn"]] = counts.get(r["fn"], 0) + 1
        where = f"corpus line {n} ({r['fn']}): {r['text'][:60]!r}"
        if r["fn"] == "normalize":
            if sha(gzmsg.normalize(r["text"])) != r["result_sha256"]:
                fails.append(f"{where}: normalize differs — {gzmsg.normalize(r['text'])[:200]!r}")
        elif r["fn"] == "parse":
            try:
                got = gzmsg.parse(r["text"])
            except gzmsg.NotGzcoord as e:
                if str(e) != r.get("error"):
                    fails.append(f"{where}: raised {e!s}, the Node {r.get('error') or 'parsed it'}")
                continue
            if "error" in r:
                fails.append(f"{where}: parsed, the Node raised {r['error']}")
            elif sha(got) != r["result_sha256"]:
                fails.append(f"{where}: parse differs — {json.dumps(got, ensure_ascii=False)[:300]}")
        else:
            tax = r["taxonomy"]
            taxonomy = gzmsg.Taxonomy(here(tax["path"]) if tax["path"] else None, {k: k for k in tax["roles"]}) if tax else None
            got = gzmsg.validate(r["text"], taxonomy=taxonomy,
                                 max_columns=gzmsg.RELAY_MAX_COLUMNS if r["maxColumns"] is None else r["maxColumns"])
            want = {"ok": r["ok"], "errors": [here(e) for e in r["errors"]], "warnings": [here(w) for w in r["warnings"]]}
            mine = {"ok": got["ok"], "errors": got["errors"], "warnings": got["warnings"]}
            if mine != want:
                fails.append(f"{where}: verdict differs\n      node:   {json.dumps(want, ensure_ascii=False)}\n"
                             f"      python: {json.dumps(mine, ensure_ascii=False)}")
            elif sha(got["message"]) != r["message_sha256"]:
                fails.append(f"{where}: the parsed message differs — {json.dumps(got['message'], ensure_ascii=False)[:300]}")
    for f in fails:
        print(f"  FAIL {f}")
    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    print(f"test_gzcoord_parity: {'OK' if not fails else f'FAILED — {len(fails)}'} ({len(rows)} recorded calls: {summary})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
