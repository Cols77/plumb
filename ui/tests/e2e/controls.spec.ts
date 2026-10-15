import { expect, test, type Page } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { journal, open, projectRoot, receipt, row, stored } from './helpers';

const details = (page: Page, summary: string) => page.getByRole('tabpanel').locator(`details:has(summary:text-is("${summary}"))`).first();
const loaded = (page: Page) => expect(page.locator('main')).toHaveAttribute('aria-busy', 'false');

test('the skip link moves focus to the selected issue', async ({ page }) => {
  await open(page);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to selected issue' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('main#issue-detail')).toBeFocused();
  await row(page, 'Choose the export format').click();
  await expect(page).toHaveURL(/card=demo-card-5$/);
});

test('the help dialog links the third-party notices', async ({ page, context }) => {
  await open(page);
  await page.getByRole('button', { name: 'Help' }).click();
  const response = context.waitForEvent('response', item => item.url().endsWith('/assets/THIRD_PARTY_NOTICES.txt'));
  const popup = page.waitForEvent('popup');
  await page.locator('.help-dialog').getByRole('link', { name: 'Third-party notices' }).click();
  expect((await popup).url()).toMatch(/\/assets\/THIRD_PARTY_NOTICES\.txt$/);
  const notices = await response;
  expect(notices.status()).toBe(200);
  expect((await notices.text()).length).toBeGreaterThan(0);
});

test('the Processing filter shows its empty count and no rows', async ({ page }) => {
  await open(page);
  const processing = page.getByLabel('Issue inbox').getByRole('button', { name: /^Processing/ });
  await processing.click();
  await expect(processing).toHaveAttribute('aria-pressed', 'true');
  await expect(processing.locator('.count')).toHaveText('0');
  await expect(page.locator('.issue-row')).toHaveCount(0);
  await expect(page.getByText('No issues match these filters.')).toBeVisible();
});

test('the inbox splitter resizes by key, pointer and double click, and keeps its width', async ({ page }) => {
  await open(page);
  const handle = page.getByRole('separator', { name: 'Resize issue inbox' });
  const width = () => page.locator('#issue-inbox').evaluate(node => node.getBoundingClientRect().width);
  await expect(handle).toHaveAttribute('aria-valuenow', '260');
  await handle.focus();
  await page.keyboard.press('ArrowRight');
  await expect(handle).toHaveAttribute('aria-valuenow', '276');
  expect(await width()).toBe(276);
  await page.keyboard.press('Home');
  await expect(handle).toHaveAttribute('aria-valuenow', '220');
  await page.keyboard.press('End');
  await expect(handle).toHaveAttribute('aria-valuenow', '380');
  expect(await width()).toBe(380);
  await handle.dblclick();
  await expect(handle).toHaveAttribute('aria-valuenow', '260');
  await page.keyboard.press('ArrowRight');
  await page.reload();
  await loaded(page);
  await expect(handle).toHaveAttribute('aria-valuenow', '276');
  expect(await page.evaluate(() => localStorage.getItem('plumb.inbox-width'))).toBe('276');
  const box = (await handle.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 200);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 40, box.y + 200, { steps: 4 });
  await page.mouse.up();
  await expect(handle).toHaveAttribute('aria-valuenow', '316');
  expect(await width()).toBe(316);
});

test('the evidence splitter grows leftwards and keeps its width', async ({ page }) => {
  await open(page);
  const handle = page.getByRole('separator', { name: 'Resize evidence pane' });
  const width = () => page.locator('.evidence-pane').evaluate(node => node.getBoundingClientRect().width);
  await expect(handle).toHaveAttribute('aria-valuenow', '320');
  await handle.focus();
  await page.keyboard.press('ArrowLeft');
  await expect(handle).toHaveAttribute('aria-valuenow', '336');
  expect(await width()).toBe(336);
  await page.keyboard.press('End');
  await expect(handle).toHaveAttribute('aria-valuenow', '460');
  await page.keyboard.press('Home');
  await expect(handle).toHaveAttribute('aria-valuenow', '260');
  await handle.dblclick();
  await expect(handle).toHaveAttribute('aria-valuenow', '320');
  await page.keyboard.press('ArrowLeft');
  await page.reload();
  await loaded(page);
  await expect(handle).toHaveAttribute('aria-valuenow', '336');
  expect(await page.evaluate(() => localStorage.getItem('plumb.evidence-width'))).toBe('336');
});

