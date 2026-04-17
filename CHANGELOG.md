# Changelog

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
