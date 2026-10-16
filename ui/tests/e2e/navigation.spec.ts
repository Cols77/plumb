import { expect, test } from '@playwright/test';
import { open, row, shot } from './helpers';

test('selects an issue by click and by keyboard', async ({ page }, info) => {
  await open(page);
  await expect(page.locator('h1')).toHaveText('Keep exports readable');
  await expect(page.locator('.issue-row')).toHaveCount(6);
  await row(page, 'Choose the export format').click();
  await expect(page.locator('h1')).toHaveText('Choose the export format');
  await expect(page).toHaveURL(/card=demo-card-5/);
  await expect(row(page, 'Choose the export format')).toHaveAttribute('aria-current', 'true');
  await row(page, 'Preserve the previous format').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('h1')).toHaveText('Preserve the previous format');
  await expect(page).toHaveURL(/card=demo-card-2/);
  await page.keyboard.press('Tab');
  await page.keyboard.press('Space');
  await expect(page.locator('h1')).toHaveText('Confirm the saved filter');
  await expect(page.locator('.status-badge').first()).toHaveText('done');
  await shot(page, info, 'workspace');
});

test('filters by state and kind, searches, and resets', async ({ page }, info) => {
  await open(page);
  const inbox = page.getByLabel('Issue inbox');
  await inbox.getByRole('button', { name: /^Waiting/ }).click();
  await expect(page.locator('.issue-row')).toHaveCount(3);
  await inbox.getByRole('button', { name: /^Blocked/ }).click();
  await expect(page.locator('.issue-row')).toHaveText([/Preserve the previous format/]);
  await inbox.getByRole('button', { name: /^Done/ }).click();
  await expect(page.locator('.issue-row')).toHaveText([/Confirm the saved filter/]);
  await inbox.getByRole('button', { name: /^Left open/ }).click();
  await expect(page.locator('.issue-row')).toHaveText([/Choose when to send notifications/]);
  await inbox.getByRole('button', { name: /^All/ }).click();
  await page.getByLabel('Issue kind').selectOption('conflict');
  await expect(page.locator('.issue-row')).toHaveText([/Export column order/]);
  await page.getByLabel('Issue kind').selectOption('all');
  await page.getByLabel('Search issues').fill('CSV');
  await expect(page.locator('.issue-row')).toHaveText([/Choose the export format/]);
  await page.getByLabel('Search issues').fill('nothing matches this');
  await expect(page.locator('.issue-row')).toHaveCount(0);
  await expect(page.getByText('No issues match these filters.')).toBeVisible();
  await shot(page, info, 'filters-empty');
  await page.getByRole('button', { name: 'Clear filters' }).click();
  await expect(page.locator('.issue-row')).toHaveCount(6);
  await expect(page.getByLabel('Search issues')).toHaveValue('');
  await expect(inbox.getByRole('button', { name: /^All/ })).toHaveAttribute('aria-pressed', 'true');
});

test('browser back and forward restore the selection', async ({ page }) => {
  await open(page);
  await row(page, 'Choose the export format').click();
  await row(page, 'Preserve the previous format').click();
  await expect(page.locator('h1')).toHaveText('Preserve the previous format');
  await page.goBack();
  await expect(page.locator('h1')).toHaveText('Choose the export format');
  await expect(page).toHaveURL(/card=demo-card-5/);
  await page.goBack();
  await expect(page.locator('h1')).toHaveText('Keep exports readable');
  await page.goForward();
  await expect(page.locator('h1')).toHaveText('Choose the export format');
  await expect(row(page, 'Choose the export format')).toHaveAttribute('aria-current', 'true');
});

test('the selection survives a reload', async ({ page }) => {
  await open(page);
  await row(page, 'Export column order').click();
  await expect(page).toHaveURL(/card=conflict%3AIC-001/);
  await page.reload();
  await expect(page.locator('h1')).toHaveText('Export column order');
  await expect(page.locator('.connection')).toHaveText('Connected');
  await expect(page).toHaveURL(/session=demo-session&card=conflict%3AIC-001$/);
});

test('refresh draws again and help opens and closes', async ({ page }, info) => {
  await open(page);
  const drawn = page.waitForResponse(response => response.url().endsWith('/api/sessions/demo-session/draw'));
  await page.getByRole('button', { name: 'Refresh' }).click();
  expect((await drawn).status()).toBe(200);
  await expect(page.locator('.connection')).toHaveText('Connected');
  await expect(page.locator('h1')).toHaveText('Keep exports readable');
  await page.getByRole('button', { name: 'Help' }).click();
  const help = page.locator('.help-dialog');
  await expect(help).toBeVisible();
  await expect(help.getByRole('heading')).toHaveText('Decide with the evidence in view');
  await shot(page, info, 'help');
  await help.getByRole('button', { name: 'Close help' }).click();
  await expect(help).toBeHidden();
});

test('a session that never drew a card is not offered', async ({ page }) => {
  await open(page);
  const options = await page.getByLabel('Source session').locator('option').allTextContents();
  expect(options.some((o) => o.includes('empty-session'))).toBe(false);
  expect(options.some((o) => o.includes('demo-session'))).toBe(true);
});

test('tabs show the explanation, evidence with records, and activity', async ({ page }, info) => {
  await open(page, 'demo-session', 'demo-card-1');
  await expect(page.locator('h1')).toHaveText('Keep exports readable');
  await expect(page.locator('.context')).toBeVisible();
  await expect(page.locator('.option-explanations li')).toHaveCount(3);
  const evidence = page.getByRole('tabpanel');
  await expect(page.getByRole('tab', { name: 'Evidence' })).toHaveAttribute('aria-selected', 'true');
  await expect(evidence.locator('.record .eyebrow')).toHaveText('SR-001');
  await expect(evidence.locator('.record h3')).toHaveText('Keep exports readable');
  await evidence.getByText('Full record body').click();
  await expect(evidence.getByText('Demonstration evidence only.')).toBeVisible();
  await evidence.getByText('Stored fields and hash').click();
  await expect(evidence.locator('.record code')).toContainText('sha256:');
  await shot(page, info, 'evidence');
  await page.getByRole('tab', { name: /^Activity/ }).click();
  await expect(page.getByRole('tab', { name: /^Activity/ })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tabpanel')).toContainText('demo-session');
  await expect(page.getByText('No follow-up activity recorded.')).toBeVisible();
  await row(page, 'Preserve the previous format').click();
  await page.getByRole('tab', { name: 'Evidence' }).click();
  await expect(page.getByRole('tabpanel').locator('.record .eyebrow')).toHaveText('SR-002');
});
