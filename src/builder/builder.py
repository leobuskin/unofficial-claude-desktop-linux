"""Unified builder for Claude Desktop Linux."""

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
    DEBIAN_PACKAGES_MAC,
    OUTPUT_DIR,
    PACKAGE_DIR,
    WORK_DIR,
)
from .sources import MacSource, get_source_handler
from .templates import write_resources


class ClaudeDesktopBuilder:
    """Builds Claude Desktop for Linux from Windows or Mac sources."""

    def __init__(
        self,
        source: str = 'windows',
        *,
        patch_claude_code_platforms: bool = False,
    ) -> None:
        """Initialize the builder.

        Args:
            source: Source platform ('windows' or 'macos')
            patch_claude_code_platforms: Enable Linux platform in Claude Code

        """
        self.source_handler = get_source_handler(source)
        self.patch_claude_code_platforms = patch_claude_code_platforms
        self.work_dir = WORK_DIR
        self.output_dir = OUTPUT_DIR
        self.package_dir = PACKAGE_DIR
        self._metadata: dict[str, Any] | None = None
        self.logger = logging.getLogger(__name__)

    @property
    def metadata(self) -> dict[str, Any]:
        """Get metadata, raising error if not loaded."""
        if self._metadata is None:
            msg = 'Metadata not loaded. Run extraction first.'
            raise RuntimeError(msg)
        return self._metadata

    def get_required_packages(self) -> list[str]:
        """Get the list of required packages for the current source."""
        is_mac_source = isinstance(self.source_handler, MacSource)
        return DEBIAN_PACKAGES_MAC if is_mac_source else DEBIAN_PACKAGES

    def check_dependencies(self) -> None:
        """Check and install required system dependencies."""
        if not shutil.which('apt'):
            msg = 'apt package manager not found. This tool only supports Debian/Ubuntu systems.'
            raise RuntimeError(msg)

        packages = self.get_required_packages()
        required_commands = self.source_handler.required_commands
        missing = [cmd for cmd in required_commands if not shutil.which(cmd)]

        if missing:
            self.logger.warning('Missing required commands: %s', ', '.join(missing))
            self.logger.info('Installing dependencies using apt...')
            subprocess.run(['sudo', 'apt', 'update'], check=True)
            subprocess.run(['sudo', 'apt', 'install', '-y', *packages], check=True)

        if not shutil.which('pnpm'):
            self.logger.info('Installing pnpm...')
            subprocess.run(['npm', 'install', '-g', 'pnpm'], check=True)

    def build_native_module(self) -> Path:
        """Build the native module (patchy-cnb).

        Returns:
            Path to the built .node file

        """
        self.logger.info('Building native module...')

        native_dir = self.work_dir / 'native-module'
        native_dir.mkdir(parents=True, exist_ok=True)

        patchy_src = Path('src/native/patchy-cnb')
        if not patchy_src.exists():
            msg = 'patchy-cnb not found at src/native/patchy-cnb'
            raise RuntimeError(msg)

        shutil.copytree(patchy_src, native_dir, dirs_exist_ok=True)

        original_dir = Path.cwd()
        os.chdir(native_dir)

        try:
            self.logger.info('Building patchy-cnb with npm...')
            subprocess.run(['npm', 'install'], check=True, cwd=native_dir)
            subprocess.run(['npm', 'run', 'build'], check=True, cwd=native_dir)
        finally:
            os.chdir(original_dir)

        built_modules = list(native_dir.glob('*.node'))
        if not built_modules:
            msg = 'No .node file found after build'
            raise RuntimeError(msg)

        return built_modules[0]

    def _patch_title_bar(self, app_dir: Path) -> None:
        """Apply title bar patch to enable it on Linux."""
        self.logger.info('Applying title bar patch...')

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

        # Change if(!isWindows && isMainWindow) to if(isWindows && isMainWindow)
        pattern = r'if\(!(\w+)\s*&&\s*(\w+)\)'
        replacement = r'if(\1 && \2)'

        new_content = re.sub(pattern, replacement, content)

        if new_content != content:
            target_file.write_text(new_content)
            self.logger.info('Title bar patch applied successfully')
        else:
            self.logger.warning('Title bar patch pattern not found')

    def _patch_browser_window_frame(self, app_dir: Path) -> None:
        """Patch BrowserWindow options and close behavior for Linux.

        Fixes:
        1. titleBarStyle:"hidden" with no overlay → no window controls on Linux.
           Cleared so the OS provides standard window decorations.
        2. Close handler only quits on Windows (gs check). On Linux the window hides
           but there's no tray to restore it. Patch to include Linux in the quit path.
        3. Tray icon: Linux needs dark/light variant selection like Windows, since
           macOS template image auto-inversion doesn't work on Linux.
        """
        self.logger.info('Applying BrowserWindow frame patch...')

        build_dir = app_dir / '.vite' / 'build'
        if not build_dir.exists():
            self.logger.warning('Build directory not found for frame patch')
            return

        patched_count = 0
        for js_file in build_dir.glob('*.js'):
            content = js_file.read_text()
            original = content

            # Replace titleBarStyle:"hidden"/"hiddenInset" with "default" for native
            # decorations. Empty string is not a valid Electron value and strips the
            # close button on Linux/Wayland.
            content = re.sub(
                r'titleBarStyle\s*:\s*"hidden(?:Inset)?"', 'titleBarStyle:"default"', content
            )

            # Patch close handler: gs&& → (gs||process.platform==="linux")&&
            # so Linux also quits on close when tray is disabled (instead of hiding
            # to a non-existent tray).
            # Original: if(gs&&!Dr("menuBarEnabled")){...I0();return}l.preventDefault()
            content = re.sub(
                r'if\(gs&&!(\w+)\("menuBarEnabled"\)\)',
                r'if((gs||process.platform==="linux")&&!\1("menuBarEnabled"))',
                content,
            )

            # Patch tray icon selection for Linux dark mode support.
            # Original: gs?e=...Dark.ico:...ico:e="TrayIconTemplate.png"
            # Change to also check dark mode on Linux and use the Dark variant.
            content = re.sub(
                r':e="TrayIconTemplate\.png"',
                ':e=ke.nativeTheme.shouldUseDarkColors?"TrayIconTemplate-Dark.png":"TrayIconTemplate.png"',
                content,
            )

            # Patch tray recreation to update icon in-place instead of destroy+recreate.
            # The destroy/recreate cycle causes DBus "already exported" errors on Linux
            # because the StatusNotifierItem registration isn't cleaned up fast enough.
            # Original: if(dh&&(dh.destroy(),dh=null),!!t){if(dh=new ke.Tray(...)
            # Patched: if existing tray and still enabled, just update the image.
            content = re.sub(
                r'if\(dh&&\(dh\.destroy\(\),dh=null\),!!t\)\{if\(dh=new ke\.Tray\(ke\.nativeImage\.createFromPath\(r\)\)',
                'if(dh&&t){dh.setImage(ke.nativeImage.createFromPath(r))}else if(dh&&(dh.destroy(),dh=null),!!t){if(dh=new ke.Tray(ke.nativeImage.createFromPath(r))',
                content,
            )

            if content != original:
                js_file.write_text(content)
                patched_count += 1

        if patched_count:
            self.logger.info('BrowserWindow frame patch applied to %d files', patched_count)
        else:
            self.logger.warning('No files needed BrowserWindow frame patching')

    def _patch_claude_code_platform_detection(self, app_dir: Path) -> None:
        """Patch getHostPlatform() to support Linux for Claude Code.

        Inserts a Linux platform check before the 'Unsupported platform' throw
        inside getHostPlatform(). Uses a targeted insertion approach that survives
        upstream changes to other platform branches (e.g. added arm64 for win32).
        """
        self.logger.info('Applying Claude Code platforms patch...')

        index_js = app_dir / '.vite' / 'build' / 'index.js'
        if not index_js.exists():
            self.logger.warning('index.js not found, skipping Claude Code patch')
            return

        content = index_js.read_text()

        # Check if already patched (look specifically inside getHostPlatform)
        if 'process.platform==="linux")return e==="arm64"?"linux-arm64"' in content:
            self.logger.info('Claude Code platforms patch already applied, skipping')
            return

        # Insert Linux check right before the throw inside getHostPlatform().
        # We match the throw pattern that follows the win32 check and prepend the linux branch.
        linux_check = 'if(process.platform==="linux")return e==="arm64"?"linux-arm64":"linux-x64";'
        throw_pattern = r'(getHostPlatform\(\)\{const e=process\.arch;.*?)(throw new Error\(`Unsupported platform: \$\{process\.platform\}-\$\{e\}`\))'

        new_content = re.sub(throw_pattern, rf'\g<1>{linux_check}\2', content)

        if new_content != content:
            index_js.write_text(new_content)
            self.logger.info('Claude Code platforms patch applied successfully')
        else:
            self.logger.error('Claude Code platforms patch: getHostPlatform throw pattern not found')
            raise RuntimeError('Failed to apply Claude Code platforms patch: pattern not found')

    def patch_app_asar(self, resources_dir: Path, native_module: Path) -> Path:
        """Patch app.asar with native module and apply patches.

        Args:
            resources_dir: Path to resources directory
            native_module: Path to built Linux native module

        Returns:
            Path to patched app.asar

        """
        self.logger.info('Patching app.asar...')

        app_asar = resources_dir / 'app.asar'

        with tempfile.TemporaryDirectory() as tmpdir:
            app_extract = Path(tmpdir) / 'app'

            subprocess.run(
                ['npx', 'asar', 'extract', str(app_asar), str(app_extract)],
                check=True,
            )

            # Replace native module
            native_module_dir = app_extract / 'node_modules' / '@ant' / 'claude-native'
            native_module_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(native_module, native_module_dir / 'claude-native-binding.node')

            # Apply source-specific patches (e.g., Swift stub for Mac)
            self.source_handler.post_patch_app(app_extract)

            # Copy tray icons into app resources
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

            # Apply title bar patch (renderer/UI layer)
            self._patch_title_bar(app_extract)

            # Apply Claude Code platforms patch if requested (before frame patch,
            # since frame patch also modifies index.js and could affect idempotency checks)
            if self.patch_claude_code_platforms:
                self._patch_claude_code_platform_detection(app_extract)

            # Apply BrowserWindow frame patch (main process layer)
            self._patch_browser_window_frame(app_extract)

            # Repack app.asar
            new_asar = self.work_dir / 'app.asar'
            subprocess.run(
                ['npx', 'asar', 'pack', str(app_extract), str(new_asar)],
                check=True,
            )

        return new_asar

    def assemble_package(self, resources_dir: Path, app_asar: Path) -> None:
        """Assemble the final package structure."""
        self.logger.info('Assembling package...')

        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate resource files (launcher script, desktop entry)
        write_resources(self.output_dir)

        lib_dir = self.output_dir / 'lib' / 'claude-desktop'
        lib_dir.mkdir(parents=True, exist_ok=True)

        # Copy app.asar
        shutil.copy2(app_asar, lib_dir / 'app.asar')

        # Copy unpacked native modules
        unpacked_src = resources_dir / 'app.asar.unpacked'
        if unpacked_src.exists():
            unpacked_dst = lib_dir / 'app.asar.unpacked'
            shutil.copytree(unpacked_src, unpacked_dst)

            # Replace native module with our Linux build
            native_dst = unpacked_dst / 'node_modules' / '@ant' / 'claude-native'
            if native_dst.exists():
                native_src = self.work_dir / 'native-module'
                built_modules = list(native_src.glob('*.node'))
                if built_modules:
                    shutil.copy2(built_modules[0], native_dst / 'claude-native-binding.node')

        # Apply source-specific post-assembly
        self.source_handler.post_assemble(lib_dir, resources_dir)

        # Process icons
        self.source_handler.process_icons(resources_dir, self.output_dir)

        # Install Electron and dependencies
        self._install_electron(lib_dir)

    def _install_electron(self, lib_dir: Path) -> None:
        """Install Electron and other npm dependencies."""
        self.logger.info('Installing Electron %s...', self.metadata['electron_version'])

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            dependencies: dict[str, str] = {
                'electron': self.metadata['electron_version'],
            }

            # Add source-specific dependencies
            if hasattr(self.source_handler, 'get_extra_npm_dependencies'):
                dependencies.update(self.source_handler.get_extra_npm_dependencies())

            package_json = {
                'name': 'claude-desktop-electron',
                'version': '1.0.0',
                'private': True,
                'dependencies': dependencies,
            }
            (tmp_path / 'package.json').write_text(json.dumps(package_json, indent=2))

            subprocess.run(['npm', 'install', '--production'], cwd=tmp_path, check=True)

            electron_src = tmp_path / 'node_modules'
            electron_dst = lib_dir / 'node_modules'
            shutil.copytree(electron_src, electron_dst, dirs_exist_ok=True)

            # Copy i18n files and tray icons to electron resources directory.
            # When app.isPackaged=true, the app resolves these at process.resourcesPath
            # which maps to node_modules/electron/dist/resources/.
            electron_resources = electron_dst / 'electron' / 'dist' / 'resources'
            app_asar = lib_dir / 'app.asar'
            if app_asar.exists():
                with tempfile.TemporaryDirectory() as extract_dir:
                    subprocess.run(
                        ['npx', 'asar', 'extract', str(app_asar), extract_dir],
                        check=True,
                        capture_output=True,
                    )
                    i18n_src = Path(extract_dir) / 'resources' / 'i18n'
                    if i18n_src.exists():
                        for json_file in i18n_src.glob('*.json'):
                            shutil.copy2(json_file, electron_resources / json_file.name)

                    # Copy tray icons so the system tray works on Linux
                    resources_src = Path(extract_dir) / 'resources'
                    for tray_file in resources_src.glob('Tray*'):
                        shutil.copy2(tray_file, electron_resources / tray_file.name)

    def build_deb_package(self) -> Path:
        """Build Debian package."""
        self.logger.info('Building .deb package...')

        pkg_name = f'claude-desktop_{self.metadata["version"]}_amd64'
        pkg_root = self.package_dir / pkg_name

        if pkg_root.exists():
            shutil.rmtree(pkg_root)

        shutil.copytree(self.output_dir, pkg_root / 'usr')

        debian_dir = pkg_root / 'DEBIAN'
        debian_dir.mkdir(parents=True, exist_ok=True)

        source_note = f' (from {self.source_handler.name} source)'
        control_content = f"""Package: claude-desktop
Version: {self.metadata['version']}
Architecture: amd64
Maintainer: Some Contributors
Description: Unofficial Claude Desktop for Linux{source_note}
 Unofficial Claude Desktop is the official desktop application for Claude.ai,
 repackaged for Linux systems with Electron bundled.
"""
        (debian_dir / 'control').write_text(control_content)

        subprocess.run(['dpkg-deb', '--build', str(pkg_root)], check=True)

        return self.package_dir / f'{pkg_name}.deb'

    def build(self, *, download: bool = True, force_download: bool = False, package: bool = True) -> Path:
        """Run the complete build process.

        Args:
            download: Download installer if not found locally
            force_download: Force re-download even if cached
            package: Build .deb package (False to stop after assembly)

        Returns:
            Path to built .deb package, or output directory if package=False

        """
        self.logger.info('Starting Claude Desktop Linux build from %s...', self.source_handler.name)

        # Download if needed
        if not self.source_handler.has_installer():
            if download:
                self.logger.info('Installer not found locally, downloading...')
                self.source_handler.download(force=force_download)
            else:
                msg = f'No {self.source_handler.name} installer found. Use --download or provide installer path.'
                raise RuntimeError(msg)
        elif force_download:
            self.source_handler.download(force=True)

        # Clean work directory
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Extract source
        resources_dir = self.source_handler.extract(self.work_dir)

        # Get metadata
        self._metadata = self.source_handler.extract_metadata(resources_dir)
        self.logger.info(
            'Building Claude Desktop %s (from %s) with Electron %s',
            self.metadata['version'],
            self.source_handler.name,
            self.metadata['electron_version'],
        )

        if self.patch_claude_code_platforms:
            self.logger.info('Claude Code platforms patch ENABLED')

        # Build native module
        native_module = self.build_native_module()

        # Patch app.asar
        app_asar = self.patch_app_asar(resources_dir, native_module)

        # Assemble package
        self.assemble_package(resources_dir, app_asar)

        if not package:
            self.logger.info('Build complete (output: %s)', self.output_dir)
            return self.output_dir

        # Build Debian package
        self.package_dir.mkdir(parents=True, exist_ok=True)
        deb = self.build_deb_package()
        self.logger.info('Built Debian package: %s', deb)

        self.logger.info('Build complete!')
        return deb
