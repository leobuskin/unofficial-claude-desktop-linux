"""Detection and extraction of Claude Desktop from Mac DMG."""

import hashlib
import json
import logging
import plistlib
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .config import CACHE_DIR, CLAUDE_URL_MAC
from .downloader import (
    check_for_update,
    download_file,
    extract_version_from_url,
    get_cached_url,
)


class MacDmgDetector:
    """Detects Claude Desktop version from Mac DMG and extracts resources."""

    CACHE_KEY = 'mac'

    def __init__(self, dmg_path: Path | None = None) -> None:
        """Initialize the detector.

        Args:
            dmg_path: Path to the DMG file. If not provided, will look in cache.

        """
        self.cache_dir = CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._metadata: dict[str, Any] | None = None
        self.logger = logging.getLogger(__name__)
        self.dmg_path = self._find_dmg_path(dmg_path)

    def _find_dmg_path(self, dmg_path: Path | None) -> Path | None:
        """Find the DMG file path."""
        if dmg_path:
            return dmg_path

        # Check cache
        cached_dmg = self.cache_dir / 'Claude.dmg'
        if cached_dmg.exists():
            return cached_dmg

        return None

    def download_dmg(self, *, force: bool = False) -> Path:
        """Download Claude Desktop DMG with progress bar.

        Args:
            force: Force re-download even if cached

        Returns:
            Path to downloaded DMG file

        """
        dmg_path = self.cache_dir / 'Claude.dmg'

        # Check if we need to download
        if not force and dmg_path.exists():
            # Use cached file without checking remote (expensive browser launch)
            self.logger.info('Using cached DMG: %s', dmg_path)
            self.dmg_path = dmg_path
            return dmg_path

        self.logger.info('Downloading Claude Desktop DMG...')
        dmg_path, _resolved_url = download_file(
            CLAUDE_URL_MAC,
            dmg_path,
            cache_dir=self.cache_dir,
            cache_key=self.CACHE_KEY,
        )

        self.dmg_path = dmg_path
        return dmg_path

    def check_for_update(self) -> tuple[bool, str | None, str | None]:
        """Check if a new version is available without downloading.

        Returns:
            Tuple of (update_available, new_version, cached_version)

        """
        return check_for_update(CLAUDE_URL_MAC, self.cache_dir, self.CACHE_KEY)

    def get_cached_version(self) -> str | None:
        """Get the version from cached URL without network request."""
        cached_url = get_cached_url(self.cache_dir, self.CACHE_KEY)
        return extract_version_from_url(cached_url) if cached_url else None

    def get_dmg_hash(self, dmg_path: Path) -> str:
        """Calculate SHA256 hash of the DMG file."""
        sha256_hash = hashlib.sha256()
        with dmg_path.open('rb') as f:
            for byte_block in iter(lambda: f.read(4096), b''):
                sha256_hash.update(byte_block)
        return f'sha256-{sha256_hash.digest().hex()}'

    def extract_dmg(self, dmg_path: Path, output_dir: Path) -> Path:
        """Extract DMG contents using 7z.

        Args:
            dmg_path: Path to the DMG file
            output_dir: Directory to extract to

        Returns:
            Path to the extracted Claude.app/Contents directory

        """
        self.logger.info('Extracting DMG: %s', dmg_path)

        # 7z can extract DMG files (extracts HFS+ filesystem)
        # Note: 7z may return error code 2 for HFS+ "header errors" which are
        # actually just warnings about the filesystem format - extraction still works
        result = subprocess.run(
            ['7z', 'x', '-y', str(dmg_path), f'-o{output_dir}'],
            check=False,
            capture_output=True,
            text=True,
        )

        # Check if extraction actually failed (no files extracted)
        # vs just HFS+ warnings (files extracted successfully)
        if result.returncode != 0:
            self.logger.debug('7z stderr: %s', result.stderr)
            self.logger.debug('7z stdout: %s', result.stdout)

        # Find Claude.app inside the extracted contents
        app_path = output_dir / 'Claude' / 'Claude.app' / 'Contents'
        if not app_path.exists():
            app_path = self._find_app_contents(output_dir)

        if not app_path.exists():
            msg = f'Claude.app/Contents not found in extracted DMG at {output_dir}'
            raise RuntimeError(msg)

        return app_path

    def _find_app_contents(self, output_dir: Path) -> Path:
        """Find Claude.app/Contents in extracted DMG."""
        for candidate in output_dir.rglob('Claude.app'):
            candidate_contents = candidate / 'Contents'
            if candidate_contents.exists():
                return candidate_contents
        return output_dir / 'not_found'  # Return non-existent path

    def parse_plist(self, plist_path: Path) -> dict[str, Any]:
        """Parse a plist file."""
        with plist_path.open('rb') as f:
            result: dict[str, Any] = plistlib.load(f)
            return result

    def _get_electron_version_from_framework(self, app_contents: Path) -> str | None:
        """Get Electron version from the framework plist."""
        electron_plist_path = (
            app_contents / 'Frameworks' / 'Electron Framework.framework' / 'Versions' / 'A' / 'Resources' / 'Info.plist'
        )
        if electron_plist_path.exists():
            electron_plist = self.parse_plist(electron_plist_path)
            return electron_plist.get('CFBundleVersion')
        return None

    def _extract_package_data(
        self,
        app_contents: Path,
        tmppath: Path,
    ) -> tuple[str | None, str | None, str | None]:
        """Extract and parse package.json from app.asar.

        Returns:
            Tuple of (electron_version, node_requirement, app_name) from package.json

        """
        app_asar = app_contents / 'Resources' / 'app.asar'
        if not app_asar.exists():
            return None, None, None

        app_extract_dir = tmppath / 'app'
        subprocess.run(
            ['npx', 'asar', 'extract', str(app_asar), str(app_extract_dir)],
            check=True,
            capture_output=True,
        )

        package_json_path = app_extract_dir / 'package.json'
        if not package_json_path.exists():
            return None, None, None

        package_data = json.loads(package_json_path.read_text())

        electron_version = package_data.get('devDependencies', {}).get('electron')
        node_requirement = package_data.get('engines', {}).get('node')
        app_name = package_data.get('productName')

        return electron_version, node_requirement, app_name

    def extract_metadata(self, dmg_path: Path | None = None) -> dict[str, Any]:
        """Extract version and requirements from the DMG.

        Args:
            dmg_path: Optional path to DMG. Uses self.dmg_path if not provided.

        Returns:
            Dictionary with version metadata

        """
        if self._metadata is not None:
            return self._metadata

        dmg_path = dmg_path or self.dmg_path
        if dmg_path is None:
            msg = 'No DMG file found. Run mac-download first or use --dmg option.'
            raise RuntimeError(msg)

        metadata_cache = self.cache_dir / 'mac_metadata.json'
        dmg_hash = self.get_dmg_hash(dmg_path)

        # Check cached metadata
        if metadata_cache.exists():
            cached: dict[str, Any] = json.loads(metadata_cache.read_text())
            if cached.get('dmg_hash') == dmg_hash:
                self._metadata = cached
                return cached

        self.logger.info('Extracting version information from DMG...')

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            app_contents = self.extract_dmg(dmg_path, tmppath)

            # Read Info.plist for app version
            info_plist_path = app_contents / 'Info.plist'
            if not info_plist_path.exists():
                msg = f'Info.plist not found at {info_plist_path}'
                raise RuntimeError(msg)

            info_plist = self.parse_plist(info_plist_path)
            version = info_plist.get(
                'CFBundleShortVersionString',
                info_plist.get('CFBundleVersion', 'unknown'),
            )

            # Get Electron version from framework
            electron_version = self._get_electron_version_from_framework(app_contents)

            # Get data from package.json
            pkg_electron, node_requirement, pkg_app_name = self._extract_package_data(
                app_contents,
                tmppath,
            )

            # Use package.json electron version if not found in framework
            if not electron_version:
                electron_version = pkg_electron

            if not electron_version:
                msg = 'Could not determine Electron version'
                raise RuntimeError(msg)

            # Determine app name
            app_name = pkg_app_name or info_plist.get('CFBundleDisplayName') or info_plist.get('CFBundleName', 'Claude')

            metadata = {
                'version': version,
                'electron_version': electron_version,
                'node_requirement': node_requirement,
                'dmg_hash': dmg_hash,
                'app_name': app_name,
                'source': 'mac',
                'bundle_id': info_plist.get('CFBundleIdentifier', 'com.anthropic.claudefordesktop'),
            }

            # Cache the metadata
            metadata_cache.write_text(json.dumps(metadata, indent=2))
            self._metadata = metadata

            return metadata

    def get_version_info(self) -> dict[str, Any]:
        """Get all version information."""
        return self.extract_metadata()

    def has_dmg(self) -> bool:
        """Check if a DMG file is available."""
        return self.dmg_path is not None and self.dmg_path.exists()
