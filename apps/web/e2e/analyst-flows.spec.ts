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

test('entity catalog pages past the first 200 and discloses the filtered total', async ({ page }) => {
  const requests: Array<{ offset: number; q: string | null; entityType: string | null }> = [];
  await installApiMocks(page, {
    authedInitially: true,
    entityTotal: 450,
    entityFilteredTotal: 30,
    entityEventTotal: 250,
    onEntitiesRequest: ({ offset, q, entityType }) => { requests.push({ offset, q, entityType }); },
  });

  await gotoApp(page, `/cases/${baseCase.id}`);
  await page.getByRole('button', { name: 'Entities', exact: true }).click();

  const loadState = page.locator('.entity-load-state');
  await expect(loadState).toHaveText('200 of 450 entities loaded');

  await page.getByRole('button', { name: 'Load 200 more entities' }).click();
  await expect(loadState).toHaveText('400 of 450 entities loaded');
  // Load-more is bounded: exactly one further page, never a whole-source fetch.
  await expect.poll(() => requests.map((r) => r.offset)).toContain(200);
  expect(new Set(requests.map((r) => r.offset))).toEqual(new Set([0, 200]));

  await page.getByRole('button', { name: 'Load 200 more entities' }).click();
  await expect(loadState).toHaveText('450 of 450 entities loaded');
  await expect(page.getByRole('button', { name: 'Load 200 more entities' })).toHaveCount(0);

  // Related events page independently of the entity list.
  await page.locator('.item-list-row').first().click();
  const relatedState = page.locator('.related-load-state');
  await expect(relatedState).toHaveText('Related timeline — 100 of 250 events loaded');
  await page.getByRole('button', { name: 'Load 100 more events' }).click();
  await expect(relatedState).toHaveText('Related timeline — 200 of 250 events loaded');

  // A filter restarts paging from offset 0 and reports the filtered total.
  await page.getByLabel('Search entities').fill('analyst');
  await expect(loadState).toHaveText('30 of 30 entities loaded (filtered)');
  await expect.poll(() => requests.at(-1)).toMatchObject({ offset: 0, q: 'analyst' });

  await page.getByRole('button', { name: 'Reset filters' }).click();
  await expect(page.getByLabel('Search entities')).toHaveValue('');
  await expect(loadState).toHaveText('200 of 450 entities loaded');
});

test('a failed entity page keeps loaded rows and recovers on retry', async ({ page }) => {
  await installApiMocks(page, {
    authedInitially: true,
    entityTotal: 450,
    entityFailOffsets: [200],
  });

  await gotoApp(page, `/cases/${baseCase.id}`);
  await page.getByRole('button', { name: 'Entities', exact: true }).click();

  const loadState = page.locator('.entity-load-state');
  await expect(loadState).toHaveText('200 of 450 entities loaded');

  await page.getByRole('button', { name: 'Load 200 more entities' }).click();
  await expect(page.locator('.alert-error')).toContainText('Could not load more entities');
  // The rows already on screen survive the failure.
  await expect(loadState).toHaveText('200 of 450 entities loaded');
  await expect(page.locator('.item-list-row')).toHaveCount(200);

  await page.locator('.alert-error').getByRole('button', { name: 'Retry' }).click();
  await expect(page.locator('.alert-error')).toHaveCount(0);
  await expect(loadState).toHaveText('400 of 450 entities loaded');
});

test('a failed first entity page is an error, not an empty result', async ({ page }) => {
  await installApiMocks(page, {
    authedInitially: true,
    entityTotal: 3,
    // React's development StrictMode runs the mount effect twice; both initial
    // requests fail, while the explicit retry succeeds.
    entityFailOffsets: [0, 0],
  });

  await gotoApp(page, `/cases/${baseCase.id}`);
  await page.getByRole('button', { name: 'Entities', exact: true }).click();

  const error = page.locator('.alert-error');
  await expect(error).toContainText('No results for this query were loaded');
  await expect(page.getByText('No entities match your filters.')).toHaveCount(0);
  await expect(page.locator('.entity-load-state')).toHaveCount(0);

  await error.getByRole('button', { name: 'Retry' }).click();
  await expect(error).toHaveCount(0);
  await expect(page.locator('.entity-load-state')).toHaveText('3 of 3 entities loaded');
});

test('successful pages disclose when exact totals are unavailable', async ({ page }) => {
  await installApiMocks(page, {
    authedInitially: true,
    entityTotal: 250,
    entityCountFails: true,
    entityEventTotal: 150,
    entityEventCountFails: true,
  });

  await gotoApp(page, `/cases/${baseCase.id}`);
  await page.getByRole('button', { name: 'Entities', exact: true }).click();
  await expect(page.locator('.entity-load-state')).toHaveText(
    '200 entities loaded (total unavailable)'
  );

  await page.locator('.item-list-row').first().click();
  await expect(page.locator('.related-load-state')).toHaveText(
    'Related timeline — 100 events loaded (total unavailable)'
  );
});

