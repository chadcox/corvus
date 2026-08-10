import { expect, test } from '@playwright/test';
import { gotoApp, installApiMocks } from './helpers';

test('control panel shows structured ingest error code and stage for failed jobs', async ({ page }) => {
  await installApiMocks(page, {
    authedInitially: true,
    userRole: 'administrator',
    adminJobs: [
      {
        id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        evidence_source_id: '33333333-3333-3333-3333-333333333333',
        case_id: '22222222-2222-2222-2222-222222222222',
        case_name: 'WKS-042 Investigation',
        hostname: 'WKS-042',
        status: 'failed',
        progress: 67,
        message: 'manifest.json failed validation',
        error_code: 'manifest_invalid',
        error_stage: 'parse',
        created_at: '2026-01-01T00:00:00Z',
        started_at: '2026-01-01T00:00:00Z',
        finished_at: '2026-01-01T00:01:00Z',
      },
    ],
  });

  await gotoApp(page, '/admin/control-panel');
  await expect(page.getByRole('heading', { name: 'Control Panel' })).toBeVisible();
  await expect(page.getByText('code: manifest_invalid')).toBeVisible();
  await expect(page.getByText('stage: parse')).toBeVisible();
});

test('control panel job filters narrow failed taxonomy results', async ({ page }) => {
  await installApiMocks(page, {
    authedInitially: true,
    userRole: 'administrator',
    adminJobs: [
      {
        id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        evidence_source_id: '33333333-3333-3333-3333-333333333333',
        case_id: '22222222-2222-2222-2222-222222222222',
        case_name: 'WKS-042 Investigation',
        hostname: 'WKS-042',
        status: 'failed',
        progress: 67,
        message: 'manifest.json failed validation',
        error_code: 'manifest_invalid',
        error_stage: 'parse',
        created_at: '2026-01-01T00:00:00Z',
        started_at: '2026-01-01T00:00:00Z',
        finished_at: '2026-01-01T00:01:00Z',
      },
      {
        id: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        evidence_source_id: '44444444-4444-4444-4444-444444444444',
        case_id: '22222222-2222-2222-2222-222222222222',
        case_name: 'WKS-042 Investigation',
        hostname: 'WKS-042',
        status: 'failed',
        progress: 71,
        message: 'timeline parser failed',
        error_code: 'timeline_parse_failed',
        error_stage: 'timeline',
        created_at: '2026-01-01T00:00:00Z',
        started_at: '2026-01-01T00:00:00Z',
        finished_at: '2026-01-01T00:01:00Z',
      },
    ],
  });

  await gotoApp(page, '/admin/control-panel');
  await expect(page.getByText('code: manifest_invalid')).toBeVisible();
  await expect(page.getByText('code: timeline_parse_failed')).toBeVisible();

  await page.getByLabel('Job error code filter').fill('manifest_invalid');
  await expect(page.getByText('code: manifest_invalid')).toBeVisible();
  await expect(page.getByText('code: timeline_parse_failed')).toHaveCount(0);

  await page.getByLabel('Job error code filter').fill('');
  await page.getByLabel('Job error stage filter').fill('timeline');
  await expect(page.getByText('stage: timeline')).toBeVisible();
  await expect(page.getByText('stage: parse')).toHaveCount(0);
});

test('bulk delete confirmation snapshots the selected case ids', async ({ page }) => {
  let deletedCaseIds: string[] = [];
  await installApiMocks(page, {
    authedInitially: true,
    userRole: 'administrator',
  });
  await page.route('**/api/v1/admin/cases/bulk-delete', async (route) => {
    const body = route.request().postDataJSON() as { case_ids: string[] };
    deletedCaseIds = body.case_ids;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        deleted_cases: body.case_ids.length,
        case_ids: body.case_ids,
        evidence_dirs_removed: 0,
        orphan_evidence_dirs_removed: 0,
        dry_run: false,
      }),
    });
  });

  await gotoApp(page, '/admin/control-panel');
  const checkbox = page.getByRole('checkbox', { name: /WKS-042 Investigation/ });
  await checkbox.check();
  await page.getByRole('button', { name: 'Delete Selected Cases (1)' }).click();

  const dialog = page.getByRole('alertdialog', { name: 'Delete selected cases' });
  await expect(dialog).toContainText('Delete 1 selected case(s)?');

  // Simulate an asynchronous selection update while the modal is open.
  await checkbox.evaluate((element: HTMLInputElement) => element.click());
  await expect(dialog).toContainText('Delete 1 selected case(s)?');
  await dialog.getByRole('button', { name: 'Delete' }).click();

  await expect.poll(() => deletedCaseIds).toEqual(['22222222-2222-2222-2222-222222222222']);
});

test('container failure message is friendly without duplicated prefixes', async ({ page }) => {
  await installApiMocks(page, {
    authedInitially: true,
    userRole: 'administrator',
  });
  await page.route('**/api/v1/admin/containers', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Internal Server Error' }),
    });
  });

  await gotoApp(page, '/admin/control-panel');
  await expect(page.getByText(
    'Container status is unavailable right now. This usually means the Docker daemon is not running or not reachable from the API.'
  )).toBeVisible();
  await expect(page.getByText(/Container status unavailable: Container status is unavailable/)).toHaveCount(0);
});