test('Cancel closes the composer, sends nothing and keeps the draft', async ({ page, request }) => {
  const root = await projectRoot(request);
  const before = journal(root, 'demo-session').length;
  let presses = 0;
  page.on('request', item => { if (item.url().endsWith('/press')) presses++; });
  await open(page, 'demo-session', 'demo-card-1');
  await page.getByRole('button', { name: 'Ask for a change', exact: true }).click();
  await page.getByLabel('Your correction').fill('Keep the column headers.');
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByLabel('Your correction')).toHaveCount(0);
  expect(presses).toBe(0);
  expect(journal(root, 'demo-session')).toHaveLength(before);
  await page.getByRole('button', { name: 'Ask for a change', exact: true }).click();
  await expect(page.getByLabel('Your correction')).toHaveValue('Keep the column headers.');
});

test('back after changing the session restores the previous session and card', async ({ page }) => {
  await open(page, 'demo-session', 'demo-card-5');
  await page.getByLabel('Source session').selectOption('e2e-trial');
  await expect(page).toHaveURL(/session=e2e-trial$/);
  await page.goBack();
  await expect(page.getByLabel('Source session')).toHaveValue('demo-session');
  await expect(page.locator('h1')).toHaveText('Choose the export format');
  await expect(page).toHaveURL(/session=demo-session&card=demo-card-5$/);
  await page.goForward();
  await expect(page.getByLabel('Source session')).toHaveValue('e2e-trial');
  await expect(page.locator('h1')).toHaveText('Keep exports readable'); // the first issue is selected when the address names none
});

test('the workspace polls every 15 seconds while visible, never while hidden', async ({ page, request }) => {
  const root = await projectRoot(request);
  await page.clock.install();
  const hits = { workspace: 0, draw: 0 };
  page.on('request', item => { if (item.url().endsWith('/api/workspace')) hits.workspace++; if (item.url().endsWith('/draw')) hits.draw++; });
  await open(page, 'e2e-poll');
  expect(hits).toEqual({ workspace: 1, draw: 1 });
  const cardsFile = join(root, '.plumb/session/e2e-poll/cards.json');
  const cards = JSON.parse(readFileSync(cardsFile, 'utf8'));
  cards.find((card: { id: string }) => card.id === 'demo-card-3').topic = 'Confirm the renamed filter';
  writeFileSync(cardsFile, JSON.stringify(cards));
  await page.clock.runFor(15000);
  await expect(row(page, 'Confirm the renamed filter')).toBeVisible();
  expect(hits).toEqual({ workspace: 2, draw: 2 });
  await page.evaluate(() => Object.defineProperty(document, 'hidden', { get: () => true }));
  await page.clock.runFor(15000);
  expect(hits).toEqual({ workspace: 2, draw: 2 });
});

test('resizing the window switches between the inbox and the drawer', async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 800 });
  await open(page);
  const inbox = page.locator('#issue-inbox');
  const issues = page.locator('.mobile-bar').getByRole('button', { name: /^Issues/ });
  await expect(inbox).not.toHaveAttribute('inert', '');
  await expect(issues).toBeHidden();
  await page.setViewportSize({ width: 600, height: 800 });
  await expect(inbox).toHaveAttribute('inert', '');
  await expect(issues).toBeVisible();
  await issues.click();
  await expect(inbox).toHaveClass(/drawer-open/);
  await page.setViewportSize({ width: 1200, height: 800 });
  await expect(inbox).not.toHaveAttribute('inert', '');
  await expect(issues).toBeHidden();
  await row(page, 'Choose the export format').click();
  await expect(page.locator('h1')).toHaveText('Choose the export format');
});

test('a press that never reaches the server keeps the text and retries under the same request id', async ({ page, request }) => {
  const root = await projectRoot(request);
  const bodies: { request_id: string }[] = [];
  page.on('request', item => { if (item.url().endsWith('/press')) bodies.push(item.postDataJSON()); });
  await page.route('**/press', route => route.abort('connectionrefused'), { times: 1 });
  await open(page, 'e2e-retry', 'demo-card-1');
  await page.getByRole('button', { name: 'Ask for a change', exact: true }).click();
  await page.getByLabel('Your correction').fill('Keep the column headers.');
  const send = page.getByRole('button', { name: 'Send correction' });
  await send.click();
  await expect(page.locator('.action-error')).toContainText('Your text is kept; retry the same action to check its receipt.');
  await expect(page.locator('.connection')).toHaveText('Disconnected');
  await expect(page.getByLabel('Your correction')).toHaveValue('Keep the column headers.');
  await expect(send).toBeEnabled();
  await send.click();
  await expect(receipt(page)).toContainText('Say what to change about "Keep exports readable"');
  await expect(page.locator('.connection')).toHaveText('Connected');
  expect((await stored(request, 'e2e-retry', 'demo-card-1')).card.status).toBe('change_requested');
  expect(journal(root, 'e2e-retry').filter(entry => entry.text === 'Keep the column headers.')).toHaveLength(1);
  expect(bodies).toHaveLength(2);
  expect(bodies[1].request_id).toBe(bodies[0].request_id);
});

