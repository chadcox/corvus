import { expect, test } from '@playwright/test';

const runBackendE2E = process.env.PLAYWRIGHT_BACKEND_E2E === '1';
const adminUsername = process.env.FF_E2E_ADMIN_USERNAME ?? 'admin';
const adminPassword = process.env.FF_E2E_ADMIN_PASSWORD ?? 'admin';
const apiBaseUrl = (process.env.FF_E2E_API_URL ?? 'http://api:8000').replace(/\/$/, '');
const validationSample = process.env.FF_E2E_SAMPLE ?? 'kape-minimal';

type LoginResponse = {
  access_token: string;
  token_type: string;
};

type IngestStartResponse = {
  case_id: string;
  job_id: string;
  evidence_source_id: string;
  outcome_path: string;
  job_path: string;
};

type IngestOutcomeResponse = {
  success: boolean;
  job_status: string;
  checks: Array<{ name: string; passed: boolean; detail?: string | null }>;
};

type IngestJobResponse = {
  status: string;
  message?: string | null;
};

async function requestWithRetry<T>(
  fn: () => Promise<T>,
  page: { waitForTimeout(ms: number): Promise<void> },
  attempts = 5,
): Promise<T> {
  let lastError: unknown;
  for (let i = 0; i < attempts; i += 1) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      const message = error instanceof Error ? error.message : String(error);
      const retriable =
        message.includes('ECONNREFUSED') ||
        message.includes('ECONNRESET') ||
        message.includes('ENOTFOUND');
      if (!retriable || i === attempts - 1) {
        throw error;
      }
      await page.waitForTimeout(1000);
    }
  }
  throw lastError;
}

test.describe('backend analyst flow', () => {
  test.skip(!runBackendE2E, 'Set PLAYWRIGHT_BACKEND_E2E=1 to run backend-data-backed e2e.');

  test('analyst case workspace loads real ingest data', async ({ page, request, baseURL }) => {
    test.setTimeout(240_000);
    expect(baseURL).toBeTruthy();

    const loginRes = await requestWithRetry(
      () =>
        request.post(`${apiBaseUrl}/api/v1/auth/login`, {
          data: { username: adminUsername, password: adminPassword },
        }),
      page,
    );
    expect(loginRes.ok()).toBeTruthy();
    const login = (await loginRes.json()) as LoginResponse;

    const authHeader = { Authorization: `Bearer ${login.access_token}` };
    const caseName = `Validation UI backend ${Date.now()}`;
    const startRes = await requestWithRetry(
      () =>
        request.post(
          `${apiBaseUrl}/api/v1/validation/ingest-sample?sample=${encodeURIComponent(validationSample)}&min_filesystem_nodes=1&case_name=${encodeURIComponent(caseName)}`,
          { headers: authHeader },
        ),
      page,
    );
    expect(startRes.ok()).toBeTruthy();
    const start = (await startRes.json()) as IngestStartResponse;

    let outcome: IngestOutcomeResponse | null = null;
    let jobStatus = 'pending';
    for (let i = 0; i < 90; i += 1) {
      const jobRes = await requestWithRetry(
        () => request.get(`${apiBaseUrl}${start.job_path}`, { headers: authHeader }),
        page,
      );
      expect(jobRes.ok()).toBeTruthy();
      const job = (await jobRes.json()) as IngestJobResponse;
      jobStatus = job.status;
      if (jobStatus === 'failed') {
        throw new Error(`Ingest failed: ${job.message ?? 'no message'}`);
      }
      if (jobStatus === 'completed') {
        break;
      }
      const outcomeRes = await requestWithRetry(
        () => request.get(`${apiBaseUrl}${start.outcome_path}`, { headers: authHeader }),
        page,
      );
      expect(outcomeRes.ok()).toBeTruthy();
      outcome = (await outcomeRes.json()) as IngestOutcomeResponse;
      if (outcome.success) break;
      if (outcome.job_status === 'failed') {
        throw new Error(`Ingest failed: ${JSON.stringify(outcome.checks)}`);
      }
      await page.waitForTimeout(2000);
    }

    expect(jobStatus).toBe('completed');

    await page.addInitScript((token: string) => {
      window.localStorage.setItem('ff_auth_token', token);
    }, login.access_token);

    await page.goto(`/cases/${start.case_id}`);
    await expect(page.getByRole('heading', { name: caseName })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Timeline' })).toBeVisible();
    await expect(page.getByText(/Loaded .* of .* events/)).toBeVisible();

    await page.getByRole('button', { name: 'Entities', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Entities' })).toBeVisible();
  });
});
