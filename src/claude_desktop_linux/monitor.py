"""Version monitoring utilities for Claude Desktop Linux."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from .detector import ClaudeVersionDetector

logger = logging.getLogger(__name__)


class VersionMonitor:
    """Monitor Claude Desktop versions and manage updates."""

    def __init__(self, github_repo: str = 'leobuskin/claude-desktop-linux'):
        """Initialize the version monitor."""
        self.github_repo = github_repo
        self.detector = ClaudeVersionDetector()

    def get_latest_upstream_version(self) -> dict[str, Any]:
        """Get the latest version from Claude upstream."""
        return self.detector.get_version_info()

    def get_latest_built_version(self) -> str | None:
        """Get the latest version we've built from GitHub releases."""
        try:
            url = f'https://api.github.com/repos/{self.github_repo}/releases/latest'
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            # Extract version from tag name (v0.10.38 -> 0.10.38)
            tag = data.get('tag_name', '')
            return tag.lstrip('v') if tag else None
        except Exception as e:
            logger.error('Failed to fetch latest built version: %s', e)
            return None

    def get_all_built_versions(self) -> list[str]:
        """Get all versions we've built from GitHub releases."""
        try:
            url = f'https://api.github.com/repos/{self.github_repo}/releases'
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            versions = []
            for release in response.json():
                tag = release.get('tag_name', '')
                if tag:
                    versions.append(tag.lstrip('v'))
            
            return sorted(versions, reverse=True)
        except Exception as e:
            logger.error('Failed to fetch built versions: %s', e)
            return []

    def check_for_update(self) -> dict[str, Any]:
        """Check if a new version is available."""
        upstream = self.get_latest_upstream_version()
        built = self.get_latest_built_version()
        
        result = {
            'upstream_version': upstream['version'],
            'built_version': built,
            'update_available': False,
            'check_time': datetime.utcnow().isoformat(),
        }
        
        if built is None:
            result['update_available'] = True
            result['message'] = 'No built version found'
        elif upstream['version'] != built:
            result['update_available'] = True
            result['message'] = f'New version {upstream["version"]} available (current: {built})'
        else:
            result['message'] = 'Already up to date'
        
        return result

    def get_build_status(self) -> dict[str, Any]:
        """Get the current build status from GitHub Actions."""
        try:
            url = f'https://api.github.com/repos/{self.github_repo}/actions/workflows/auto-build.yml/runs'
            response = requests.get(url, params={'per_page': 1}, timeout=10)
            response.raise_for_status()
            
            runs = response.json().get('workflow_runs', [])
            if not runs:
                return {'status': 'unknown', 'message': 'No workflow runs found'}
            
            latest_run = runs[0]
            return {
                'status': latest_run['status'],
                'conclusion': latest_run.get('conclusion'),
                'created_at': latest_run['created_at'],
                'html_url': latest_run['html_url'],
            }
        except Exception as e:
            logger.error('Failed to fetch build status: %s', e)
            return {'status': 'error', 'message': str(e)}

    def save_status_report(self, output_path: Path | None = None) -> Path:
        """Save a comprehensive status report."""
        if output_path is None:
            output_path = Path('claude-desktop-status.json')
        
        report = {
            'check_time': datetime.utcnow().isoformat(),
            'update_check': self.check_for_update(),
            'build_status': self.get_build_status(),
            'built_versions': self.get_all_built_versions()[:10],  # Last 10 versions
        }
        
        output_path.write_text(json.dumps(report, indent=2))
        logger.info('Status report saved to %s', output_path)
        
        return output_path


def main() -> None:
    """CLI entry point for version monitoring."""
    import click
    
    @click.command()
    @click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
    @click.option('--repo', default='leobuskin/claude-desktop-linux', help='GitHub repository')
    def monitor(output_json: bool, repo: str) -> None:
        """Check Claude Desktop version status."""
        monitor = VersionMonitor(repo)
        status = monitor.check_for_update()
        
        if output_json:
            click.echo(json.dumps(status, indent=2))
        else:
            click.echo(f'Upstream version: {status["upstream_version"]}')
            click.echo(f'Built version: {status["built_version"] or "None"}')
            click.echo(f'Update available: {"Yes" if status["update_available"] else "No"}')
            if status.get('message'):
                click.echo(f'Status: {status["message"]}')
    
    monitor()


if __name__ == '__main__':
    main()