// runtime/mcp/websearch-locale/server.mjs — web search located in a
// login's locale, as an MCP server on stdio, over two engines.
//
// Claude Code's own WebSearch tool takes a query and two domain lists
// and nothing else (read back 2026-09-17: its schema is closed, and its
// description says US-only); Anthropic's `user_location` exists on the
// Messages API and is not exposed by the harness. So a language-culture
// holder, who must search as a reader of its locale would, gets this
// server instead: one tool per engine the locale file configures
// (identities/roles/language-culture/locale/<suffix>/locale.json, kept
// by the CEO: "keep both engines"):
//
//   web_search         Google's results through SerpAPI (serpapi.com),
//                      with `gl` (the country), `hl` (the language) and,
//                      where the file names them, `google_domain` and
//                      `lr` fixed from the file — the locale as a browser
//                      there would have it. Google's own Custom Search
//                      JSON API is closed to new customers (its overview
//                      page, 2026-09-17) and Google sells no other
//                      web-search API, so a SERP proxy is the way to
//                      Google's index; the CEO's account is SerpAPI's.
//                      Secret SERPAPI_API_KEY — SerpAPI takes it only as
//                      the `api_key` query parameter, so this is the one
//                      request whose URL carries a secret: the URL is
//                      built per call and never logged or returned.
//   web_search_global  Brave's Search API, `country` from the file (ALL
//                      for a locale Brave lacks — it has no Georgian: GE,
//                      ka and ka-GE each refused, 2026-09-17) and
//                      search_lang / ui_lang only where the file names
//                      them: a second index, steered by the query's
//                      language. Secret BRAVE_SEARCH_API_KEY.
//
// The caller chooses the query, never the locale. Installed into the
// user scope of a language-culture login by install-agent-files.sh,
// removed from any other. Every secret is read from the synced file at
// call time and put into one header — never a URL, a log line or a
// result. Each tool's description is the file's, in the locale: its
// reader is the holder, who reasons in that language. The worker never
// sees these tools — it has one inert tool by design.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { syncedVar } from '../../control/gzcoord.mjs';

export const SERPAPI_URL = 'https://serpapi.com/search.json';
export const BRAVE_URL = 'https://api.search.brave.com/res/v1/web/search';
export const SECRETS = { serpapi: ['SERPAPI_API_KEY'], brave: ['BRAVE_SEARCH_API_KEY'] };
const REQUIRED = { serpapi: ['gl', 'hl', 'tool_description'], brave: ['country', 'tool_description'] };

export function readLocale(file = process.env.WEBSEARCH_LOCALE_FILE) {
  if (!file) throw new Error('WEBSEARCH_LOCALE_FILE is not set: the locale file decides the country and language');
  const l = JSON.parse(fs.readFileSync(file, 'utf8'));
  const engines = Object.keys(REQUIRED).filter(e => l[e]);
  if (!engines.length) throw new Error(`locale file ${file}: no engine configured (serpapi, brave)`);
  for (const e of engines) for (const k of REQUIRED[e]) if (typeof l[e][k] !== 'string' || !l[e][k]) throw new Error(`locale file ${file}: ${e}.${k} missing`);
  return l;
}

// The request per engine, both GETs with the parameters in the URL.
// SerpAPI's `api_key` is the secret itself (its only auth), added here
// from `secrets` and nowhere else; Brave's key rides in a header.
export function request(engine, query, locale, { count, secrets = {} } = {}) {
  if (engine === 'serpapi') {
    const u = new URL(SERPAPI_URL); const p = locale.serpapi;
    u.searchParams.set('engine', 'google'); u.searchParams.set('q', query); u.searchParams.set('gl', p.gl); u.searchParams.set('hl', p.hl);
    if (p.google_domain) u.searchParams.set('google_domain', p.google_domain);
    if (p.lr) u.searchParams.set('lr', p.lr);
    u.searchParams.set('num', String(Math.min(20, Math.max(1, Number(count) || 10))));
    if (secrets.SERPAPI_API_KEY) u.searchParams.set('api_key', secrets.SERPAPI_API_KEY);
    return { url: u.toString(), method: 'GET' };
  }
  const u = new URL(BRAVE_URL); const b = locale.brave;
  u.searchParams.set('q', query); u.searchParams.set('country', b.country);
  if (b.search_lang) u.searchParams.set('search_lang', b.search_lang);
  if (b.ui_lang) u.searchParams.set('ui_lang', b.ui_lang);
  u.searchParams.set('count', String(Math.min(20, Math.max(1, Number(count) || 10))));
  return { url: u.toString(), method: 'GET' };
}

