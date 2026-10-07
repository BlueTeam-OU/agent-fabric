// runtime/control/ops.mjs — what a control agent can say about its own
// account, as pure extractors: each takes its inputs (a home, a fetch, an
// exec) so a test runs them against a scratch home and a fake relay, and
// each returns only fixed, whitelisted keys — never a value from a secret.
// The fingerprints are the one place a secret is read: hashed in place,
// twelve hex digits of its sha256, enough to tell two keys apart and
// nothing else (the CEO, 2026-09-17: "the username it logs in with, or
// the api key hash").
//
// A section that cannot be read says so inline ({status: ...}) rather than
// throwing: a reply always arrives, and its gaps are named.
//
// The extractors live in ops/, one module per subject; this module keeps the
// op names, the dispatch, and every name it exported before the split, so
// no importer changed.

import { jobs } from './jobs.mjs';
import { memoryPressure } from './pressure.mjs';
import { identity, fabric, session, presence } from './ops/identity.mjs';
import { usage, accounts, tokens } from './ops/usage.mjs';
import { keys, storeRefusal, signingSecret } from './ops/keys.mjs';
import { host, disk } from './ops/host.mjs';
import { recall, script } from './ops/activity.mjs';
import { memory } from './ops/memory.mjs';
import { local } from './local.mjs';

export { identity, fabric, session, presence } from './ops/identity.mjs';
export { USAGE_URL, usage, ACCOUNTS_TIMEOUT_MS, ACCOUNT_SLUG, accountsDir, takeReadLock, accountSlugs, claudeBin, parseUsageReport, readAccount, accounts, TOKEN_RATIOS, TOKENS_DAYS, equivalent, tokens } from './ops/usage.mjs';
export { KEY_NAMES, keys, STORE_ROW, storeRefusal, SIGNING_ROW, signingSecret } from './ops/keys.mjs';
export { host, DISK_TIMEOUT_MS, DISK_MAX_BUFFER, DISK_TOP, disk } from './ops/host.mjs';
export { scriptCounts, langidCmd, languages, recallKind, recall, notesDir, script, WORKER_TYPE, workerTranscripts } from './ops/activity.mjs';
export { MEMORY_PART_BYTES, memorySlug, memoryDirs, memory } from './ops/memory.mjs';


export const OPS = ['ping', 'identity', 'usage', 'keys', 'fabric', 'session', 'script', 'recall', 'tokens', 'memory', 'host', 'disk', 'accounts', 'upgrade', 'secrets-sync', 'status', 'presence', 'jobs', 'jobs-add', 'local', 'local-prune', 'secrets-selftest'];

// Answered for any placed account, not only an operator: whether a session
// is running is what every sender needs before it writes to one, and it
// names nothing a relay reader could not already infer (the owner,
// 2026-09-25: presence moves from HELLO/GOODBYE, now retired, to the
// control plane).
export const PUBLIC_OPS = ['presence'];


// Everything, for `status`; the sections a request names, otherwise.
export async function collect(op, ctx = {}) {
  const wants = op === 'status' ? ['identity', 'usage', 'keys', 'fabric', 'session'] : op === 'tokens' ? ['identity', 'tokens'] : [op];
  const data = {};
  const guard = async (name, fn) => { try { data[name] = await fn(); } catch (e) { data[name] = { status: 'failed', error: String(e?.message ?? e).slice(0, 200) }; } };
  await Promise.all(wants.map(name => {
    if (name === 'identity') return guard(name, () => identity(ctx.home, ctx.who));   // ctx.who unset: whoami() per request, so a rebind shows
    if (name === 'usage') return guard(name, () => ctx.usageCached ? ctx.usageCached() : usage(ctx.home, ctx.fetch));
    if (name === 'keys') return guard(name, async () => [...keys(ctx.home), await signingSecret(ctx.exec), storeRefusal(ctx.home, ctx.storeDir)]);
    if (name === 'fabric') return guard(name, () => fabric(ctx.root, ctx.exec));
    if (name === 'session') return guard(name, () => session(ctx.uid, ctx.exec));
    if (name === 'presence') return guard(name, () => presence(ctx.presenceOpts));
    if (name === 'script') return guard(name, () => script(ctx.home));
    if (name === 'recall') return guard(name, () => recall(ctx.home));
    if (name === 'tokens') return guard(name, () => tokens(ctx.home, ctx.days ? { days: ctx.days } : {}));
    if (name === 'memory') return guard(name, () => memory(ctx.home, { exec: ctx.exec, all: true }));
    // The machine now, and the pressure this daemon sampled up to now (pressure.mjs).
    if (name === 'host') return guard(name, () => ({ ...host(ctx.hostOpts), memory_pressure: memoryPressure(ctx.pressureOpts) }));
    // One scan per daemon however many ask at once (agentd's diskKeeper).
    if (name === 'disk') return guard(name, () => ctx.diskCached ? ctx.diskCached() : disk(ctx.home, ctx.diskOpts));
    if (name === 'local') return guard(name, () => local({ home: ctx.home, root: ctx.root }));
    if (name === 'jobs') return guard(name, () => jobs({ home: ctx.home, root: ctx.root, ...(ctx.jobsOpts ?? {}) }));
    if (name === 'accounts') return guard(name, () => ctx.accountsCached ? ctx.accountsCached() : accounts(ctx.home, ctx.accountsOpts));
    return Promise.resolve();
  }));
  return data;
}
