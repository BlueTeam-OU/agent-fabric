"""Parity cases for control/jobs.py against runtime/control/jobs.mjs (tests/control_parity.py).
jobs-add and jobs run the real tools/fabric/jobs.py in each side's fixture home.

jobs.py adds to the list of the login it runs as, which is the runner's
(home["self"]), never a fixture account: the login is the euid's, and no
environment makes it another. Its list is under the fixture's state dir,
and is compared as stored, but for the times each side wrote it at.
The bytes are not: jobs.py stamps the wall clock, which a subprocess's
caller cannot set."""
CASES = [
    {"name": "check_job_args on what a request may carry", "module": "jobs",
     "input": [None, {"title": "x"}, {"title": "x", "extra": 1}, {"title": ""}, {"title": "a\nb"}, {"title": "x" * 301},
               {"title": "x", "project": "../etc"}, {"title": "x", "project": None}, {"title": "x", "project": 5},
               {"title": "x", "priority": "urgent"}, {"title": "a\u009b31m"}, {"title": "\U0001F600" * 151}, {"title": "x", "2": 1, "1": 2}],
     "node": "return input.map(a => m.checkJobArgs(a));", "py": "return [m.check_job_args(a) for a in input]"},
    {"name": "jobs-add of the owner's job, then jobs: the list as each side reads it", "module": "jobs",
     "input": {"from": "h/user", "to": ["h/py"], "args": {"title": "-port \u00e9 it", "topic": "wave-8", "priority": "high"}},
     "node": "const opts = { home: home.homes.py, root: process.env.AGENT_FABRIC_ROOT }; process.env.AGENT_FABRIC_STATE_DIR = home.state;"
             "const a = await m.jobsAdd(input, opts); const l = await m.jobs(opts);"
             "const at = new Set(['created', 'updated', 'at', 'updated_at']);"
             "const stored = JSON.parse((await import('node:fs')).readFileSync(`${home.state}/agents/${home.self}/jobs.json`, 'utf8'),"
             " (k, v) => at.has(k) ? '<t>' : v);"
             "return [a.status, l.jobs.map(j => [j.id, j.title, j.topic, j.priority, j.source]), stored];",
     "py": "import os\nopts = dict(home=home['homes']['py'], root=os.environ['AGENT_FABRIC_ROOT'])\n"
           "a = m.jobs_add(input, **opts)\nlisted = m.jobs(**opts)\n"
           "def times(v):\n"
           "    if isinstance(v, dict):\n"
           "        return {k: '<t>' if k in ('created', 'updated', 'at', 'updated_at') else times(x) for k, x in v.items()}\n"
           "    return [times(x) for x in v] if isinstance(v, list) else v\n"
           "with open(os.path.join(home['state'], 'agents', home['self'], 'jobs.json'), encoding='utf-8') as fh:\n"
           "    stored = times(js.json_parse(fh.read()))\n"
           "return [a['status'], [[j['id'], j['title'], j['topic'], j['priority'], j['source']] for j in listed['jobs']], stored]"},
    {"name": "a jobs-add to more than one login runs nothing", "module": "jobs",
     "input": {"from": "h/user", "to": ["h/py", "h/web"], "args": {"title": "x"}},
     "node": "return await m.jobsAdd(input, { exec: async () => { throw new Error('ran'); } });",
     "py": "def run(*a, **k):\n    raise AssertionError('ran')\nreturn m.jobs_add(input, run=run)"},
]
