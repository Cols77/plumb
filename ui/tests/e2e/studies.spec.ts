import { expect, test } from '@playwright/test';
import { readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { shot } from './helpers';

// SR-293 EX-1: the study page in plain words with its diagram, from the real bundle under the
// room's content policy: Markdown drawn, the mermaid block drawn as an SVG in plum and brass.
test('a study is drawn as Markdown with its mermaid diagram', async ({ page }, info) => {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/?study=how-plumb-s-background-jobs-run#token=e2e-token');
  const body = page.locator('.study-body');
  await expect(body.locator('h2')).toHaveText('The dispatcher');
  await expect(body.locator('strong')).toHaveText('dispatcher');
  await expect(body.locator('table td')).toHaveCount(3);
  const svg = page.locator('figure.study-diagram svg');
  await expect(svg).toBeVisible();
  await expect(svg).toContainText('dispatcher');
  await expect(page.locator('code.language-mermaid')).toHaveCount(0);
  expect(await svg.locator('rect, polygon, path').first().evaluate(n => getComputedStyle(n).stroke)).toMatch(/176, 95, 176|201, 162, 39/);
  await shot(page, info, 'study-markdown-diagram');
  expect(errors).toEqual([]);
});

test('a broken diagram shows its source with a short note', async ({ page }, info) => {
  await page.goto('/?study=a-broken-diagram#token=e2e-token');
  await expect(page.locator('.study-diagram-note')).toHaveText('This diagram could not be drawn; its source is below.');
  await expect(page.locator('code.language-mermaid')).toContainText('D[dispatcher -->');
  await shot(page, info, 'study-broken-diagram');
});

// SR-342 (DEC-315): a landing rebuilds the bundle under an open tab and removes the old hashed
// chunks; opening a study then still draws its diagram (the page reloads onto the new build).
function rebuild(dir: string) {
  const assets = join(dir, 'assets');
  const names = readdirSync(assets);
  const renamed = (name: string) => name.replace(/(\.[a-z0-9]+)$/, 'x$1'); // a new hash
  const text = (name: string) => /\.(js|css|html)$/.test(name);
  const swapRefs = (body: string) => names.reduce((out, name) => out.split(name).join(renamed(name)), body);
  for (const name of names) {
    const from = join(assets, name);
    if (text(name)) writeFileSync(join(assets, renamed(name)), swapRefs(readFileSync(from, 'utf8')));
    else writeFileSync(join(assets, renamed(name)), readFileSync(from));
    rmSync(from);
  }
  writeFileSync(join(dir, 'index.html'), swapRefs(readFileSync(join(dir, 'index.html'), 'utf8')));
}

test('a study opened after a rebuild under the open tab still draws its diagram', async ({ page }, info) => {
  await page.goto('http://127.0.0.1:8767/#token=e2e-token');
  await expect(page.getByRole('navigation', { name: 'Studies' })).toBeVisible();
  rebuild(process.env.PLUMB_E2E_SWAP!);
  await page.getByText("How plumb's background jobs run").first().click();
  const svg = page.locator('figure.study-diagram svg');
  await expect(svg).toBeVisible();
  await expect(svg).toContainText('dispatcher');
  await expect(page.locator('.study-diagram-note')).toHaveCount(0);
  await shot(page, info, 'study-diagram-after-rebuild');
});
