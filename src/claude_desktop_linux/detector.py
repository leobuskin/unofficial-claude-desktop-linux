"""Dynamic detection of Claude Desktop version and requirements."""

import hashlib
import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .config import CACHE_DIR, CLAUDE_URL_WINDOWS
from .downloader import (
    check_for_update,
    download_file,
    extract_version_from_url,
    get_cached_url,
)


class ClaudeVersionDetector:
    """Detects Claude Desktop version and requirements dynamically."""

    CACHE_KEY = 'windows'

    def __init__(self) -> None:
        """Initialize the detector."""
        self.cache_dir = CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._metadata: dict[str, Any] | None = None
        self.logger = logging.getLogger(__name__)

    def download_exe(self, *, force: bool = False) -> Path:
        """Download Claude Desktop exe with progress bar."""
        exe_path = self.cache_dir / 'Claude-Setup-x64.exe'

        # Check if we need to download
        if not force and exe_path.exists():
            # Use cached file without checking remote (expensive browser launch)
            self.logger.info('Using cached installer: %s', exe_path)
            return exe_path

        self.logger.info('Downloading Claude Desktop installer...')
        exe_path, _resolved_url = download_file(
            CLAUDE_URL_WINDOWS,
            exe_path,
            cache_dir=self.cache_dir,
            cache_key=self.CACHE_KEY,
        )

        return exe_path

    def check_for_update(self) -> tuple[bool, str | None, str | None]:
        """Check if a new version is available without downloading.

        Returns:
            Tuple of (update_available, new_version, cached_version)

        """
        return check_for_update(CLAUDE_URL_WINDOWS, self.cache_dir, self.CACHE_KEY)

    def get_cached_version(self) -> str | None:
        """Get the version from cached URL without network request."""
        cached_url = get_cached_url(self.cache_dir, self.CACHE_KEY)
        return extract_version_from_url(cached_url) if cached_url else None

    def get_exe_hash(self, exe_path: Path) -> str:
        """Calculate SHA256 hash of the exe file."""
        sha256_hash = hashlib.sha256()
        with exe_path.open('rb') as f:
            for byte_block in iter(lambda: f.read(4096), b''):
                sha256_hash.update(byte_block)
        return f'sha256-{sha256_hash.digest().hex()}'

    def _extract_nupkg_and_version(self, tmpdir: str, exe_path: Path) -> tuple[Path, str]:
        """Extract exe and nupkg, return nupkg path and version."""
        subprocess.run(
            ['7z', 'x', '-y', str(exe_path), f'-o{tmpdir}'],
            check=True,
            capture_output=True,
        )

        nupkg_files = list(Path(tmpdir).glob('*.nupkg'))
        if not nupkg_files:
            msg = 'No .nupkg file found in extracted exe'
            raise RuntimeError(msg)

        nupkg_file = nupkg_files[0]

        match = re.match(r'AnthropicClaude-(.+)-full\.nupkg', nupkg_file.name)
        if not match:
            msg = f'Unexpected nupkg filename: {nupkg_file.name}'
            raise RuntimeError(msg)

        version = match.group(1)

        subprocess.run(
            ['7z', 'x', '-y', str(nupkg_file), f'-o{tmpdir}/nupkg'],
            check=True,
            capture_output=True,
        )

        return nupkg_file, version

    def _read_package_json(self, tmpdir: str) -> dict[str, Any]:
        """Extract and read package.json from app.asar."""
        app_asar = Path(tmpdir) / 'nupkg' / 'lib' / 'net45' / 'resources' / 'app.asar'
        if not app_asar.exists():
            msg = f'app.asar not found at {app_asar}'
            raise RuntimeError(msg)

        subprocess.run(
            ['npx', 'asar', 'extract', str(app_asar), f'{tmpdir}/app'],
            check=True,
            capture_output=True,
        )

        package_json_path = Path(tmpdir) / 'app' / 'package.json'
        result: dict[str, Any] = json.loads(package_json_path.read_text())
        return result

    def extract_metadata(self, exe_path: Path) -> dict[str, Any]:
        """Extract version and requirements from the exe."""
        if self._metadata is not None:
            return self._metadata

        metadata_cache = self.cache_dir / 'metadata.json'
        exe_hash = self.get_exe_hash(exe_path)

        # Check cached metadata
        if metadata_cache.exists():
            cached: dict[str, Any] = json.loads(metadata_cache.read_text())
            if cached.get('exe_hash') == exe_hash:
                self._metadata = cached
                return cached

        self.logger.info('Extracting version information...')

        with tempfile.TemporaryDirectory() as tmpdir:
            _nupkg_file, version = self._extract_nupkg_and_version(tmpdir, exe_path)
            package_data = self._read_package_json(tmpdir)

            # Find Electron version
            electron_version = package_data.get('devDependencies', {}).get('electron')
            if not electron_version:
                msg = 'Electron version not found in package.json'
                raise RuntimeError(msg)

            metadata = {
                'version': version,
                'electron_version': electron_version,
                'node_requirement': package_data.get('engines', {}).get('node'),
                'exe_hash': exe_hash,
                'app_name': package_data.get('productName', 'Claude'),
                'app_version': package_data.get('version', version),
            }

            # Cache the metadata
            metadata_cache.write_text(json.dumps(metadata, indent=2))
            self._metadata = metadata

            return metadata

    def get_version_info(self) -> dict[str, Any]:
        """Get all version information."""
        exe_path = self.download_exe()
        return self.extract_metadata(exe_path)
