# CLI Development

- Follow [CONTRIBUTING.md](CONTRIBUTING.md) for contribution and commit requirements.
- Follow [docs/TESTING-GUIDELINES.md](docs/TESTING-GUIDELINES.md) for check timing: run related regressions during development, Ruff lint and format checks before commits, and full tests with coverage at feature acceptance and in CI. Do not run full pytest automatically on every commit or pre-push.
- Use the project virtual environment through `uv run`. Keep temporary files and tool caches under `.local/` and use explicit absolute pytest/cache paths.
