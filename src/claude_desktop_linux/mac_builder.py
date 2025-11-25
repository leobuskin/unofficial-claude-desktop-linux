"""Mac-based builder for Claude Desktop Linux.

This module builds Claude Desktop for Linux using the Mac DMG as the source,
which typically has a newer version than the Windows installer.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .config import (
    DEBIAN_PACKAGES,
    DNF_PACKAGES,
    OUTPUT_DIR,
    PACKAGE_DIR,
    WORK_DIR,
)
from .mac_detector import MacDmgDetector

# Swift addon stub for Linux - provides no-op implementations of macOS-only features
SWIFT_ADDON_STUB = """const EventEmitter = require("events");

/**
 * Stub implementation of @ant/claude-swift for Linux.
 *
 * The real module provides macOS-specific features:
 * - Quick Entry overlay (floating panel for quick Claude access)
 * - Option key double-tap shortcut
 * - Voice dictation integration
 * - Window/document listing via Accessibility APIs
 * - Window screenshot capture
 *
 * On Linux, these features are not available, so we provide no-op stubs.
 */
class SwiftAddonStub extends EventEmitter {
  constructor() {
    super();
    // No native addon to initialize on Linux
  }

  // Test function
  helloWorldClaudeSwift(input = "") {
    return "";
  }

  // Quick Entry Overlay UI methods - no-ops on Linux
  toggleOverlayVisible() {}
  showOverlay() {}
  hideOverlay() {}

  // Dictation methods - no-ops on Linux
  showDictation(mode) {}
  toggleDictation(mode) {}
  hideDictationAndPotentiallySubmit() {}

  // State setters for overlay - no-ops on Linux
  setRecentChats(chats) {}
  setActiveChatId(chatId) {}
  setLoggedIn(loggedIn) {}
  setDictationInfo(baseURL, cookieHeader, languageCode) {}

  // Accessibility API methods - return empty on Linux
  getOpenDocuments() {
    return [];
  }

  getOpenWindows() {
    return [];
  }

  // Screenshot capture - returns null on Linux
  captureWindowScreenshot(windowId) {
    return Promise.resolve(null);
  }
}

