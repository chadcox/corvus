# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) and is pre-1.0.

## [Unreleased]

### Added
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue/PR templates.
- Dependabot config and CodeQL workflow.
- Volatility 3 (VSL-1.0) entry in third-party notices.

### Security
- Analyst CSV exports (timeline and file hashes) now neutralize spreadsheet
  formula injection: cells beginning with `=`, `+`, `-`, `@`, their full-width
  forms, or a whitespace control are prefixed with `'`. Formula-like starts
  after semicolon, tab, or line boundaries are also prefixed so parsing the
  canonical comma stream with those alternate delimiters cannot expose them as
  active data cells. Plain numbers are exempt only when they comprise the whole
  original value. Stored evidence, JSON API responses, and worker COPY
  serialization are unchanged. Controlled by `CSV_EXPORT_FORMULA_ESCAPE`
  (default `true`).

### Changed
- API archive extraction now rejects uploads whose members claim the same path as
  both a file and a directory, and enforces a fixed ceiling on the number of
  distinct path components an archive may declare. That structural ceiling is
  separate from `EXTRACTED_MAX_FILES`, which still limits file count only. Both
  checks run before any member is written to disk.
- Hardened default `docker-compose`: removed the host Docker socket mount from
  the default API service, bound OpenSearch to localhost, and defaulted the
  optional Volatility 3 install to off.
- `.env.example` no longer ships a working default admin password.

### Fixed
- Failed API uploads now remove their newly created evidence directory when
  package storage or extraction raises `OSError` before database persistence.
  The original exception is preserved and cleanup remains best-effort. The
  removal target is built from the persisted case and server-generated source
  identifiers and is only deleted when it resolves to a strict descendant of the
  resolved evidence root, so a symlinked ancestor cannot redirect the delete.
- Worker boot reconciliation no longer marks running ingest jobs as failed by
  default. It previously failed every job in `running` state, so a restart or
  scale-up reported another worker's in-flight ingest as failed while that
  ingest kept writing rows. Reconciliation now probes Celery `active`/
  `reserved`/`scheduled` for the ingest task ids workers hold (a job id is
  dispatched as its task id), but treats that reply as presence-only evidence:
  it proves a job is still owned, never that it is orphaned, because a worker
  that does not answer within the probe timeout is silently absent from the
  reply and is indistinguishable from an idle one. Jobs no worker claims are
  therefore logged and left running (`WORKER_RECONCILE_UNCLAIMED_ACTION=skip`,
  the default). The trade-off is deliberate: a genuinely dead job now stays in
  `running` until an operator clears it, rather than a live ingest being
  reported as failed. Setting `WORKER_RECONCILE_UNCLAIMED_ACTION=fail` opts back
  into failing unclaimed jobs (`error_code=interrupted`,
  `error_stage=worker_restart`, and the evidence source failed only when none of
  its running jobs are claimed); that setting can still mark a live ingest as
  failed when its worker did not answer, so it suits single-worker deployments
  only. The probe runs after a bounded startup grace window
  (`WORKER_RECONCILE_STARTUP_DELAY_SECONDS`, default 15s) and is skipped
  entirely when no job is running.
- Search terms are now matched literally: `%` and `_` in timeline, timeline
  density histogram, global search, filesystem path, and entity queries are
  escaped instead of being treated as SQL LIKE wildcards.

## [0.1.0]

- Initial public release: offline forensic triage platform (API, worker, web)
  with source adapters, Sigma/Chainsaw detection, Hindsight browser forensics,
  and evidence-package ingest.
