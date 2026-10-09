"""Parity cases for control/ctl.py against runtime/control/ctl.mjs (tests/control_parity.py):
argv, the request built, who is asked, the rows and every table over replies of the shapes
an account may send — answered, silent, partial, failed, forged — the state rows, the
signing key, the drain's bundles and the memory-pressure line."""
import base64
import gzip
import hashlib

EXPECTED = [{"login": "a", "host": "h1", "address": "h1/a"}, {"login": "b", "host": "h1", "address": "h1/b"},
            {"login": "c", "host": "h2", "address": "h2/c"}, {"login": "quiet", "host": "h2", "address": "h2/quiet"}]


def rep(login, op, data, host="h1", **more):
    return {"kind": "reply", "from": f"{host}/{login}", "op": op, "data": data, **more}


ARGVS = [["all"], ["a", "ping", "--json"], ["all", "memory", "--out", "/tmp/d"], ["all", "memory"], ["all", "tokens", "--days", "3"], ["all", "tokens", "--days=14"],
         ["all", "tokens", "--days", "0"], ["all", "status", "--days", "3"], ["a", "b", "usage", "--timeout", "3"], ["all", "--nope"], ["all", "--timeout", "20s"],
         ["all", "--timeout=0"], ["all", "--timeout", "Infinity"], ["all", "--timeout", "0x10"], ["all", "--timeout"], ["all", "disk"], ["u", "accounts"],
         ["all", "upgrade", "claude"], ["all", "upgrade"], ["all", "upgrade", "kernel"], ["all", "upgrade", "claude", "--version", "2.1.282"],
         ["all", "upgrade", "claude", "--version=latest"], ["all", "upgrade", "claude", "--version"], ["all", "upgrade", "fabric", "--version", "2.1.282"],
         ["all", "status", "--version", "2.1.282"], ["x", "secrets-sync", "--expect", "183a68e97389", "--restart"], ["all", "secrets-sync", "--expect", "sk-ant-oat01-x"],
         ["all", "status", "--restart"], ["all", "secrets-sync", "--expect"], ["all", "states", "--follow", "--json"], ["all", "status", "--follow"],
         ["a", "jobs-add", "--topic", "t", "--priority", "high", "--", "-a title"], ["a", "jobs-add", "a title"], ["a", "jobs-add"], ["all", "jobs-add", "t"],
         ["a", "jobs-add", "t", "--priority", "urgent"], ["a", "status", "--topic", "t"], ["h", "pool-add", "--role", "python-dev", "t"], ["h", "pool-add", "t"],
         ["all", "pool-add", "--role", "python-dev", "t"], ["a", "pool-list"], ["a", "pool-claim"], ["all", "role", "--role", "x"], ["all", "tools-install", "doppler"],
         ["all", "tools-install"], ["all", "tools-install", "Bad Name"], ["keygen"], ["keygen", "--force"], ["a", "keygen"], [], ["-h"], ["--help"], ["all", "-h"],
         ["a", "b", "c", "presence"], ["all", "--out=/x"], ["all", "--out"], ["all", "--json", "--json"], ["all", "--timeout=5", "--timeout", "7"], ["all", "script"],
         ["all", "recall"], ["all", "host"], ["all", "keys"], ["all", "jobs"], ["all", "tools"], ["all", "local"], ["all", "local-prune"], ["all", "secrets-selftest"]]

CFG = {"ttl_s": 30}
REQ_CASES = [["a", "ping"], ["all", "tokens", "--days", "3"], ["all", "upgrade", "claude"], ["all", "upgrade", "claude", "--version", "2.1.9"], ["all", "upgrade", "fabric"],
             ["a", "jobs-add", "--topic", "t", "--project", "p", "--priority", "high", "a title"], ["a", "jobs-add", "a title"], ["h", "pool-add", "--role", "python-dev", "--topic", "t", "x"],
             ["a", "secrets-sync"], ["a", "secrets-sync", "--expect", "183a68e97389"], ["a", "secrets-sync", "--restart"], ["a", "secrets-sync", "--expect", "183a68e97389", "--restart"],
             ["a", "tools-install", "doppler"], ["a", "memory", "--out", "/x", "--timeout", "9999"], ["a", "upgrade", "claude", "--timeout", "3600"], ["a", "status", "--timeout", "1"],
             ["a", "states"]]