// Export singleton instance (matches Mac behavior)
module.exports = new SwiftAddonStub();
"""

SWIFT_ADDON_PACKAGE_JSON = """{
  "name": "@ant/claude-swift",
  "version": "1.0.0",
  "description": "Linux stub for macOS Swift addon",
  "main": "index.js",
  "private": true
}
"""


class MacClaudeDesktopBuilder:
    """Builds Claude Desktop for Linux from Mac DMG."""

    def __init__(self, dmg_path: Path | None = None) -> None:
        """Initialize the builder.

        Args:
            dmg_path: Optional path to DMG file

        """
        self.detector = MacDmgDetector(dmg_path)
        self.work_dir = WORK_DIR
        self.output_dir = OUTPUT_DIR
        self.package_dir = PACKAGE_DIR
        self._metadata: dict[str, Any] | None = None
        self.logger = logging.getLogger(__name__)

    def detect_package_manager(self) -> tuple[str, list[str]]:
        """Detect the system package manager and required packages."""
        if shutil.which('dnf'):
            return 'dnf', DNF_PACKAGES
        if shutil.which('apt'):
            return 'apt', DEBIAN_PACKAGES
        msg = 'No supported package manager found (dnf or apt)'
        raise RuntimeError(msg)

    def check_dependencies(self) -> None:
        """Check and install required system dependencies."""
        pkg_manager, packages = self.detect_package_manager()

        # Check if all required commands exist
        # Note: No need for wrestool/icotool since we use icns files from Mac
        required_commands = ['7z', 'npx', 'cargo', 'convert']
        missing = [cmd for cmd in required_commands if not shutil.which(cmd)]

        if missing:
            self.logger.warning('Missing required commands: %s', ', '.join(missing))
            self.logger.info('Installing dependencies using %s...', pkg_manager)

            if pkg_manager == 'dnf':
                subprocess.run(['sudo', 'dnf', 'install', '-y', *packages], check=True)
            else:
                subprocess.run(['sudo', 'apt', 'update'], check=True)
                subprocess.run(['sudo', 'apt', 'install', '-y', *packages], check=True)

        # Install pnpm if not available
        if not shutil.which('pnpm'):
            self.logger.info('Installing pnpm...')
            subprocess.run(['npm', 'install', '-g', 'pnpm'], check=True)

    @property
    def metadata(self) -> dict[str, Any]:
        """Get metadata, raising error if not loaded."""
        if self._metadata is None:
            msg = 'Metadata not loaded. Call detector.get_version_info() first.'
            raise RuntimeError(msg)
        return self._metadata

    def extract_dmg(self) -> Path:
        """Extract the Mac DMG to work directory.

        Returns:
            Path to Claude.app/Contents directory

        """
        self.logger.info('Extracting Mac DMG...')

        extract_dir = self.work_dir / 'dmg-extract'
        extract_dir.mkdir(parents=True, exist_ok=True)

        if self.detector.dmg_path is None:
            msg = 'No DMG file available for extraction'
            raise RuntimeError(msg)

        return self.detector.extract_dmg(self.detector.dmg_path, extract_dir)

    def build_native_module(self) -> Path:
        """Build the native module (patchy-cnb style).

        Returns:
            Path to the built .node file

        """
        self.logger.info('Building native module...')

        native_dir = self.work_dir / 'native-module'
        native_dir.mkdir(parents=True, exist_ok=True)

        # Copy patchy-cnb source from submodule
        patchy_src = Path('claude-desktop-linux-flake/patchy-cnb')
        if patchy_src.exists():
            shutil.copytree(patchy_src, native_dir, dirs_exist_ok=True)
        else:
            msg = (
                'patchy-cnb not found. Please ensure the claude-desktop-linux-flake '
                'submodule is initialized: git submodule update --init'
            )
            raise RuntimeError(msg)

        # Build the module
        original_dir = Path.cwd()
        os.chdir(native_dir)

        try:
            package_json_path = native_dir / 'package.json'
            if package_json_path.exists():
                self.logger.info('Building patchy-cnb with npm...')
                subprocess.run(['npm', 'install'], check=True, cwd=native_dir)
                subprocess.run(['npm', 'run', 'build'], check=True, cwd=native_dir)
            else:
                msg = 'No package.json found in native module directory'
                raise RuntimeError(msg)
        finally:
            os.chdir(original_dir)

        # Find the built module
        built_modules = list(native_dir.glob('*.node'))
        if not built_modules:
            msg = 'No .node file found after build'
            raise RuntimeError(msg)

        return built_modules[0]

    def process_icons(self, app_contents: Path) -> None:
        """Extract and process application icons from Mac .icns file.

        Args:
            app_contents: Path to Claude.app/Contents

        """
        self.logger.info('Processing icons...')

        resources_dir = app_contents / 'Resources'
        icns_file = resources_dir / 'electron.icns'

        if not icns_file.exists():
            self.logger.warning('electron.icns not found, skipping icon processing')
            return

        icon_work_dir = self.work_dir / 'icons'
        icon_work_dir.mkdir(parents=True, exist_ok=True)

        # Convert .icns to PNG files using ImageMagick
        # icns files contain multiple sizes, ImageMagick extracts them
        try:
            subprocess.run(
                ['convert', str(icns_file), str(icon_work_dir / 'claude.png')],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            # Try using iconutil if available (macOS) or sips
            self.logger.warning('ImageMagick convert failed, trying alternate method')
            # Just copy the icns and we'll handle it later
            shutil.copy2(icns_file, icon_work_dir / 'claude.icns')
            return

        # Create icon directories for different sizes
        for size in [16, 24, 32, 48, 64, 128, 256, 512]:
            size_dir = self.output_dir / 'share' / 'icons' / 'hicolor' / f'{size}x{size}' / 'apps'
            size_dir.mkdir(parents=True, exist_ok=True)

            # Look for extracted icon of this size
            # ImageMagick names them claude-0.png, claude-1.png, etc.
            icon_files = list(icon_work_dir.glob('claude-*.png')) + list(icon_work_dir.glob('claude.png'))

            if icon_files:
                # Resize to exact size needed
                output_icon = size_dir / 'claude-desktop.png'
                subprocess.run(
                    ['convert', str(icon_files[0]), '-resize', f'{size}x{size}', str(output_icon)],
                    check=True,
                    capture_output=True,
                )

    def create_swift_stub(self, app_dir: Path) -> None:
        """Create stub implementation for @ant/claude-swift.

        Args:
            app_dir: Path to extracted app directory

        """
        self.logger.info('Creating Swift addon stub for Linux...')

        swift_module_dir = app_dir / 'node_modules' / '@ant' / 'claude-swift'

        # Remove existing swift module contents (but keep directory)
        if swift_module_dir.exists():
            shutil.rmtree(swift_module_dir)

        swift_module_dir.mkdir(parents=True, exist_ok=True)

        # Write stub index.js
        (swift_module_dir / 'index.js').write_text(SWIFT_ADDON_STUB)

        # Write package.json
        (swift_module_dir / 'package.json').write_text(SWIFT_ADDON_PACKAGE_JSON)

        # Also handle the js/ subdirectory structure if it exists in app.asar
        js_dir = swift_module_dir / 'js'
        js_dir.mkdir(exist_ok=True)
        (js_dir / 'index.js').write_text(SWIFT_ADDON_STUB)

    def patch_app_asar(self, app_contents: Path, native_module: Path) -> Path:
        """Patch app.asar with native module and stubs.

        Args:
            app_contents: Path to Claude.app/Contents
            native_module: Path to built Linux native module

        Returns:
            Path to patched app.asar

        """
        self.logger.info('Patching app.asar...')

        resources_dir = app_contents / 'Resources'
        app_asar = resources_dir / 'app.asar'

        with tempfile.TemporaryDirectory() as tmpdir:
            app_extract = Path(tmpdir) / 'app'

            # Extract app.asar
            subprocess.run(
                ['npx', 'asar', 'extract', str(app_asar), str(app_extract)],
                check=True,
            )

            # Replace native module
            native_module_dir = app_extract / 'node_modules' / '@ant' / 'claude-native'
            native_module_dir.mkdir(parents=True, exist_ok=True)

            # Copy our Linux native module
            shutil.copy2(
                native_module,
                native_module_dir / 'claude-native-binding.node',
            )

            # Create Swift stub
            self.create_swift_stub(app_extract)

            # Copy tray icons into app resources (Nix approach)
            app_resources = app_extract / 'resources'
            app_resources.mkdir(exist_ok=True)

            for tray_file in resources_dir.glob('Tray*'):
                shutil.copy2(tray_file, app_resources)

            # Copy i18n files
            i18n_dir = app_resources / 'i18n'
            i18n_dir.mkdir(exist_ok=True)
            for json_file in resources_dir.glob('*.json'):
                if json_file.name not in ['build-props.json']:
                    shutil.copy2(json_file, i18n_dir)

            # Apply title bar patch
            self._patch_title_bar(app_extract)

            # Repack app.asar
            new_asar = self.work_dir / 'app.asar'
            subprocess.run(
                ['npx', 'asar', 'pack', str(app_extract), str(new_asar)],
                check=True,
            )

        return new_asar

    def _patch_title_bar(self, app_dir: Path) -> None:
        """Apply title bar patch to enable it on Linux.

        Args:
            app_dir: Path to extracted app directory

        """
        self.logger.info('Applying title bar patch...')

        # Find MainWindowPage-*.js file
        search_base = app_dir / '.vite' / 'renderer' / 'main_window' / 'assets'
        if not search_base.exists():
            self.logger.warning('Could not find assets directory for title bar patch')
            return

        main_window_files = list(search_base.glob('MainWindowPage-*.js'))
        if len(main_window_files) != 1:
            self.logger.warning('Expected 1 MainWindowPage file, found %d', len(main_window_files))
            return

        target_file = main_window_files[0]
        content = target_file.read_text()

        # Apply the patch: change if(!isWindows && isMainWindow) to if(isWindows && isMainWindow)
        # This enables the title bar on Linux
        pattern = r'if\(!(\w+)\s*&&\s*(\w+)\)'
        replacement = r'if(\1 && \2)'

        new_content = re.sub(pattern, replacement, content)

        if new_content != content:
            target_file.write_text(new_content)
            self.logger.info('Title bar patch applied successfully')
        else:
            self.logger.warning('Title bar patch pattern not found')

    def create_desktop_file(self) -> Path:
        """Create .desktop file for Linux desktop integration.

        Returns:
            Path to created desktop file

        """
        desktop_content = """[Desktop Entry]
