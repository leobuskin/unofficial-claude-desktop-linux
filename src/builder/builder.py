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
        """Build the native module (claude-native).

        Returns:
            Path to the built .node file

        """
        self.logger.info('Building native module...')

        native_dir = self.work_dir / 'native-module'
        native_dir.mkdir(parents=True, exist_ok=True)

        native_src = Path('src/native/claude-native')
        if not native_src.exists():
            msg = 'claude-native not found at src/native/claude-native'
            raise RuntimeError(msg)

        shutil.copytree(native_src, native_dir, dirs_exist_ok=True)

        original_dir = Path.cwd()
        os.chdir(native_dir)

        try:
            self.logger.info('Building claude-native with npm...')
            subprocess.run(['npm', 'install'], check=True, cwd=native_dir)
            subprocess.run(['npm', 'run', 'build'], check=True, cwd=native_dir)
        finally:
            os.chdir(original_dir)

        built_modules = list(native_dir.glob('*.node'))
        if not built_modules:
            msg = 'No .node file found after build'
            raise RuntimeError(msg)

        return built_modules[0]

    def _apply_patch(self, content: str, name: str, pattern: str, replacement: str) -> str:
        """Apply a single regex patch, raising on failure.

        Every patch MUST match. If the upstream code changed and a pattern no longer
        matches, the build fails immediately so we can update the patch.
        """
        new_content = re.sub(pattern, replacement, content)
        if new_content == content:
            msg = f'Patch "{name}" failed: pattern not found in source'
            raise RuntimeError(msg)
        self.logger.info('Applied patch: %s', name)
        return new_content

    def _patch_title_bar(self, app_dir: Path) -> None:
        """Apply title bar patch to enable it on Linux."""
        self.logger.info('Applying title bar patch...')

        search_base = app_dir / '.vite' / 'renderer' / 'main_window' / 'assets'
        if not search_base.exists():
            raise RuntimeError('Title bar patch: assets directory not found')

        main_window_files = list(search_base.glob('MainWindowPage-*.js'))
        if len(main_window_files) != 1:
            raise RuntimeError(f'Title bar patch: expected 1 MainWindowPage file, found {len(main_window_files)}')

        target_file = main_window_files[0]
        content = target_file.read_text()

        # Change if(!isWindows && isMainWindow) to if(isWindows && isMainWindow)
        content = self._apply_patch(
            content, 'title-bar-negation',
            r'if\(!(\w+)\s*&&\s*(\w+)\)',
            r'if(\1 && \2)',
        )
        target_file.write_text(content)

    def _patch_index_js(self, app_dir: Path) -> None:
        """Apply all patches to .vite/build/index.js.

        All patches use _apply_patch which raises on failure. This ensures the
        build fails immediately if upstream code changes break any pattern.
        """
        self.logger.info('Applying index.js patches...')

        index_js = app_dir / '.vite' / 'build' / 'index.js'
        if not index_js.exists():
            raise RuntimeError('index.js not found at .vite/build/index.js')

        content = index_js.read_text()

        # --- Claude Code platform detection ---
        # Insert Linux check before the "Unsupported platform" throw in getHostPlatform().
        if self.patch_claude_code_platforms:
            linux_check = 'if(process.platform==="linux")return e==="arm64"?"linux-arm64":"linux-x64";'
            content = self._apply_patch(
                content, 'claude-code-platform-detection',
                r'(getHostPlatform\(\)\{const e=process\.arch;.*?)'
                r'(throw new Error\(`Unsupported platform: \$\{process\.platform\}-\$\{e\}`\))',
                rf'\g<1>{linux_check}\2',
            )

        # --- Window frame: titleBarStyle ---
        # Replace "hidden"/"hiddenInset" with "default" for native window decorations.
        content = self._apply_patch(
            content, 'title-bar-style',
            r'titleBarStyle\s*:\s*"hidden(?:Inset)?"',
            'titleBarStyle:"default"',
        )

        # --- Close handler: quit on Linux ---
        # Original only quits on Windows (gs). Include Linux so closing the window
        # actually exits the app when tray is disabled.
        content = self._apply_patch(
            content, 'close-handler-linux-quit',
            r'if\(gs&&!(\w+)\("menuBarEnabled"\)\)',
            r'if((gs||process.platform==="linux")&&!\1("menuBarEnabled"))',
        )

        # --- Tray icon: dark mode on Linux ---
        # macOS template images auto-invert; Linux needs explicit dark/light selection.
        content = self._apply_patch(
            content, 'tray-icon-dark-mode',
            r':e="TrayIconTemplate\.png"',
            ':e=ke.nativeTheme.shouldUseDarkColors?"TrayIconTemplate-Dark.png":"TrayIconTemplate.png"',
        )

        # --- Tray: update icon in-place ---
        # Destroy+recreate causes DBus "already exported" errors on Linux.
        # If tray exists and is still enabled, just update the image.
        content = self._apply_patch(
            content, 'tray-icon-inplace-update',
            r'if\(dh&&\(dh\.destroy\(\),dh=null\),!!t\)\{if\(dh=new ke\.Tray\(ke\.nativeImage\.createFromPath\(r\)\)',
            'if(dh&&t){dh.setImage(ke.nativeImage.createFromPath(r))}'
            'else if(dh&&(dh.destroy(),dh=null),!!t)'
            '{if(dh=new ke.Tray(ke.nativeImage.createFromPath(r))',
        )

        # --- Platform label: "Unsupported Platform" → "Linux" ---
        content = self._apply_patch(
            content, 'platform-label-linux',
            r'(switch\(process\.platform\)\{case"darwin":return"macOS";case"win32":return"Windows";)'
            r'default:return"Unsupported Platform"',
            r'\1case"linux":return"Linux";default:return"Unsupported Platform"',
        )

        # --- File dialog: allow openDirectory on Linux ---
        # macOS allows both openFile+openDirectory, Linux/Windows only openFile.
        # Linux GTK supports openDirectory fine; enable it.
        content = self._apply_patch(
            content, 'file-dialog-open-directory',
            r'process\.platform==="darwin"\?'
            r'\["openFile","openDirectory","multiSelections"\]'
            r':\["openFile","multiSelections"\]',
            'process.platform==="win32"'
            '?["openFile","multiSelections"]'
            ':["openFile","openDirectory","multiSelections"]',
        )

        # --- Chrome extension: native messaging host paths for Linux ---
        # Original returns [] for non-darwin/win32. Add Linux browser paths.
        content = self._apply_patch(
            content, 'chrome-native-host-paths',
            r'(return process\.platform==="win32"\?\[\{name:"All",path:Ae\.join\(ke\.app\.getPath\("userData"\),"ChromeNativeHost"\)\}\]:)\[\]',
            r'\1(()=>{const h=FCt.homedir();'
            r'const c=Ae.join(h,".config");'
            r'return[{name:"Chrome",path:Ae.join(c,"google-chrome","NativeMessagingHosts")},'
            r'{name:"Brave",path:Ae.join(c,"BraveSoftware","Brave-Browser","NativeMessagingHosts")},'
            r'{name:"Edge",path:Ae.join(c,"microsoft-edge","NativeMessagingHosts")},'
            r'{name:"Chromium",path:Ae.join(c,"chromium","NativeMessagingHosts")},'
            r'{name:"Vivaldi",path:Ae.join(c,"vivaldi","NativeMessagingHosts")}]})()',
        )

        # --- Chrome extension: browser profile paths for Linux ---
        # Original returns [] for non-darwin/win32. Add Linux profile directories.
        content = self._apply_patch(
            content, 'chrome-browser-profile-paths',
            r'(if\(process\.platform==="win32"\)\{const e=ut\.join\(t,"AppData","Local"\),'
            r'r=ut\.join\(t,"AppData","Roaming"\);return\[.*?\]\})'
            r'return\[\]',
            r'\1{const e=ut.join(t,".config");'
            r'return[{name:"Chrome",path:ut.join(e,"google-chrome")},'
            r'{name:"Brave",path:ut.join(e,"BraveSoftware","Brave-Browser")},'
            r'{name:"Edge",path:ut.join(e,"microsoft-edge")},'
            r'{name:"Chromium",path:ut.join(e,"chromium")},'
            r'{name:"Vivaldi",path:ut.join(e,"vivaldi")}]}',
        )

        # --- Chrome extension: install on Linux ---
        # Original rejects non-macOS. Add Linux support using External Extensions dir.
        content = self._apply_patch(
            content, 'chrome-extension-install-linux',
            r'if\(process\.platform!=="darwin"\)return\{status:x_\.Error,'
            r'error:`Unsupported platform: \$\{process\.platform\}\. Only macOS is supported\.`\}',
            'if(process.platform!=="darwin"&&process.platform!=="linux")'
            'return{status:x_.Error,'
            'error:`Unsupported platform: ${process.platform}. Only macOS and Linux are supported.`}',
        )

        # --- Chrome extension: Chrome base path for Linux ---
        # FG is hardcoded to macOS Chrome path. On Linux it should be ~/.config/google-chrome.
        content = self._apply_patch(
            content, 'chrome-extension-base-path',
            r'FG=ut\.join\(Ii\.homedir\(\),"Library","Application Support","Google","Chrome"\)',
            'FG=process.platform==="linux"'
            '?ut.join(Ii.homedir(),".config","google-chrome")'
            ':ut.join(Ii.homedir(),"Library","Application Support","Google","Chrome")',
        )

        # --- DXT extension platform compatibility: treat Linux as compatible ---
        # Extension manifests declare compatibility.platforms (e.g. ["darwin","win32"]).
        # xGr() checks if process.platform is in that list and rejects "linux".
        # Since Linux shares Node/Python runtimes with macOS, extensions that work
        # on macOS will generally work on Linux. Patch: also accept "linux" when
        # "darwin" is listed.
        content = self._apply_patch(
            content, 'dxt-platform-compat-linux',
            r'return t\.compatibility\.platforms\.some\(n=>n===e\)\?null:"platform-mismatch"\}',
            'return t.compatibility.platforms.some(n=>n===e)'
            '||(e==="linux"&&t.compatibility.platforms.some(n=>n==="darwin"))'
            '?null:"platform-mismatch"}',
        )

        index_js.write_text(content)
        self.logger.info('All index.js patches applied successfully')

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

            # Apply all index.js patches (main process layer)
            self._patch_index_js(app_extract)

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

            # Electron's process.resourcesPath points to node_modules/electron/dist/resources/.
            # The app expects app.asar at that location (for MCP runtime, i18n, tray icons).
            # Symlink app.asar there so it's found at process.resourcesPath/app.asar.
            electron_resources = electron_dst / 'electron' / 'dist' / 'resources'
            app_asar = lib_dir / 'app.asar'
            resources_asar = electron_resources / 'app.asar'
            if app_asar.exists():
                # Relative symlink: ../../../../app.asar (resources -> dist -> electron -> node_modules -> lib_dir)
                resources_asar.symlink_to(os.path.relpath(app_asar, electron_resources))

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

            # Create chrome-native-host wrapper that delegates to the Claude Code binary.
            # Claude Desktop looks for this at process.resourcesPath/chrome-native-host
            # to bridge the Chrome extension via native messaging.
            # Priority: 1) CCD binary (bundled, managed by Claude Desktop)
            #           2) Standalone Claude Code (user-installed)
            native_host = electron_resources / 'chrome-native-host'
            native_host.write_text(
                '#!/bin/sh\n'
                '# Bridge Chrome extension to Claude Code binary (claude --chrome-native-host)\n'
                '# Try CCD (Claude Code for Desktop) first, then standalone Claude Code\n'
                'CCD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/Claude/claude-code"\n'
                'if [ -d "$CCD_DIR" ]; then\n'
                '  LATEST=$(ls -1 "$CCD_DIR" | sort -V | tail -1)\n'
                '  if [ -n "$LATEST" ] && [ -x "$CCD_DIR/$LATEST/claude" ]; then\n'
                '    exec "$CCD_DIR/$LATEST/claude" --chrome-native-host\n'
                '  fi\n'
                'fi\n'
                'if command -v claude >/dev/null 2>&1; then\n'
                '  exec claude --chrome-native-host\n'
                'fi\n'
                'echo "Claude Code binary not found" >&2\n'
                'exit 1\n'
            )
            native_host.chmod(0o755)

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