test('a project without source sessions shows its empty state', async ({ page }) => {
  await page.goto('http://127.0.0.1:8766/#token=e2e-token');
  await loaded(page);
  await expect(page.locator('h1')).toHaveText('No source sessions yet');
  await expect(page.getByText('No source sessions yet.')).toBeVisible();
  await expect(page.getByLabel('Source session')).toBeDisabled();
  await expect(page).toHaveURL('http://127.0.0.1:8766/');
});

test('Retry diagram loads the diagram after a failed fetch', async ({ page }) => {
  await page.route(url => url.pathname.endsWith('/diagram'), route => route.abort('connectionrefused'), { times: 1 });
  await open(page, 'demo-session', 'demo-card-1');
  const fallback = page.locator('.diagram-fallback');
  await expect(fallback.locator('p')).not.toBeEmpty();
  await fallback.getByRole('button', { name: 'Retry diagram' }).click();
  await expect(page.locator('.diagram-viewport img')).toBeVisible();
  await expect(page.getByLabel('Diagram zoom')).toHaveText('100%');
  await expect(fallback).toHaveCount(0);
});

test('zoom stops at 50% and 300% until Fit', async ({ page }) => {
  await open(page, 'demo-session', 'demo-card-1');
  const zoom = page.getByLabel('Diagram zoom');
  const zoomOut = page.getByRole('button', { name: 'Zoom out' });
  const zoomIn = page.getByRole('button', { name: 'Zoom in' });
  await zoomOut.click();
  await zoomOut.click();
  await expect(zoom).toHaveText('50%');
  await expect(zoomOut).toBeDisabled();
  await zoomOut.dispatchEvent('click');
  await expect(zoom).toHaveText('50%');
  for (let n = 0; n < 10; n++) await zoomIn.click();
  await expect(zoom).toHaveText('300%');
  await expect(zoomIn).toBeDisabled();
  await page.getByRole('button', { name: 'Fit' }).click();
  await expect(zoom).toHaveText('100%');
  await expect(zoomIn).toBeEnabled();
  await expect(zoomOut).toBeEnabled();
});

test('Source evidence is open by default and Technical details shows the stored status', async ({ page, request }) => {
  await open(page, 'demo-session', 'demo-card-1');
  const evidence = details(page, 'Source evidence');
  await expect(evidence).toHaveAttribute('open', '');
  await expect(evidence.locator('.prose')).toBeVisible();
  await evidence.locator('summary').click();
  await expect(evidence).not.toHaveAttribute('open', '');
  await expect(evidence.locator('.prose')).toBeHidden();
  const technical = details(page, 'Technical details');
  await expect(technical.locator('pre')).toBeHidden();
  await technical.locator('summary').click();
  await expect(technical.locator('pre')).toBeVisible();
  const status = (await stored(request, 'demo-session', 'demo-card-1')).card.records[0].status;
  expect(status).toHaveProperty('confirmation');
  expect(JSON.parse(await technical.locator('pre').innerText())).toEqual(status);
});

test('conflict evidence: Split after Unified, Base value, and no proposed version', async ({ page, request }) => {
  await open(page, 'demo-session', 'conflict:IC-001');
  const evidence = page.getByRole('tabpanel');
  await evidence.getByRole('button', { name: 'Unified' }).click();
  await expect(evidence.locator('.diff-scroll .urow')).toHaveCount(2);
  await evidence.getByRole('button', { name: 'Split' }).click();
  await expect(evidence.getByRole('button', { name: 'Split' })).toHaveAttribute('aria-pressed', 'true');
  await expect(evidence.getByRole('button', { name: 'Unified' })).toHaveAttribute('aria-pressed', 'false');
  await expect(evidence.locator('.diff-scroll .srow')).toHaveCount(1);
  await expect(evidence.locator('.diff-scroll .srow .cell')).toHaveCount(2);
  const base = details(page, 'Base value');
  await expect(base.locator('pre')).toBeHidden();
  await base.locator('summary').click();
  await expect(base.locator('pre')).toBeVisible();
  await expect(base.locator('pre')).toHaveText((await stored(request, 'demo-session', 'conflict:IC-001')).card.diff.fields.statement.base);
  await expect(evidence.getByText('Stored proposed version')).toHaveCount(0);
});

