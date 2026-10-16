import { expect, test } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { approvals, correct, journal, logged, open, projectRoot, receipt, row, shot, stored } from './helpers';

test('a double click records one answer', async ({ page, request }) => {
  const root = await projectRoot(request);
  await open(page, 'e2e-duplicate', 'demo-card-4');
  await page.getByRole('button', { name: 'Yes', exact: true }).dblclick();
  await expect(receipt(page)).toContainText('You pressed Yes: now confirmed: "Choose when to send notifications".');
  await expect(receipt(page)).not.toContainText('already recorded');
  const now = await stored(request, 'e2e-duplicate', 'demo-card-4');
  expect(now.card.answers).toHaveLength(1);
  expect(now.followups).toHaveLength(1);
  expect(logged(root, 'card-press').filter(payload => payload.session === 'e2e-duplicate' && payload.card === 'demo-card-4')).toHaveLength(1);
  expect(approvals(root, 'e2e-duplicate', 'demo-card-4')).toHaveLength(1);
});

test('trial card: Leave open, Ask for a change with text, Yes, and No', async ({ page, request }, info) => {
  const root = await projectRoot(request);
  await open(page, 'e2e-trial', 'demo-card-1');
  await page.getByRole('button', { name: 'Leave open' }).click();
  await expect(receipt(page)).toContainText('Left open: "Keep exports readable"');
  await expect(receipt(page)).toContainText('Follow-up queued');
  let now = await stored(request, 'e2e-trial', 'demo-card-1');
  expect(now.card.state).toBe('left_open');
  expect(now.followups.map(item => item.status)).toEqual(['queued']);
  await expect(page.locator('.status-badge').first()).toHaveText('left open');

  await correct(page, 'Ask for a change', 'Keep the column headers exactly as they are.');
  await expect(receipt(page)).toContainText('Say what to change about "Keep exports readable"');
  now = await stored(request, 'e2e-trial', 'demo-card-1');
  expect(now.card.state).toBe('waiting');
  expect(now.card.status).toBe('change_requested');
  expect(journal(root, 'e2e-trial').filter(entry => entry.text === 'Keep the column headers exactly as they are.').map(entry => entry.status)).toEqual(['queued']);
  await shot(page, info, 'receipt');

  await page.getByRole('button', { name: 'Yes', exact: true }).click();
  await expect(receipt(page)).toContainText('You pressed Yes: now confirmed: "Keep exports readable".');
  await expect(page.getByText('Recorded answer: accepted')).toBeVisible();
  now = await stored(request, 'e2e-trial', 'demo-card-1');
  expect(now.card.state).toBe('done');
  expect(now.card.answers.map((answer: { answer: string }) => answer.answer)).toEqual(['accepted']);
  expect(now.followups).toHaveLength(3);
  expect(approvals(root, 'e2e-trial', 'demo-card-1')).toHaveLength(1);
  await page.getByRole('tab', { name: /^Activity/ }).click();
  await expect(page.getByRole('tabpanel').locator('.activity-list li')).toHaveCount(3);
  await expect(page.getByRole('tabpanel').locator('.activity-list .status-badge').first()).toHaveText('queued');

  await row(page, 'Choose when to send notifications').click();
  await page.getByRole('button', { name: 'No', exact: true }).click();
  await expect(receipt(page)).toContainText('You pressed No');
  now = await stored(request, 'e2e-trial', 'demo-card-4');
  expect(now.card.state).toBe('done');
  expect(now.card.answers.map((answer: { answer: string }) => answer.answer)).toEqual(['rejected']);
});

test('trial card: Fix it with text', async ({ page, request }) => {
  const root = await projectRoot(request);
  await open(page, 'e2e-choice', 'demo-card-4');
  await correct(page, 'Fix it', 'Send notifications only after export completes.');
  await expect(receipt(page)).toContainText('Say what to change about "Choose when to send notifications"');
  const now = await stored(request, 'e2e-choice', 'demo-card-4');
  expect(now.card.status).toBe('change_requested');
  expect(now.card.offers).toHaveLength(1);
  expect(journal(root, 'e2e-choice').filter(entry => entry.card === 'demo-card-4').map(entry => entry.text)).toEqual(['Send notifications only after export completes.']);
});