ROWS = {
    "status": [
        rep("a", "status", {"identity": {"role": "r", "claude_account": {"email": "x@y.z"}}, "usage": {"status": "ok", "five_hour": {"utilization": 12.5, "resets_at": "2026-09-17T10:50:00+00:00"},
                                                                                                         "seven_day": {"utilization": 0.5, "resets_at": "2026-09-21T16:00:00+00:00"}},
                            "fabric": {"status": "ok", "head": "abc1234", "behind": 2, "dirty": True}}),
        rep("b", "status", {"identity": {"claude_account": {"via": "setup-token", "token_sha256_12": "0123456789ab"}}, "usage": {"status": "no-credentials"}, "fabric": {"status": "failed"}}),
        rep("c", "status", {"identity": {"role": None, "claude_account": None}, "usage": {"status": "ok", "five_hour": None, "seven_day": {"utilization": "88", "resets_at": ""}}, "fabric": {"status": "ok", "head": "z", "behind": 0}}, host="h2"),
        rep("quiet", "status", {}, host="h2")],
    "ping": [rep("a", "ping", {}, latency_ms=0), rep("b", "ping", {}, latency_ms=120), rep("c", "ping", {}, host="h2")],
    "keys": [
        rep("a", "keys", {"keys": [{"name": "GH_TOKEN", "present": True}, {"name": "X", "present": False}, {"name": "signing key secret", "present": True}, {"name": "store commits verified", "present": True}]}),
        rep("b", "keys", {"keys": [{"name": "signing key secret", "present": False}, {"name": "store commits verified", "present": False, "refused": {"commit": "0123", "at": None, "reason": "r\u001b[2J"},
                                  "mirrors": [{"agent_id": "k", "unreadable": True}, {"agent_id": "k2", "state": "no base"}, {"agent_id": "k3", "commit": "c", "at": "T", "reason": "x"}]}]}),
        rep("c", "keys", {"keys": {"status": "failed"}}, host="h2")],
    "disk": [
        rep("a", "disk", {"disk": {"status": "ok", "total_kb": 2097152, "largest": [{"name": ".cache", "kb": 1048576}], "targets": [], "targets_kb": 0}}),
        rep("b", "disk", {"disk": {"status": "partial", "total_kb": 3072, "largest": [{"name": "x", "kb": 1536.5}], "targets": [{"path": "p/a", "kb": 1048576}, {"path": "p/b", "kb": 2048}, {"path": "p/c", "kb": 3},
                                                                                                                    {"path": "p/d", "kb": 4}], "targets_kb": 1050627, "errors": ["e1", "e2\u0007"]}}),
        rep("c", "disk", {"disk": {"status": "failed", "error": "EACCES"}}, host="h2"),
        rep("quiet", "disk", {"disk": {"status": "ok", "total_kb": None}}, host="h2")],
    "tokens": [
        rep("a", "tokens", {"identity": {"claude_account": {"email": "x@y.z"}}, "tokens": {"status": "ok", "days": 7, "models": {"opus": {"equiv": 3000000}, "z": {"equiv": 1}},
                                                                                           "claude": {"requests": 3, "cache_read": 4000000, "output": 5000, "equiv": 3000000}, "broker": {"requests": 2, "equiv": 100000}}}),
        rep("b", "tokens", {"identity": {"claude_account": {"email": "x@y.z"}}, "tokens": {"status": "ok", "days": 7, "models": {},
                                                                                           "claude": {"requests": 1, "cache_read": 999, "output": 1500, "equiv": 2500000000}, "broker": {"requests": 0, "equiv": 0}}}),
        rep("c", "tokens", {"identity": {"claude_account": None}, "tokens": {"status": "ok", "days": 7, "models": {"m": {"equiv": 0}}, "claude": {"requests": 0, "cache_read": 0, "output": 0, "equiv": 0},
                                                                              "broker": {"requests": 0, "equiv": 0}}}, host="h2"),
        rep("quiet", "tokens", {"tokens": {"status": "no-records", "days": 7}}, host="h2")],
    "host": [
        rep("a", "host", {"host": {"status": "ok", "cpus": 6, "loadavg": [0.9, 1.255, 0.8], "mem_mb": {"total": 18152, "available": 12685, "swap_free": 9216},
                                   "balloon_mb": {"current": 18345, "static_max": None}, "disk": [{"mount": "/rw", "avail_gb": 41, "use_pct": 87}],
                                   "leases": [{"name": "t", "holder": "d", "pid": 42, "since": "2026-09-19T08:26:43Z", "label": "L"}, {"name": "u"}],
                                   "top_rss": [{"user": "u", "rss_mb": 1, "comm": "c"}] * 6, "memory_pressure": {"status": "ok", "hour": {"samples": 5, "some_avg10": {"value": 1.5, "ts": "2026-09-19T08:26:43Z"}},
                                                                                                                  "last": [{"ts": "2026-09-19T08:26:43Z", "some_avg10": 0.1, "full_avg10": 0, "mem_available_mb": 12000}]}}}),
        rep("b", "host", {"host": {"status": "ok", "cpus": None, "loadavg": None, "mem_mb": None, "balloon_mb": {"current": 1, "static_max": 2}, "memory_pressure": {"status": "none"}}}),
        rep("c", "host", {"host": {"status": "failed", "error": "EACCES"}}, host="h2")],
    "accounts": [
        rep("a", "accounts", {"accounts": {"status": "ok", "accounts": [
            {"slug": "s", "email": "e@x", "status": "ok", "limits": [{"kind": "session", "percent": 5, "resets_at": "2026-09-24T18:49:59Z"}, {"kind": "weekly_scoped", "percent": None, "model": "Opus"}],
             "read_at": "2026-09-24T20:00:00Z", "error": "boom"}, {"slug": "t", "email": None, "status": "not-signed-in"}]}}),
        rep("b", "accounts", {"accounts": {"status": "none"}}), rep("c", "accounts", {"accounts": {"status": "failed", "error": "x"}}, host="h2")],
    "upgrade": [
        rep("a", "upgrade", {"upgrade": {"status": "upgraded", "from": "1", "to": "2", "session": "restarting", "settings": "refreshed"}}),
        rep("b", "upgrade", {"upgrade": {"status": "current", "piece": "fabric", "to": "abc"}}),
        rep("c", "upgrade", {"upgrade": {"status": "current", "version": "2.1"}}, host="h2"), rep("quiet", "upgrade", {"upgrade": {"status": "failed", "reason": "r", "note": "n", "settings": "s"}}, host="h2")],
    "presence": [
        rep("a", "presence", {"presence": {"status": "ok", "online": True, "sessions": 3, "since": "2026-09-25T09:57:22.000Z", "role": "r", "project": "p", "planning": True}}),
        rep("b", "presence", {"presence": {"status": "ok", "online": False, "sessions": 0, "since": None}}), rep("c", "presence", {"presence": {"status": "failed", "error": "e"}}, host="h2"),
        rep("quiet", "presence", {"presence": {"status": "ok", "online": True, "sessions": 1, "since": "2026"}}, host="h2")],
    "jobs": [
        rep("a", "jobs", {"jobs": {"status": "ok", "jobs": [{"id": "j1", "state": "active", "priority": "high", "project": "p", "title": "t\u0007", "topic": "x", "source": "owner", "blocked_on": "j0"},
                                                          {"id": "j2", "state": "queued", "title": "u", "source": "self"}, {"id": 3, "state": "q", "priority": None, "title": None}]}}),
        rep("b", "jobs", {"jobs": {"status": "ok", "jobs": []}}), rep("c", "jobs", {"jobs": {"status": "failed", "error": "e"}}, host="h2")],
    "tools": [
        rep("a", "tools", {"tools": {"status": "ok", "age_s": 30, "tools": [{"project": "p", "name": "n", "status": "missing", "version": "1.x", "where": "host"}, {"project": "p", "name": "o", "status": "missing", "optional": True},
                                                                         {"name": "x", "status": "ok"}]}}),
        rep("b", "tools", {"tools": {"status": "ok", "age_s": 3600, "tools": []}}), rep("c", "tools", {"tools": {"status": "none"}}, host="h2"),
        rep("quiet", "tools", {"tools": {"status": "ok", "age_s": 400000, "tools": [{"project": "p", "name": "n", "status": "missing"}]}}, host="h2")],
    "tools-install": [rep("a", "tools-install", {"tools-install": {"status": "installed", "tool": "doppler", "version": "3.1"}}), rep("b", "tools-install", {"tools-install": {"status": "skipped", "reason": "no wc"}}),
                      rep("c", "tools-install", {"tools-install": {"status": "failed", "tool": "t", "reason": "r\u001b"}}, host="h2")],
    "jobs-add": [rep("a", "jobs-add", {"jobs-add": {"status": "added", "job": "j9", "warning": "w"}}), rep("b", "jobs-add", {"jobs-add": {"status": "refused", "reason": "r"}})],
    "pool-add": [rep("a", "pool-add", {"pool-add": {"status": "added", "job": {"id": "p1", "role": "r", "priority": "high", "title": "t"}}}), rep("b", "pool-add", {"pool-add": {"status": "refused", "reason": "r"}})],
    "local": [rep("a", "local", {"local": {"status": "ok", "files": [{"working_copy": "wc", "status": "ok", "env": ["A", "B"], "secrets": ["A"], "permissions": {"allow": 1, "deny": 2, "ask": 3}, "keys": ["k"]},
                                                                  {"working_copy": "w2", "status": "unreadable"}, {"working_copy": "w3", "status": "ok", "env": [], "secrets": [], "permissions": {"allow": 0, "deny": 0, "ask": 0}, "keys": []}]}}),
              rep("b", "local", {"local": {"status": "ok", "files": []}}), rep("c", "local", {"local": {"status": "failed", "error": "e"}}, host="h2")],
    "local-prune": [rep("a", "local-prune", {"local-prune": {"status": "pruned", "files": [{"working_copy": "wc", "status": "pruned", "removed": ["A", "B"]}, {"working_copy": "w2", "status": "clean", "reason": "r"}]}}),
                    rep("b", "local-prune", {"local-prune": {"status": "refused", "reason": "x"}}), rep("c", "local-prune", {"local-prune": {"status": "clean", "files": []}}, host="h2")],
    "secrets-sync": [rep("a", "secrets-sync", {"secrets-sync": {"status": "synced", "claude_sign_in": {"via": "setup-token", "token_sha256_12": "0123456789ab"}, "session": "restarting"}}),
                     rep("b", "secrets-sync", {"secrets-sync": {"status": "synced", "claude_sign_in": {"via": "none: x"}, "missing": ["A", "B"]}}),
                     rep("c", "secrets-sync", {"secrets-sync": {"status": "failed", "reason": "r"}}, host="h2")],
    "secrets-selftest": [rep("a", "secrets-selftest", {"secrets-selftest": {"status": "pass", "steps": [{"step": "set", "ok": True}, {"step": "use", "ok": True}]}}),
                         rep("b", "secrets-selftest", {"secrets-selftest": {"status": "fail", "steps": [{"step": "set", "ok": True}, {"step": "use", "ok": False, "reason": "no"}]}}),
                         rep("c", "secrets-selftest", {"secrets-selftest": {"status": "fail", "reason": "r"}}, host="h2")],
    "memory": [rep("a", "memory", {"memory": {"status": "ok", "bundles": [{"slug": "s", "working_copy": "/h/a/projects/gzapp", "files": 3, "status": "ok", "written": "/o/a/gzapp.tar",
                                                                          "report": {"claims": 5, "needs_rendering": ["x"], "skipped_no_roles_class": []}},
                                                                         {"slug": "t", "files": 1, "status": "no-working-copy"},
                                                                         {"slug": "u", "working_copy": "/h/a/projects/root", "projects_root": True, "files": 2, "status": "harvest-failed", "error": "l1\nl2\nl3"},
                                                                         {"slug": "v", "working_copy": "/w/x", "files": 0, "status": "wrong-agent", "manifest_agent": None}]}}),
               rep("b", "memory", {"memory": {"status": "failed", "error": "boom"}}), rep("c", "memory", {"memory": {"status": "ok", "bundles": []}}, host="h2")],
    "script": [
        rep("a", "script", {"script": {"status": "ok", "turns": 3, "text": {"letters": 40, "georgian": 100, "files": 2}, "thinking_blocks": {"only": 1, "mixed": 0, "latin": 2, "empty": 3},
                                       "notes": {"status": "ok", "files": 1, "letters": 9, "georgian": 100, "blocks": {"only": 2, "mixed": 0, "latin": 0},
                                                 "language": {"status": "ok", "paragraphs": 2, "unreliable": 1, "shares": {"ka": 100, "en": 0}}},
                                       "workers": {"status": "ok", "files": 2, "input": {"blocks": {"only": 3, "mixed": 0, "latin": 1}, "language": {"status": "ok", "paragraphs": 4, "unreliable": 0, "shares": {"ka": 71.4}}},
                                                   "text": {"blocks": {"only": 4, "mixed": 0, "latin": 0}, "language": {"status": "unavailable"}}}}}),
        rep("b", "script", {"script": {"status": "ok", "turns": 0, "text": {"letters": 0}, "thinking_blocks": None, "notes": {"status": "not measured", "reason": "src"}, "workers": {"status": "none"}}}),
        rep("c", "script", {"script": {"status": "failed", "notes": {"status": "none"}}}, host="h2")],
    "recall": [rep("a", "recall", {"recall": {"status": "ok", "sessions": 5, "sessions_without_recall": 1, "turns": 40, "index": 3, "slice": 2, "search": 1, "identity": 4, "top": [{"path": "p/x", "reads": 7}]}}),
               rep("b", "recall", {"recall": {"status": "ok", "sessions": 0, "sessions_without_recall": 0, "turns": 0, "index": 0, "slice": 0, "search": 0, "identity": 0, "top": []}}),
               rep("c", "recall", {"recall": {"status": "failed"}}, host="h2")],
}
OPS = list(ROWS)
PRESSURE = [[], [None], [{"status": "none"}], [{"status": "failed", "error": "e\u0007"}], [{"status": "weird"}],
            [{"status": "ok", "hour": {"samples": 2, "some_avg10": {"value": 1, "ts": "2026-09-19T08:26:43Z"}, "full_avg10": None, "mem_available_mb": {"value": 100, "ts": "t"}}, "last": []},
             {"status": "ok", "hour": {"samples": 9}, "last": [{"ts": "2026-09-19T08:26:43Z", "some_avg10": 0.5, "full_avg10": None, "mem_available_mb": 5}]}], [{"status": "ok"}]]

