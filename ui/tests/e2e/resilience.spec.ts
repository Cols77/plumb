import { expect, test } from '@playwright/test';
import { open, row, shot } from './helpers';

test('an unreachable server shows an error and retry reconnects', async ({ page }, info) => {
  await open(page);
  await page.route('**/api/**', route => route.abort('connectionrefused'));
  await page.getByRole('button', { name: 'Refresh' }).click();
  await expect(page.getByRole('alert')).toContainText('Connection needs attention.');
  await expect(page.locator('.connection')).toHaveText('Disconnected');
  await expect(page.locator('h1')).toHaveText('Keep exports readable');
  await shot(page, info, 'disconnected');
  await page.unroute('**/api/**');
  await page.getByRole('button', { name: 'Retry connection' }).click();
  await expect(page.locator('.connection')).toHaveText('Connected');
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test.describe('phone width', () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test('the inbox is a drawer and the issue stays usable', async ({ page }, info) => {
    await open(page);
    const inbox = page.locator('#issue-inbox');
    const issues = page.locator('.mobile-bar').getByRole('button', { name: /^Issues/ });
    await expect(issues).toHaveAttribute('aria-expanded', 'false');
    await expect(inbox).toHaveAttribute('inert', '');
    await issues.click();
    await expect(inbox).toHaveClass(/drawer-open/);
    await expect(page.getByLabel('Search issues')).toBeFocused();
    await shot(page, info, 'phone-drawer');
    await row(page, 'Choose the export format').click();
    await expect(inbox).not.toHaveClass(/drawer-open/);
    await expect(page.locator('h1')).toHaveText('Choose the export format');
    await expect(page.getByRole('button', { name: 'Keep CSV' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await shot(page, info, 'phone-issue');
    await issues.click();
    await page.keyboard.press('Escape');
    await expect(inbox).not.toHaveClass(/drawer-open/);
    await expect(issues).toBeFocused();
  });
});
