# Changelog

## v0.1.14 (Unreleased)

Changes since v0.1.13. This version has not been published.

### Features

- **Non-interactive project creation** — Add repeatable `--component` options and `--non-interactive` to `hohu create`; accept `web` as an alias for `frontend` and validate selections before creating files.
- **GitHub and Gitee sources** — Add `--source auto|github|gitee` and a saved source preference. Auto mode falls back to the official Gitee mirror on network failure; explicit sources and custom repositories do not fall back. Record each cloned component's source and commit in `.hohu/project.json`.
- **Project agent guidance** — Generate localized root `AGENTS.md`, `CLAUDE.md`, `README.md` and `.gitignore` files from bundled templates, with links to the selected components' existing documentation and guidance for choosing applicable Skills. Refuse to overwrite existing root files.
- **Skills installation** — Add `hohu skills install` using pinned `skills@1.7.0`, with repeatable `--agent`, `--global` and `--yes` options. Requires stable Node.js >=22.20.0 and npm/npx.
- **Monitoring commands** — Add `hohu monitoring init|up|down|logs|ps|restart` for the optional Prometheus/Grafana stack, including AI Tool Gateway and HITL dashboards and alert rules. Stopping monitoring leaves the application stack running.

### Deployment

- **Automatic database initialization** — Run `python -m scripts.init_db` after Alembic migrations during deploy, migrate and upgrade. Generate `HOHU_ADMIN_PASSWORD` in the deployment `.env`; subsequent deployments synchronize built-in data without resetting the administrator password. Migration or initialization failure stops deployment.
- **Official image fallback** — Add `--image-source auto|official|acr` and `HOHU_IMAGE_SOURCE`. Auto mode retries supported official images through ACR on network failure; preserve custom images and digest-pinned references.
- **Infrastructure mirrors** — Add an ACR synchronization workflow for PostgreSQL, Redis and Nginx, with `linux/amd64` and `linux/arm64` runtime digest checks and anonymous download verification.
- **Upload limits** — Align backend upload limits and the Nginx request-body ceiling, validate deployment settings and render the configured limit into proxy templates.
- **Private storage persistence** — Mount shared private storage into API and Scheduler containers and initialize both public and private storage directories during build/deploy setup.
- **Template upgrade** — Update the deployment template marker so existing v0.1.13 installations are prompted to synchronize the new configuration.

### Security

- **Private artifact access** — Return 404 for legacy `/uploads/file_storage/**` and public upload requests for `.csv`, `.txt`, `.xls` and `.xlsx` files in built-in, SSL and external Nginx templates.
- **Production defaults** — Require configured database, Redis, application and Grafana secrets; use a 60-minute access-token default, one API worker and distinct API/Scheduler Snowflake worker IDs.
- **Proxy headers** — Replace incoming `X-Forwarded-For` values with the client address at the bundled Nginx edge.

### Bug Fixes

- **Windows console output** — Avoid `UnicodeEncodeError` when emoji or surrogate characters are written to captured GBK/cp936 streams, while preserving the stream encoding.
- **Command hints** — Clarify the `web` alias for the frontend component in project-creation messages.

### Licensing

- Adopt Apache-2.0 for the current development tree, except where otherwise noted, and include license notices in distributions.
- Versions through v0.1.13 were released under MIT; that grant remains effective for copies already distributed. Existing third-party notices are retained.

### Documentation and Testing

- Document project creation, Skills installation, deployment initialization and infrastructure mirrors.
- Add Windows/Linux CI coverage for project creation, Skills installation, repository sources, deployment image fallback and mirror tooling, with a 70% coverage gate for the configured modules.
- Keep commit hooks focused on Ruff lint and formatting; run full tests and coverage at feature acceptance and in CI. Make deployment help assertions robust to ANSI colors.

### Upgrade Notes

- Refresh deployment templates and review `.env` before deploying; the new templates require a backend with the `scripts.init_db` module and replace the old `--init` workflow with automatic initialization.
- Review `API_WORKER_ID`, `SCHEDULER_WORKER_ID`, required secrets and upload limits when upgrading an existing deployment.