test('a failed related-event page keeps loaded rows and retries that page', async ({ page }) => {
  await installApiMocks(page, {
    authedInitially: true,
    entityEventTotal: 250,
    entityEventFailOffsets: [100],
  });

  await gotoApp(page, `/cases/${baseCase.id}`);
  await page.getByRole('button', { name: 'Entities', exact: true }).click();
  await page.locator('.item-list-row').first().click();

  const relatedPanel = page.locator('.resizable-split > .panel').nth(1);
  const loadState = relatedPanel.locator('.related-load-state');
  await expect(loadState).toHaveText('Related timeline — 100 of 250 events loaded');
  await relatedPanel.getByRole('button', { name: 'Load 100 more events' }).click();
  await expect(relatedPanel.locator('.alert-error')).toContainText(
    'Could not load more related events'
  );
  await expect(loadState).toHaveText('Related timeline — 100 of 250 events loaded');
  await expect(relatedPanel.locator('.item-list-row')).toHaveCount(100);

  await relatedPanel.locator('.alert-error').getByRole('button', { name: 'Retry' }).click();
  await expect(relatedPanel.locator('.alert-error')).toHaveCount(0);
  await expect(loadState).toHaveText('Related timeline — 200 of 250 events loaded');
});

test('a superseded entity filter response cannot overwrite the newer one', async ({ page }) => {
  await installApiMocks(page, {
    authedInitially: true,
    entityTotal: 450,
    entityFilteredTotal: 30,
  });

  let releaseStaleResponse!: () => void;
  const staleGate = new Promise<void>((resolve) => { releaseStaleResponse = resolve; });
  // Hold the "slow" filter's list response open until the newer filter settles.
  await page.route('**/api/v1/cases/*/sources/*/entities?*', async (route) => {
    if (new URL(route.request().url()).searchParams.get('q') === 'slow') {
      await staleGate;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: '88888888-8888-8888-8888-999999999999',
            evidence_source_id: baseSource.id,
            entity_type: 'user',
            display_name: 'stale-result',
            attributes: {},
          },
        ]),
      });
      return;
    }
    await route.fallback();
  });

  await gotoApp(page, `/cases/${baseCase.id}`);
  await page.getByRole('button', { name: 'Entities', exact: true }).click();
  await expect(page.locator('.entity-load-state')).toHaveText('200 of 450 entities loaded');

  await page.getByLabel('Search entities').fill('slow');
  await page.getByLabel('Search entities').fill('fresh');
  await expect(page.locator('.entity-load-state')).toHaveText('30 of 30 entities loaded (filtered)');

  releaseStaleResponse();
  // The late response belongs to a superseded generation and must be dropped.
  await expect(page.getByText('stale-result')).toHaveCount(0);
  await expect(page.locator('.entity-load-state')).toHaveText('30 of 30 entities loaded (filtered)');
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

test('MFT search queries the whole source and repages on the filtered count', async ({ page }) => {
  const requests: Array<{ offset: number; q: string | null; mftOnly: boolean }> = [];
  await installApiMocks(page, {
    authedInitially: true,
    timelineTotal: 1200,
    timelineFilteredTotal: 700,
    onTimelineRequest: ({ offset, q, mftOnly }) => { requests.push({ offset, q, mftOnly }); },
  });

  await gotoApp(page, `/cases/${baseCase.id}`);
  await page.getByRole('button', { name: 'MFT', exact: true }).click();

  const pageInfo = page.locator('.mft-page-info');
  // Unfiltered paging comes from the source-wide count, not the loaded page.
  await expect(page.locator('.panel-header .mft-count')).toHaveText('1,200 total');
  await expect(pageInfo).toContainText('Page 1 of 3');

  await page.getByRole('button', { name: 'Next →' }).click();
  await expect(pageInfo).toContainText('Page 2 of 3');

  await page.getByLabel('Search MFT paths').fill('Windows\\System32');

  // Search is server-side over every MFT record, so it re-queries from page 1.
  await expect.poll(() => requests.at(-1)).toMatchObject({
    offset: 0,
    q: 'Windows\\System32',
    mftOnly: true,
  });
  await expect(page.locator('.panel-header .mft-count')).toHaveText('700 matching');
  await expect(pageInfo).toContainText('Page 1 of 2');
  await expect(page.locator('.mft-scope-note')).toContainText('every MFT record in this source');
});
