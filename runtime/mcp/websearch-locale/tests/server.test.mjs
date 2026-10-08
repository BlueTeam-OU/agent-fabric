// The locale search server: the locale fixes country and languages per
// engine, the caller only the query; every secret goes into one header
// and nowhere else; the MCP subset answers what Claude Code asks, one
// tool per configured engine.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { scratch } from '../../../../tests/scratch.mjs';
import { readLocale, request, search, handle, tools , stripTags } from '../server.mjs';
import { fileURLToPath } from 'node:url';

const SERVER = fileURLToPath(new URL('../server.mjs', import.meta.url));
const LOCALE = { timezone: 'Asia/Tbilisi',
                 serpapi: { gl: 'ge', hl: 'ka', google_domain: 'google.ge', tool_description: 'ვებ-ძიება ქართულად', label: 'ძირითადი ძრავა' },
                 brave: { country: 'ALL', tool_description: 'გლობალური ვებ-ძიება' } };
const G = { SERPAPI_API_KEY: 'serpapi-secret-key-value-0123456789' };
const B = { BRAVE_SEARCH_API_KEY: 'BSA-secret-key-value-0123456789' };
const localeFile = (l = LOCALE) => { const f = path.join(scratch('loc-'), 'locale.json'); fs.writeFileSync(f, JSON.stringify(l)); return f; };

test('readLocale: an engine block is complete or absent; at least one; request per engine — the locale decides the parameters, the caller the query; the SerpAPI key rides only as its api_key', () => {
  assert.deepEqual(readLocale(localeFile()), LOCALE);
  assert.throws(() => readLocale(localeFile({ timezone: 'x', serpapi: { ...LOCALE.serpapi, hl: '' } })), /serpapi\.hl missing/);
  assert.throws(() => readLocale(localeFile({ timezone: 'x' })), /no engine configured/);
  assert.deepEqual(Object.keys(readLocale(localeFile({ timezone: 'x', brave: LOCALE.brave }))), ['timezone', 'brave'], 'one engine alone is fine');
  assert.throws(() => readLocale(undefined), /WEBSEARCH_LOCALE_FILE/);
  const g = request('serpapi', 'თბილისის მეტრო', LOCALE, { count: 5, secrets: G }); const gu = new URL(g.url);
  assert.equal(g.method, 'GET'); assert.equal(gu.origin + gu.pathname, 'https://serpapi.com/search.json');
  assert.deepEqual(['engine', 'q', 'gl', 'hl', 'google_domain', 'num', 'api_key'].map(k => gu.searchParams.get(k)), ['google', 'თბილისის მეტრო', 'ge', 'ka', 'google.ge', '5', G.SERPAPI_API_KEY]);
  assert.ok(!gu.searchParams.has('lr'), 'lr only where the file names it');
  assert.ok(!new URL(request('serpapi', 'x', LOCALE).url).searchParams.has('api_key'), 'no secret given, no api_key');
  assert.equal(new URL(request('serpapi', 'x', LOCALE, { count: 99 }).url).searchParams.get('num'), '20', 'clamped');
  const b = request('brave', 'თბილისის მეტრო', LOCALE, { count: 5 }); const bu = new URL(b.url);
  assert.equal(b.method, 'GET'); assert.equal(bu.origin + bu.pathname, 'https://api.search.brave.com/res/v1/web/search');
  assert.deepEqual(['q', 'country', 'count'].map(k => bu.searchParams.get(k)), ['თბილისის მეტრო', 'ALL', '5']);
  assert.ok(!bu.searchParams.has('search_lang') && !bu.searchParams.has('ui_lang'), 'a language Brave lacks is not sent');
  const withLang = new URL(request('brave', 'x', { brave: { country: 'US', search_lang: 'en', ui_lang: 'en-US' } }).url);
  assert.equal(withLang.searchParams.get('search_lang'), 'en'); assert.equal(withLang.searchParams.get('ui_lang'), 'en-US');
});

