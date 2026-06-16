# Security Policy

## Reporting a vulnerability

Please report security issues **privately**. Do not open a public issue for a
vulnerability.

- Preferred: use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  ("Report a vulnerability" under the repository **Security** tab).
- We aim to acknowledge reports within a few days and to provide a remediation
  timeline after triage.

Please include reproduction steps, affected versions/commit, and impact.

## Supported versions

ForensicFlow is pre-1.0. Only the latest `main` receives security fixes.

## Scope and intended use

ForensicFlow is a **defensive** DFIR triage tool: it ingests and analyzes
endpoint evidence and runs detection rules. It is intended for authorized
forensic and incident-response work on evidence you are permitted to process.

The default `docker compose` stack ships **development defaults** (known JWT
secret, open OpenSearch, weak datastore passwords) and is meant to run on a
trusted, localhost-only host. Before any shared or internet-exposed deployment:

- Set a strong `AUTH_SECRET_KEY` and a strong bootstrap admin password.
- Set `ENVIRONMENT=production` (rejects the default auth secret at startup).
- Do not expose the API, OpenSearch, Postgres, or Redis ports to untrusted networks.
- Re-enable the OpenSearch security plugin and set real datastore credentials.
