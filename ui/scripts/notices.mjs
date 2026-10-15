import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
const read = path => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const entries = [['Escouade · 34322c696757790dd32589311f46c662c057ebd0','licenses/Escouade-MIT.txt'],['diagram-mod · 050643c9e1ce2ae942a0ffa2c2d8cf9404e15bdc','licenses/diagram-mod-MIT.txt']];
let text = read('THIRD_PARTY_NOTICES.md') + '\n';
for (const [name,path] of entries) text += `\n${name}\n${'='.repeat(60)}\n${read(path)}\n`;
for (const [name,license] of [['svelte','LICENSE.md'],['clsx','license'],['esm-env','LICENSE'],['vite','LICENSE.md'],['dompurify','LICENSE'],['dompurify','LICENSE-MPL'],['@fontsource/hanken-grotesk','LICENSE'],['@fontsource/jetbrains-mono','LICENSE']]) {
  const info=JSON.parse(read(`node_modules/${name}/package.json`));
  text += `\n${name} ${info.version} · ${info.license}\n${'='.repeat(60)}\n${read(`node_modules/${name}/${license}`)}\n`;
}
mkdirSync(new URL('../public/assets/',import.meta.url),{recursive:true});
writeFileSync(new URL('../public/assets/THIRD_PARTY_NOTICES.txt',import.meta.url),text.split('\n').map(line => line.trimEnd()).join('\n').trimEnd()+'\n');
