"""Main builder for Claude Desktop Linux."""

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
    NATIVE_MODULE_NAME,
    OUTPUT_DIR,
    PACKAGE_DIR,
    WORK_DIR,
)
from .detector import ClaudeVersionDetector


class ClaudeDesktopBuilder:
    """Builds Claude Desktop for Linux."""

    def __init__(self) -> None:
        """Initialize the builder."""
        self.detector = ClaudeVersionDetector()
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
        required_commands = ['7z', 'npx', 'cargo', 'convert', 'wrestool', 'icotool']
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

    def extract_installer(self, exe_path: Path) -> Path:
        """Extract the Windows installer."""
        self.logger.info('Extracting Windows installer...')

        extract_dir = self.work_dir / 'extract'
        extract_dir.mkdir(parents=True, exist_ok=True)

        # Extract exe
        subprocess.run(
            ['7z', 'x', '-y', str(exe_path), f'-o{extract_dir}'],
            check=True,
            capture_output=True,
        )

        # Find and extract nupkg
        nupkg_files = list(extract_dir.glob('*.nupkg'))
        if not nupkg_files:
            msg = 'No .nupkg file found'
            raise RuntimeError(msg)

        nupkg_dir = self.work_dir / 'nupkg'
        subprocess.run(
            ['7z', 'x', '-y', str(nupkg_files[0]), f'-o{nupkg_dir}'],
            check=True,
            capture_output=True,
        )

        return nupkg_dir

    def build_native_module(self) -> Path:
        """Build the native module (patchy-cnb style)."""
        self.logger.info('Building native module %s...', NATIVE_MODULE_NAME)

        native_dir = self.work_dir / 'native-module'
        native_dir.mkdir(parents=True, exist_ok=True)

        # Copy patchy-cnb source
        patchy_src = Path('claude-desktop-linux-flake/patchy-cnb')
        if patchy_src.exists():
            # Use the existing patchy-cnb source
            shutil.copytree(patchy_src, native_dir, dirs_exist_ok=True)
        else:
            # Create our own minimal implementation
            self._create_native_module(native_dir)

        # Build the module
        original_dir = Path.cwd()
        os.chdir(native_dir)

        try:
            # For patchy-cnb, we can use npm directly like Nix does
            # This avoids yarn.lock issues
            package_json_path = native_dir / 'package.json'
            if package_json_path.exists():
                package_json = json.loads(package_json_path.read_text())

                # Check if this is patchy-cnb
                if package_json.get('name') == 'patchy-cnb':
                    self.logger.info('Building patchy-cnb with npm...')
                    # Use npm directly to avoid yarn.lock issues
                    subprocess.run(['npm', 'install'], check=True, cwd=native_dir)
                    subprocess.run(['npm', 'run', 'build'], check=True, cwd=native_dir)
                elif 'yarn' in package_json.get('packageManager', ''):
                    # For other yarn projects
                    subprocess.run(['corepack', 'enable'], check=True)
                    subprocess.run(['yarn', 'install'], check=True, cwd=native_dir)
                    subprocess.run(['yarn', 'run', 'build'], check=True, cwd=native_dir)
                else:
                    # Default to pnpm
                    subprocess.run(['pnpm', 'install'], check=True, cwd=native_dir)
                    subprocess.run(['pnpm', 'run', 'build'], check=True, cwd=native_dir)
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

    def _create_native_module(self, native_dir: Path) -> None:
        """Create a minimal native module if patchy-cnb is not available."""
        # This would contain the Rust code from patchy-cnb
        # For now, we'll assume the user has cloned the flake repo
        msg = 'Please clone the claude-desktop-linux-flake repository first'
        raise NotImplementedError(msg)

    def process_icons(self, nupkg_dir: Path) -> None:
        """Extract and process application icons."""
        self.logger.info('Processing icons...')

        exe_path = nupkg_dir / 'lib' / 'net45' / 'claude.exe'
        icon_dir = self.work_dir / 'icons'
        icon_dir.mkdir(parents=True, exist_ok=True)

        # Extract icon from exe
        subprocess.run(
            ['wrestool', '-x', '-t', '14', str(exe_path), '-o', str(icon_dir / 'claude.ico')],
            check=True,
        )

        # Convert to PNG
        subprocess.run(
            ['icotool', '-x', str(icon_dir / 'claude.ico')],
            cwd=icon_dir,
            check=True,
        )

        # Create icon directories
        for size in [16, 24, 32, 48, 64, 256]:
            size_dir = self.output_dir / 'share' / 'icons' / 'hicolor' / f'{size}x{size}' / 'apps'
            size_dir.mkdir(parents=True, exist_ok=True)

            # Find and copy the appropriate icon
            icon_files = list(icon_dir.glob(f'*_{size}x{size}x*.png'))
            if icon_files:
                shutil.copy2(icon_files[0], size_dir / 'claude-desktop.png')

    def patch_app_asar(self, nupkg_dir: Path, native_module: Path) -> Path:
        """Patch app.asar with native module and tray icons."""
        self.logger.info('Patching app.asar...')

        resources_dir = nupkg_dir / 'lib' / 'net45' / 'resources'
        app_asar = resources_dir / 'app.asar'

        with tempfile.TemporaryDirectory() as tmpdir:
            # Extract app.asar
            subprocess.run(
                ['npx', 'asar', 'extract', str(app_asar), f'{tmpdir}/app'],
                check=True,
            )

            # Copy native module
            native_binding_path = Path(tmpdir) / 'app' / 'node_modules' / 'claude-native' / 'claude-native-binding.node'
            native_binding_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(native_module, native_binding_path)

            # Copy to unpacked as well
            unpacked_path = (
                resources_dir / 'app.asar.unpacked' / 'node_modules' / 'claude-native' / 'claude-native-binding.node'
            )
            if unpacked_path.parent.exists():
                shutil.copy2(native_module, unpacked_path)

            # Copy tray icons into app.asar (Nix approach)
            app_resources = Path(tmpdir) / 'app' / 'resources'
            app_resources.mkdir(exist_ok=True)

            for tray_file in resources_dir.glob('Tray*'):
                shutil.copy2(tray_file, app_resources)

            # Copy i18n files
            i18n_dir = app_resources / 'i18n'
            i18n_dir.mkdir(exist_ok=True)
            for json_file in resources_dir.glob('*.json'):
                if json_file.name not in ['build-props.json']:
                    shutil.copy2(json_file, i18n_dir)

            # Apply title bar patch (from Nix)
            self._patch_title_bar(Path(tmpdir) / 'app')

            # Repack app.asar
            new_asar = self.work_dir / 'app.asar'
            subprocess.run(
                ['npx', 'asar', 'pack', f'{tmpdir}/app', str(new_asar)],
                check=True,
            )

        return new_asar

    def _patch_title_bar(self, app_dir: Path) -> None:
        """Apply title bar patch to enable it on Linux."""
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
        """Create .desktop file for Linux desktop integration."""
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

    @property
    def metadata(self) -> dict[str, Any]:
        """Get metadata, raising error if not loaded."""
        if self._metadata is None:
            msg = 'Metadata not loaded. Call detector.get_version_info() first.'
            raise RuntimeError(msg)
        return self._metadata

    def create_launcher_script(self) -> Path:
        """Create launcher script."""
        launcher_content = """#!/bin/bash
APP_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"

# Launch with Wayland support if available
exec "$APP_DIR/lib/claude-desktop/node_modules/electron/dist/electron" \\
    "$APP_DIR/lib/claude-desktop/app.asar" \\
    ${WAYLAND_DISPLAY:+--ozone-platform-hint=auto --enable-features=WaylandWindowDecorations} \\
    "$@"
"""

        launcher_file = self.work_dir / 'claude-desktop'
        # Write with LF line endings only
        launcher_file.write_text(launcher_content.replace('\r\n', '\n'))
        launcher_file.chmod(0o755)
        return launcher_file

    def assemble_package(self, nupkg_dir: Path, app_asar: Path) -> None:
        """Assemble the final package structure."""
        self.logger.info('Assembling package...')

        # Clear and create output directory
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)

        lib_dir = self.output_dir / 'lib' / 'claude-desktop'
        lib_dir.mkdir(parents=True, exist_ok=True)

        # Copy app.asar and unpacked
        shutil.copy2(app_asar, lib_dir / 'app.asar')

        unpacked_src = nupkg_dir / 'lib' / 'net45' / 'resources' / 'app.asar.unpacked'
        if unpacked_src.exists():
            shutil.copytree(unpacked_src, lib_dir / 'app.asar.unpacked')

        # Copy desktop file
        desktop_dir = self.output_dir / 'share' / 'applications'
        desktop_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.create_desktop_file(), desktop_dir / 'claude-desktop.desktop')

        # Copy launcher
        bin_dir = self.output_dir / 'bin'
        bin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.create_launcher_script(), bin_dir / 'claude-desktop')

        # Install Electron in the package
        self.logger.info('Installing Electron %s...', self.metadata['electron_version'])

        # Create a temporary directory for npm install (to use user's Node)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            package_json = {
                'name': 'claude-desktop-electron',
                'version': '1.0.0',
                'private': True,
                'dependencies': {'electron': self.metadata['electron_version']},
            }
            (tmp_path / 'package.json').write_text(json.dumps(package_json, indent=2))

            # Install in temp directory
            subprocess.run(['npm', 'install', '--production'], cwd=tmp_path, check=True)

            # Copy electron to the package
            electron_src = tmp_path / 'node_modules'
            electron_dst = lib_dir / 'node_modules'
            shutil.copytree(electron_src, electron_dst, dirs_exist_ok=True)

    def build_deb_package(self) -> Path:
        """Build Debian package."""
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
Description: Desktop application for Claude.ai
 Claude Desktop is the official desktop application for Claude.ai,
 repackaged for Linux systems with Electron bundled.
