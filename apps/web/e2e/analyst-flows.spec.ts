import { expect, test } from '@playwright/test';
import { baseCase, baseSource, gotoApp, installApiMocks, loginViaUi } from './helpers';

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

  await page.getByRole('button', { name: 'Hash all evidence files' }).click();
  await page
    .getByRole('alertdialog', { name: 'Hash all evidence files' })
    .getByRole('button', { name: 'Continue' })
    .click();
  await page.getByRole('button', { name: 'Scan evidence with YARA' }).click();
  await page
    .getByRole('alertdialog', { name: 'Scan evidence with YARA' })
    .getByRole('button', { name: 'Continue' })
    .click();

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

test('timeline exports a complete CSV in one click with no confirmation prompt', async ({ page }) => {
  const exportAuthHeaders: Array<string | null> = [];
  await installApiMocks(page, {
    authedInitially: false,
    timelineTotal: 2,
    exportRowLimit: 2,
    exportRowCount: 2,
    onExportRequest: ({ authorization }) => { exportAuthHeaders.push(authorization); },
  });
  await loginViaUi(page);
  // Login has to finish storing the token before navigating away, or the
  // export would be sent unauthenticated and this assertion would pass
  // vacuously against a null header.
  await expect
    .poll(() => page.evaluate(() => window.localStorage.getItem('ff_auth_token')))
    .toBe('smoke-token');
  await gotoApp(page, `/cases/${baseCase.id}`);
  await expect(page.getByText(/Loaded .* of 2 events/)).toBeVisible();

  // One click, one download: the browser cannot know the cap outcome up front,
  // so there is nothing honest to prompt about beforehand.
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export CSV' }).click();

  await expect(page.getByRole('alertdialog')).toHaveCount(0);
  expect((await download).suggestedFilename()).toBe('timeline-WKS-042.csv');

  // Authenticated fetch, not an anchor navigation: the router needs the bearer.
  await expect.poll(() => exportAuthHeaders).toEqual(['Bearer smoke-token']);
  await expect(page.getByTestId('timeline-export-outcome')).toContainText(
    'Complete export: 2 rows written to timeline-WKS-042.csv'
  );
});

test('timeline reports a truncated export as partial with the rows actually written', async ({ page }) => {
  await installApiMocks(page, {
    authedInitially: true,
    timelineTotal: 3,
    exportRowLimit: 2,
    exportRowCount: 2,
    exportTruncated: true,
  });
  await gotoApp(page, `/cases/${baseCase.id}`);
  await expect(page.getByText(/Loaded .* of 3 events/)).toBeVisible();

  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export CSV' }).click();
  await download;

  // The response headers are the only source: exact rows written, oldest first,
  // and no claim about a total the API never reported.
  const outcome = page.getByTestId('timeline-export-outcome');
  await expect(outcome).toContainText('Partial export: 2 rows written to timeline-WKS-042.csv');
  await expect(outcome).toContainText('oldest matches by timestamp');
  await expect(outcome).toContainText('export cap of 2 rows');
  await expect(outcome).toContainText('More events match this filter than were written');
  await expect(outcome).not.toContainText('of 3');
});

test('timeline calls completeness unverified when the API omits the export headers', async ({ page }) => {
  await installApiMocks(page, {
    authedInitially: true,
    timelineTotal: 3,
    exportOmitMetadata: true,
    exportRowCount: 3,
  });
  await gotoApp(page, `/cases/${baseCase.id}`);
  await expect(page.getByText(/Loaded .* of 3 events/)).toBeVisible();

  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export CSV' }).click();
  await download;

  // Missing headers must never read as "complete".
  const outcome = page.getByTestId('timeline-export-outcome');
  await expect(outcome).toContainText('did not report whether the export was truncated');
  await expect(outcome).toContainText('completeness as unconfirmed');
  await expect(outcome).not.toContainText('Complete export');
});

test('timeline reports an export rejected by the API instead of failing silently', async ({ page }) => {
  await installApiMocks(page, {
    authedInitially: true,
    timelineTotal: 2,
    exportStatus: 401,
  });

  await gotoApp(page, `/cases/${baseCase.id}`);
  await expect(page.getByText(/Loaded .* of 2 events/)).toBeVisible();

  await page.getByRole('button', { name: 'Export CSV' }).click();
  await expect(page.getByTestId('timeline-export-outcome')).toContainText(
    'no longer authorized'
  );
});

test('export outcome is announced through a status region mounted before the download', async ({ page }) => {
  await installApiMocks(page, {
    authedInitially: true,
    timelineTotal: 2,
    exportRowLimit: 2,
    exportRowCount: 2,
  });
  await gotoApp(page, `/cases/${baseCase.id}`);
  await expect(page.getByText(/Loaded .* of 2 events/)).toBeVisible();

  // The live region exists and is empty before any export, so the announcement
  // is a text change inside a registered region rather than a new node.
  const outcome = page.getByTestId('timeline-export-outcome');
  await expect(outcome).toHaveAttribute('role', 'status');
  await expect(outcome).toHaveAttribute('aria-live', 'polite');
  await expect(outcome).toHaveText('');

  const download = page.waitForEvent('download');
  const button = page.getByRole('button', { name: 'Export CSV' });
  await button.click();
  await download;

  await expect(outcome).toContainText('Complete export');
  // Same node, same role: the region was never remounted.
  await expect(outcome).toHaveAttribute('role', 'status');
  await expect(outcome).toHaveAttribute('aria-live', 'polite');
  // The busy button returns to its idle label once the download settles.
  await expect(button).toBeEnabled();
  await expect(button).toHaveAttribute('aria-busy', 'false');
});

