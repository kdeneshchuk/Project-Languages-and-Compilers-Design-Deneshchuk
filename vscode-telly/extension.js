const vscode = require('vscode');

// [word, emoji, meaning]
const EMOJI = [
  ['yes',     '👍', 'true'],
  ['no',      '👎', 'false'],
  ['equals',  '🟰', 'comparison =='],
  ['differs', '🚫', 'comparison !='],
];

function activate(context) {
  const provider = vscode.languages.registerCompletionItemProvider('telly', {
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
  context.subscriptions.push(provider);
}

function deactivate() {}
module.exports = { activate, deactivate };
