<div align="center">

# HoHu CLI

A modern full-stack development toolkit for the **hohu-admin** ecosystem.

[![PyPI version](https://img.shields.io/pypi/v/hohu?color=blue&label=pypi)](https://pypi.org/project/hohu/)
[![Python](https://img.shields.io/pypi/pyversions/hohu?label=python)](https://pypi.org/project/hohu/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![GitHub Issues](https://img.shields.io/github/issues/aihohu/hohu-cli)](https://github.com/aihohu/hohu-cli/issues)

[English](README.md) · [中文](README_zh.md)

</div>

---

## Features

- **Blazing Fast** — Built on `uv` for near-instant CLI response times
- **Smart Init** — Auto-detects and installs dependencies (`uv sync` / `pnpm install`), auto-installs `uv` if missing
- **One-Click Deploy** — Deploy the full stack (Backend + Frontend + PostgreSQL + Redis + Nginx SSL) with a single `hohu deploy`
- **Database Migrations** — Run migrations and seed data via `hohu migrate`
- **Context-Aware** — Run commands from any subdirectory via `.hohu` project config
- **i18n** — Full Chinese & English support with automatic system language detection
- **Polished UX** — Rich-formatted output with interactive prompts via Questionary

## About hohu-admin

**hohu-admin** is an enterprise-grade full-stack admin management platform built for the AI era. It provides a complete set of production-ready backend infrastructure out of the box — user authentication, RBAC permission control, distributed ID generation, database migration, log monitoring, and API documentation — so developers can focus on business innovation instead of repetitive boilerplate.

### Highlights

- **Async High Performance** — Full async pipeline (FastAPI + SQLAlchemy 2.0 async + PostgreSQL)
- **Distributed Snowflake ID** — Time-ordered, high-performance primary keys with automatic `BigInt` → string serialization
- **RBAC Permission Model** — User-Role-Menu based access control with button-level granularity
- **Dual Auth Support** — OAuth2 form login (Swagger UI) + JSON login (SPA), with Redis token blacklist
- **Unified API Response** — Consistent `{code, message, data}` envelope across all endpoints
- **Auto Case Conversion** — Backend `snake_case` ↔ Frontend `camelCase` via Pydantic `alias_generator`

### Projects

| Project | Description | Tech Stack |
|---------|-------------|------------|
| [hohu-admin](https://github.com/aihohu/hohu-admin) | Backend API | FastAPI, SQLAlchemy 2.0 (async), PostgreSQL, Redis |
| [hohu-admin-web](https://github.com/aihohu/hohu-admin-web) | Admin dashboard | Vue 3, NaiveUI, UnoCSS, Pinia, TypeScript |
| [hohu-admin-app](https://github.com/aihohu/hohu-admin-app) | Mobile app | uni-app, Vue 3, Wot Design Uni, alova |

## Quick Start

### Install

```bash
# uv (recommended)
uv tool install hohu

# pip
pip install hohu
```

### Update

```bash
# uv
uv tool upgrade hohu

# pip
pip install --upgrade hohu
```

### Create a Project

```bash
hohu create my-project
```

Confirm each component (Backend / Frontend / App) interactively. Defaults to `hohu-admin` if no name is given.

### Install Dependencies

```bash
cd my-project
hohu init
```

Automatically detects project config and installs all dependencies.

> **Windows Users:** If `hohu init` fails with `EPERM: operation not permitted, symlink`, try the following:
> 1. Enable **Developer Mode** in Windows Settings: **Settings → Update & Security → For developers → Developer Mode**. This allows symlink creation without admin privileges.
> 2. Run your terminal as Administrator.
> 3. Check your antivirus software (e.g., 360, Huorong) — some may block symlink creation. Try adding the project directory to the exclusion list or temporarily disabling real-time protection.

### Switch Language

```bash
hohu lang
```

## Development Server

`hohu dev` launches all services in a single terminal with merged, color-coded log output.

```bash
hohu dev          # Start all components
hohu dev -o be    # Backend only
hohu dev -s app   # Frontend + Backend, skip App
hohu dev -t mp    # App in WeChat Mini Program mode
```

### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--app-target` | `-t` | App runtime: `h5` / `mp` / `app` | `h5` |
| `--only` | `-o` | Only start specified components (repeatable) | all |
| `--skip` | `-s` | Skip specified components (repeatable) | none |

Component aliases (case-insensitive): `be` / `backend`, `fe` / `frontend`, `app`

### Log Colors

| Prefix | Color | Service |
|--------|-------|---------|
| `[Backend]` | green | FastAPI |
| `[Frontend]` | cyan | Vite / pnpm |
| `[App]` | yellow | Uni-app |

Press `Ctrl+C` for graceful shutdown — all child processes are terminated cleanly.

## Deployment

Deploy the full stack to a Linux server with Docker Compose. Includes PostgreSQL, Redis, Nginx (SSL termination), and the application services.

### First-Time Deploy

```bash
hohu deploy
```

This will:
1. Create `.hohu/deploy/` with configuration files (docker-compose.yml, nginx.conf, .env)
2. Generate `.env` from template — edit it before proceeding
3. Pull images, start PostgreSQL & Redis, run migrations, and launch all services

After editing `.env` (passwords, SECRET_KEY, SSL certs), run `hohu deploy` again.

### Deploy Commands

```bash
hohu deploy          # One-click deploy (pull → migrate → start)
hohu deploy pull     # Pull latest images and restart
hohu deploy ps       # Show service status
hohu deploy logs     # View logs (-f to follow)
hohu deploy restart  # Restart services
hohu deploy down     # Stop all services
hohu migrate         # Run database migrations only
```

### Custom Images

By default, `hohu deploy` uses the official images from GHCR. To deploy your own fork:

1. Push your code to your GitHub repo
2. Set up GitHub Actions to build and push images to your own registry
3. Edit `.hohu/deploy/.env`:

```env
API_IMAGE=ghcr.io/your-org/hohu-admin
WEB_IMAGE=ghcr.io/your-org/hohu-admin-web
IMAGE_TAG=v1.0.0
```

### Architecture

```
Internet → Nginx (SSL) → hohu-admin-web → hohu-admin-api → PostgreSQL + Redis
```

### SSL Certificates

Place your certificate files in `.hohu/deploy/ssl/`:

```
ssl/
├── fullchain.pem
└── privkey.pem
```

For Let's Encrypt, point `SSL_CERT_PATH` in `.env` to the certbot output directory.

## Command Reference

| Command | Description |
|---------|-------------|
| `hohu create [NAME]` | Create project and clone repo templates |
| `hohu init` | Install all sub-project dependencies |
| `hohu dev` | Start development server |
| `hohu deploy` | One-click Docker deployment |
| `hohu deploy pull` | Pull latest images and restart |
| `hohu deploy ps` | Show service status |
| `hohu deploy logs` | View service logs |
| `hohu deploy restart` | Restart services |
| `hohu deploy down` | Stop all services |
| `hohu migrate` | Run database migrations and initialization |
| `hohu lang` | Switch display language (zh / en / auto) |
| `hohu info` | View current CLI configuration |
| `hohu --version` | Show version |
| `hohu --help` | Show help |

## Project Structure

```
my-project/
├── .hohu/            # Project config
│   ├── project.json  # Project metadata
│   └── deploy/       # Deployment config (auto-generated by hohu deploy)
│       ├── docker-compose.yml
│       ├── .env
│       ├── nginx/
│       └── ssl/
├── hohu-admin/       # Backend   — FastAPI / uv
├── hohu-admin-web/   # Frontend  — Vue 3 / pnpm
└── hohu-admin-app/   # App       — Uni-app / pnpm
```

## Tech Stack

| Layer | Tool |
|-------|------|
| CLI Framework | [Typer](https://typer.tiangolo.com/) |
| Terminal UI | [Rich](https://rich.readthedocs.io/) + [Questionary](https://questionary.readthedocs.io/) |
| Package Manager | [uv](https://docs.astral.sh/uv/) |
| Deployment | [Docker Compose](https://docs.docker.com/compose/) + [Nginx](https://nginx.org/) |
| Backend | [FastAPI](https://fastapi.tiangolo.com/) |
| Frontend | [Vue 3](https://vuejs.org/) |
| App | [Uni-app](https://uniapp.dcloud.net.cn/) |

## Contributing

Issues and Pull Requests are welcome!

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'Add my-feature'`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

## License

[MIT](LICENSE)
