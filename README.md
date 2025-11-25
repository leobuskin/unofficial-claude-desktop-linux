# Claude Desktop for Linux

[![Auto Build](https://github.com/leobuskin/claude-desktop-linux/actions/workflows/auto-build.yml/badge.svg)](https://github.com/leobuskin/claude-desktop-linux/actions/workflows/auto-build.yml)
[![Latest Release](https://img.shields.io/github/v/release/leobuskin/claude-desktop-linux)](https://github.com/leobuskin/claude-desktop-linux/releases/latest)

Automated Linux packages for Claude Desktop, built from the official Windows installer. This project provides a maintenance-free way to install and update Claude Desktop on Debian/Ubuntu systems.

## 🚀 Features

- **Automatic Updates**: Daily checks for new Claude Desktop releases
- **Zero Maintenance**: Fully automated build and distribution
- **Transparency**: All builds happen in public GitHub Actions
- **Version History**: All releases preserved with ability to rollback

## 📦 Installation

### Direct Download (Recommended)

Download the latest .deb package from the [releases page](https://github.com/leobuskin/claude-desktop-linux/releases/latest):

```bash
# Download and install
wget https://github.com/leobuskin/claude-desktop-linux/releases/latest/download/claude-desktop_VERSION_amd64.deb
sudo dpkg -i claude-desktop_*.deb
```

## 🔄 Updates

To get notified of new releases:
1. Click "Watch" → "Custom" → "Releases" on this repository
2. Check the [releases page](https://github.com/leobuskin/claude-desktop-linux/releases) regularly
3. Download and install new versions when available

## 🏗️ How It Works

1. **Daily Automation**: GitHub Actions runs every day at midnight UTC
2. **Version Detection**: Checks the official Claude Desktop Windows installer for new versions
3. **Automatic Building**: If a new version is found, builds Linux packages automatically
4. **Distribution**: Creates a GitHub release with built packages

## 🛠️ Building from Source

If you want to build packages manually:

```bash
# Clone the repository
git clone --recursive https://github.com/leobuskin/claude-desktop-linux.git
cd claude-desktop-linux

# Install dependencies
pip install -e .

# Build packages
claude-desktop-build build
```

## 📋 System Requirements

- **OS**: Debian/Ubuntu (amd64)
- **Dependencies**: Automatically handled by the package manager

## 🔍 Verification

All packages are built using GitHub Actions for transparency. You can verify any build by:
1. Checking the [GitHub Actions history](https://github.com/leobuskin/claude-desktop-linux/actions)
2. Comparing package checksums with release notes
3. Building from source and comparing results

## 🐛 Troubleshooting

### Tray Icon Issues
If the tray icon doesn't appear, make sure you have a system tray extension installed:
- GNOME: [AppIndicator extension](https://extensions.gnome.org/extension/615/appindicator-support/)
- KDE: Built-in support

### Wayland Support
The package automatically detects and enables Wayland support when available.

## 🤝 Contributing

Contributions are welcome! The build process is fully automated, so contributions should focus on:
- Improving the build scripts
- Adding support for more distributions
- Enhancing error handling
- Documentation improvements

## 📄 License

This project is licensed under the MIT License. Claude Desktop itself is proprietary software by Anthropic.

## 🔗 Links

- [Official Claude Desktop](https://claude.ai/download)
- [Anthropic](https://www.anthropic.com/)
- [Original Nix implementation](https://github.com/k3d3/claude-desktop-linux-flake)

---

*This project is not affiliated with Anthropic. It simply repackages the official Claude Desktop application for Linux systems.*