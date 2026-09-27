#!/usr/bin/env node
// The lines the GZCoord tools print, in the language of the login that
// reads them.
//
// A language-culture holder reasons in the locale it is named for, and
// the fabric removes every English it controls from that session
// (docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md). The inbox was the last piece named
// as residue there — "the inbox drain (the wire is English)" — and it is
// two things, not one: the MESSAGE is the wire and stays as its sender
// wrote it, while everything the inbox says AROUND it (the head line,
// the delivery title, the validator's diagnostics, the cut notice, every
// error) is the fabric's own text and is the reader's to have in its
// language. This module is that seam. The owner, 2026-09-21.
//
// The validator's diagnostics are keys like the rest, which puts the
// seam INSIDE gzmsg.mjs rather than at the inbox's edge: the same
// sentences are printed by send.mjs and the gzmsg CLI, and a refusal a
// holder reads when composing is that holder's line too. It also means
// paths.mjs exists — see there.
//
// The dictionaries are the house i18n standard: one flat key -> string
// JSON file per locale, named for the locale's BCP-47 tag, keys as
// dotted slugs, `{name}` interpolation, no empty values, and every
// active locale complete against the default. i18n/README.md states it,
// cites where the house keeps it, and says what the fabric's copy cannot
// keep and why.
//
//   communication/gzcoord/i18n/en-US.json                the default locale
//   identities/roles/<role>/locale/<suffix>/<tag>.json    an active locale
//
// A login reaches its dictionary the way the launcher reaches its
// prompt — by the LOGIN's suffix (language-culture-ge -> ge) under the
// role the session is bound to — and the suffix names its tag in that
// locale's locale.json. Absent, unreadable or incomplete: the default
// locale, never invented text. For a missing key that is a key-level
// fallback, which gzapp's ADR-024 does not allow its clients; the fabric
// keeps it because a session start never fails on a translation, and
// lint keeps an incomplete dictionary from landing (agent-fabric
// docs/adr/ADR-028-house-i18n-standard-gzcoord-speaks-the-readers-language.md §4).
//
// What is NOT in the dictionary, deliberately: the message body, the
// metadata keys (FROM, TO, TO-ROLE, MESSAGE-ID), the type names and
// `broadcast`. Those are the wire's vocabulary — a reader matches them
// by name, across locales, and a translated one would name nothing.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { FABRIC_ROOT } from './paths.mjs';

// Beside the code, not under FABRIC_ROOT: the default dictionary ships
// WITH the script and is the last fallback there is, while the locale
// lookup below is a lookup into identities/ and is FABRIC_ROOT's by
// right. A test (or a tool) that points AGENT_FABRIC_ROOT at a fixture
// is naming where the roles live, never where this module's source is.
export const DEFAULT_LOCALE = 'en-US';
// fileURLToPath, not URL.pathname: a checkout under a path with a space
// in it is percent-encoded in the URL, and .pathname hands back a name
// no file has (blind review F2 on PR #28).
export const I18N_DIR = fileURLToPath(new URL('../i18n/', import.meta.url));
export const DEFAULT_PATH = path.join(I18N_DIR, `${DEFAULT_LOCALE}.json`);

export function defaultDictionary(file = DEFAULT_PATH) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

// The reader every entry point uses. A tool that cannot read its own
// default dictionary must not die of it — parse() is called inside bare
// catches that would read the throw as "not a GZCOORD/1 message", and
// send.mjs's exit codes mean something to its callers — but it must not
// go quiet either: an empty dictionary prints every line as its own key,
// which is unreadable unless something says why. So: degrade, and say so
// once (blind review F6 and the round after it, PR #28).
let said = false;
export function defaultDictionaryOrEmpty(file = DEFAULT_PATH) {
  try {
    const d = defaultDictionary(file);
    // Parsed is not usable: null, a string, a number and an array are all
    // valid JSON and none of them is a dictionary. `key in null` throws at
    // the first line printed, far from here (re-review N2).
    if (!d || typeof d !== 'object' || Array.isArray(d)) throw new TypeError('not an object of lines');
    return d;
  }
  catch (e) {
    if (!said) {
      said = true;
      console.error(`gzcoord: ${file} could not be read (${e.message}); every line will print as its own key`);
    }
    return {};
  }
}

/** The locale directory a login is named for: what follows its last dash
 *  (language-culture-ge -> ge). tools/fabric/launch_prompt.py::_suffix. */
export function suffix(agent) {
  return agent.includes('-') ? agent.slice(agent.lastIndexOf('-') + 1) : agent;
}

/** The locale's BCP-47 tag, from the one place that says what a suffix
 *  means: identities/roles/<role>/locale/<suffix>/locale.json. `ge` is
 *  Georgian (ka-GE), not German — which is why the tag is data and not
 *  something a reader of the directory name infers. */
export function localeTag(dir) {
  try { return JSON.parse(fs.readFileSync(path.join(dir, 'locale.json'), 'utf8')).tag; }
  catch { return undefined; }
}