test('a conflict with a proposed version shows it on request', async ({ page }) => {
  await open(page, 'e2e-proposed', 'conflict:IC-003');
  const proposed = details(page, 'Stored proposed version');
  await expect(proposed.locator('pre')).toBeHidden();
  await proposed.locator('summary').click();
  await expect(proposed.locator('pre')).toBeVisible();
  await expect(proposed.locator('pre')).toContainText('name, email, address, phone');
});

test('Only this issue narrows the activity to the selected card', async ({ page }) => {
  await open(page, 'e2e-activity', 'demo-card-1');
  await page.getByRole('button', { name: 'Leave open' }).click();
  await expect(receipt(page)).toContainText('Left open: "Keep exports readable"');
  await row(page, 'Choose the export format').click();
  await page.getByRole('button', { name: 'Leave open' }).click();
  await expect(receipt(page)).toContainText('Left open: "Choose the export format"');
  await page.getByRole('tab', { name: /^Activity/ }).click();
  const items = page.locator('.activity-list li');
  await expect(items).toHaveCount(2);
  await page.getByLabel('Only this issue').check();
  await expect(items).toHaveCount(1);
  await expect(items.locator('.wrap')).toHaveText('demo-card-5');
  await page.getByLabel('Only this issue').uncheck();
  await expect(items).toHaveCount(2);
});

test('a long diff stays folded until asked, then draws 500 rows at a time', async ({ page }) => {
  await open(page, 'e2e-long', 'conflict:IC-004');
  const scroll = page.getByRole('tabpanel').locator('.diff-scroll');
  await expect(scroll.locator('.note')).toContainText('2400 lines');
  await expect(scroll.locator('.urow, .srow')).toHaveCount(0);
  const show = scroll.getByRole('button', { name: 'Show diff' });
  await show.scrollIntoViewIfNeeded();
  const scrolled = () => page.evaluate(() => [window.scrollY, document.querySelector('.evidence-pane')!.scrollTop]);
  const before = await scrolled();
  await show.click();
  await expect(scroll.locator('.srow')).toHaveCount(500);
  await expect(scroll.getByRole('button', { name: 'Show 500 more lines' })).toBeFocused();
  expect(await scrolled()).toEqual(before);
  await scroll.getByRole('button', { name: 'Show 500 more lines' }).click();
  await expect(scroll.locator('.srow')).toHaveCount(1000);
  await expect(scroll.getByRole('button', { name: 'Show 200 more lines' })).toBeFocused();
  await scroll.getByRole('button', { name: 'Show 200 more lines' }).click();
  await expect(scroll.locator('.srow')).toHaveCount(1200);
  await expect(scroll.getByRole('button', { name: /more lines/ })).toHaveCount(0);
  await expect(scroll.locator('.rows')).toBeFocused();
});

test.describe('phone width', () => {
  test.use({ viewport: { width: 390, height: 844 } });
  const opened = async (page: Page) => {
    await open(page);
    const inbox = page.locator('#issue-inbox');
    const issues = page.locator('.mobile-bar').getByRole('button', { name: /^Issues/ });
    await issues.click();
    await expect(inbox).toHaveClass(/drawer-open/);
    return { inbox, issues };
  };
  const closed = async (inbox: ReturnType<Page['locator']>, issues: ReturnType<Page['locator']>) => {
    await expect(inbox).not.toHaveClass(/drawer-open/);
    await expect(inbox).toHaveAttribute('inert', '');
    await expect(issues).toBeFocused();
    await expect(issues).toHaveAttribute('aria-expanded', 'false');
  };

  test('the shade closes the drawer', async ({ page }) => {
    const { inbox, issues } = await opened(page);
    await page.locator('.drawer-shade').click({ position: { x: 370, y: 600 } });
    await closed(inbox, issues);
  });

  test('the close button closes the drawer', async ({ page }) => {
    const { inbox, issues } = await opened(page);
    await page.getByRole('button', { name: 'Close issues', exact: true }).click();
    await closed(inbox, issues);
  });

  test('Tab wraps inside the open drawer', async ({ page }) => {
    await opened(page);
    const first = page.getByRole('button', { name: 'Close issues', exact: true });
    const last = page.locator('.issue-row').last();
    await last.focus();
    await page.keyboard.press('Tab');
    await expect(first).toBeFocused();
    await page.keyboard.press('Shift+Tab');
    await expect(last).toBeFocused();
    expect(await page.evaluate(() => document.getElementById('issue-inbox')!.contains(document.activeElement))).toBe(true);
  });
});