Name=Claude
Comment=Desktop application for Claude.ai
Exec=claude-desktop %u
Icon=claude-desktop
Type=Application
Categories=Office;Utility;
Terminal=false
MimeTypes=x-scheme-handler/claude;
"""

        desktop_file = self.work_dir / 'claude-desktop.desktop'
        desktop_file.write_text(desktop_content)
        return desktop_file

    def create_launcher_script(self) -> Path:
        """Create launcher script.

        Returns:
            Path to created launcher script

        """
        launcher_content = """#!/bin/bash
APP_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"

# Launch with Wayland support if available
exec "$APP_DIR/lib/claude-desktop/node_modules/electron/dist/electron" \\
    "$APP_DIR/lib/claude-desktop/app.asar" \\
    ${WAYLAND_DISPLAY:+--ozone-platform-hint=auto --enable-features=WaylandWindowDecorations} \\
    "$@"
"""

        launcher_file = self.work_dir / 'claude-desktop'
        launcher_file.write_text(launcher_content.replace('\r\n', '\n'))
        launcher_file.chmod(0o755)
        return launcher_file

    def assemble_package(self, app_contents: Path, app_asar: Path) -> None:
        """Assemble the final package structure.

        Args:
            app_contents: Path to Claude.app/Contents
            app_asar: Path to patched app.asar

        """
        self.logger.info('Assembling package...')

        # Clear and create output directory
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)

        lib_dir = self.output_dir / 'lib' / 'claude-desktop'
        lib_dir.mkdir(parents=True, exist_ok=True)

        # Copy app.asar
        shutil.copy2(app_asar, lib_dir / 'app.asar')

        # Copy unpacked native modules
        unpacked_src = app_contents / 'Resources' / 'app.asar.unpacked'
        if unpacked_src.exists():
            unpacked_dst = lib_dir / 'app.asar.unpacked'
            shutil.copytree(unpacked_src, unpacked_dst)

            # Replace Mac native modules with our Linux ones
            native_dst = unpacked_dst / 'node_modules' / '@ant' / 'claude-native'
            if native_dst.exists():
                # Copy our built Linux native module
                native_src = self.work_dir / 'native-module'
                built_modules = list(native_src.glob('*.node'))
                if built_modules:
                    shutil.copy2(
                        built_modules[0],
                        native_dst / 'claude-native-binding.node',
                    )

            # Remove Mac Swift addon (we stub it in app.asar)
            swift_dst = unpacked_dst / 'node_modules' / '@ant' / 'claude-swift'
            if swift_dst.exists():
                shutil.rmtree(swift_dst)

            # Handle node-pty - needs Linux version
            pty_dst = unpacked_dst / 'node_modules' / 'node-pty'
            if pty_dst.exists():
                # Remove Mac binary, we'll install Linux version
                shutil.rmtree(pty_dst)

        # Copy desktop file
        desktop_dir = self.output_dir / 'share' / 'applications'
        desktop_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.create_desktop_file(), desktop_dir / 'claude-desktop.desktop')

        # Copy launcher
        bin_dir = self.output_dir / 'bin'
        bin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.create_launcher_script(), bin_dir / 'claude-desktop')

        # Install Electron
        self.logger.info('Installing Electron %s...', self.metadata['electron_version'])

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            package_json = {
                'name': 'claude-desktop-electron',
                'version': '1.0.0',
                'private': True,
                'dependencies': {
                    'electron': self.metadata['electron_version'],
                    'node-pty': '^1.0.0',  # Install Linux node-pty
                },
            }
            (tmp_path / 'package.json').write_text(json.dumps(package_json, indent=2))

            # Install in temp directory
            subprocess.run(['npm', 'install', '--production'], cwd=tmp_path, check=True)

            # Copy to the package
            electron_src = tmp_path / 'node_modules'
            electron_dst = lib_dir / 'node_modules'
            shutil.copytree(electron_src, electron_dst, dirs_exist_ok=True)

    def build_deb_package(self) -> Path:
        """Build Debian package.

        Returns:
            Path to built .deb file

        """
        self.logger.info('Building .deb package...')

        pkg_name = f'claude-desktop_{self.metadata["version"]}_amd64'
        pkg_root = self.package_dir / pkg_name

        # Create package structure
        if pkg_root.exists():
            shutil.rmtree(pkg_root)

        # Copy files
        shutil.copytree(self.output_dir, pkg_root / 'usr')

        # Create DEBIAN directory
        debian_dir = pkg_root / 'DEBIAN'
        debian_dir.mkdir(parents=True, exist_ok=True)

        # Create control file
        control_content = f"""Package: claude-desktop
