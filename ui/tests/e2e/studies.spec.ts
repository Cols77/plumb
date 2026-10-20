import { expect, test } from '@playwright/test';
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
