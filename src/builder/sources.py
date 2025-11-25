"""Source handlers for extracting Claude Desktop from different platforms."""

import json
import logging
import plistlib
import re
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .config import CACHE_DIR, CLAUDE_URL_MAC, CLAUDE_URL_WINDOWS
from .downloader import download_file, get_latest_version


class SourceHandler(ABC):
    """Abstract base class for platform-specific source handling."""

    def __init__(self) -> None:
        """Initialize the source handler."""
        self.cache_dir = CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        self._metadata: dict[str, Any] | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the source name (e.g., 'windows', 'macos')."""

    @property
    @abstractmethod
    def cache_key(self) -> str:
        """Return the cache key for this source."""

    @property
    @abstractmethod
    def download_url(self) -> str:
        """Return the download URL for this source."""

    @property
    @abstractmethod
    def installer_filename(self) -> str:
        """Return the installer filename."""

    @property
    @abstractmethod
    def required_commands(self) -> list[str]:
        """Return list of required system commands for this source."""

    @abstractmethod
    def extract(self, work_dir: Path) -> Path:
        """Extract the installer and return path to resources directory.

        Args:
            work_dir: Working directory for extraction

        Returns:
            Path to the resources directory containing app.asar

        """

    @abstractmethod
    def extract_metadata(self, resources_dir: Path) -> dict[str, Any]:
        """Extract version metadata from the source.

        Args:
            resources_dir: Path to extracted resources

        Returns:
            Dictionary with version, electron_version, etc.

        """

    @abstractmethod
    def process_icons(self, resources_dir: Path, output_dir: Path) -> None:
        """Process and install application icons.

        Args:
            resources_dir: Path to extracted resources
            output_dir: Output directory for icons

        """

    def get_installer_path(self) -> Path:
        """Get path to cached installer."""
        return self.cache_dir / self.installer_filename

    def has_installer(self) -> bool:
        """Check if installer is cached."""
        return self.get_installer_path().exists()

    def download(self, *, force: bool = False) -> Path:
        """Download the installer.

        Args:
            force: Force re-download even if cached

        Returns:
            Path to downloaded installer

        """
        installer_path = self.get_installer_path()

        if not force and installer_path.exists():
            self.logger.info('Using cached installer: %s', installer_path)
            return installer_path

        self.logger.info('Downloading %s installer...', self.name)
        installer_path, _url = download_file(
            self.download_url,
            installer_path,
            cache_dir=self.cache_dir,
            cache_key=self.cache_key,
        )
        return installer_path

    def get_latest_version(self) -> str | None:
        """Get latest version without downloading."""
        return get_latest_version(self.download_url)

    def post_patch_app(self, app_dir: Path) -> None:
        """Apply source-specific patches to extracted app.

        Override in subclasses for source-specific patches.

        Args:
            app_dir: Path to extracted app directory

        """
        # Default: no additional patches needed
        _ = app_dir

    def post_assemble(self, lib_dir: Path, resources_dir: Path) -> None:
        """Post-assembly tasks for source-specific handling.

        Override in subclasses for source-specific assembly steps.

        Args:
            lib_dir: Path to lib/claude-desktop directory
            resources_dir: Path to original resources directory

        """
        # Default: no additional assembly needed
        _ = lib_dir, resources_dir


class WindowsSource(SourceHandler):
    """Handler for Windows installer source."""

    @property
    def name(self) -> str:
        """Return source name."""
        return 'windows'

    @property
    def cache_key(self) -> str:
        """Return cache key."""
        return 'windows'

    @property
    def download_url(self) -> str:
        """Return download URL."""
        return CLAUDE_URL_WINDOWS

    @property
    def installer_filename(self) -> str:
        """Return installer filename."""
        return 'Claude-Setup-x64.exe'

    @property
    def required_commands(self) -> list[str]:
        """Return required system commands."""
        return ['7z', 'npx', 'cargo', 'convert', 'wrestool', 'icotool']

    def extract(self, work_dir: Path) -> Path:
        """Extract Windows exe -> nupkg -> resources."""
        self.logger.info('Extracting Windows installer...')

        installer_path = self.get_installer_path()
        extract_dir = work_dir / 'extract'
        extract_dir.mkdir(parents=True, exist_ok=True)

        # Extract exe
        subprocess.run(
            ['7z', 'x', '-y', str(installer_path), f'-o{extract_dir}'],
            check=True,
            capture_output=True,
        )

        # Find and extract nupkg
        nupkg_files = list(extract_dir.glob('*.nupkg'))
        if not nupkg_files:
            msg = 'No .nupkg file found in extracted exe'
            raise RuntimeError(msg)

        nupkg_dir = work_dir / 'nupkg'
        subprocess.run(
            ['7z', 'x', '-y', str(nupkg_files[0]), f'-o{nupkg_dir}'],
            check=True,
            capture_output=True,
        )

        resources_dir = nupkg_dir / 'lib' / 'net45' / 'resources'
        if not resources_dir.exists():
            msg = f'Resources directory not found at {resources_dir}'
            raise RuntimeError(msg)

        return resources_dir

    def extract_metadata(self, resources_dir: Path) -> dict[str, Any]:
        """Extract metadata from Windows installer."""
        # Get version from nupkg parent path
        nupkg_dir = resources_dir.parent.parent.parent
        nupkg_files = list(nupkg_dir.parent.glob('*.nupkg'))

        version = 'unknown'
        if nupkg_files:
            match = re.match(r'AnthropicClaude-(.+)-full\.nupkg', nupkg_files[0].name)
            if match:
                version = match.group(1)

        # Extract app.asar to get package.json
        app_asar = resources_dir / 'app.asar'
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                ['npx', 'asar', 'extract', str(app_asar), f'{tmpdir}/app'],
                check=True,
                capture_output=True,
            )

            package_json_path = Path(tmpdir) / 'app' / 'package.json'
            package_data: dict[str, Any] = json.loads(package_json_path.read_text())

            electron_version = package_data.get('devDependencies', {}).get('electron')
            if not electron_version:
                msg = 'Electron version not found in package.json'
                raise RuntimeError(msg)

            return {
                'version': version,
                'electron_version': electron_version,
                'node_requirement': package_data.get('engines', {}).get('node'),
                'app_name': package_data.get('productName', 'Claude'),
                'source': self.name,
            }

    def process_icons(self, resources_dir: Path, output_dir: Path) -> None:
        """Extract icons from Windows exe using wrestool/icotool."""
        self.logger.info('Processing icons from Windows exe...')

        exe_path = resources_dir.parent / 'claude.exe'
        icon_work_dir = output_dir.parent.parent.parent / 'work' / 'icons'
        icon_work_dir.mkdir(parents=True, exist_ok=True)

        # Extract icon from exe
        subprocess.run(
            ['wrestool', '-x', '-t', '14', str(exe_path), '-o', str(icon_work_dir / 'claude.ico')],
            check=True,
        )

        # Convert to PNG
        subprocess.run(
            ['icotool', '-x', str(icon_work_dir / 'claude.ico')],
            cwd=icon_work_dir,
            check=True,
        )

        # Create icon directories for different sizes
        for size in [16, 24, 32, 48, 64, 128, 256]:
            size_dir = output_dir / 'share' / 'icons' / 'hicolor' / f'{size}x{size}' / 'apps'
            size_dir.mkdir(parents=True, exist_ok=True)

            # Find and copy the appropriate icon
            icon_files = list(icon_work_dir.glob(f'*_{size}x{size}x*.png'))
            if icon_files:
                shutil.copy2(icon_files[0], size_dir / 'claude-desktop.png')


class MacSource(SourceHandler):
    """Handler for Mac DMG source."""

    # Swift addon stub for Linux
    SWIFT_STUB_INDEX = """const EventEmitter = require("events");

