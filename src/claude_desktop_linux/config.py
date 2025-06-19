"""Configuration for Claude Desktop Linux builder."""

from pathlib import Path

# Claude Desktop download URL (version-agnostic)
CLAUDE_URL = 'https://storage.googleapis.com/osprey-downloads-c02f6a0d-347c-492b-a752-3e0651722e97/nest-win-x64/Claude-Setup-x64.exe'

# Directory structure
WORK_DIR = Path.cwd() / 'build'
CACHE_DIR = Path.cwd() / '.cache' / 'downloads'
OUTPUT_DIR = Path.cwd() / 'claude-desktop'
PACKAGE_DIR = Path.cwd() / 'packages'

# Package dependencies
DNF_PACKAGES = ['p7zip', 'p7zip-plugins', 'nodejs', 'rust', 'cargo', 'ImageMagick', 'icoutils']
DEBIAN_PACKAGES = ['p7zip-full', 'nodejs', 'cargo', 'rustc', 'imagemagick', 'icoutils', 'dpkg-dev']

# Native module name (using Nix's approach)
NATIVE_MODULE_NAME = 'patchy-cnb'
