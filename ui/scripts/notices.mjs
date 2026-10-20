import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
const read = path => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const entries = [['Escouade · 34322c696757790dd32589311f46c662c057ebd0','licenses/Escouade-MIT.txt'],['diagram-mod · 050643c9e1ce2ae942a0ffa2c2d8cf9404e15bdc','licenses/diagram-mod-MIT.txt']];
let text = read('THIRD_PARTY_NOTICES.md') + '\n';
for (const [name,path] of entries) text += `\n${name}\n${'='.repeat(60)}\n${read(path)}\n`;
for (const [name,license] of [['svelte','LICENSE.md'],['clsx','license'],['esm-env','LICENSE'],['vite','LICENSE.md'],['dompurify','LICENSE'],['dompurify','LICENSE-MPL'],['@fontsource/hanken-grotesk','LICENSE'],['@fontsource/jetbrains-mono','LICENSE']]) {
  const info=JSON.parse(read(`node_modules/${name}/package.json`));
  text += `\n${name} ${info.version} · ${info.license}\n${'='.repeat(60)}\n${read(`node_modules/${name}/${license}`)}\n`;
}
// marked and mermaid (SR-293), with every package mermaid's lazy chunks may bundle: their
// dependency tree, resolved as node does; type-only packages ship no code
import { existsSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const ui = fileURLToPath(new URL('..', import.meta.url));
const listed = new Set(['svelte','clsx','esm-env','vite','dompurify','@fontsource/hanken-grotesk','@fontsource/jetbrains-mono']);
const walked = new Map();
function walk(name, from) {
  if (name.startsWith('@types/')) return;
  let dir = from, found = null;
  for (;;) { const at = join(dir, 'node_modules', name); if (existsSync(join(at, 'package.json'))) { found = at; break; } if (dir === ui) break; dir = dirname(dir); }
  if (!found || walked.has(found)) return;
  const info = JSON.parse(readFileSync(join(found, 'package.json'), 'utf8')); walked.set(found, info);
  for (const dep of Object.keys(info.dependencies ?? {})) walk(dep, found);
}
walk('marked', ui); walk('mermaid', ui);
for (const [at, info] of [...walked].sort((a, b) => a[1].name.localeCompare(b[1].name) || a[0].localeCompare(b[0]))) {
  if (listed.has(info.name)) continue;
  const files = readdirSync(at).filter(f => /^(licen[cs]e|copying)(\.(md|txt))?$/i.test(f));
  const body = files.map(f => readFileSync(join(at, f), 'utf8')).join('\n') || `${info.license ?? 'see package'}: no licence file in the package`;
  text += `\n${info.name} ${info.version} · ${info.license}\n${'='.repeat(60)}\n${body}\n`;
}
mkdirSync(new URL('../public/assets/',import.meta.url),{recursive:true});
writeFileSync(new URL('../public/assets/THIRD_PARTY_NOTICES.txt',import.meta.url),text.split('\n').map(line => line.trimEnd()).join('\n').trimEnd()+'\n');