class SwiftAddonStub extends EventEmitter {
  constructor() { super(); }
  helloWorldClaudeSwift(input = "") { return ""; }
  toggleOverlayVisible() {}
  showOverlay() {}
  hideOverlay() {}
  showDictation(mode) {}
  toggleDictation(mode) {}
  hideDictationAndPotentiallySubmit() {}
  setRecentChats(chats) {}
  setActiveChatId(chatId) {}
  setLoggedIn(loggedIn) {}
  setDictationInfo(baseURL, cookieHeader, languageCode) {}
  getOpenDocuments() { return []; }
  getOpenWindows() { return []; }
  captureWindowScreenshot(windowId) { return Promise.resolve(null); }
}

module.exports = new SwiftAddonStub();
"""

    SWIFT_STUB_PACKAGE = """{
  "name": "@ant/claude-swift",
  "version": "1.0.0",
  "description": "Linux stub for macOS Swift addon",
  "main": "index.js",
  "private": true
}
"""

    @property
    def name(self) -> str:
        """Return source name."""
        return 'macos'

    @property
    def cache_key(self) -> str:
        """Return cache key."""
        return 'mac'

    @property
    def download_url(self) -> str:
        """Return download URL."""
        return CLAUDE_URL_MAC

    @property
    def installer_filename(self) -> str:
        """Return installer filename."""
        return 'Claude.dmg'

    @property
    def required_commands(self) -> list[str]:
        """Return required system commands."""
        # icns2png from icnsutils package for .icns conversion
        return ['7z', 'npx', 'cargo', 'convert', 'icns2png']

    def extract(self, work_dir: Path) -> Path:
        """Extract Mac DMG -> Claude.app/Contents/Resources."""
        self.logger.info('Extracting Mac DMG...')

        installer_path = self.get_installer_path()
        extract_dir = work_dir / 'dmg-extract'
        extract_dir.mkdir(parents=True, exist_ok=True)

        # 7z can extract DMG (may return error code 2 for HFS+ warnings)
        result = subprocess.run(
            ['7z', 'x', '-y', str(installer_path), f'-o{extract_dir}'],
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            self.logger.debug('7z stderr: %s', result.stderr)

        # Find Claude.app/Contents/Resources
        app_contents = self._find_app_contents(extract_dir)
        resources_dir = app_contents / 'Resources'

        if not resources_dir.exists():
            msg = f'Resources directory not found at {resources_dir}'
            raise RuntimeError(msg)

        # Store app_contents for later use (icons, etc.)
        self._app_contents = app_contents

        return resources_dir

    def _find_app_contents(self, extract_dir: Path) -> Path:
        """Find Claude.app/Contents in extracted DMG."""
        # Try common location first
        app_path = extract_dir / 'Claude' / 'Claude.app' / 'Contents'
        if app_path.exists():
            return app_path

        # Search for it
        for candidate in extract_dir.rglob('Claude.app'):
            contents = candidate / 'Contents'
            if contents.exists():
                return contents

        msg = f'Claude.app/Contents not found in {extract_dir}'
        raise RuntimeError(msg)

    def extract_metadata(self, resources_dir: Path) -> dict[str, Any]:
        """Extract metadata from Mac DMG."""
        app_contents = resources_dir.parent

        # Read Info.plist for version
        info_plist_path = app_contents / 'Info.plist'
        with info_plist_path.open('rb') as f:
            info_plist = plistlib.load(f)

        version = info_plist.get(
            'CFBundleShortVersionString',
            info_plist.get('CFBundleVersion', 'unknown'),
        )

        # Get Electron version from framework
        electron_plist_path = (
            app_contents / 'Frameworks' / 'Electron Framework.framework'
            / 'Versions' / 'A' / 'Resources' / 'Info.plist'
        )
        electron_version = None
        if electron_plist_path.exists():
            with electron_plist_path.open('rb') as f:
                electron_plist = plistlib.load(f)
                electron_version = electron_plist.get('CFBundleVersion')

        # Fallback: get from package.json
        if not electron_version:
            app_asar = resources_dir / 'app.asar'
            with tempfile.TemporaryDirectory() as tmpdir:
                subprocess.run(
                    ['npx', 'asar', 'extract', str(app_asar), f'{tmpdir}/app'],
                    check=True,
                    capture_output=True,
                )
                package_json_path = Path(tmpdir) / 'app' / 'package.json'
                package_data: dict[str, Any] = json.loads(package_json_path.read_text())
                electron_version = package_data.get('devDependencies', {}).get('electron')

        if not electron_version:
            msg = 'Could not determine Electron version'
            raise RuntimeError(msg)

        return {
            'version': version,
            'electron_version': electron_version,
            'app_name': info_plist.get('CFBundleDisplayName', 'Claude'),
            'bundle_id': info_plist.get('CFBundleIdentifier', 'com.anthropic.claudefordesktop'),
            'source': self.name,
        }

    def process_icons(self, resources_dir: Path, output_dir: Path) -> None:
        """Process icons from Mac .icns file."""
        self.logger.info('Processing icons from Mac icns...')

        icns_file = resources_dir / 'electron.icns'
        if not icns_file.exists():
            self.logger.warning('electron.icns not found, skipping icon processing')
            return

        icon_work_dir = output_dir.parent.parent.parent / 'work' / 'icons'
        icon_work_dir.mkdir(parents=True, exist_ok=True)

        # Convert .icns to PNG using icns2png (icnsutils package)
        try:
            subprocess.run(
                ['icns2png', '-x', '-o', str(icon_work_dir), str(icns_file)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            self.logger.warning('Failed to convert icns: %s', e.stderr)
            return

        # Find the largest extracted icon to use as source
        extracted_icons = sorted(icon_work_dir.glob('*.png'), key=lambda p: p.stat().st_size, reverse=True)
        if not extracted_icons:
            self.logger.warning('No icons extracted from icns')
            return

        source_icon = extracted_icons[0]

        # Create icon directories for different sizes
        for size in [16, 24, 32, 48, 64, 128, 256, 512]:
            size_dir = output_dir / 'share' / 'icons' / 'hicolor' / f'{size}x{size}' / 'apps'
            size_dir.mkdir(parents=True, exist_ok=True)

            output_icon = size_dir / 'claude-desktop.png'
            subprocess.run(
                ['convert', str(source_icon), '-resize', f'{size}x{size}', str(output_icon)],
                check=True,
                capture_output=True,
            )

    def post_patch_app(self, app_dir: Path) -> None:
        """Create Swift stub for Linux."""
        self.logger.info('Creating Swift addon stub...')

        swift_dir = app_dir / 'node_modules' / '@ant' / 'claude-swift'
        if swift_dir.exists():
            shutil.rmtree(swift_dir)

        swift_dir.mkdir(parents=True, exist_ok=True)
        (swift_dir / 'index.js').write_text(self.SWIFT_STUB_INDEX)
        (swift_dir / 'package.json').write_text(self.SWIFT_STUB_PACKAGE)

        # Also handle js/ subdirectory
        js_dir = swift_dir / 'js'
        js_dir.mkdir(exist_ok=True)
        (js_dir / 'index.js').write_text(self.SWIFT_STUB_INDEX)

    def post_assemble(self, lib_dir: Path, resources_dir: Path) -> None:  # noqa: ARG002
        """Handle Mac-specific post-assembly (node-pty, swift removal)."""
        unpacked_dst = lib_dir / 'app.asar.unpacked'

        if not unpacked_dst.exists():
            return

        # Remove Mac Swift addon from unpacked
        swift_dst = unpacked_dst / 'node_modules' / '@ant' / 'claude-swift'
        if swift_dst.exists():
            shutil.rmtree(swift_dst)

        # Remove Mac node-pty (will be installed as Linux version)
        pty_dst = unpacked_dst / 'node_modules' / 'node-pty'
        if pty_dst.exists():
            shutil.rmtree(pty_dst)

    def get_extra_npm_dependencies(self) -> dict[str, str]:
        """Return extra npm dependencies needed for Mac source."""
        return {'node-pty': '^1.0.0'}


def get_source_handler(source: str) -> SourceHandler:
    """Get the appropriate source handler.

    Args:
        source: Source name ('windows' or 'macos')

    Returns:
        SourceHandler instance

    """
    handlers = {
        'windows': WindowsSource,
        'macos': MacSource,
    }

    if source not in handlers:
        msg = f"Unknown source: {source}. Available: {', '.join(handlers.keys())}"
        raise ValueError(msg)

    return handlers[source]()