"""
        (debian_dir / 'control').write_text(control_content)

        # Build package
        subprocess.run(['dpkg-deb', '--build', str(pkg_root)], check=True)

        return self.package_dir / f'{pkg_name}.deb'

    def build_rpm_package(self) -> Path:
        """Build RPM package."""
        self.logger.info('Building .rpm package...')

        # Create RPM build structure
        rpm_root = self.package_dir / 'rpmbuild'
        for subdir in ['BUILD', 'RPMS', 'SOURCES', 'SPECS', 'SRPMS']:
            (rpm_root / subdir).mkdir(parents=True, exist_ok=True)

        # Create tarball of the output
        tar_name = f'claude-desktop-{self.metadata["version"]}.tar.gz'
        tar_path = rpm_root / 'SOURCES' / tar_name

        subprocess.run(
            ['tar', 'czf', str(tar_path), '-C', str(self.output_dir.parent), self.output_dir.name],
            check=True,
        )

        # Create spec file
        spec_content = f"""Name: claude-desktop
Version: {self.metadata['version']}
Release: 1%{{?dist}}
Summary: Desktop application for Claude.ai
License: Proprietary
URL: https://claude.ai

%description
Claude Desktop is the official desktop application for Claude.ai,
repackaged for Linux systems with Electron bundled.