CASES = [
    {"name": "argv: every shape, accepted or refused with the Node's words", "module": "ctl", "input": ARGVS,
     "node": "return input.map(a => { try { return m.parseArgs(a); } catch (e) { return { error: e.message }; } });",
     "py": "out = []\nfor a in input:\n    try:\n        out.append(m.parse_args(a))\n    except m.CtlError as e:\n        out.append({'error': str(e)})\nreturn out"},
    {"name": "the request built for every op shape", "module": "ctl", "input": {"argvs": REQ_CASES, "cfg": CFG},
     "node": "return input.argvs.map(a => { const p = m.parseArgs(a); return m.buildRequest(p, { id: 'i', from: 'h/me', to: '*', cfg: input.cfg, ts: 'T', commit: () => 'c'.repeat(40), version: () => '2.1.1' }); });",
     "py": "return [m.build_request(m.parse_args(a), id='i', from_='h/me', to='*', cfg=input['cfg'], ts='T', commit=lambda: 'c' * 40, version=lambda: '2.1.1') for a in input['argvs']]"},
    {"name": "who is asked, from the fixture's registry (humans never)", "module": "ctl", "input": [["all"], ["user"], ["nobody"], ["user", "nobody"], ["a", "b"]],
     "node": "const placed = m.placements(home.registry); return [placed, input.map(t => m.targetsOf(t, placed))];",
     "py": "placed = m.placements(home['registry'])\nreturn [placed, [m.targets_of(t, placed) for t in input]]"},
    {"name": "state rows over records of every shape", "module": "ctl", "input": None,
     "node": "const now = Date.parse('2026-10-07T12:00:00Z'); const r = (extra) => ({ ts: '2026-10-07T11:59:00Z', sessions: [], ...extra });"
             "return [m.stateRow('a', undefined, now), m.stateRow('a', r({}), now), m.stateRow('a', r({ role: 'x', project: 'p', sessions: [{ session: 's', state: 'idle', since: 't' }, { session: 'u', state: 'blocked' }, { session: 'v', state: 'working', since: 'w' }] }), now),"
             " m.stateRow('a', r({ last_session: 'abcdefgh', resumable: true }), now), m.stateRow('a', r({ last_session: 'abcdefgh', resumable: 1 }), now), m.stateRow('a', r({ ts: '2026-10-07T11:00:00Z' }), now),"
             " m.stateRow('a', r({ ts: 'nonsense' }), now), m.stateRow('a', r({ sessions: [{ session: 's', state: 'zzz' }] }), now), m.stateRow('a', r({ sessions: 'x' }), now)];",
     "py": "now = 1791374400000.0\nr = lambda **extra: {'ts': '2026-10-07T11:59:00Z', 'sessions': [], **extra}\n"
           "return [m.state_row('a', None, now), m.state_row('a', r(), now), m.state_row('a', r(role='x', project='p', sessions=[{'session': 's', 'state': 'idle', 'since': 't'}, {'session': 'u', 'state': 'blocked'}, {'session': 'v', 'state': 'working', 'since': 'w'}]), now),"
           " m.state_row('a', r(last_session='abcdefgh', resumable=True), now), m.state_row('a', r(last_session='abcdefgh', resumable=1), now), m.state_row('a', r(ts='2026-10-07T11:00:00Z'), now),"
           " m.state_row('a', r(ts='nonsense'), now), m.state_row('a', r(sessions=[{'session': 's', 'state': 'zzz'}]), now), m.state_row('a', r(sessions='x'), now)]"},
    {"name": "state records: which a relay-token holder's post is shown", "module": "ctl", "input": None,
     "node": "const want = new Set(['h/a']); const ts = '2026-10-07T11:59:00Z'; const c = o => ({ content: JSON.stringify(o) });"
             "const base = { v: 1, kind: 'state', from: 'h/a', ts, sessions: [] };"
             "const variants = [base, { ...base, v: 2 }, { ...base, v: true }, { ...base, kind: 'reply' }, { ...base, from: 'h/z' }, { ...base, from: ['h/a'] }, { ...base, ts: 5 }, { ...base, role: 3 }, { ...base, role: null },"
             " { ...base, project: {} }, { ...base, last_session: 'abcdefgh' }, { ...base, last_session: 'abc' }, { ...base, last_session: 'abcdefgh!' }, { ...base, resumable: false }, { ...base, resumable: 0 }, { ...base, sessions: [{ session: 's', state: 'x' }] },"
             " { ...base, sessions: [{ session: 's', state: 'x', since: 3 }] }, { ...base, sessions: [{ session: 1, state: 'x' }] }, { ...base, sessions: 'x' }, { ...base, sessions: [null] }];"
             "return [...variants.map(v => m.stateRecordOf(c(v), want) !== null), m.stateRecordOf({ content: 'not json' }, want) !== null, m.stateRecordOf({}, want) !== null, m.stateRecordOf(null, want) !== null];",
     "py": "want = {'h/a'}\nts = '2026-10-07T11:59:00Z'\nimport json\nc = lambda o: {'content': json.dumps(o)}\nbase = {'v': 1, 'kind': 'state', 'from': 'h/a', 'ts': ts, 'sessions': []}\n"
           "variants = [base, {**base, 'v': 2}, {**base, 'v': True}, {**base, 'kind': 'reply'}, {**base, 'from': 'h/z'}, {**base, 'from': ['h/a']}, {**base, 'ts': 5}, {**base, 'role': 3}, {**base, 'role': None},"
           " {**base, 'project': {}}, {**base, 'last_session': 'abcdefgh'}, {**base, 'last_session': 'abc'}, {**base, 'last_session': 'abcdefgh!'}, {**base, 'resumable': False}, {**base, 'resumable': 0}, {**base, 'sessions': [{'session': 's', 'state': 'x'}]},"
           " {**base, 'sessions': [{'session': 's', 'state': 'x', 'since': 3}]}, {**base, 'sessions': [{'session': 1, 'state': 'x'}]}, {**base, 'sessions': 'x'}, {**base, 'sessions': [None]}]\n"
           "return [*[m.state_record_of(c(v), want) is not None for v in variants], m.state_record_of({'content': 'not json'}, want) is not None, m.state_record_of({}, want) is not None, m.state_record_of(None, want) is not None]"},
    {"name": "the memory-pressure line over every answer", "module": "ctl", "input": PRESSURE,
     "node": "return input.map(a => m.pressureText(a));", "py": "return [m.pressure_text(a) for a in input]"},
]


