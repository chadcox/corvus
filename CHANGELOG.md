# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) and is pre-1.0.

## [Unreleased]

### Added
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue/PR templates.
- Dependabot config and CodeQL workflow.
- Volatility 3 (VSL-1.0) entry in third-party notices.

### Changed
- Hardened default `docker-compose`: removed the host Docker socket mount from
  the default API service, bound OpenSearch to localhost, and defaulted the
  optional Volatility 3 install to off.
- `.env.example` no longer ships a working default admin password.

## [0.1.0]

- Initial public release: offline forensic triage platform (API, worker, web)
  with source adapters, Sigma/Chainsaw detection, Hindsight browser forensics,
  and evidence-package ingest.
