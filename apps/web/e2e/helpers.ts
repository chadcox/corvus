import { Page, Route, expect } from '@playwright/test';

export const analystUser = {
  id: '11111111-1111-1111-1111-111111111111',
  username: 'analyst1',
  role: 'analyst',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

export const baseCase = {
  id: '22222222-2222-2222-2222-222222222222',
  name: 'WKS-042 Investigation',
  description: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  evidence_source_count: 1,
};

export const baseSource = {
  id: '33333333-3333-3333-3333-333333333333',
  case_id: baseCase.id,
  hostname: 'WKS-042',
  collector: 'import',
  collector_version: null,
  source_type: 'endpoint',
  platform: 'windows',
  os_version: null,
  architecture: null,
  timezone: null,
  collected_at: null,
  package_path: '/data/evidence/wks-042.zip',
  uploaded_filename: 'wks-042.zip',
  status: 'completed',
  manifest: { collected_at: '2026-01-01T00:00:00Z', modules_run: ['evtx', 'mft'] },
  created_at: '2026-01-01T00:00:00Z',
  processing_started_at: null,
  processing_finished_at: null,
  total_processing_seconds: 42,
  latest_job_id: '44444444-4444-4444-4444-444444444444',
};

type MockOptions = {
  authedInitially?: boolean;
  userRole?: 'analyst' | 'administrator';
  allowCaseCreate?: boolean;
  onHashCompute?: () => void;
  onYaraScan?: () => void;
  timelineTotal?: number;
  onTimelineRequest?: (params: { limit: number; offset: number }) => void;
  adminJobs?: Array<Record<string, unknown>>;
};

async function json(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

export async function installApiMocks(page: Page, options: MockOptions = {}): Promise<void> {
  const {
    authedInitially = false,
    userRole = 'analyst',
    allowCaseCreate = false,
    onHashCompute,
    onYaraScan,
    timelineTotal = 1,
    onTimelineRequest,
    adminJobs = [],
  } = options;
  let authed = authedInitially;
  let createdCaseName = 'Created Case';

  await page.route('**/api/v1/**', async (route) => {
    const req = route.request();
    const method = req.method();
    const url = new URL(req.url());
    const path = url.pathname;

    if (path === '/api/v1/auth/me' && method === 'GET') {
      if (!authed) {
        await json(route, { detail: 'Authentication required' }, 401);
        return;
      }
      await json(route, { ...analystUser, role: userRole });
      return;
    }

    if (path === '/api/v1/auth/login' && method === 'POST') {
      authed = true;
      await json(route, { access_token: 'smoke-token', token_type: 'bearer', user: { ...analystUser, role: userRole } });
      return;
    }

    if (path === '/api/v1/auth/logout' && method === 'POST') {
      authed = false;
      await json(route, { message: 'Logged out' });
      return;
    }

    if (path === '/api/v1/system/status' && method === 'GET') {
      await json(route, {
        hostname: 'forensic-lab',
        cpu_usage_percent: 10.2,
        memory_used_bytes: 1024,
        memory_total_bytes: 2048,
        disk_used_bytes: 1024,
        disk_total_bytes: 4096,
        jobs: { running: 0, queued: 0, completed: 1, failed: 0 },
      });
      return;
    }

    if (path === '/api/v1/cases' && method === 'GET') {
      await json(route, [baseCase]);
      return;
    }

    if (path === '/api/v1/cases' && method === 'POST' && allowCaseCreate) {
      const body = JSON.parse(req.postData() || '{}') as { name?: string };
      createdCaseName = body.name || createdCaseName;
      await json(route, {
        ...baseCase,
        id: '55555555-5555-5555-5555-555555555555',
        name: createdCaseName,
        evidence_source_count: 0,
      });
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+$/.test(path) && method === 'GET') {
      const id = path.split('/').pop() || baseCase.id;
      if (id === '55555555-5555-5555-5555-555555555555') {
        await json(route, { ...baseCase, id, name: createdCaseName, evidence_source_count: 0 });
        return;
      }
      await json(route, { ...baseCase, id });
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/evidence$/.test(path) && method === 'GET') {
      await json(route, [baseSource]);
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/sources\/[^/]+\/stats$/.test(path) && method === 'GET') {
      await json(route, {
        timeline_count: 3,
        filesystem_count: 2,
        entity_count: 2,
        sigma_detection_count: 1,
        mft_count: 1,
        browser_count: 1,
        event_types: ['logon', 'process'],
      });
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/evidence\/[^/]+\/hashes$/.test(path) && method === 'GET') {
      await json(route, {
        sha256: null,
        sha1: null,
        md5: null,
        hash_status: null,
        hash_file_count: null,
        hashed_files_in_db: 0,
        yara_status: null,
        yara_match_count: 0,
        yara_file_count: 0,
      });
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/evidence\/[^/]+\/hashes\/compute$/.test(path) && method === 'POST') {
      onHashCompute?.();
      await json(route, { message: 'Hashing started' });
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/evidence\/[^/]+\/yara\/scan$/.test(path) && method === 'POST') {
      onYaraScan?.();
      await json(route, { message: 'YARA started' });
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/sources\/[^/]+\/sigma$/.test(path) && method === 'GET') {
      await json(route, [
        {
          id: '66666666-6666-6666-6666-666666666666',
          evidence_source_id: baseSource.id,
          engine: 'sigma',
          rule_id: 'test.rule',
          title: 'Suspicious Logon',
          level: 'medium',
          description: 'Synthetic detection',
          tags: ['attack.t1078'],
          match_count: 1,
          sample_event_ids: ['77777777-7777-7777-7777-777777777777'],
          created_at: '2026-01-01T00:00:00Z',
        },
      ]);
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/sources\/[^/]+\/timeline\/count/.test(path) && method === 'GET') {
      await json(route, { count: timelineTotal });
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/sources\/[^/]+\/stats\/histogram/.test(path) && method === 'GET') {
      await json(route, { buckets: [{ ts: '2026-01-01T00:00:00Z', count: 1 }], total: 1, granularity: 'hour' });
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/sources\/[^/]+\/timeline/.test(path) && method === 'GET') {
      const limit = Number(url.searchParams.get('limit') || '200');
      const offset = Number(url.searchParams.get('offset') || '0');
      onTimelineRequest?.({ limit, offset });
      const pageLength = Math.max(0, Math.min(limit, timelineTotal - offset));
      await json(route, Array.from({ length: pageLength }, (_, index) => {
        const rowNumber = offset + index + 1;
        const suffix = String(rowNumber).padStart(12, '0');
        return {
          id: `77777777-7777-7777-7777-${suffix}`,
          evidence_source_id: baseSource.id,
          timestamp_utc: new Date(Date.UTC(2026, 0, 1, 0, 0, index)).toISOString(),
          event_type: 'logon',
          summary: `User logon ${rowNumber}`,
          artifact_type: 'mft',
          original_source: 'security.evtx',
          data: { path: `C:/Users/analyst${rowNumber}` },
          entity_refs: ['88888888-8888-8888-8888-888888888888'],
          sigma_hits: [{ rule_id: 'test.rule', title: 'Suspicious Logon', level: 'medium', engine: 'sigma' }],
        };
      }));
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/sources\/[^/]+\/entities/.test(path) && method === 'GET') {
      await json(route, [
        {
          id: '88888888-8888-8888-8888-888888888888',
          evidence_source_id: baseSource.id,
          entity_type: 'user',
          display_name: 'analyst1',
          attributes: { sid: 'S-1-5-21-test' },
        },
      ]);
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/sources\/[^/]+\/filesystem/.test(path) && method === 'GET') {
      await json(route, [
        {
          id: '99999999-9999-9999-9999-999999999999',
          evidence_source_id: baseSource.id,
          full_path: '/Users/analyst1/AppData/Local/Temp',
          name: 'Temp',
          is_directory: true,
          size: null,
          is_deleted: false,
          parent_path: '/Users/analyst1/AppData/Local',
        },
      ]);
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/sources\/[^/]+\/search/.test(path) && method === 'GET') {
      await json(route, { query: 'test', timeline: [], filesystem: [], entities: [], total: 0 });
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/sources\/[^/]+\/filesystem\/[^/]+\/preview/.test(path) && method === 'GET') {
      await json(route, {
        node_id: '99999999-9999-9999-9999-999999999999',
        name: 'Temp',
        full_path: '/Users/analyst1/AppData/Local/Temp',
        offset: 0,
        length: 0,
        file_size: 0,
        truncated: false,
        hex: '',
        ascii: '',
      });
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/sources\/[^/]+\/filesystem\/[^/]+\/hashes/.test(path) && method === 'GET') {
      await json(route, {
        node_id: '99999999-9999-9999-9999-999999999999',
        relative_path: '/Users/analyst1/AppData/Local/Temp',
        sha256: null,
        sha1: null,
        md5: null,
        available: false,
      });
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/sources\/[^/]+\/evidence\/[^/]+\/jobs/.test(path) && method === 'GET') {
      await json(route, []);
      return;
    }

    if (/^\/api\/v1\/cases\/[^/]+\/sources\/[^/]+\/jobs$/.test(path) && method === 'GET') {
      await json(route, []);
      return;
    }

    if (path === '/api/v1/admin/overview' && method === 'GET') {
      await json(route, {
        readiness: { status: 'ready' },
        table_counts: {
          cases: 1,
          evidence_sources: 1,
          ingest_jobs: 2,
          timeline_events: 3,
          filesystem_nodes: 2,
          entities: 2,
          relations: 0,
          sigma_detections: 1,
        },
        jobs_by_status: { failed: 1, completed: 1 },
        evidence_by_status: { completed: 1 },
        disk: { path: '/data/evidence', total_bytes: 1024, used_bytes: 512, free_bytes: 512, error: null },
        sigma_rules: {
          state: 'idle',
          rule_count: 0,
          ref: 'master',
          updated_at: null,
          message: null,
          task_id: null,
          refresh_interval_hours: 24,
        },
        feature_flags: { enable_validation_api: true, enable_admin_api: true },
        auth_security: {
          failed_logins_5m: 0,
          active_lockouts: 0,
          redis_available: true,
          revocation_redis_available: true,
          revocation_failures_5m: 0,
          error: null,
        },
        search_observability: {
          window_seconds: 300,
          total_queries: 0,
          opensearch_hits: 0,
          fallback_hits: 0,
          fallback_short_queries: 0,
          fallback_avg_ms: 0,
        },
      });
      return;
    }

    if (path === '/api/v1/detection-rules' && method === 'GET') {
      await json(route, {
        sigma: {
          state: 'idle',
          rule_count: 0,
          ref: 'master',
          updated_at: null,
          message: null,
          task_id: null,
          refresh_interval_hours: 24,
        },
        chainsaw: {
          state: 'idle',
          rule_count: 0,
          mapping_count: 0,
          binary_available: true,
          chainsaw_version: 'dev',
          ref: 'master',
          updated_at: null,
          message: null,
          task_id: null,
          include_sigma_in_hunt: true,
        },
      });
      return;
    }

    if (path === '/api/v1/yara/rules' && method === 'GET') {
      await json(route, { state: 'idle', rule_count: 0, updated_at: null, message: null, task_id: null });
      return;
    }

    if (path.startsWith('/api/v1/admin/jobs') && method === 'GET') {
      const status = url.searchParams.get('status');
      const errorCode = url.searchParams.get('error_code');
      const errorStage = url.searchParams.get('error_stage');
      const filtered = adminJobs.filter((job) => {
        if (status && job.status !== status) return false;
        if (errorCode && (job.error_code ?? '') !== errorCode) return false;
        if (errorStage && (job.error_stage ?? '') !== errorStage) return false;
        return true;
      });
      await json(route, filtered);
      return;
    }

    if (path === '/api/v1/admin/containers' && method === 'GET') {
      await json(route, []);
      return;
    }

    if (path === '/api/v1/auth/users' && method === 'GET') {
      await json(route, [{ ...analystUser, role: userRole }]);
      return;
    }

    await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled mock route: ${method} ${path}` }) });
  });
}

export async function loginViaUi(page: Page): Promise<void> {
  await gotoApp(page, '/');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await page.getByPlaceholder('Username').fill('analyst1');
  await page.getByPlaceholder('Password').fill('password123');
  await page.getByRole('button', { name: 'Sign in' }).click();
}

export async function gotoApp(page: Page, path: string): Promise<void> {
  const attempts = 10;
  let lastErr: unknown;
  for (let i = 0; i < attempts; i += 1) {
    try {
      await page.goto(path);
      return;
    } catch (err) {
      lastErr = err;
      const msg = err instanceof Error ? err.message : String(err);
      const retriable = msg.includes('ERR_NAME_NOT_RESOLVED') || msg.includes('ERR_CONNECTION_REFUSED');
      if (!retriable || i === attempts - 1) break;
      await page.waitForTimeout(1000);
    }
  }
  throw lastErr;
}