def table_case(op):
    return {"name": f"rows and the {op} table over answered, silent, partial, failed and odd replies", "module": "ctl", "input": {"op": op, "expected": EXPECTED, "replies": ROWS[op]},
            "node": "const rs = m.rows(input.expected, input.replies); return { rows: rs, table: m.table(input.op, rs) };",
            "py": "rs = m.rows(input['expected'], input['replies'])\nreturn {'rows': rs, 'table': m.table(input['op'], rs)}"}


CASES += [table_case(op) for op in OPS]
CASES.append({"name": "the table of an op with no replies at all, for every op", "module": "ctl", "input": {"ops": OPS + ["usage", "identity", "fabric", "session"], "expected": EXPECTED},
              "node": "return input.ops.map(op => m.table(op, m.rows(input.expected, [])));",
              "py": "return [m.table(op, m.rows(input['expected'], [])) for op in input['ops']]"})


# Every table over a corpus of forged replies: each field of every reply of every
# op, scalar or container, one at a time, replaced by a value of another kind. Where the Node prints a
# table (it refuses some shapes with a TypeError), so does Python, the same one.
FUZZ_VARIANTS = [None, "", 0, 5, 1.5, True, "x", "\u001b[2J", [], {}, ["x"], {"a": 1}, [5], [None], [{}]]


