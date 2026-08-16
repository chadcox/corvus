import { expect, test } from '@playwright/test';
import { baseCase, baseSource, gotoApp, installApiMocks, loginViaUi } from './helpers';

test('analyst can create a case and land on case workspace', async ({ page }) => {
  await installApiMocks(page, { authedInitially: false, allowCaseCreate: true });
  await loginViaUi(page);

  await page.getByLabel('Case name').fill('IR-2026-042');
  await page.getByRole('button', { name: 'Create case' }).click();

  await expect(page).toHaveURL(/\/cases\/55555555-5555-5555-5555-555555555555$/);
  await expect(page.locator('.case-name')).toContainText('IR-2026-042');
  // The workspace opens on the case nav rail; ingest now lives in the Sources view.
  await expect(page.getByRole('navigation', { name: 'Case views' })).toBeVisible();
  await page.getByRole('button', { name: 'Sources', exact: true }).click();
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

  await page.getByRole('button', { name: 'MFT', exact: true }).evaluate(
    (element: HTMLButtonElement) => element.click()
  );
  await expect(page.getByRole('heading', { name: 'MFT Records' })).toBeVisible();

  await page.getByRole('button', { name: 'Browser', exact: true }).evaluate(
    (element: HTMLButtonElement) => element.click()
  );
  await expect(page.getByRole('heading', { name: 'Browser' })).toBeVisible();

  // Evidence actions live on the Sources view now (plan §6.3).
  await page.getByRole('button', { name: 'Sources', exact: true }).click();
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
  // The workspace lands on Overview; the virtualized list only mounts on Timeline.
  await page.getByRole('button', { name: 'Timeline', exact: true }).click();
  await expect(page.getByText(new RegExp(`Loaded .* of ${totalRows} events`))).toBeVisible();
  await expect.poll(() => requestedOffsets).toContain(0);

  await page.locator('.virtual-list-container').evaluate((el) => {
    el.scrollTop = el.scrollHeight;
    el.dispatchEvent(new Event('scroll', { bubbles: true }));
  });

  await expect.poll(() => requestedOffsets).toContain(expectedLastPageOffset);
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
  await page.getByRole('button', { name: 'Sources', exact: true }).click();
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

test('Chainsaw coverage warning is distinct from partial timeline parsing', async ({ page }) => {
  const summary = 'Ingested 12 events, 3 entities, 4 filesystem nodes';
  const coverageNote =
    'Partial detection coverage: 312 EVTX file(s) found, 64 hunted, 248 not hunted '
    + '(248 omitted by the effective CHAINSAW_EVTX_MAX ceiling of 64). '
    + 'Re-ingest with a higher CHAINSAW_EVTX_MAX to hunt the omitted files.';

  await installApiMocks(page, {
    authedInitially: true,
    sourceStatus: 'running',
    sourceJobs: [
      {
        id: '44444444-4444-4444-4444-444444444444',
        evidence_source_id: baseSource.id,
        status: 'completed',
        progress: 100,
        message: `${summary} — ${coverageNote}`,
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
  await expect(panel.locator('.ingest-diagnostics-coverage')).toContainText(
    'Incomplete detection coverage',
  );
  await expect(panel.locator('.ingest-diagnostics-partial')).toHaveCount(0);
  await expect(panel.locator('li.coverage')).toHaveText(coverageNote);
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

test('primary investigation rows support roving keyboard navigation', async ({ page }) => {
  test.setTimeout(60_000);
  await installApiMocks(page, {
    authedInitially: true,
    timelineTotal: 3,
    collectionRows: 3,
  });
  await gotoApp(page, `/cases/${baseCase.id}`);

  await page.getByRole('button', { name: 'Timeline', exact: true }).click();
  const timeline = page.getByRole('listbox', { name: 'Timeline events' });
  const timelineRows = timeline.getByRole('option');
  await expect(timelineRows).toHaveCount(3);
  await timelineRows.nth(0).focus();
  await page.keyboard.press('ArrowDown');
  await expect(timelineRows.nth(1)).toBeFocused();
  await page.keyboard.press('End');
  await expect(timelineRows.nth(2)).toBeFocused();
  await page.keyboard.press('Home');
  await expect(timelineRows.nth(0)).toBeFocused();
  await page.keyboard.press('PageDown');
  await expect(timelineRows.nth(2)).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('.detail-summary')).toContainText('User logon 3');
  await page.keyboard.press('Tab');
  await expect(timeline.locator('[tabindex="0"]')).not.toBeFocused();

  await page.getByRole('button', { name: 'Entities', exact: true }).click();
  const entities = page.getByRole('listbox', { name: 'Entities' });
  await entities.getByRole('option').nth(0).focus();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press(' ');
  await expect(page.locator('.detail-summary')).toContainText('analyst2');

  const related = page.getByRole('listbox', { name: 'Related timeline events' });
  await related.getByRole('option').nth(0).focus();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Timeline' })).toBeVisible();

  await page.getByRole('button', { name: 'Disk', exact: true }).click();
  const diskRows = page.locator('.data-table tbody tr');
  await diskRows.nth(0).focus();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(page.locator('.disk-detail-name')).toContainText('file-2.log');

  await page.locator('button.stat-card--action').filter({ hasText: 'MFT' }).click({ force: true });
  await expect(page.getByRole('heading', { name: 'MFT Records' })).toBeVisible();
  const mftRows = page.locator('.mft-table tbody tr');
  await mftRows.nth(0).focus();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(page.locator('.mft-detail-path')).toContainText('User logon 2');

  await page.locator('button.stat-card--action').filter({ hasText: 'Browser' }).click({ force: true });
  await expect(page.getByRole('heading', { name: 'Browser' })).toBeVisible();
  const browserRows = page.locator('.browser-table tbody tr');
  await browserRows.nth(0).focus();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(page.locator('.detail-dl')).toContainText('User logon 2');
});

test('evidence and ingest dialogs trap focus and restore their openers', async ({ page }) => {
  await installApiMocks(page, { authedInitially: true });
  await gotoApp(page, `/cases/${baseCase.id}`);

  await page.getByRole('button', { name: 'Sources', exact: true }).click();
  const sourceOpener = page.getByRole('button', { name: /WKS-042 Windows completed/ });
  await sourceOpener.click();
  const sourceDialog = page.getByRole('dialog', { name: 'Evidence source details' });
  await expect(sourceDialog.getByRole('button', { name: 'Close' })).toBeFocused();
  await expect(page.locator('#root')).toHaveJSProperty('inert', true);
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('hidden');
  for (let index = 0; index < 25; index += 1) await page.keyboard.press('Tab');
  await expect.poll(() => sourceDialog.evaluate((dialog) => dialog.contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(sourceOpener).toBeFocused();

  const historyOpener = page.getByRole('button', { name: 'View ingest history' });
  await historyOpener.click();
  const historyDialog = page.getByRole('dialog', { name: 'Ingest history' });
  await expect(historyDialog.getByRole('button', { name: 'Close' })).toBeFocused();
  for (let index = 0; index < 25; index += 1) await page.keyboard.press('Shift+Tab');
  await expect.poll(() => historyDialog.evaluate((dialog) => dialog.contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(historyOpener).toBeFocused();
  await expect(page.locator('#root')).toHaveJSProperty('inert', false);
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('');
});

test('partial jobs and load failures never render optimistic evidence claims', async ({ page }) => {
  await installApiMocks(page, {
    authedInitially: true,
    sourceJobs: [{
      id: '44444444-4444-4444-4444-444444444444',
      evidence_source_id: baseSource.id,
      status: 'completed',
      progress: 100,
      message: 'Ingested 0 events, 0 entities, 0 filesystem nodes — Unable to mount image',
      error_code: 'partial_parse',
      error_stage: 'disk_image',
      started_at: '2026-01-01T00:00:00Z',
      finished_at: '2026-01-01T00:01:00Z',
      created_at: '2026-01-01T00:00:00Z',
    }],
  });
  let failTimeline = true;
  await page.route(/\/api\/v1\/cases\/[^/]+\/sources\/[^/]+\/timeline(?:\?|$)/, async (route) => {
    if (failTimeline) {
      await route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"failed"}' });
      return;
    }
    await route.fallback();
  });

  await gotoApp(page, `/cases/${baseCase.id}`);
  // The timeline only mounts on its own view now, so the failure has to be
  // provoked there; the claim it must not make is that evidence loaded fine.
  await page.getByRole('button', { name: 'Timeline', exact: true }).click();
  await expect(page.getByText('Failed to load timeline events.')).toBeVisible();
  await expect(page.getByText('No events yet — ingest may still be running.')).toHaveCount(0);
  await expect(page.locator('.timeline-distribution')).toHaveCount(0);
  // The failed count must not leak back into the shell's pivots or the summary.
  await expect(page.locator('.stats-strip').getByRole('button', { name: /Events/ })).toHaveCount(0);
  await page.getByRole('button', { name: 'Overview', exact: true }).click();
  await expect(page.locator('.summary-kpis').getByText('—')).toBeVisible();

  // Re-entering Timeline refetches, so the error has to still be live for Retry
  // to exist; only then does flipping the route prove the retry path recovers.
  await page.getByRole('button', { name: 'Timeline', exact: true }).click();
  await expect(page.getByText('Failed to load timeline events.')).toBeVisible();
  failTimeline = false;
  await page.getByRole('button', { name: 'Retry' }).click();
  await expect(page.getByText(/Loaded 1 of 1 events/)).toBeVisible();
  await page.getByRole('button', { name: 'Overview', exact: true }).click();
  await expect(page.locator('.summary-kpis').getByText('—')).toHaveCount(0);

  await page.getByRole('button', { name: 'Sources', exact: true }).click();
  await page.getByRole('button', { name: 'View ingest history' }).click({ force: true });
  await expect(page.getByText('completed with errors')).toBeVisible();
  await expect(page.locator('.status-badge.partial')).toHaveCount(1);
});

test('cases connection failure names the origin and suppresses the empty state', async ({ page }) => {
  await installApiMocks(page, { authedInitially: true });
  await page.route('**/api/v1/cases', async (route) => {
    if (route.request().method() === 'GET') {
      await route.abort('connectionrefused');
      return;
    }
    await route.fallback();
  });
  await gotoApp(page, '/');

  await expect(page.getByText(/Cannot reach API at http/)).toBeVisible();
  await expect(page.getByText('No cases yet. Create one above to begin your investigation.')).toHaveCount(0);
});

test('bundled font faces load without third-party requests', async ({ page }) => {
  await installApiMocks(page, { authedInitially: true });
  await gotoApp(page, '/');
  const loaded = await page.evaluate(async () => {
    const expected = [
      ['Libre Franklin', '400'], ['Libre Franklin', '500'], ['Libre Franklin', '600'],
      ['Red Hat Mono', '400'], ['Red Hat Mono', '500'],
    ] as const;
    return Promise.all(expected.map(async ([family, weight]) => {
      const faces = await document.fonts.load(`${weight} 16px "${family}"`);
      return { family, weight, count: faces.length, loaded: faces.every((face) => face.status === 'loaded') };
    }));
  });
  expect(loaded).toHaveLength(5);
  expect(loaded.every((face) => face.count > 0 && face.loaded)).toBe(true);

  const externalFonts = await page.evaluate(() => performance.getEntriesByType('resource')
    .map((entry) => entry.name)
    .filter((name) => name.includes('google' + 'apis') || name.includes('g' + 'static')));
  expect(externalFonts).toEqual([]);
});

test('interactive text contrast and keyboard focus styles meet the P0 floor', async ({ page }) => {
  await installApiMocks(page, { authedInitially: true });
  await gotoApp(page, '/');
  await page.getByLabel('Case name').fill('Contrast check');

  const ratio = async (selector: string) => page.locator(selector).first().evaluate((element) => {
    const parse = (value: string): [number, number, number, number] => {
      const parts = value.match(/[\d.]+/g)?.map(Number) ?? [];
      return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0, parts[3] ?? 1];
    };
    const blend = (front: number[], back: number[]) => {
      const alpha = front[3] + back[3] * (1 - front[3]);
      return [0, 1, 2].map((index) => (
        (front[index] * front[3] + back[index] * back[3] * (1 - front[3])) / alpha
      )).concat(alpha);
    };
    const chain: Element[] = [];
    for (let node: Element | null = element; node; node = node.parentElement) chain.unshift(node);
    let background = [255, 255, 255, 1];
    for (const node of chain) background = blend(parse(getComputedStyle(node).backgroundColor), background);
    const foreground = parse(getComputedStyle(element).color);
    const luminance = (color: number[]) => {
      const channels = color.slice(0, 3).map((part) => {
        const value = part / 255;
        return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    };
    const first = luminance(foreground);
    const second = luminance(background);
    return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
  });

  const primary = page.getByRole('button', { name: 'Create case' });
  expect(await ratio('button[type="submit"]')).toBeGreaterThanOrEqual(4.5);
  await primary.hover();
  expect(await ratio('button[type="submit"]')).toBeGreaterThanOrEqual(4.5);
  await page.mouse.move(0, 0);
  await page.getByLabel('Case name').focus();
  await page.keyboard.press('Tab');
  await expect(primary).toBeFocused();
  await expect(primary).toHaveCSS('outline-style', 'solid');
  await expect(primary).toHaveCSS('outline-color', 'rgb(130, 177, 255)');

  await gotoApp(page, `/cases/${baseCase.id}`);
  const statCard = page.locator('.stat-card--action').first();
  await statCard.hover();
  expect(await ratio('.stat-card--action:first-of-type .stat-label')).toBeGreaterThanOrEqual(4.5);
  expect(await ratio('.stat-card--action:first-of-type .stat-value')).toBeGreaterThanOrEqual(4.5);

  // Nav rail (plan §5): the active item must stay legible, and keyboard focus
  // must paint a visible ring on whichever item the user tabs onto.
  const navOverview = page.getByRole('button', { name: 'Overview', exact: true });
  const navTimeline = page.getByRole('button', { name: 'Timeline', exact: true });
  await navTimeline.click();
  await expect(navTimeline).toHaveClass(/active/);
  await navTimeline.hover();
  expect(await ratio('.nav-item.active')).toBeGreaterThanOrEqual(4.5);
  await page.mouse.move(0, 0);
  // Shift+Tab is a keyboard interaction, so :focus-visible applies.
  await page.keyboard.press('Shift+Tab');
  await expect(navOverview).toBeFocused();
  await expect(navOverview).toHaveCSS('outline-style', 'solid');
  await expect(navOverview).toHaveCSS('outline-color', 'rgb(130, 177, 255)');

  const search = page.getByRole('searchbox', { name: 'Global search' });
  await search.click();
  await expect(search).toBeFocused();
  await expect(search).toHaveCSS('outline-style', 'solid');
  await page.keyboard.press('Escape');
  const splitter = page.getByRole('separator', { name: /Resize timeline/ });
  await splitter.focus();
  await expect(splitter).toHaveCSS('outline-style', 'solid');
});

test('detail drawers overlay the workspace from every opener and close on the backdrop', async ({ page }) => {
  // The drawer replaces the old centred modals (plan §7.2): it must render
  // through the portal above the workspace, carry real content, and be
  // dismissible by the backdrop as well as Escape/Close.
  await installApiMocks(page, {
    authedInitially: true,
    sourceJobs: [
      {
        id: '66666666-6666-6666-6666-666666666666',
        evidence_source_id: baseSource.id,
        status: 'completed',
        progress: 100,
        message: 'Ingested 11 events, 20 entities',
        error_code: null,
        error_stage: null,
        started_at: '2026-01-01T00:00:00Z',
        finished_at: '2026-01-01T00:01:00Z',
        created_at: '2026-01-01T00:00:00Z',
      },
    ],
  });
  await gotoApp(page, `/cases/${baseCase.id}`);

  // Opener 1: the context-bar ⓘ, available from any view.
  const contextOpener = page.getByRole('button', { name: 'Source details' });
  await contextOpener.click();
  const sourceDrawer = page.getByRole('dialog', { name: 'Evidence source details' });
  await expect(sourceDrawer).toBeVisible();
  await expect(sourceDrawer).toContainText('WKS-042');
  await expect(sourceDrawer).toContainText('Windows');
  // Portalled to <body>, so the drawer is never clipped by the workspace grid.
  await expect(sourceDrawer.locator('xpath=ancestor::*[@id="root"]')).toHaveCount(0);
  // Backdrop click dismisses; clicks inside the panel must not.
  await sourceDrawer.click({ position: { x: 10, y: 10 } });
  await expect(sourceDrawer).toBeVisible();
  await page.locator('.drawer-backdrop').click({ position: { x: 5, y: 5 } });
  await expect(sourceDrawer).toBeHidden();
  await expect(contextOpener).toBeFocused();

  // Opener 2: the Sources view card, same drawer, fresh hash state.
  await page.getByRole('button', { name: 'Sources', exact: true }).click();
  await page.getByRole('button', { name: /WKS-042 Windows completed/ }).click();
  await expect(page.getByRole('dialog', { name: 'Evidence source details' })).toBeVisible();
  await page.getByRole('dialog', { name: 'Evidence source details' })
    .getByRole('button', { name: 'Close' })
    .click();
  await expect(page.getByRole('dialog', { name: 'Evidence source details' })).toBeHidden();

  // Ingest history drawer renders one section per source with its job lines.
  await page.getByRole('button', { name: 'View ingest history' }).click();
  const historyDrawer = page.getByRole('dialog', { name: 'Ingest history' });
  await expect(historyDrawer).toBeVisible();
  await expect(historyDrawer.getByRole('heading', { name: 'WKS-042' })).toBeVisible();
  await expect(historyDrawer.locator('.job-history-item')).toHaveCount(1);
  await expect(historyDrawer).toContainText('Ingested 11 events, 20 entities');
  await page.locator('.drawer-backdrop').click({ position: { x: 5, y: 5 } });
  await expect(historyDrawer).toBeHidden();
});

test('nav rail collapse survives reload and keeps its labels reachable', async ({ page }) => {
  await installApiMocks(page, { authedInitially: true });
  await gotoApp(page, `/cases/${baseCase.id}`);

  const workspace = page.locator('.case-workspace');
  const collapse = page.getByRole('button', { name: 'Collapse navigation' });
  await expect(workspace).not.toHaveClass(/nav-collapsed/);

  await collapse.click();
  await expect(workspace).toHaveClass(/nav-collapsed/);
  expect(await page.evaluate(() => window.localStorage.getItem('corvus.navCollapsed'))).toBe('1');
  // Collapsed rail keeps the accessible name (icon + tooltip only visually).
  const timeline = page.getByRole('button', { name: 'Timeline', exact: true });
  await expect(timeline).toHaveAttribute('title', 'Timeline');
  await timeline.click();
  await expect(timeline).toHaveClass(/active/);

  await page.reload();
  await expect(page.locator('.case-workspace')).toHaveClass(/nav-collapsed/);
  const expand = page.getByRole('button', { name: 'Expand navigation' });
  await expect(expand).toBeVisible();

  await expand.click();
  await expect(page.locator('.case-workspace')).not.toHaveClass(/nav-collapsed/);
  expect(await page.evaluate(() => window.localStorage.getItem('corvus.navCollapsed'))).toBe('0');
  await page.reload();
  await expect(page.locator('.case-workspace')).not.toHaveClass(/nav-collapsed/);
  await expect(page.getByRole('button', { name: 'Collapse navigation' })).toBeVisible();
});

test('overview summarises the source and pivots into detections and timeline', async ({ page }) => {
  await installApiMocks(page, { authedInitially: true });
  await gotoApp(page, `/cases/${baseCase.id}`);

  // Overview is the landing view and must carry the whole-source summary, not
  // a single card: severity distribution, the detection table and the source
  // table all render from data the shell already fetched.
  const overview = page.locator('.overview-grid').first();
  await expect(page.locator('.summary-kpis')).toBeVisible();
  await expect(
    overview.getByRole('img', { name: /Detection severity distribution:/ })
  ).toBeVisible();
  const detectionRow = page.locator('.overview-detections-table tbody tr');
  await expect(detectionRow).toHaveCount(1);
  await expect(detectionRow).toContainText('Suspicious Logon');
  const sourceRow = page.locator('.overview-sources-table tbody tr');
  await expect(sourceRow).toHaveCount(1);
  await expect(sourceRow).toContainText('WKS-042');
  // The selected source is the only row allowed to claim an event count.
  await expect(sourceRow).toHaveClass(/selected/);
  await expect(sourceRow.locator('td.num-col')).toHaveText('3');

  // Detection pivot: opening a rule from Overview lands on Detections with
  // that rule's detail already open, so the analyst never re-searches for it.
  await detectionRow.getByRole('button', { name: 'Open MED detection Suspicious Logon' }).click();
  await expect(page.getByRole('button', { name: 'Detections', exact: true })).toHaveClass(/active/);
  // §6.7: the detail is the persistent right inspector, not a modal.
  const detail = page.getByRole('complementary', { name: 'Detection details' });
  await expect(detail).toBeVisible();
  await expect(detail).toContainText('test.rule');
  await detail.getByRole('button', { name: 'Clear selection' }).click();
  await expect(detail).toContainText('Select a detection.');

  // Source pivot: the host link selects that source and opens Timeline.
  await page.getByRole('button', { name: 'Overview', exact: true }).click();
  await sourceRow.getByRole('button', { name: 'Open WKS-042 in Timeline' }).click();
  await expect(page.getByRole('button', { name: 'Timeline', exact: true })).toHaveClass(/active/);
  await expect(page.getByText(/Loaded \d+ of \d+ events/)).toBeVisible();
});

test('detections view filters, expands hits, and pivots to the event', async ({ page }) => {
  await installApiMocks(page, { authedInitially: true });
  await page.goto(`/cases/${baseCase.id}`);
  await page.getByRole('button', { name: 'Detections', exact: true }).click();

  // The grouped table replaces the old card list: one row per rule, with the
  // hit count in its own column instead of buried in prose.
  const row = page.getByRole('row', { name: /Suspicious Logon/ });
  await expect(row).toBeVisible();
  await expect(row.locator('td.col-num')).toHaveText('1');
  await expect(row.locator('td.col-engine')).toContainText(/sigma/i);

  // Severity filter only offers levels actually present, so the analyst never
  // picks a filter that can only return nothing.
  const severitySelect = page.getByLabel('Filter by severity');
  await expect(severitySelect.locator('option')).toHaveText(['All severities', 'medium']);
  await severitySelect.selectOption('medium');
  await expect(row).toBeVisible();

  // Search narrows on rule text, not just title, and the empty state offers a
  // way back.
  await page.getByLabel('Search detections').fill('nomatch');
  await expect(page.getByText('No detections match these filters.')).toBeVisible();
  await page.getByRole('button', { name: 'Clear filters' }).click();
  await expect(row).toBeVisible();
  await expect(severitySelect).toHaveValue('all');
  await page.getByLabel('Search detections').fill('test.rule');
  await expect(row).toBeVisible();

  // Selecting the row fills the persistent inspector (no modal to dismiss).
  await row.click();
  const inspector = page.getByRole('complementary', { name: 'Detection details' });
  await expect(inspector).toContainText('test.rule');
  await expect(inspector).toContainText('Synthetic detection');

  // Expanding hits resolves the sample event ids to real summaries.
  await row.getByRole('button', { name: 'Expand hits for Suspicious Logon' }).click();
  const hit = page.locator('.detection-hit').first();
  await expect(hit).toContainText('User logon 1');

  // View event pivots to Timeline with that event focused.
  await hit.getByRole('button', { name: 'View event' }).click();
  await expect(page.getByRole('button', { name: 'Timeline', exact: true })).toHaveClass(/active/);
  await expect(page.getByText(/Loaded \d+ of \d+ events/)).toBeVisible();
});
