import { expect, type APIRequestContext, type Page, type TestInfo } from '@playwright/test';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

export const BASE = 'http://127.0.0.1:8765';
const headers = { Authorization: 'Bearer e2e-token', Origin: BASE, 'Content-Type': 'application/json' };

export async function open(page: Page, session = 'demo-session', card = '') {
  await page.goto(`${BASE}/?${new URLSearchParams({ session, ...(card ? { card } : {}) })}#token=e2e-token`);
  await expect(page.getByLabel('Source session')).toHaveValue(session);
  await expect(page.locator('main')).toHaveAttribute('aria-busy', 'false');
}

export async function projectRoot(request: APIRequestContext) {
  const response = await request.get(`${BASE}/api/workspace`, { headers });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).project.root as string;
}

/** What the server stores now: the card as a fresh draw returns it, plus the session's follow-ups. */
export async function stored(request: APIRequestContext, session: string, card: string) {
  const response = await request.post(`${BASE}/api/sessions/${session}/draw`, { headers, data: {} });
  expect(response.ok()).toBeTruthy();
  const drawn = await response.json();
  return { card: drawn.cards.find((item: { id: string }) => item.id === card), followups: drawn.followups as { id: string; card: string; status: string }[] };
}

function jsonFiles(dir: string) {
  try { return readdirSync(dir).map(name => JSON.parse(readFileSync(join(dir, name), 'utf8'))); } catch { return []; }
}
export const logged = (root: string, kind: string) => jsonFiles(join(root, '.plumb/log', kind)).map(entry => entry.payload);
export const journal = (root: string, session: string) => jsonFiles(join(root, '.plumb/session', session, 'browser-actions'));

export const row = (page: Page, title: string) => page.locator('.issue-row', { hasText: title });
export const receipt = (page: Page) => page.locator('.receipt');
export const shot = (page: Page, info: TestInfo, name: string) => page.screenshot({ path: info.outputPath(`${name}.png`) });

/** Open the composer with a change button, send the correction and return the receipt. */
export async function correct(page: Page, button: string, text: string) {
  await page.getByRole('button', { name: button, exact: true }).click();
  const send = page.getByRole('button', { name: 'Send correction' });
  await expect(send).toBeDisabled();
  await page.getByLabel('Your correction').fill(text);
  await send.click();
  await expect(page.getByLabel('Your correction')).toHaveCount(0);
}
/** Offer ids are content digests shared by identical cards, so approvals are counted per session and card. */
export const approvals = (root: string, session: string, card: string) => logged(root, 'approval').filter(payload => payload.session === session && payload.card === card);