// Run the tools in the default locale whatever login is running them.
// It governs the AMBIENT resolution — what a tool picks for the login
// running it — and nothing else: a caller that names a locale passes its
// own `env` and is answered with that locale, because it asked.
//
// The suites need it: they assert the lines the tools print, and the tool
// speaks the READER's language — so a suite that pins English is green on
// a login with no locale (CI's) and red on every holder's, which is the
// worst way round to find out. It is also how a coordinator reproduces a
// holder's report in a language it can read (the ru holder, 2026-09-21,
// who found this by being the first login to have a dictionary at all).
//
// Exactly '1' turns it on. Truthiness would make `=0`, `=false` and `=no`
// all mean yes, which is the one reading an operator setting it that way
// cannot have intended; `GZCOORD_TEST_BUS_ANY === '1'` one file away is
// the house form (blind review F2 on PR #30).
export const DEFAULT_LOCALE_ONLY = 'GZCOORD_DEFAULT_LOCALE_ONLY';
const pinnedToDefault = env => env[DEFAULT_LOCALE_ONLY] === '1';

const localeDir = (me, root) => path.join(root, 'identities', 'roles', me.role, 'locale', suffix(me.agent));

// A configured locale that is suppressed is visible to its reader — the
// same rule this module already applies to a dictionary it cannot read.
// Silence is the case the switch's threat model asks about: a holder
// served English, and losing the standing reminder its bridge appends to
// every drain, with nothing to distinguish that from a missing file
// (blind review F3 on PR #30). Said once, only when there was something
// to suppress.
let pinSaid = false;
function sayPinnedOnce(dir) {
  if (pinSaid || !fs.existsSync(dir)) return;
  pinSaid = true;
  console.error(`gzcoord: ${DEFAULT_LOCALE_ONLY}=1 — printing the default locale, not ${dir}`);
}

/** The standing reminder this locale's holder reads on every drain and
 *  every delivery: "think in <the language>", the owner's own words, in
 *  the locale (the owner, 2026-09-21). It is not a dictionary key —
 *  there is no English line it translates, and an en-US login has no
 *  such rule to be reminded of — so it lives with the locale's other
 *  facts and is appended to the head line, the one line a holder reads
 *  every time. Absent: nothing is appended. */
export function localeReminder(me, root = FABRIC_ROOT, env = process.env) {
  if (!me?.agent || !me?.role) return '';
  const dir = localeDir(me, root);
  // The reminder is a line like any other: the same switch silences it, or
  // a suite asserting a head line would break on a holder's login too.
  if (pinnedToDefault(env)) { sayPinnedOnce(dir); return ''; }
  try {
    const r = JSON.parse(fs.readFileSync(path.join(dir, 'locale.json'), 'utf8')).reminder;
    return typeof r === 'string' ? r : '';
  } catch { return ''; }
}

/** The dictionary file for this login, or null for the default locale. */
export function dictionaryPath(me, root = FABRIC_ROOT, env = process.env) {
  if (!me?.agent || !me?.role) return null;
  const dir = localeDir(me, root);
  if (pinnedToDefault(env)) { sayPinnedOnce(dir); return null; }
  const tag = localeTag(dir);
  if (!tag || tag === DEFAULT_LOCALE) return null;
  const file = path.join(dir, `${tag}.json`);
  return fs.existsSync(file) ? file : null;
}

/** The dictionary this login reads: the default locale, with an active
 *  locale's own values over it. Completeness is enforced where it can be
 *  fixed — tools/fabric/lint.py, before the file lands — so a key missing
 *  HERE falls back rather than failing a session start; nothing is ever
 *  invented (gzapp's ADR-024 §2.5: a client MUST NOT fabricate fallback
 *  text). */
export function dictionary(me, { root = FABRIC_ROOT, file = DEFAULT_PATH, env = process.env } = {}) {
  const base = defaultDictionaryOrEmpty(file);
  const p = dictionaryPath(me, root, env);
  if (!p) return base;
  try {
    const loc = JSON.parse(fs.readFileSync(p, 'utf8'));
    for (const [k, v] of Object.entries(loc))
      if (typeof v === 'string' && v !== '' && Object.hasOwn(base, k)) base[k] = v;
  } catch { /* unreadable or not JSON: the default locale, silently — this is a session start */ }
  return base;
}

/** `{name}` from `vars`, the house interpolation. A placeholder the
 *  caller did not supply is left standing rather than blanked: a
 *  translation that invented one is then visible in the line instead of
 *  silently eating the value beside it. */
export function fill(template, vars = {}) {
  return template.replace(/\{([a-z_]+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
}

/** The printer the tools hold: t('inbox.head', {...}). An unknown key is
 *  returned as itself — a line that names its own key is a bug report,
 *  not a crash, and tests/i18n.test.mjs is where it is caught. */
export function printer(dict) {
  return (key, vars) => (key in dict ? fill(dict[key], vars) : key);
}

/** The printer for a given login. `me` is passed, never discovered here:
 *  whoami() lives in gzmsg.mjs and this module must not import it — the
 *  validator there takes its diagnostics from this one (paths.mjs). */
export function t(me, opts) {
  return printer(dictionary(me, opts));
}