const secretsOf = (engine, env = process.env) => Object.fromEntries(SECRETS[engine].map(n => [n, syncedVar(n) ?? env[n]]));

// One search on one engine: the results as text, one block each —
// title, link, snippet — or an error the caller can read, never a secret.
export async function search(engine, query, locale, { secrets = secretsOf(engine), fetchImpl = globalThis.fetch, count } = {}) {
  const missing = SECRETS[engine].find(n => !secrets[n]);
  if (missing) return { isError: true, text: `no ${missing} in the synced secrets: bin/fabric-secrets sync, after it is in the store of this login` };
  const { url, method } = request(engine, query, locale, { count, secrets });
  const headers = engine === 'brave' ? { Accept: 'application/json', 'X-Subscription-Token': secrets.BRAVE_SEARCH_API_KEY } : { Accept: 'application/json' };
  let r;
  try { r = await fetchImpl(url, { method, headers, signal: AbortSignal.timeout(20000) }); }
  catch (e) { return { isError: true, text: `search failed: ${e?.name === 'TimeoutError' ? 'timeout' : 'unreachable'}` }; }
  if (!r.ok) {
    let why = ''; try { const j = await r.json(); why = typeof j?.error === 'string' ? j.error : (j?.message ?? j?.error?.message ?? j?.error?.detail ?? ''); } catch { /* no body */ }
    return { isError: true, text: `search refused: HTTP ${r.status}${why ? ` — ${String(why).slice(0, 200)}` : ''}` };
  }
  let j; try { j = await r.json(); } catch { return { isError: true, text: 'search answered something that is not JSON' }; }
  if (engine === 'serpapi' && j?.error) return { isError: true, text: `search refused: ${String(j.error).slice(0, 200)}` };
  const items = engine === 'serpapi' ? (j?.organic_results ?? []).map(x => [x.title, x.link, x.snippet]) : (j?.web?.results ?? []).map(x => [x.title, x.url, stripTags(x.description ?? '')]);
  if (!items.length) return { isError: false, text: `no results (${engine})` };
  return { isError: false, text: items.map(([t, l, d], i) => `${i + 1}. ${t ?? ''}\n   ${l ?? ''}\n   ${(d ?? '').replace(/\s+/g, ' ')}`).join('\n\n') };
}

// A description's markup (tag-shaped spans only, so "a < b" prose stays),
// removed until none is left: one pass over
// "<<b>b>" leaves "<b>", and a stray angle bracket is dropped too. The
// text reaches a model, not a browser; this keeps it plain.
export function stripTags(text) {
  // Bounded: a description is a few hundred bytes, and each pass is
  // linear, so 16 passes and 4 kB cap a crafted "<b<b<b…>>>" (review of #39).
  let s = String(text).slice(0, 4096), prev, i = 0;
  do { prev = s; s = s.replace(/<\/?[A-Za-z][^<>]*>/g, ''); } while (s !== prev && ++i < 16);
  return s.replace(/[<>]/g, '');
}