%prep
%setup -q

%install
mkdir -p %{{buildroot}}/usr
cp -r * %{{buildroot}}/usr/

%files
/usr/bin/claude-desktop
/usr/lib/claude-desktop
/usr/share/applications/claude-desktop.desktop
/usr/share/icons/hicolor/*/apps/claude-desktop.png

%changelog
* $(date +"%a %b %d %Y") Claude Desktop Linux Contributors
- Automated build of version {self.metadata['version']}
"""

        spec_file = rpm_root / 'SPECS' / 'claude-desktop.spec'
        spec_file.write_text(spec_content)

        # Build RPM
        subprocess.run(
            ['rpmbuild', '-bb', str(spec_file), '--define', f'_topdir {rpm_root}'],
            check=True,
        )

        # Find built RPM
        rpm_files = list((rpm_root / 'RPMS').rglob('*.rpm'))
        if not rpm_files:
            msg = 'No RPM file found after build'
            raise RuntimeError(msg)

        # Move to package directory
        rpm_file = self.package_dir / rpm_files[0].name
        shutil.move(rpm_files[0], rpm_file)

        return rpm_file

    def build(self) -> None:
        """Run the complete build process."""
        self.logger.info('Starting Claude Desktop Linux build...')

        # Get version info
        self._metadata = self.detector.get_version_info()
        self.logger.info(
            'Building Claude Desktop %s with Electron %s',
            self.metadata['version'],
            self.metadata['electron_version'],
        )

        # Check dependencies
        self.check_dependencies()

        # Clean work directory
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Download and extract
        exe_path = self.detector.download_exe()
        nupkg_dir = self.extract_installer(exe_path)

        # Build native module
        native_module = self.build_native_module()

        # Process icons
        self.process_icons(nupkg_dir)

        # Patch app.asar
        app_asar = self.patch_app_asar(nupkg_dir, native_module)

        # Assemble package
        self.assemble_package(nupkg_dir, app_asar)

        # Build packages
        self.package_dir.mkdir(parents=True, exist_ok=True)

        pkg_manager, _ = self.detect_package_manager()
        if pkg_manager == 'apt':
            package = self.build_deb_package()
            self.logger.info('✓ Built Debian package: %s', package)
        else:
            package = self.build_rpm_package()
            self.logger.info('✓ Built RPM package: %s', package)

        self.logger.info('✓ Build complete! Install with:')
        if pkg_manager == 'apt':
            self.logger.info('  sudo dpkg -i %s', package)
        else:
            self.logger.info('  sudo rpm -i %s', package)