Version: {self.metadata['version']}
Architecture: amd64
Maintainer: Claude Desktop Linux Contributors
Description: Desktop application for Claude.ai (from Mac source)
 Claude Desktop is the official desktop application for Claude.ai,
 repackaged for Linux systems from the Mac DMG with Electron bundled.
"""
        (debian_dir / 'control').write_text(control_content)

        # Build package
        subprocess.run(['dpkg-deb', '--build', str(pkg_root)], check=True)

        return self.package_dir / f'{pkg_name}.deb'

    def build(self, *, download: bool = True) -> None:
        """Run the complete build process.

        Args:
            download: If True, download DMG if not found locally

        """
        self.logger.info('Starting Claude Desktop Linux build from Mac DMG...')

        if not self.detector.has_dmg():
            if download:
                self.logger.info('DMG not found locally, downloading...')
                self.detector.download_dmg()
            else:
                msg = (
                    'No DMG file found. Run with download enabled to fetch it automatically,\n'
                    'or use --dmg option to specify a DMG file path.'
                )
                raise RuntimeError(msg)

        # Get version info
        self._metadata = self.detector.get_version_info()
        self.logger.info(
            'Building Claude Desktop %s (from Mac) with Electron %s',
            self.metadata['version'],
            self.metadata['electron_version'],
        )

        # Check dependencies
        self.check_dependencies()

        # Clean work directory
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Extract DMG
        app_contents = self.extract_dmg()

        # Build native module
        native_module = self.build_native_module()

        # Process icons
        self.process_icons(app_contents)

        # Patch app.asar
        app_asar = self.patch_app_asar(app_contents, native_module)

        # Assemble package
        self.assemble_package(app_contents, app_asar)

        # Build packages
        self.package_dir.mkdir(parents=True, exist_ok=True)

        pkg_manager, _ = self.detect_package_manager()
        if pkg_manager == 'apt':
            package = self.build_deb_package()
            self.logger.info('Built Debian package: %s', package)
        else:
            # RPM building from Mac source is not yet implemented
            self.logger.warning('RPM building from Mac source not yet implemented')
            package = None

        if package:
            self.logger.info('Build complete! Install with:')
            self.logger.info('  sudo dpkg -i %s', package)
