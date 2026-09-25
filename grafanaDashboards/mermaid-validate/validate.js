// Validates every jdbranham-diagram-panel's mermaid content against the EXACT
// mermaid version that plugin bundles (8.8.0 - confirmed by downloading and
// inspecting the actual published plugin .zip; the plugin's package.json says
// "^8.8.0" but that range resolves to whatever was latest 8.x at BUILD time,
// which was frozen at 8.8.0, not today's latest 8.x). This mermaid version
// predates several features later mermaid releases support silently and
// happily in a browser preview - most notably per-subgraph `direction`, which
// it parses as a bare vertex id and then fails on the next token.
//
// Usage (from this directory):
//   npm install                 (once - installs the pinned mermaid + jsdom)
//   node validate.js            (validates every dashboard JSON one level up)
//   node validate.js <file.json> [file2.json ...]   (validate specific files)
'use strict';
const fs = require('fs');
const path = require('path');

const { JSDOM } = require('jsdom');
const dom = new JSDOM('<!doctype html><html><body></body></html>');
global.window = dom.window;
global.document = dom.window.document;
// Node 21+ defines a getter-only `navigator` global; plain assignment throws
// under 'use strict'.
Object.defineProperty(global, 'navigator', { value: dom.window.navigator, configurable: true });
const mermaid = require('mermaid');

function findDiagramPanels(panels, out) {
  for (const p of panels || []) {
    if (p.type === 'jdbranham-diagram-panel' && p.options && p.options.content) {
      out.push(p);
    }
    if (p.panels) findDiagramPanels(p.panels, out);
  }
  return out;
}

function checkFile(file) {
  const dashboard = JSON.parse(fs.readFileSync(file, 'utf8'));
  const diagrams = findDiagramPanels(dashboard.panels, []);
  let failures = 0;
  for (const p of diagrams) {
    try {
      mermaid.parse(p.options.content);
      console.log(`  OK    ${file} :: "${p.title}"`);
    } catch (e) {
      failures++;
      const msg = typeof e === 'string' ? e : (e && (e.str || e.message)) || String(e);
      console.log(`  FAIL  ${file} :: "${p.title}"\n${msg.split('\n').map(l => '        ' + l).join('\n')}`);
    }
  }
  if (diagrams.length === 0) {
    console.log(`  --    ${file} (no diagram panels)`);
  }
  return failures;
}

function walkJsonFiles(dir) {
  let out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out = out.concat(walkJsonFiles(full));
    else if (entry.name.endsWith('.json')) out.push(full);
  }
  return out;
}

const argFiles = process.argv.slice(2);
const files = argFiles.length ? argFiles : walkJsonFiles(path.join(__dirname, '..', 'dashboards'));

let total = 0;
for (const f of files) total += checkFile(f);

if (total > 0) {
  console.error(`\n${total} mermaid parse failure(s).`);
  process.exit(1);
} else {
  console.log('\nAll diagram panels parse cleanly under mermaid 8.8.0.');
}
