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
- **Smart Init** — Auto-detects and installs dependencies (`uv sync` / `pnpm install`)
- **Context-Aware** — Run commands from any subdirectory via `.hohu` project config
- **i18n** — Full Chinese & English support with automatic system language detection
- **Polished UX** — Rich-formatted output with interactive prompts via Questionary

## Quick Start

### Install

```bash
# uv (recommended)
uv tool install hohu

# pip
pip install hohu
```

### Create a Project

```bash
hohu admin create my-project
```

Select components (Backend / Frontend / App) interactively. Defaults to `hohu-admin` if no name is given.

### Install Dependencies

```bash
cd my-project
hohu admin init
```

Automatically detects project config and installs all dependencies.

### Switch Language

```bash
hohu lang
```

## Development Server

`hohu admin dev` launches all services in a single terminal with merged, color-coded log output.

```bash
hohu admin dev          # Start all components
hohu admin dev -o be    # Backend only
hohu admin dev -s app   # Frontend + Backend, skip App
hohu admin dev -t mp    # App in WeChat Mini Program mode
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

## Command Reference

| Command | Description |
|---------|-------------|
| `hohu admin create [NAME]` | Create project and clone repo templates |
| `hohu admin init` | Install all sub-project dependencies |
| `hohu admin dev` | Start development server |
| `hohu lang` | Switch display language (zh / en / auto) |
| `hohu info` | View current CLI configuration |
| `hohu --version` | Show version |
| `hohu --help` | Show help |

## Project Structure

```
my-project/
├── .hohu/            # Project config
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
