# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Unofficial Claude Desktop for Linux - A Python-based build automation tool that extracts Claude Desktop from official Windows/macOS installers, compiles a native Linux module (patchy-cnb), patches the application for Linux compatibility, and generates Debian (.deb) and RPM packages.

## Key Commands

### Build Commands
```bash
# Build from Windows installer (default)
claude-desktop-build build

# Build from macOS installer (recommended for Claude Code support)
claude-desktop-build build --source macos

# Enable Claude Code Linux platform detection
claude-desktop-build build --source macos --patch-claude-code-platforms

# Skip dependency checking
claude-desktop-build build --skip-deps

# Force re-download of installer
claude-desktop-build build --force-download
```

### Utility Commands
```bash
claude-desktop-build info [--source windows|macos]   # Show version info
claude-desktop-build download [--source windows|macos] [-o path]  # Download installer only
claude-desktop-build compare [--json]                # Compare Windows vs macOS versions
claude-desktop-build check-update                    # Check for new versions
claude-desktop-build clean                           # Clean build artifacts
```

### Code Quality
```bash
ruff check src/                  # Lint
ruff format src/                 # Format
mypy src/                        # Type check
pre-commit run --all-files       # All pre-commit checks
```

### Development Setup
```bash
pip install -e ".[dev]"          # Install with dev dependencies
pre-commit install               # Setup pre-commit hooks
```

## Architecture

### Python Build System (`src/builder/`)
- **cli.py** - Click CLI entry point (`claude-desktop-build` command)
- **builder.py** - `ClaudeDesktopBuilder` class orchestrates: dependency check → download → extract → patch → package
- **sources.py** - Platform abstraction: `SourceHandler` base class with `WindowsSource` (.exe) and `MacSource` (.dmg) implementations
- **downloader.py** - Downloads with Cloudflare bypass via Playwright
- **config.py** - URLs, directory paths, package dependencies

### Native Module (`src/native/patchy-cnb/`)
- Rust-based native module using NAPI-RS
- Builds to `.node` binary for Linux
- Replaces Windows/macOS native bindings

### Directory Conventions
- **WORK_DIR** (`./build/`) - Temporary build artifacts
- **CACHE_DIR** (`./.cache/downloads/`) - Downloaded installers and metadata
- **OUTPUT_DIR** (`./claude-desktop/`) - Final assembled package structure
- **PACKAGE_DIR** (`./packages/`) - Final .deb packages

## Build Process

1. **Dependency Check** → Verify/install system packages (apt)
2. **Download** → Fetch installer via Playwright (Cloudflare bypass)
3. **Extract Metadata** → Parse version, Electron version
4. **Build Native Module** → Compile patchy-cnb for Linux using npm/Rust
5. **Extract Resources** → Unzip/mount installer
6. **Patch app.asar** → Modify JavaScript for Linux compatibility (title bar, platform detection)
7. **Assemble Package** → Copy files to output structure
8. **Install Electron** → Download and bundle Electron runtime
9. **Create .deb** → Generate Debian package

## Code Style

- Python 3.13+ required
- Strict MyPy type checking enabled
- Ruff formatting: line-length 120, single quotes
- Pre-commit hooks enforce formatting

## System Dependencies

**Debian/Ubuntu (apt):** p7zip-full, nodejs, cargo, rustc, imagemagick, icoutils (Windows source only)

**Additional:** npm/pnpm, Playwright chromium browser
