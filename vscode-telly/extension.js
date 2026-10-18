const vscode = require('vscode');
const cp = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { parseCompilerError } = require('./errors');

// [word, emoji, meaning]
const EMOJI = [
  ['yes',     '👍', 'true'],
  ['no',      '👎', 'false'],
  ['equals',  '🟰', 'comparison =='],
  ['differs', '🚫', 'comparison !='],
];

const DELAY_MS = 400;     // wait this long after the last keystroke
const TIMEOUT_MS = 10000;

function compilerSettings(document) {
  const cfg = vscode.workspace.getConfiguration('telly', document.uri);
  const folder = vscode.workspace.getWorkspaceFolder(document.uri)
    || (vscode.workspace.workspaceFolders || [])[0];
  const configured = cfg.get('compilerPath');
  const compiler = configured || (folder ? path.join(folder.uri.fsPath, 'compiler.py') : '');
  return {
    enabled: cfg.get('diagnostics'),
    python: cfg.get('pythonPath') || 'python3',
    compiler,
  };
}

// Compile the text of the editor (not the file on disk, so it works while
// you type) into a temporary directory and report what the compiler said.
function compile(settings, text) {
  return new Promise((resolve) => {
    if (!settings.compiler || !fs.existsSync(settings.compiler)) {
      resolve({ missing: true });
      return;
    }
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'telly-'));
    const source = path.join(dir, 'program.txt');
    fs.writeFileSync(source, text, 'utf8');
    cp.execFile(
      settings.python,
      [settings.compiler, source, path.join(dir, 'out.ll')],
      { cwd: path.dirname(settings.compiler), timeout: TIMEOUT_MS, encoding: 'utf8' },
      (error, _stdout, stderr) => {
        fs.rmSync(dir, { recursive: true, force: true });
        resolve({ error, stderr: stderr || '' });
      });
  });
}

function activate(context) {
  const completion = vscode.languages.registerCompletionItemProvider('telly', {
    provideCompletionItems() {
      return EMOJI.map(([word, emoji, meaning]) => {
        const item = new vscode.CompletionItem(
          `${emoji}  ${word}`, vscode.CompletionItemKind.Keyword);
        item.insertText = emoji;   // what gets typed into the file
        item.filterText = word;    // what you type to find it
        item.detail = `Telly: ${meaning}`;
        return item;
      });
    }
  });
  context.subscriptions.push(completion);

  // ---- diagnostics: the compiler's own error line under the code ----
  const diagnostics = vscode.languages.createDiagnosticCollection('telly');
  const timers = new Map();      // document uri -> pending timer
  const versions = new Map();    // document uri -> last version that was started
  context.subscriptions.push(diagnostics);

  async function check(document) {
    if (document.languageId !== 'telly') return;
    const settings = compilerSettings(document);
    if (!settings.enabled) { diagnostics.delete(document.uri); return; }

    const key = document.uri.toString();
    const version = document.version;
    versions.set(key, version);
    const result = await compile(settings, document.getText());
    if (versions.get(key) !== version) return;      // a newer check has started

    if (result.missing) {
      diagnostics.set(document.uri, [new vscode.Diagnostic(
        new vscode.Range(0, 0, 0, 0),
        `Telly: compiler.py not found (${settings.compiler || 'no workspace folder'}). ` +
        'Set "telly.compilerPath".',
        vscode.DiagnosticSeverity.Warning)]);
      return;
    }
    const found = result.error ? parseCompilerError(result.stderr, document.getText()) : null;
    if (!found) {
      if (result.error && result.stderr.trim()) {   // a crash, a missing llvmlite...
        const d = new vscode.Diagnostic(new vscode.Range(0, 0, 0, 0),
          `Telly: ${result.stderr.trim().split('\n').pop()}`, vscode.DiagnosticSeverity.Warning);
        d.source = 'telly';
        diagnostics.set(document.uri, [d]);
      } else {
        diagnostics.delete(document.uri);           // compiled without errors
      }
      return;
    }
    const d = new vscode.Diagnostic(
      new vscode.Range(found.line, found.start, found.line, found.end),
      found.message, vscode.DiagnosticSeverity.Error);
    d.source = 'telly';
    diagnostics.set(document.uri, [d]);
  }

  function schedule(document) {
    const key = document.uri.toString();
    clearTimeout(timers.get(key));
    timers.set(key, setTimeout(() => check(document), DELAY_MS));
  }

  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument(check),
    vscode.workspace.onDidChangeTextDocument((e) => schedule(e.document)),
    vscode.workspace.onDidSaveTextDocument(check),
    vscode.workspace.onDidCloseTextDocument((doc) => {
      diagnostics.delete(doc.uri);
      versions.delete(doc.uri.toString());
    }),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('telly')) vscode.workspace.textDocuments.forEach(check);
    }),
  );
  vscode.workspace.textDocuments.forEach(check);
}

function deactivate() {}
module.exports = { activate, deactivate };