**Changes since last release**: [v0.1.13...HEAD](https://github.com/aihohu/hohu-cli/compare/v0.1.13...HEAD)

## v0.1.13

### Features

- **Standalone scheduler service** — Add `hohu-admin-scheduler` container running `app.scheduler_worker` to isolate APScheduler from the web process; API container now defaults to `APP_ROLE=api` to avoid duplicate triggers across workers
- **`hohu admin deploy upgrade`** — New one-click subcommand for full redeployment (pull → migrate → recreate)
- **Env file for API containers** — Mount `.env` into `api` and `db-migrator` containers for simpler local overrides

### Bug Fixes

- **Seed system configs on migrate** — Run `seed_config.py` alongside `sync_menus.py` in the db-migrator deploy step
- **Dev mode APP_ROLE** — Inject `APP_ROLE=all` for backend under `hohu dev`, since the deploy template now defaults to `api` only
- **Nginx body size & SERVER_URL defaults** — Add `client_max_body_size` to nginx configs and a `SERVER_URL` default in `.env.example`

**Full Changelog**: `v0.1.12...v0.1.13`

## v0.1.12

### Bug Fixes

- **Local build pull failure** — Use `docker pull` directly for infrastructure images (postgres, redis, nginx) instead of `docker compose pull`, avoiding cascading through `depends_on` to pull non-existent local-built images from Docker Hub

### Refactor

- **Dynamic infra image names** — Read infrastructure image tags from `docker-compose.yml` at runtime instead of hardcoding, preventing tag drift when templates are updated
- **Eliminate duplicated pull logic** — Reuse `_pull_images()` in `deploy pull` subcommand instead of duplicating local-build detection and image pull code

**Full Changelog**: `v0.1.11...v0.1.12`

## v0.1.11

### Bug Fixes

- **Local build pull failure** — Use `docker pull` directly for infrastructure images (postgres, redis, nginx) instead of `docker compose pull`, avoiding cascading through `depends_on` to pull non-existent local-built images from Docker Hub

### Refactor

- **Dynamic infra image names** — Read infrastructure image tags from `docker-compose.yml` at runtime instead of hardcoding, preventing tag drift when templates are updated
- **Eliminate duplicated pull logic** — Reuse `_pull_images()` in `deploy pull` subcommand instead of duplicating local-build detection and image pull code

**Full Changelog**: `v0.1.10...v0.1.11`

## v0.1.10

### Features

- **Uploads persistence** — Mount `./uploads` as a bind volume in backend container; auto-create uploads directory with correct permissions on deploy
- **Nginx `/uploads/` proxy** — Add reverse proxy rule for uploaded files in all nginx configs (`nginx.conf`, `nginx-ssl.conf`, `proxy-snippet.conf`)
- **Auto menu sync on deploy** — Run `sync_menus.py` automatically after database initialization during migration
- **New env vars** — Add `SERVER_URL`, `UPLOAD_DIR`, `UPLOAD_MAX_SIZE` configuration options in `.env.example`
- **Version-aware template sync** — `deploy init` detects template version changes, diffs file content, and prompts before overwriting; add `--force` to skip confirmation
- **`.template-version`** — Add version marker file to deploy templates for upgrade detection

### Bug Fixes

- **Skip nginx pull when disabled** — Do not pull nginx image when `ENABLE_NGINX=false`
- **`deploy logs` error handling** — Add command resolution and friendly error when `docker` is not found

### Refactor

- **PyYAML for override generation** — Replace string concatenation with `yaml.dump()` in `docker-compose.override.yml` generation to correctly handle special characters in env values

**Full Changelog**: `v0.1.9...v0.1.10`

## v0.1.9

### Features

- **`hohu build` — Source Build** — Build Docker images from local source code with options: `--only` (backend/frontend), `--tag`, `--no-cache`, `--reset`; auto-initializes deploy config on first run
- **External PostgreSQL / Redis** — Add `ENABLE_POSTGRES` / `ENABLE_REDIS` toggles in `.env` to disable built-in containers and connect to external instances; `docker-compose.override.yml` generated dynamically based on infra flags
- **`hohu deploy init`** — New subcommand to initialize deployment directory, sync templates, and generate secrets independently
- **Deploy smart pull** — Detect local-built images and skip pulling application images, only pull infrastructure images (postgres, redis, nginx)
- **Refactor `hohu dev`** — Extract monolithic dev function into smaller focused helpers for maintainability

### Documentation

- Add `hohu build` and external database docs to README (English & Chinese)
- Add ruff complexity rules (C901, PLR0912, PLR0915) to CLAUDE.md and pyproject.toml
- Restructure deployment docs with Quick Start sections for source build and official image flows

**Full Changelog**: `v0.1.8...v0.1.9`

## v0.1.8

### Features

- **`hohu deploy` — One-Click Docker Deployment** — Deploy the full stack (Backend + Frontend + PostgreSQL + Redis + Nginx with SSL) to a Linux server with a single command, includes subcommands: `pull`, `ps`, `logs`, `restart`, `down`
- **`hohu migrate` — Database Migration** — Run Alembic migrations and seed data independently of the full deploy flow
- **Deploy Templates** — Production-ready `docker-compose.yml` (PostgreSQL 18, Redis 8.6, Nginx, Certbot), `nginx.conf` (SSL, gzip, rate limiting, security headers), `.env.example` (full configuration with comments)
- **i18n for deploy/migrate** — All deploy and migrate messages support zh/en

### Documentation

- Add deployment documentation to README (English & Chinese)
- Add deploy templates to package build artifacts

**Full Changelog**: `v0.1.7...v0.1.8`

## v0.1.7

### Features

- **Internationalize `--help` output** — All Typer help text (command descriptions, option hints) now uses `i18n.t()` for full zh/en support, no more mixed-language output
- **Improve component selection UX** — Replace `questionary.checkbox` with per-component `questionary.confirm` prompts, showing actual folder names (e.g. `Backend（hohu-admin）`) for clearer selection
- **Add i18n variable interpolation** — `i18n.t()` now accepts `**kwargs` for dynamic placeholders like `{component}` in translations
- **Auto-install uv** — Automatically install uv when missing during `hohu init` or `hohu dev`

### Documentation

- Add Windows EPERM symlink troubleshooting guide to README

**Full Changelog**: `v0.1.6...v0.1.7`

## v0.1.6

**Full Changelog**: `v0.1.5...v0.1.6`