test('choice card: Leave open, Ask for a change, then Keep CSV', async ({ page, request }) => {
  await open(page, 'e2e-choice', 'demo-card-5');
  await expect(page.locator('legend')).toHaveText('Which format should exports use?');
  await page.getByRole('button', { name: 'Leave open' }).click();
  await expect(receipt(page)).toContainText('Left open: "Choose the export format"');
  expect((await stored(request, 'e2e-choice', 'demo-card-5')).card.state).toBe('left_open');
  await correct(page, 'Ask for a change', 'Offer both formats in the dialog.');
  await expect(receipt(page)).toContainText('Say what to change about "Choose the export format"');
  expect((await stored(request, 'e2e-choice', 'demo-card-5')).card.status).toBe('change_requested');
  await page.getByRole('button', { name: 'Keep CSV' }).click();
  await expect(receipt(page)).toContainText('You pressed Keep CSV: now confirmed: "Choose the export format".');
  const now = await stored(request, 'e2e-choice', 'demo-card-5');
  expect(now.card.state).toBe('done');
  expect(now.card.answers.map((answer: { answer: string }) => answer.answer)).toEqual(['accepted']);
});

test('choice card: Use JSON records the chosen change', async ({ page, request }) => {
  await open(page, 'e2e-choice-json', 'demo-card-5');
  await page.getByRole('button', { name: 'Use JSON' }).click();
  await expect(receipt(page)).toContainText('You pressed Use JSON on "Choose the export format".');
  const now = await stored(request, 'e2e-choice-json', 'demo-card-5');
  expect(now.card.state).toBe('done');
  expect(now.card.answers.map((answer: { answer: string }) => answer.answer)).toEqual(['change: Use JSON']);
});

test('conflict card: Leave open, Ask for a change, Both, then Keep this one', async ({ page, request }, info) => {
  const root = await projectRoot(request);
  const record = join(root, '.plumb/requirements/SR-006.md');
  const before = readFileSync(record, 'utf8');
  await open(page, 'e2e-conflict', 'conflict:IC-001');
  const evidence = page.getByRole('tabpanel');
  await expect(evidence.getByText('Stored conflict · SR-006')).toBeVisible();
  await expect(evidence.locator('.diff-labels')).toContainText('saved workflow');
  await expect(evidence.locator('.diff-scroll')).toContainText('email, name');
  await evidence.getByRole('button', { name: 'Unified' }).click();
  await expect(evidence.getByRole('button', { name: 'Unified' })).toHaveAttribute('aria-pressed', 'true');
  await expect(evidence.locator('.diff-scroll')).toContainText('name, email, address');
  await page.getByRole('button', { name: 'Leave open' }).click();
  await expect(receipt(page)).toContainText('Left open: "Export column order"');
  expect((await stored(request, 'e2e-conflict', 'conflict:IC-001')).card.state).toBe('left_open');
  await correct(page, 'Ask for a change', 'Keep every column and add phone.');
  await expect(receipt(page)).toContainText('Say what to change about "Export column order"');
  await page.getByRole('button', { name: 'Both' }).click();
  await expect(receipt(page)).toContainText('Say what to change about "Export column order"');
  let now = await stored(request, 'e2e-conflict', 'conflict:IC-001');
  expect(now.card.status).toBe('change_requested');
  expect(now.card.diff.record).toBe('SR-006');
  expect(readFileSync(record, 'utf8')).toBe(before);
  await shot(page, info, 'conflict');
  await page.getByRole('button', { name: 'Keep this one' }).click();
  await expect(receipt(page)).toContainText('You pressed Keep this one on "Export column order".');
  now = await stored(request, 'e2e-conflict', 'conflict:IC-001');
  expect(now.card.state).toBe('done');
  expect(now.card.diff).toBeNull();
  expect(readFileSync(record, 'utf8')).toContain('statement: name, email, address');
  expect(logged(root, 'conflict-resolution').filter(payload => JSON.stringify(payload).includes('IC-001'))).toHaveLength(1);
});

