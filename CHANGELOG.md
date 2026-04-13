# Changelog

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
