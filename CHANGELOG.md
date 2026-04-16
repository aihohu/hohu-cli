# Changelog

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