test('search: each secret where its API takes it and nowhere else; results as text from either shape; every failure named without a secret', async () => {
  const seen = [];
  const serpapi = async (url, init) => { seen.push({ url, init }); return { ok: true, status: 200, json: async () => ({ organic_results: [{ title: 'მეტრო', link: 'https://example.ge/m', snippet: 'აღწერა\nხაზი  ორი', position: 1 }] }) }; };
  const r = await search('serpapi', 'მეტრო', LOCALE, { secrets: G, fetchImpl: serpapi });
  assert.equal(r.isError, false); assert.match(r.text, /1\. მეტრო\n   https:\/\/example\.ge\/m\n   აღწერა ხაზი ორი/);
  assert.equal(new URL(seen[0].url).searchParams.get('api_key'), G.SERPAPI_API_KEY, 'SerpAPI: the key as api_key'); assert.deepEqual(Object.keys(seen[0].init.headers), ['Accept']);
  const brave = async (url, init) => { seen.push({ url, init }); return { ok: true, status: 200, json: async () => ({ web: { results: [{ title: 't', url: 'u', description: 'd <strong>e</strong>' }] } }) }; };
  const rb = await search('brave', 'x', LOCALE, { secrets: B, fetchImpl: brave });
  assert.equal(rb.isError, false); assert.match(rb.text, /1\. t\n   u\n   d e/);
  assert.equal(seen[1].init.headers['X-Subscription-Token'], B.BRAVE_SEARCH_API_KEY); assert.ok(!seen[1].url.includes(B.BRAVE_SEARCH_API_KEY));
  for (const out of [r, rb]) assert.ok(![...Object.values(G), ...Object.values(B)].some(v => JSON.stringify(out).includes(v)), 'no secret in a result');
  assert.deepEqual(await search('serpapi', 'x', LOCALE, { secrets: {}, fetchImpl: serpapi }), { isError: true, text: 'no SERPAPI_API_KEY in the synced secrets: fabric-secrets sync, after it is in the store of this login' });
  assert.deepEqual(await search('brave', 'x', LOCALE, { secrets: {}, fetchImpl: brave }), { isError: true, text: 'no BRAVE_SEARCH_API_KEY in the synced secrets: fabric-secrets sync, after it is in the store of this login' });
  assert.deepEqual(await search('serpapi', 'x', LOCALE, { secrets: G, fetchImpl: async () => ({ ok: false, status: 401, json: async () => ({ error: 'Invalid API key. Your API key should be here: https://serpapi.com/manage-api-key' }) }) }), { isError: true, text: 'search refused: HTTP 401 — Invalid API key. Your API key should be here: https://serpapi.com/manage-api-key' });
  assert.deepEqual(await search('serpapi', 'x', LOCALE, { secrets: G, fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({ error: 'Google hasn\'t returned any results for this query.' }) }) }), { isError: true, text: 'search refused: Google hasn\'t returned any results for this query.' }, 'SerpAPI puts some refusals in a 200 body');
  assert.deepEqual(await search('brave', 'x', LOCALE, { secrets: B, fetchImpl: async () => ({ ok: false, status: 422, json: async () => ({ error: { detail: 'Unable to validate request parameter(s)' } }) }) }), { isError: true, text: 'search refused: HTTP 422 — Unable to validate request parameter(s)' });
  assert.deepEqual(await search('serpapi', 'x', LOCALE, { secrets: G, fetchImpl: async () => ({ ok: false, status: 429, json: async () => { throw new Error('x'); } }) }), { isError: true, text: 'search refused: HTTP 429' });
  assert.deepEqual(await search('serpapi', 'x', LOCALE, { secrets: G, fetchImpl: async () => { throw new Error('ECONNREFUSED'); } }), { isError: true, text: 'search failed: unreachable' });
  assert.deepEqual(await search('serpapi', 'x', LOCALE, { secrets: G, fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({}) }) }), { isError: false, text: 'no results (serpapi)' });
});

