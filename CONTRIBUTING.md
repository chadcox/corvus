# Contributing to Corvus

Thanks for your interest in contributing.

## Development setup

```bash
cp .env.example .env
./scripts/rebuild-stack.sh
```

See the [README](README.md) for service URLs and the `docs/` directory for
architecture, evidence-package format, and parser/licensing details.

## Tests

```bash
cd apps/api && python -m pytest tests/
cd apps/worker && python -m pytest tests/
docker build -f apps/web/Dockerfile -t ff-web-test . && docker run --rm ff-web-test npm run build
```

Please run the relevant tests before opening a pull request.

## Pull requests

- Keep changes focused; one logical change per PR.
- Match existing code style.
- Update docs and `CHANGELOG.md` (`Unreleased` section) when behavior changes.
- Describe what you changed and how you verified it.

## Reporting security issues

Do **not** open a public issue for vulnerabilities. See [SECURITY.md](SECURITY.md).

## Third-party tools and rules

Corvus integrates third-party forensic tools and detection rules under
their own licenses. When adding or changing a bundled/downloaded component,
update [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and add the upstream
license text under `third_party/licenses/`.
