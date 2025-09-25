"""Dynamic detection of Claude Desktop version and requirements."""

import hashlib
import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import requests
from tqdm import tqdm

from .config import CACHE_DIR, CLAUDE_URL


class ClaudeVersionDetector:
    """Detects Claude Desktop version and requirements dynamically."""

    def __init__(self) -> None:
        """Initialize the detector."""
        self.cache_dir = CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._metadata: dict[str, Any] | None = None
        self.logger = logging.getLogger(__name__)

    def download_exe(self, force: bool = False) -> Path:
        """Download Claude Desktop exe with progress bar."""
        exe_path = self.cache_dir / 'Claude-Setup-x64.exe'

        # Check if we need to download
        if not force and exe_path.exists():
            # Check if the file on server is different
            response = requests.head(CLAUDE_URL, timeout=10)
            remote_size = int(response.headers.get('Content-Length', 0))
            local_size = exe_path.stat().st_size

            if remote_size == local_size:
                self.logger.info('Using cached installer: %s', exe_path)
                return exe_path

        self.logger.info('Downloading Claude Desktop installer...')
        response = requests.get(CLAUDE_URL, stream=True, timeout=30)
        response.raise_for_status()

        total_size = int(response.headers.get('Content-Length', 0))

        with (
            exe_path.open('wb') as f,
            tqdm(total=total_size, unit='B', unit_scale=True, desc='Downloading') as pbar,
        ):
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                pbar.update(len(chunk))

        return exe_path

    def get_exe_hash(self, exe_path: Path) -> str:
        """Calculate SHA256 hash of the exe file."""
        sha256_hash = hashlib.sha256()
        with exe_path.open('rb') as f:
            for byte_block in iter(lambda: f.read(4096), b''):
                sha256_hash.update(byte_block)
        return f'sha256-{sha256_hash.digest().hex()}'

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
            # Extract the exe
            self.logger.debug('Extracting exe with 7z to: %s', tmpdir)
            self.logger.debug('Exe path: %s (size: %d bytes)', exe_path, exe_path.stat().st_size)

            try:
                result = subprocess.run(
                    ['7z', 'x', '-y', str(exe_path), f'-o{tmpdir}'],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60,  # 60 second timeout
                )
                self.logger.debug('7z extraction completed successfully')
                if result.stdout:
                    self.logger.debug('7z output: %s', result.stdout[:500])  # First 500 chars
            except subprocess.TimeoutExpired as e:
                self.logger.error('7z extraction timed out after 60 seconds')
                raise RuntimeError('7z extraction timed out. The exe file might be corrupted or too large.') from e
            except subprocess.CalledProcessError as e:
                self.logger.error('7z extraction failed: %s', e.stderr)
                raise RuntimeError(f'Failed to extract exe: {e.stderr}') from e

            # Find the nupkg file
            nupkg_files = list(Path(tmpdir).glob('*.nupkg'))
            if not nupkg_files:
                msg = 'No .nupkg file found in extracted exe'
                raise RuntimeError(msg)

            nupkg_file = nupkg_files[0]

            # Extract version from nupkg filename
            match = re.match(r'AnthropicClaude-(.+)-full\.nupkg', nupkg_file.name)
            if not match:
                msg = f'Unexpected nupkg filename: {nupkg_file.name}'
                raise RuntimeError(msg)

            version = match.group(1)

            # Extract the nupkg
            self.logger.debug('Extracting nupkg: %s', nupkg_file.name)
            try:
                subprocess.run(
                    ['7z', 'x', '-y', str(nupkg_file), f'-o{tmpdir}/nupkg'],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,  # 30 second timeout
                )
                self.logger.debug('Nupkg extraction completed')
            except subprocess.TimeoutExpired as e:
                self.logger.error('Nupkg extraction timed out')
                raise RuntimeError('Nupkg extraction timed out') from e
            except subprocess.CalledProcessError as e:
                self.logger.error('Nupkg extraction failed: %s', e.stderr)
                raise RuntimeError(f'Failed to extract nupkg: {e.stderr}') from e

            # Extract app.asar to read package.json
            app_asar = Path(tmpdir) / 'nupkg' / 'lib' / 'net45' / 'resources' / 'app.asar'
            if not app_asar.exists():
                msg = f'app.asar not found at {app_asar}'
                raise RuntimeError(msg)

            # Extract package.json from app.asar
            self.logger.debug('Extracting app.asar')
            try:
                subprocess.run(
                    ['npx', 'asar', 'extract', str(app_asar), f'{tmpdir}/app'],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,  # 30 second timeout
                )
                self.logger.debug('app.asar extraction completed')
            except subprocess.TimeoutExpired as e:
                self.logger.error('app.asar extraction timed out')
                raise RuntimeError('app.asar extraction timed out') from e
            except subprocess.CalledProcessError as e:
                self.logger.error('app.asar extraction failed: %s', e.stderr)
                raise RuntimeError(f'Failed to extract app.asar: {e.stderr}') from e

            # Read package.json
            package_json_path = Path(tmpdir) / 'app' / 'package.json'
            package_data = json.loads(package_json_path.read_text())

            # Find Electron version
            electron_version = None
            for dep, ver in package_data.get('devDependencies', {}).items():
                if dep == 'electron':
                    electron_version = ver
                    break

            if not electron_version:
                msg = 'Electron version not found in package.json'
                raise RuntimeError(msg)

            # Get Node.js requirement
            node_requirement = None
            engines = package_data.get('engines', {})
            if 'node' in engines:
                node_requirement = engines['node']

            metadata = {
                'version': version,
                'electron_version': electron_version,
                'node_requirement': node_requirement,
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