def _leaves(obj, path=()):
    yield path
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaves(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            yield from _leaves(v, path + (i,))


def fuzz_mutations():
    out = []
    for op, replies in ROWS.items():
        for ri, r in enumerate(replies):
            for path in _leaves(r["data"]):
                if not path:
                    continue
                # A string or an array in place of a refusal record: the Node reads
                # `.at` off it and prints String.prototype.at's source ("function at()
                # { [native code] }"); that is JavaScript's, not the contract.
                quirk = op == "keys" and ("refused" in path or "mirrors" in path)
                out += [[op, ri, list(path), v] for v in FUZZ_VARIANTS if not (quirk and isinstance(v, (str, list)))]
    return out


CASES.append({"name": "every table over replies with each field replaced by a value of another kind", "module": "ctl", "lenient_node_throw": True,
              "input": {"rows": ROWS, "expected": EXPECTED, "mutations": fuzz_mutations()},
              "node": "const crypto = await import('node:crypto');"
                      "const put = (o, path, v) => { for (const k of path.slice(0, -1)) o = o[k]; o[path.at(-1)] = v; };"
                      "return input.mutations.map(([op, ri, path, v]) => { const replies = structuredClone(input.rows[op]); put(replies[ri].data, path, v);"
                      " try { return crypto.createHash('sha256').update(m.table(op, m.rows(input.expected, replies))).digest('hex'); } catch (e) { return { threw: String(e.message).slice(0, 60) }; } });",
              "py": "import copy, hashlib\n\ndef put(o, path, v):\n    for k in path[:-1]:\n        o = o[k]\n    o[path[-1]] = v\n\n"
                    "out = []\nfor op, ri, path, v in input['mutations']:\n    replies = copy.deepcopy(input['rows'][op])\n    put(replies[ri]['data'], path, v)\n    try:\n"
                    "        out.append(hashlib.sha256(m.table(op, m.rows(input['expected'], replies)).encode()).hexdigest())\n    except Exception as e:\n"
                    "        out.append({'threw': f'{type(e).__name__}: {e}'[:60]})\nreturn out"})


def _tar(manifest_bytes, name=b"manifest.json", size=None):
    body = manifest_bytes
    h = bytearray(512)
    h[0:len(name)] = name
    sz = (f"{len(body):o}".rjust(11, "0") + "\0").encode() if size is None else size
    h[124:124 + len(sz)] = sz
    return bytes(h) + body + b"\0" * ((512 - len(body) % 512) % 512) + b"x" * 700


_TARS = {
    "ok": _tar(b'{"agent":"db-admin","host":"h"}\n'), "other": _tar(b'{"agent":"web-dev-01"}\n'), "null": _tar(b'{"agent":null}'), "number": _tar(b'{"agent":5}'),
    "bad json": _tar(b"not json"), "wrong name": _tar(b'{"agent":"db-admin"}', name=b"other.json"), "garbage size": _tar(b'{"agent":"db-admin"}', size=b"zzzzzzzzzzz\0"),
    "blank size": _tar(b'{"agent":"db-admin"}', size=b"           \0"), "short": b"manifest.json" + b"\0" * 100, "empty": b"", "size past the end": _tar(b'{"agent":"db-admin"}', size=b"77777777777\0"),
    "size 0": _tar(b'{"agent":"db-admin"}', size=b"00000000000\0"), "array": _tar(b'["agent"]'), "string": _tar(b'"agent"'), "nul in name": _tar(b'{"agent":"db-admin"}', name=b"manifest.json\0junk"),
}
CASES.append({"name": "the harvester's manifest: whose a tar says it is, over every malformed header", "module": "ctl",
              "input": {k: base64.b64encode(v).decode() for k, v in _TARS.items()},
              "node": "return Object.fromEntries(Object.entries(input).map(([k, b]) => [k, m.manifestAgent(Buffer.from(b, 'base64'))]));",
              "py": "import base64\nreturn {k: m.manifest_agent(base64.b64decode(b)) for k, b in input.items()}"})
CASES.append({"name": "the key of a drain part", "module": "ctl", "input": [["h/a", {"slug": "s", "part": 1}], ["h/a", {}], ["h/a", None], ["h/a", {"slug": None, "part": "2"}], ["x", {"slug": "s\u0000t", "part": 1.5}]],
              "node": "return input.map(([f, p]) => m.partKey(f, p));", "py": "return [m.part_key(f, p) for f, p in input]"})

_TAR = _tar(b'{"agent":"db-admin","host":"h"}\n')
_B64 = base64.b64encode(gzip.compress(_TAR, mtime=0)).decode()
_CUT = -(-len(_B64) // 2)
_CH = [_B64[:_CUT], _B64[_CUT:]]
_SHA = hashlib.sha256(_TAR).hexdigest()
_EXP = [{"login": "db-admin", "host": "h", "address": "h/db-admin"}, {"login": "web-dev-01", "host": "h", "address": "h/web-dev-01"}, {"login": "silent", "host": "h", "address": "h/silent"}]


def _bundle(slug, wc, **over):
    return {"slug": slug, "working_copy": wc, "files": 2, "status": "ok", "bytes": len(_TAR), "sha256": _SHA, "parts": 2, **over}


_REPLIES = [
    {"from": "h/db-admin", "data": {"memory": {"status": "ok", "bundles": [_bundle("s-a", "/h/db-admin/projects/gzapp"), _bundle("s-b", "/h/db-admin/projects/other", sha256="nope"),
                                                                           _bundle("s-c", "/h/db-admin/projects/short"), {"slug": "s-d", "files": 1, "status": "no-working-copy"},
                                                                           _bundle("s-r", "/h/db-admin/projects/agent-fabric", projects_root=True), _bundle("s-f", "/h/db-admin/projects/agent-fabric"),
                                                                           _bundle("s-g", "/h/db-admin/projects/agent-fabric")]}}},
    {"from": "h/web-dev-01", "data": {"memory": {"status": "ok", "bundles": [_bundle("s-e", "/h/web-dev-01/projects/gzapp"), _bundle("s-w", "/h/web-dev-01/projects/gzapp2")]}}},
    {"from": "h/stranger", "data": {"memory": {"status": "ok", "bundles": [_bundle("s-z", "/h/x/projects/z")]}}}]
_PARTS = {"h/db-admin": [{"slug": "s-b", "part": 1, "parts": 2, "chunk": _CH[0]}, {"slug": "s-a", "part": 2, "parts": 2, "chunk": _CH[1]}, {"slug": "s-b", "part": 2, "parts": 2, "chunk": _CH[1]},
                         {"slug": "s-a", "part": 1, "parts": 2, "chunk": _CH[0]}, {"slug": "s-a", "part": 1, "parts": 2, "chunk": "replayed"}, {"slug": "s-c", "part": 1, "parts": 2, "chunk": _CH[0]},
                         {"slug": "s-r", "part": 1, "parts": 2, "chunk": _CH[0]}, {"slug": "s-r", "part": 2, "parts": 2, "chunk": _CH[1]},
                         {"slug": "s-f", "part": 1, "parts": 2, "chunk": _CH[0]}, {"slug": "s-f", "part": 2, "parts": 2, "chunk": _CH[1]},
                         {"slug": "s-g", "part": 1, "parts": 2, "chunk": _CH[0]}, {"slug": "s-g", "part": 2, "parts": 2, "chunk": _CH[1]}],
          "h/web-dev-01": [{"slug": "s-e", "part": 1, "parts": 2, "chunk": "not base64 of a gzip!!"}, {"slug": "s-e", "part": 2, "parts": 2, "chunk": ""},
                           {"slug": "s-w", "part": 1, "parts": 2, "chunk": _CH[0]}, {"slug": "s-w", "part": 2, "parts": 2, "chunk": _CH[1]}]}
CASES.append({"name": "the drain's bundles reassembled and written: the same files, the same statuses", "module": "ctl",
              "input": {"expected": _EXP, "replies": _REPLIES, "parts": _PARTS},
              "files": ["out/db-admin/gzapp.tar", "out/db-admin/agent-fabric.tar", "out/db-admin/agent-fabric-projects-root.tar", "out/db-admin/other.tar", "out/web-dev-01/gzapp.tar",
                        "out/web-dev-01/gzapp2.tar", "out/silent/x.tar", "out/h/z.tar"],
              "node": "const parts = {}; for (const [from, list] of Object.entries(input.parts)) { const mp = new Map(); for (const p of list) { const k = m.partKey(from, p); if (!mp.has(k)) mp.set(k, p); } parts[from] = mp; }"
                      "const replies = structuredClone(input.replies); m.writeBundles(`${home.root}/out`, input.expected, replies, parts);"
                      "const fs = await import('node:fs'); const modes = {}; for (const f of ['out', 'out/db-admin', 'out/db-admin/gzapp.tar']) modes[f] = (fs.statSync(`${home.root}/${f}`).mode & 0o777).toString(8);"
                      "return { replies, modes, listing: fs.readdirSync(`${home.root}/out/db-admin`).sort(), webdev: fs.existsSync(`${home.root}/out/web-dev-01`) ? fs.readdirSync(`${home.root}/out/web-dev-01`).sort() : null, top: fs.readdirSync(`${home.root}/out`).sort() };",
              "py": "import copy, os\nparts = {}\nfor frm, lst in input['parts'].items():\n    mp = {}\n    for p in lst:\n        mp.setdefault(m.part_key(frm, p), p)\n    parts[frm] = mp\n"
                    "replies = copy.deepcopy(input['replies'])\nm.write_bundles(os.path.join(home['root'], 'out'), input['expected'], replies, parts)\n"
                    "modes = {f: format(os.stat(os.path.join(home['root'], f)).st_mode & 0o777, 'o') for f in ('out', 'out/db-admin', 'out/db-admin/gzapp.tar')}\n"
                    "return {'replies': replies, 'modes': modes, 'listing': sorted(os.listdir(os.path.join(home['root'], 'out', 'db-admin'))), 'webdev': sorted(os.listdir(os.path.join(home['root'], 'out', 'web-dev-01'))) if os.path.exists(os.path.join(home['root'], 'out', 'web-dev-01')) else None, 'top': sorted(os.listdir(os.path.join(home['root'], 'out')))}"})

_NOW = 1791374400000
_TS = "2026-10-07T11:59:00Z"


def _st(frm, state_list, ts=_TS, **extra):
    import json as _j
    return {"id": f"{frm}-{ts}", "content": _j.dumps({"v": 1, "kind": "state", "from": frm, "ts": ts, "sessions": state_list, **extra})}


_STATES = {"messages": [
    _st("h/a", [{"session": "s1", "state": "idle", "since": "t1"}, {"session": "s2", "state": "blocked", "since": "t2"}], role="web-dev", project="gzapp"),
    _st("h/b", [], "2026-10-07T11:00:00Z"), _st("h/c", [{"session": "s", "state": "working", "since": "w\u001b[2J"}], role="r\u001b]0;x\u0007", last_session="0f0e0d0c-1111-4222-8333-444455556666", resumable=True),
    _st("h/e", [{"session": "s", "state": "zzz"}, {"session": "t", "state": "working"}]), {"id": "j", "content": "junk"}, {"id": "o", "content": "{}"}]}
CASES.append({"name": "states: a snapshot, as rows in JSON and as text, and the exit code", "module": "ctl",
              "input": {"messages": _STATES["messages"], "expected": [{"address": a} for a in ("h/a", "h/b", "h/c", "h/d", "h/e")], "now": _NOW},
              "node": "const out = []; const err = []; const run = async json => { const lines = []; const rc = await m.states({ json, follow: false }, input.expected, { call: async p => ({ messages: input.messages }),"
                      " cfg: { channel: 'c', state_channel: 'c:state', relay_url: 'x' }, out: l => lines.push(l), err: e => err.push(e), now: () => input.now }); return { rc, lines }; };"
                      "return { json: await run(true), text: await run(false), err };",
              "py": "def run(json_):\n    lines = []\n    rc = m.states({'json': json_, 'follow': False}, input['expected'], call=lambda p, **kw: {'messages': input['messages']},"
                    " cfg={'channel': 'c', 'state_channel': 'c:state', 'relay_url': 'x'}, out=lines.append, err=lambda e: None, now=lambda: input['now'])\n    return {'rc': rc, 'lines': lines}\n"
                    "return {'json': run(True), 'text': run(False), 'err': []}"})
CASES.append({"name": "the signing key's every failure, and the store directory", "module": "ctl", "input": None,
              "node": "const fs = await import('node:fs'); const path = await import('node:path'); const root = home.root; const out = [];"
                      "out.push(m.storeDir({ AGENT_FABRIC_SECRET_STORE: '/s' }, '/h'), m.storeDir({ AGENT_FABRIC_SECRET_STORE: '' }, '/h'), m.storeDir({}, '/h'));"
                      "out.push(m.signingKey({ store: path.join(root, 'none') }).error.replace(root, '<root>'));"
                      "fs.mkdirSync(path.join(root, 's', 'env'), { recursive: true }); out.push(m.signingKey({ store: path.join(root, 's') }).error.replace(root, '<root>'));"
                      "fs.writeFileSync(path.join(root, 's', 'env', 'FABRIC_CONTROL_SIGNING_KEY.gpg'), 'x');"
                      "const run = r => () => r; const err = code => Object.assign(new Error('x'), { code });"
                      "for (const r of [{ error: err('ENOENT') }, { error: err('ETIMEDOUT') }, { error: new Error('boom') }, { status: 2, stdout: '', stderr: 'a\\nb: gone\\n' }, { status: 2, stdout: '', stderr: '' }, { status: null, signal: 'SIGKILL', stdout: '', stderr: '' },"
                      " { status: 0, stdout: '\\n', stderr: '' }, { status: 0, stdout: '  \\nsecond', stderr: '' }, { status: 0, stdout: 'ed25519-pkcs8:AAAA\\nsecond\\n', stderr: '' }]) out.push(m.signingKey({ store: path.join(root, 's'), run: run(r) }));"
                      "return out;",
              "py": "import os, subprocess\nroot = home['root']\nout = [m.store_dir({'AGENT_FABRIC_SECRET_STORE': '/s'}, '/h'), m.store_dir({'AGENT_FABRIC_SECRET_STORE': ''}, '/h'), m.store_dir({}, '/h')]\n"
                    "out.append(m.signing_key(os.path.join(root, 'none'))['error'].replace(root, '<root>'))\nos.makedirs(os.path.join(root, 's', 'env'))\n"
                    "out.append(m.signing_key(os.path.join(root, 's'))['error'].replace(root, '<root>'))\n"
                    "open(os.path.join(root, 's', 'env', 'FABRIC_CONTROL_SIGNING_KEY.gpg'), 'w').write('x')\n"
                    "def run(r):\n    def go(cmd, **kw):\n        if isinstance(r, BaseException):\n            raise r\n        return r\n    return go\n"
                    "done = lambda code, o='', e='': subprocess.CompletedProcess([], code, o, e)\n"
                    "for r in [FileNotFoundError(2, 'gpg'), subprocess.TimeoutExpired('gpg', 30), OSError(5, 'boom'), done(2, '', 'a\\nb: gone\\n'), done(2), done(-9), done(0, '\\n'), done(0, '  \\nsecond'), done(0, 'ed25519-pkcs8:AAAA\\nsecond\\n')]:\n"
                    "    out.append(m.signing_key(os.path.join(root, 's'), run(r)))\nreturn out"})