// The tools. `web_search` is the located search with Brave behind it:
// the engines in order (SerpAPI, then Brave), the first that answers
// wins, and the result's last line names the engine and — when SerpAPI
// refused, its 250 searches a month spent or anything else — why, so the
// holder sees the fall-back without the search failing (the CEO,
// 2026-09-17: "use SerpAPI till it works, then switch to Brave
// seamlessly"). `web_search_global` is Brave alone, explicitly.
export const ORDER = ['serpapi', 'brave'];
export function tools(locale) {
  const schema = { type: 'object', additionalProperties: false, required: ['query'],
                   properties: { query: { type: 'string', minLength: 2 }, count: { type: 'integer', minimum: 1, maximum: 20 } } };
  const out = [];
  const first = ORDER.find(e => locale[e]);
  if (first) out.push({ name: 'web_search', description: locale[first].tool_description, inputSchema: schema });
  if (locale.brave) out.push({ name: 'web_search_global', description: locale.brave.tool_description, inputSchema: schema });
  return out;
}
// The last line names the engine by the locale file's `label` for it —
// in the locale, no vendor (the CEO, 2026-09-17: a vendor's name is a
// technicality the holder has no use for) — falling back to the key.
export async function searchWithFallback(engines, query, locale, opts) {
  const refused = [];
  const label = e => locale[e]?.label || e;
  for (const engine of engines) {
    const r = await search(engine, query, locale, { fetchImpl: opts?.fetchImpl, count: opts?.count, ...(opts?.secrets ? { secrets: opts.secrets[engine] ?? {} } : {}) });
    if (!r.isError) return { isError: false, text: `${r.text}\n\n— ${label(engine)}${refused.length ? ` (${refused.join('; ')})` : ''}` };
    refused.push(`${label(engine)}: ${r.text}`);
  }
  return { isError: true, text: refused.join('; ') };
}

// JSON-RPC 2.0 over stdio, newline-delimited, the MCP subset a tool
// server needs: initialize, the initialized notification, ping,
// tools/list, tools/call. Anything else is -32601.
export async function handle(msg, ctx) {
  const reply = result => ({ jsonrpc: '2.0', id: msg.id, result });
  const error = (code, message) => ({ jsonrpc: '2.0', id: msg.id ?? null, error: { code, message } });
  if (msg.jsonrpc !== '2.0' || typeof msg.method !== 'string') return error(-32600, 'invalid request');
  if (msg.method === 'notifications/initialized' || msg.method.startsWith('notifications/')) return null;
  if (msg.method === 'initialize') return reply({ protocolVersion: msg.params?.protocolVersion ?? '2024-11-05', capabilities: { tools: {} }, serverInfo: { name: 'websearch-locale', version: '1' } });
  if (msg.method === 'ping') return reply({});
  if (msg.method === 'tools/list') return reply({ tools: tools(ctx.locale) });
  if (msg.method === 'tools/call') {
    const engines = msg.params?.name === 'web_search' ? ORDER.filter(e => ctx.locale[e]) : msg.params?.name === 'web_search_global' && ctx.locale.brave ? ['brave'] : [];
    if (!engines.length) return error(-32602, `unknown tool ${msg.params?.name}`);
    const q = msg.params?.arguments?.query;
    if (typeof q !== 'string' || q.length < 2) return error(-32602, 'query: a string of at least two characters');
    const r = await searchWithFallback(engines, q, ctx.locale, { secrets: ctx.secrets, fetchImpl: ctx.fetchImpl, count: msg.params?.arguments?.count });
    return reply({ content: [{ type: 'text', text: r.text }], isError: r.isError });
  }
  return error(-32601, `method not found: ${msg.method}`);
}

export async function main() {
  const ctx = { locale: readLocale(), fetchImpl: globalThis.fetch };   // secrets: read at each call
  let buf = '';
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) {
    buf += chunk;
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!line) continue;
      let msg; try { msg = JSON.parse(line); } catch { process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'parse error' } }) + '\n'); continue; }
      const out = await handle(msg, ctx);
      if (out) process.stdout.write(JSON.stringify(out) + '\n');
    }
  }
  return 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().then(c => process.exit(c)).catch(e => { console.error(`websearch-locale: ${e.message}`); process.exit(1); });
