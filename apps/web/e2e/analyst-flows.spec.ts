import { expect, test } from '@playwright/test';
import { gotoApp, installApiMocks, loginViaUi } from './helpers';

test('analyst can create a case and land on case workspace', async ({ page }) => {
  await installApiMocks(page, { authedInitially: false, allowCaseCreate: true });
  await loginViaUi(page);

  await page.getByLabel('Case name').fill('IR-2026-042');
  await page.getByRole('button', { name: 'Create case' }).click();

  await expect(page).toHaveURL(/\/cases\/55555555-5555-5555-5555-555555555555$/);
  await expect(page.locator('.case-name')).toContainText('IR-2026-042');
  await expect(page.getByRole('heading', { name: 'Ingest evidence' })).toBeVisible();
});

test('analyst workspace supports navigation and evidence actions', async ({ page }) => {
  let hashCalls = 0;
  let yaraCalls = 0;
  await installApiMocks(page, {
    authedInitially: true,
    onHashCompute: () => { hashCalls += 1; },
    onYaraScan: () => { yaraCalls += 1; },
  });

  await gotoApp(page, '/cases/22222222-2222-2222-2222-222222222222');
  await expect(page.getByRole('heading', { name: 'WKS-042 Investigation' })).toBeVisible();

  await page.getByRole('button', { name: 'Entities', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Entities' })).toBeVisible();

  await page.getByRole('button', { name: 'Disk', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Disk' })).toBeVisible();

  await page.getByRole('button', { name: 'MFT', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'MFT Records' })).toBeVisible();

  await page.getByRole('button', { name: 'Browser', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Browser' })).toBeVisible();

  page.on('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Hash all evidence files' }).click();
  await page.getByRole('button', { name: 'Scan evidence with YARA' }).click();

  await expect.poll(() => hashCalls).toBe(1);
  await expect.poll(() => yaraCalls).toBe(1);
});

test('timeline loads additional server pages when scrolled deep into the list', async ({ page }) => {
  const requestedOffsets: number[] = [];
  const totalRows = 25000;
  const expectedLastPageOffset = 20000;
  await installApiMocks(page, {
    authedInitially: true,
    timelineTotal: totalRows,
    onTimelineRequest: ({ offset }) => { requestedOffsets.push(offset); },
  });

  await gotoApp(page, '/cases/22222222-2222-2222-2222-222222222222');
  await expect(page.getByText(new RegExp(`Loaded .* of ${totalRows} events`))).toBeVisible();
  await expect.poll(() => requestedOffsets).toContain(0);

  await page.locator('.virtual-list-container').evaluate((el) => {
    el.scrollTop = el.scrollHeight;
    el.dispatchEvent(new Event('scroll', { bubbles: true }));
  });

  await expect.poll(() => requestedOffsets).toContain(expectedLastPageOffset);
});
