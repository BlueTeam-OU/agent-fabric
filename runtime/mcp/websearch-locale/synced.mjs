// runtime/mcp/websearch-locale/synced.mjs — the synced secrets file's one
// reader this MCP server needs (it had borrowed it from the control plane's
// gzcoord.mjs, deleted with the Node control plane: ADR-040 Wave 8, s8).
// The Python side reads the same file as tools/fabric/relay.py own_token.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// One `export NAME=value` line of the synced secrets file, unquoted, or
// undefined — read fresh, because the environment is a snapshot of it
// taken when the shell started. The value is a secret: a caller prints it
// nowhere and uses it in place (a header, a hash). sync writes the value
// with shlex.quote and the Python readers take it back with shlex.split
// (tools/fabric/relay.py own_token), so this reads the first word as
// they do: a value holding ' is written 'a'"'"'b', which stripping the
// outer quotes once read as a'"'"'b.
export function syncedVar(name, home = os.homedir()) {
  try {
    const prefix = `export ${name}=`;
    for (const line of fs.readFileSync(path.join(home, '.config', 'agent-fabric', 'secrets.env'), 'utf8').split('\n')) {
      if (!line.startsWith(prefix)) continue;
      return shellWord(line.slice(prefix.length)) || undefined;
    }
  } catch { /* not enrolled, or no sync yet */ }
  return undefined;
}

// The first word of a line as Python's shlex.split reads it (POSIX mode,
// no comments): '…' literal; "…" where a backslash escapes only " and \;
// outside quotes a backslash escapes any character. An unterminated quote
// or escape is shlex's ValueError: null, never a guess at the value.
export function shellWord(text) {
  let word = null, i = 0;
  while (i < text.length && /[ \t\r\n]/.test(text[i])) i++;
  while (i < text.length) {
    const c = text[i];
    if (/[ \t\r\n]/.test(c)) break;
    word ??= '';
    if (c === "'") {
      const end = text.indexOf("'", i + 1);
      if (end < 0) return null;
      word += text.slice(i + 1, end); i = end + 1;
    } else if (c === '"') {
      i++;
      for (;;) {
        if (i >= text.length) return null;
        const d = text[i];
        if (d === '"') { i++; break; }
        if (d === '\\' && i + 1 < text.length && (text[i + 1] === '"' || text[i + 1] === '\\')) { word += text[i + 1]; i += 2; continue; }
        if (d === '\\' && i + 1 >= text.length) return null;
        word += d; i++;
      }
    } else if (c === '\\') {
      if (i + 1 >= text.length) return null;
      word += text[i + 1]; i += 2;
    } else { word += c; i++; }
  }
  return word;
}