test('handle: the MCP subset — initialize, initialized, ping, the two tools, web_search on SerpAPI then Brave when SerpAPI refuses, web_search_global on Brave alone, -32601 for the rest', async () => {
  const calls = [];
  const fetchImpl = (serpapiStatus = 200) => async url => { calls.push(url.includes('serpapi') ? 'serpapi' : 'brave');
    if (url.includes('serpapi')) return serpapiStatus === 200 ? { ok: true, status: 200, json: async () => ({ organic_results: [{ title: 'g', link: 'u', snippet: 'd' }] }) } : { ok: false, status: serpapiStatus, json: async () => ({ error: 'Your account has run out of searches.' }) };
    return { ok: true, status: 200, json: async () => ({ web: { results: [{ title: 'b', url: 'u', description: 'd' }] } }) }; };
  const ctx = { locale: LOCALE, secrets: { serpapi: G, brave: B }, fetchImpl: fetchImpl() };
  const init = await handle({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-06-18' } }, ctx);
  assert.equal(init.result.protocolVersion, '2025-06-18'); assert.deepEqual(init.result.capabilities, { tools: {} });
  assert.equal(await handle({ jsonrpc: '2.0', method: 'notifications/initialized' }, ctx), null, 'a notification gets no reply');
  assert.deepEqual((await handle({ jsonrpc: '2.0', id: 2, method: 'ping' }, ctx)).result, {});
  const list = await handle({ jsonrpc: '2.0', id: 3, method: 'tools/list' }, ctx);
  assert.deepEqual(list.result.tools, tools(LOCALE)); assert.deepEqual(list.result.tools.map(t => [t.name, t.description]), [['web_search', 'ვებ-ძიება ქართულად'], ['web_search_global', 'გლობალური ვებ-ძიება']]);
  assert.deepEqual(tools({ brave: LOCALE.brave }).map(t => t.name), ['web_search', 'web_search_global'], 'Brave alone still offers web_search (it is then Brave)');
  assert.deepEqual(tools({ serpapi: LOCALE.serpapi }).map(t => t.name), ['web_search']);
  // SerpAPI answers: its result, named.
  const g = await handle({ jsonrpc: '2.0', id: 4, method: 'tools/call', params: { name: 'web_search', arguments: { query: 'მეტრო' } } }, ctx);
  assert.equal(g.result.isError, false); assert.match(g.result.content[0].text, /^1\. g[\s\S]*\n\n— ძირითადი ძრავა$/, 'the last line is the engine\'s label in the locale'); assert.deepEqual(calls, ['serpapi']);
  // SerpAPI refuses (the 250 spent): Brave answers the same call, and the last line says so.
  calls.length = 0;
  const fb = await handle({ jsonrpc: '2.0', id: 5, method: 'tools/call', params: { name: 'web_search', arguments: { query: 'მეტრო' } } }, { ...ctx, fetchImpl: fetchImpl(429) });
  assert.equal(fb.result.isError, false); assert.match(fb.result.content[0].text, /^1\. b[\s\S]*\n\n— brave \(ძირითადი ძრავა: search refused: HTTP 429 — Your account has run out of searches\.\)$/, 'no label for Brave in this fixture: the key'); assert.deepEqual(calls, ['serpapi', 'brave']);
  // No SerpAPI key at all: the fall-back is the same, with that reason.
  const nk = await handle({ jsonrpc: '2.0', id: 6, method: 'tools/call', params: { name: 'web_search', arguments: { query: 'მეტრო' } } }, { ...ctx, secrets: { brave: B } });
  assert.equal(nk.result.isError, false); assert.match(nk.result.content[0].text, /— brave \(ძირითადი ძრავა: no SERPAPI_API_KEY/);
  // Both refuse: an error naming both.
  const both = await handle({ jsonrpc: '2.0', id: 7, method: 'tools/call', params: { name: 'web_search', arguments: { query: 'მეტრო' } } }, { ...ctx, secrets: {} });
  assert.equal(both.result.isError, true); assert.match(both.result.content[0].text, /ძირითადი ძრავა: no SERPAPI_API_KEY.*; brave: no BRAVE_SEARCH_API_KEY/);
  // web_search_global is Brave alone, whatever SerpAPI would say.
  calls.length = 0;
  const b = await handle({ jsonrpc: '2.0', id: 8, method: 'tools/call', params: { name: 'web_search_global', arguments: { query: 'მეტრო' } } }, ctx);
  assert.match(b.result.content[0].text, /^1\. b[\s\S]*— brave$/); assert.deepEqual(calls, ['brave']);
  assert.equal((await handle({ jsonrpc: '2.0', id: 9, method: 'tools/call', params: { name: 'web_search_global', arguments: { query: 'x' } } }, { ...ctx, locale: { serpapi: LOCALE.serpapi } })).error.code, -32602, 'no Brave block, no global tool');
  assert.equal((await handle({ jsonrpc: '2.0', id: 10, method: 'tools/call', params: { name: 'web_search', arguments: { query: 'x' } } }, ctx)).error.code, -32602);
  assert.equal((await handle({ jsonrpc: '2.0', id: 11, method: 'resources/list' }, ctx)).error.code, -32601);
  assert.equal((await handle({ id: 12, method: 'ping' }, ctx)).error.code, -32600);
});

test('stdio: newline-delimited JSON-RPC end to end; a missing secret is a tool error, not a crash; no secret on stderr or stdout', async () => {
  const home = scratch('ws-home-'); fs.mkdirSync(path.join(home, '.config', 'agent-fabric'), { recursive: true });
  fs.writeFileSync(path.join(home, '.config', 'agent-fabric', 'secrets.env'), `export GH_TOKEN='${B.BRAVE_SEARCH_API_KEY}'\n`);   // neither search key
  // The synced file is the only source of a key here: a login that holds the
  // search keys in its environment (the ge holder) must not lend them to the child.
  const env = { ...process.env, HOME: home, WEBSEARCH_LOCALE_FILE: localeFile() }; delete env.SERPAPI_API_KEY; delete env.BRAVE_SEARCH_API_KEY;
  const child = spawn('node', [SERVER], { env });
  let out = '', err = ''; child.stdout.on('data', d => { out += d; }); child.stderr.on('data', d => { err += d; });
  for (const m of [{ jsonrpc: '2.0', id: 1, method: 'initialize', params: {} }, { jsonrpc: '2.0', method: 'notifications/initialized' }, { jsonrpc: '2.0', id: 2, method: 'tools/list' },
                   { jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'web_search', arguments: { query: 'მეტრო' } } }]) child.stdin.write(JSON.stringify(m) + '\n');
  child.stdin.write('not json\n'); child.stdin.end();
  await new Promise(r => child.on('close', r));
  const lines = out.trim().split('\n').map(l => JSON.parse(l));
  assert.equal(lines[0].result.serverInfo.name, 'websearch-locale');
  assert.deepEqual(lines[1].result.tools.map(t => t.name), ['web_search', 'web_search_global']);
  assert.equal(lines[2].result.isError, true); assert.match(lines[2].result.content[0].text, /ძირითადი ძრავა: no SERPAPI_API_KEY.*; brave: no BRAVE_SEARCH_API_KEY/);
  assert.equal(lines[3].error.code, -32700);
  assert.ok(!out.includes(B.BRAVE_SEARCH_API_KEY) && !err.includes(B.BRAVE_SEARCH_API_KEY));
});

test('stripTags removes markup until none is left, and a stray angle bracket with it', () => {
  assert.equal(stripTags('the <b>Rustaveli</b> avenue'), 'the Rustaveli avenue');
  assert.equal(stripTags('<<b>b>script'), 'script', 'one pass would leave "<b>"');
  assert.equal(stripTags('<scr<script>ipt>x'), 'x');
  assert.equal(stripTags('a < b and c > d'), 'a  b and c  d', 'a stray bracket is dropped, the words kept');
  const crafted = '<b'.repeat(50000) + '>'.repeat(50000);
  const t0 = Date.now(); stripTags(crafted);
  assert.ok(Date.now() - t0 < 1000, 'a crafted nesting is bounded, not quadratic in its length');
  assert.equal(stripTags('a'.repeat(5000)).length, 4096, 'the input is cut to 4096 characters');
  assert.ok(stripTags('<b'.repeat(20) + '>'.repeat(20)).length > 0, 'at most 16 passes: a deeper nesting leaves residue rather than looping on');
});