test('conflict card: Keep the other applies their version', async ({ page, request }) => {
  const root = await projectRoot(request);
  await open(page, 'e2e-conflict-other', 'conflict:IC-002');
  await expect(page.getByRole('tabpanel').getByText('Stored conflict · SR-007')).toBeVisible();
  await page.getByRole('button', { name: 'Keep the other' }).click();
  await expect(receipt(page)).toContainText('You pressed Keep the other on "Export column order".');
  const now = await stored(request, 'e2e-conflict-other', 'conflict:IC-002');
  expect(now.card.state).toBe('done');
  expect(readFileSync(join(root, '.plumb/requirements/SR-007.md'), 'utf8')).toContain('statement: email, name');
});

test('a card or record changed on disk after the draw cannot be answered as shown', async ({ page, request }, info) => {
  const root = await projectRoot(request);
  await open(page, 'e2e-stale', 'demo-card-5');
  const cardsFile = join(root, '.plumb/session/e2e-stale/cards.json');
  const cards = JSON.parse(readFileSync(cardsFile, 'utf8'));
  cards.find((card: { id: string }) => card.id === 'demo-card-5').questions[0].text = 'A materially different question';
  writeFileSync(cardsFile, JSON.stringify(cards));
  await page.getByRole('button', { name: 'Keep CSV' }).click();
  await expect(page.locator('.action-error')).toHaveText(/The card changed since it was shown\. Refresh it before answering\. Refresh to review the latest issue\./);
  await expect(page.getByRole('button', { name: 'Keep CSV' })).toBeDisabled();
  let now = await stored(request, 'e2e-stale', 'demo-card-5');
  expect(now.card.answers).toEqual([]);
  expect(now.followups.map(item => item.status)).toEqual(['failed']);
  await shot(page, info, 'stale-card');
  await page.locator('.action-error').getByRole('button', { name: 'Refresh issue' }).click();
  await expect(page.locator('legend')).toHaveText('A materially different question');
  await expect(page.getByRole('button', { name: 'Keep CSV' })).toBeEnabled();

  await row(page, 'Keep exports readable').click();
  const record = join(root, '.plumb/requirements/SR-001.md');
  const original = readFileSync(record, 'utf8');
  writeFileSync(record, original.replace('statement: Keep exports readable.', 'statement: Keep exports readable and sorted.'));
  try {
    await page.getByRole('button', { name: 'Yes', exact: true }).click();
    await expect(receipt(page)).toContainText('"Keep exports readable" changed since it was shown; nothing was confirmed.');
    now = await stored(request, 'e2e-stale', 'demo-card-1');
    expect(now.card.state).toBe('blocked');
    expect(now.card.answers).toEqual([]);
    expect(approvals(root, 'e2e-stale', 'demo-card-1')).toHaveLength(0);
    await shot(page, info, 'stale-record');
  } finally {
    writeFileSync(record, original);
  }
});

test('a multi-question card answers each question on its own and shows the missing-diagram fallback', async ({ page, request }, info) => {
  await open(page, 'multi-question', 'multi-card');
  await expect(page.locator('legend')).toHaveText(['Is this what you meant?', 'Which format should exports use?']);
  await expect(page.locator('.diagram-fallback')).toHaveText('Diagram file is missing');
  await expect(page.locator('.diagram img')).toHaveCount(0);
  await shot(page, info, 'multi-question');
  await page.locator('fieldset').first().getByRole('button', { name: 'Yes', exact: true }).click();
  await expect(receipt(page)).toContainText('You pressed Yes');
  await expect(page.locator('fieldset').first()).toContainText('Answer recorded for this question.');
  let now = await stored(request, 'multi-question', 'multi-card');
  expect(now.card.state).toBe('waiting');
  expect(now.card.answers.map((answer: { question: string }) => answer.question)).toEqual([expect.stringContaining('SR-001')]);
  await expect(page.locator('fieldset').nth(1).getByRole('button', { name: 'Keep CSV' })).toBeEnabled();
  await page.locator('fieldset').nth(1).getByRole('button', { name: 'Keep CSV' }).click();
  await expect(receipt(page)).toContainText('You pressed Keep CSV');
  now = await stored(request, 'multi-question', 'multi-card');
  expect(now.card.state).toBe('done');
  expect(now.card.answers.map((answer: { question: string }) => answer.question)).toEqual([expect.stringContaining('SR-001'), 'second']);
});
