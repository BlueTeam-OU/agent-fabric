"""Parity cases for control/protocol.py and control/gzcoord.py's own pieces (tests/control_parity.py)."""
CASES = [
    {"name": "the envelopes' keys", "module": "protocol", "input": None,
     "node": "return m.ENVELOPE_KEYS;",
     "py": "return {k: {'required': list(v['required']), 'optional': list(v['optional'])} for k, v in m.ENVELOPE_KEYS.items()}"},
    {"name": "gzcoord: api_timeout and shell_word on every shape", "module": "gzcoord",
     "input": {"paths": ["/api/messages", "/api/wait?timeout_seconds=55", "/x?timeout_seconds=0x10", "/x?timeout_seconds=1_0", "/x?timeout_seconds=5?y=1"],
               "words": ["'a'\"'\"'b' tail", "a\\ b c", "''", "'open", "a 'b", "ab-c/d=e:f"]},
     "node": "return [input.paths.map(p => m.apiTimeoutMs(p) / 1000), input.words.map(w => m.shellWord(w))];",
     "py": "return [[m.api_timeout_s(p) for p in input['paths']], [m.shell_word(w) for w in input['words']]]"},
]
