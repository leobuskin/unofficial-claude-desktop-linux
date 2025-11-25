"""Configuration for Claude Desktop Linux builder."""

from pathlib import Path

# Claude Desktop download URLs (redirect to latest version)
# These URLs require Cloudflare bypass - handled by downloader.py using playwright
# Windows installer
CLAUDE_URL_WINDOWS = 'https://claude.ai/redirect/claudedotcom.v1.290130bf-1c36-4eb0-9a93-2410ca43ae53/api/desktop/win32/x64/exe/latest/redirect'
# Mac DMG (universal binary)
CLAUDE_URL_MAC = 'https://claude.ai/redirect/claudedotcom.v1.290130bf-1c36-4eb0-9a93-2410ca43ae53/api/desktop/darwin/universal/dmg/latest/redirect'

# Directory structure
WORK_DIR = Path.cwd() / 'build'
CACHE_DIR = Path.cwd() / '.cache' / 'downloads'
OUTPUT_DIR = Path.cwd() / 'claude-desktop'
PACKAGE_DIR = Path.cwd() / 'packages'

# Package dependencies
# For Windows source: needs icoutils for icon extraction
DNF_PACKAGES = ['p7zip', 'p7zip-plugins', 'nodejs', 'rust', 'cargo', 'ImageMagick', 'icoutils']
DEBIAN_PACKAGES = ['p7zip-full', 'nodejs', 'cargo', 'rustc', 'imagemagick', 'icoutils']

# For Mac source: no icoutils needed (uses .icns files)
DNF_PACKAGES_MAC = ['p7zip', 'p7zip-plugins', 'nodejs', 'rust', 'cargo', 'ImageMagick']
DEBIAN_PACKAGES_MAC = ['p7zip-full', 'nodejs', 'cargo', 'rustc', 'imagemagick']

# Native module name (using Nix's approach)
NATIVE_MODULE_NAME = 'patchy-cnb'

# Build source options
SOURCE_WINDOWS = 'windows'
SOURCE_MAC = 'mac'
