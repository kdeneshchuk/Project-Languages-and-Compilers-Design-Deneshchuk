// Turns the compiler's one-line error into a position in the text.
// No dependency on vscode, so it can be tested with plain node.

const ERROR_LINE = /^compilation error: (?:line (\d+):(\d+): )?(.*)$/m;

// The compiler counts columns in bytes (an emoji is four), VS Code counts
// UTF-16 units. Walk the line and convert.
function byteColumnToIndex(lineText, byteColumn) {
  let bytes = 0;
  let index = 0;
  for (const ch of lineText) {
    if (bytes >= byteColumn) break;
    bytes += Buffer.byteLength(ch, 'utf8');
    index += ch.length;
  }
  return index;
}

// How far the red underline goes: the whole word, number or emoji at the
// position, or one character for a symbol.
function endOfToken(lineText, start) {
  const rest = lineText.slice(start);
  const word = rest.match(/^[A-Za-z0-9_]+/);
  if (word) return start + word[0].length;
  const first = rest.codePointAt(0);
  return start + (first === undefined ? 0 : String.fromCodePoint(first).length);
}

// Returns { line, start, end, message } (all zero-based), or null when the
// text is not a compiler error line.
function parseCompilerError(stderr, text) {
  const m = ERROR_LINE.exec(stderr);
  if (!m) return null;
  const lines = text.split(/\r\n|\n|\r/);
  if (m[1] === undefined) {                 // an error without a position
    return { line: 0, start: 0, end: (lines[0] || '').length, message: m[3] };
  }
  const line = Math.min(Math.max(parseInt(m[1], 10) - 1, 0), lines.length - 1);
  const lineText = lines[line] || '';
  const start = Math.min(byteColumnToIndex(lineText, parseInt(m[2], 10) - 1), lineText.length);
  let end = endOfToken(lineText, start);
  if (end <= start) end = Math.min(start + 1, Math.max(lineText.length, start));
  return { line, start, end, message: m[3] };
}

module.exports = { parseCompilerError, byteColumnToIndex };