# Claude Desktop Linux Builder (Python)

A Python-based tool to build Claude Desktop for Linux from the official Windows installer.

## Features

- **Dynamic version detection** - Automatically detects the latest Claude Desktop version
- **Automatic Electron matching** - Extracts and uses the correct Electron version
- **Native module compatibility** - Uses patchy-cnb approach from Nix implementation
- **Proper tray icon support** - Fixes the missing tray icons issue
- **Title bar enablement** - Patches the app to show title bar on Linux
- **Multi-distro support** - Creates .deb (Debian/Ubuntu) or .rpm (Fedora/RHEL) packages

## Requirements

- Python 3.13+
- Node.js 18+ (preferably 22+ as required by Claude)
- System packages (will be auto-installed if missing):
  - p7zip
  - ImageMagick  
  - Rust/Cargo
  - icoutils
  - dpkg-dev (for Debian) or rpm-build (for Fedora)

## Installation

1. Clone this repository with the patchy-cnb submodule:
   ```bash
   git clone https://github.com/your-repo/claude-desktop-linux.git
   cd claude-desktop-linux
   git clone https://github.com/k3d3/claude-desktop-linux-flake.git
   ```

2. Set up Python environment:
   ```bash
   python3.13 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

3. Install pre-commit hooks (for development):
   ```bash
   pip install -e ".[dev]"
   pre-commit install
   ```

## Usage

### Check latest version info
```bash
claude-desktop-build info
```

### Build Claude Desktop
```bash
claude-desktop-build build
```

This will:
1. Download the latest Claude Desktop installer
2. Extract and detect versions automatically
3. Build the native module
4. Apply necessary patches
5. Create a .deb or .rpm package

### Clean build artifacts
```bash
claude-desktop-build clean
```

## How It Works

1. **Downloads** the official Windows installer from Google Cloud Storage
2. **Extracts** version information and Electron requirements from package.json
3. **Builds** a Linux-compatible native module (patchy-cnb)
4. **Patches** the app.asar to:
   - Include tray icons inside the archive
   - Enable title bar on Linux
   - Replace Windows native bindings
5. **Packages** everything as a native Linux package

## Advantages Over Bash Script

- Automatic version detection (no manual updates needed)
- Better error handling and progress reporting
- Modular, maintainable code structure
- Type hints and strict linting
- Proper dependency resolution
- Cross-platform Python vs bash-specific code

## Development

Run linters and formatters:
```bash
ruff check src/
ruff format src/
mypy src/
```

Run tests:
```bash
pytest
```

## License

MIT