test('danger confirmation is modal, labelled, and restores focus', async ({ page }) => {
  await installApiMocks(page, { authedInitially: true });
  await gotoApp(page, '/');

  const opener = page.getByRole('button', { name: 'Delete' });
  await opener.click();

  const dialog = page.getByRole('alertdialog', { name: 'Delete case' });
  const cancel = dialog.getByRole('button', { name: 'Cancel' });
  const confirm = dialog.getByRole('button', { name: 'Delete' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute('aria-labelledby', /.+/);
  await expect(dialog).toHaveAttribute('aria-describedby', /.+/);
  await expect(cancel).toBeFocused();
  await expect(page.locator('#root')).toHaveJSProperty('inert', true);

  await page.keyboard.press('Shift+Tab');
  await expect(confirm).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(cancel).toBeFocused();

  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
  await expect(page.locator('#root')).toHaveJSProperty('inert', false);
});

test('login uses explicit labels without nesting the password toggle', async ({ page }) => {
  await installApiMocks(page, { authedInitially: false });
  await gotoApp(page, '/');

  await expect(page.locator('label[for="username"]')).toHaveText('Username');
  await expect(page.locator('label[for="password"]')).toHaveText('Password');
  await expect(page.locator('label button')).toHaveCount(0);
  await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('id', 'password');
  const toggle = page.getByRole('button', { name: 'Show password' });
  await expect(toggle).not.toHaveAttribute('aria-pressed');
  await toggle.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Hide password' })).toBeFocused();
  await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('type', 'text');
});

test('evidence action remains scoped to its source while the request is pending', async ({ page }) => {
  const secondSource = {
    ...baseSource,
    id: '33333333-3333-3333-3333-333333333334',
    hostname: 'WKS-043',
  };
  await installApiMocks(page, { authedInitially: true });
  let releaseHashRequest!: () => void;
  const hashRequestGate = new Promise<void>((resolve) => {
    releaseHashRequest = resolve;
  });
  await page.route('**/api/v1/cases/*/evidence', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([baseSource, secondSource]),
      });
      return;
    }
    await route.fallback();
  });
  await page.route('**/api/v1/cases/*/evidence/*/hashes/compute', async (route) => {
    await hashRequestGate;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Hashing started' }),
    });
  });

  await gotoApp(page, '/cases/22222222-2222-2222-2222-222222222222');
  await page.getByRole('button', { name: 'Hash all evidence files' }).click();
  const dialog = page.getByRole('alertdialog', { name: 'Hash all evidence files' });
  await expect(dialog).toBeVisible();

  const hashRequest = page.waitForRequest(
    new RegExp(`/evidence/${baseSource.id}/hashes/compute$`)
  );
  await dialog.getByRole('button', { name: 'Continue' }).click();
  await hashRequest;
  await page.getByRole('button', { name: /WKS-043 Windows completed/ }).evaluate(
    (element: HTMLButtonElement) => element.click()
  );
  await expect(page.getByRole('button', { name: 'Hash all evidence files' })).toBeEnabled();

  releaseHashRequest();
  await expect(page.getByRole('button', { name: 'Hash all evidence files' })).toBeEnabled();
  await expect(page.getByText('Hashing files…')).toHaveCount(0);
});

test('ingest diagnostics keep notes that contain the summary separator', async ({ page }) => {
  // A completed ingest message is "<summary> — <note>; <note>", and a note may
  // itself contain " — " (the empty-module-CSV fallback note does). Only the
  // first separator ends the summary; the rest belongs to the notes.
  const fallbackNote =
    'evtx: 1 pre-parsed module CSV(s) contributed no timeline events '
    + '(empty or no parseable timestamps) — raw evtx parsing not suppressed';
  const sigmaNote = 'Sigma matched 2 of 3 events';
  const summary = 'Ingested 12 events, 3 entities, 4 filesystem nodes';

  await installApiMocks(page, {
    authedInitially: true,
    // Source still marked busy so the workspace keeps the ingest panel mounted
    // while the job itself has completed.
    sourceStatus: 'running',
    sourceJobs: [
      {
        id: '44444444-4444-4444-4444-444444444444',
        evidence_source_id: baseSource.id,
        status: 'completed',
        progress: 100,
        message: `${summary} — ${fallbackNote}; ${sigmaNote}`,
        error_code: null,
        error_stage: null,
        started_at: '2026-01-01T00:00:00Z',
        finished_at: '2026-01-01T00:01:00Z',
        created_at: '2026-01-01T00:00:00Z',
      },
    ],
  });

  await gotoApp(page, `/cases/${baseCase.id}`);

  const panel = page.locator('.ingest-status-panel');
  await expect(panel.locator('.ingest-status-detail')).toHaveText(summary);

  const notes = panel.locator('.ingest-diagnostics li');
  await expect(notes).toHaveCount(2);
  // The tail after the note's own separator must survive.
  await expect(notes.nth(0)).toHaveText(fallbackNote);
  await expect(notes.nth(0)).toContainText('raw evtx parsing not suppressed');
  await expect(notes.nth(1)).toHaveText(sigmaNote);
});
