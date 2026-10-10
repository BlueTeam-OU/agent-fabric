"""Answers of the deleted Node control plane, frozen (ADR-040 Wave 8, s8).

Some tests of the Python control plane ran the Node module beside it and
compared; the Node was deleted with the Node control plane, and the answers
it gave to those inputs are kept in tests/fixtures/node-oracle-<name>.json,
keyed by the question: a test that asks the same question gets the same
answer, and one whose input changed is told so (a new input has no Node to
ask: it is a case of its own, written as one)."""
from __future__ import annotations

import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def key(js: str, data) -> str:
    return hashlib.sha256((js + "\0" + json.dumps(data, sort_keys=True, ensure_ascii=True)).encode()).hexdigest()


class Oracle:
    def __init__(self, name: str):
        with open(os.path.join(HERE, "fixtures", f"node-oracle-{name}.json"), encoding="utf-8") as fh:
            self.table = json.load(fh)

    def node(self, js: str, data):
        """What the Node answered to `js` run on `data`."""
        try:
            return self.table[key(js, data)]
        except KeyError:
            raise KeyError("no Node answer is kept for this input: the Node is deleted, so a changed battery "
                           "is a new case with an expected value written by hand") from None
