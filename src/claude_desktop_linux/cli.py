"""CLI interface for Claude Desktop Linux builder."""

import json
import logging
import shutil
import sys
from pathlib import Path

import click

from . import __version__
from .builder import ClaudeDesktopBuilder
from .config import CACHE_DIR, PACKAGE_DIR, WORK_DIR
from .detector import ClaudeVersionDetector
from .mac_builder import MacClaudeDesktopBuilder
from .mac_detector import MacDmgDetector
from .monitor import VersionMonitor


@click.group()
@click.version_option(version=__version__, prog_name='claude-desktop-build')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.option('--debug', is_flag=True, help='Enable debug output')
def cli(*, verbose: bool, debug: bool) -> None:
    """Build Claude Desktop for Linux from Windows or Mac installer."""
    # Set up logging
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s',
    )


@cli.command()
@click.option('--force', is_flag=True, help='Force re-download of installer')
def info(*, force: bool) -> None:
    """Show information about the latest Claude Desktop version."""
    detector = ClaudeVersionDetector()

    try:
        detector.download_exe(force=force)
        metadata = detector.get_version_info()

        click.echo(f'Claude Desktop Version: {metadata["version"]}')
        click.echo(f'Electron Version: {metadata["electron_version"]}')
        click.echo(f'Node Requirement: {metadata.get("node_requirement", "Not specified")}')
        click.echo(f'Application Name: {metadata["app_name"]}')
        click.echo(f'Installer Hash: {metadata["exe_hash"]}')

    except (OSError, RuntimeError, KeyError) as e:
        click.echo(f'Error: {e!s}', err=True)
        sys.exit(1)


@cli.command()
@click.option('--work-dir', type=click.Path(path_type=Path), help='Working directory for build')
@click.option('--output-dir', type=click.Path(path_type=Path), help='Output directory for built files')
@click.option('--skip-deps', is_flag=True, help='Skip dependency check')
def build(work_dir: Path | None, output_dir: Path | None, *, skip_deps: bool) -> None:
    """Build Claude Desktop for Linux."""
    builder = ClaudeDesktopBuilder()

    # Override directories if specified
    if work_dir:
        builder.work_dir = work_dir
    if output_dir:
        builder.output_dir = output_dir

    try:
        if not skip_deps:
            builder.check_dependencies()

        builder.build()

    except (OSError, RuntimeError) as e:
        click.echo(f'Error: {e!s}', err=True)
        sys.exit(1)


@cli.command()
def clean() -> None:
    """Clean build artifacts and cache."""
    dirs_to_clean = [WORK_DIR, PACKAGE_DIR]

    for dir_path in dirs_to_clean:
        if dir_path.exists():
            click.echo(f'Removing {dir_path}...')
            shutil.rmtree(dir_path)

    # Optionally clean cache
    if CACHE_DIR.exists() and click.confirm('Also remove download cache?'):
        click.echo(f'Removing {CACHE_DIR}...')
        shutil.rmtree(CACHE_DIR)

    click.echo('Cleanup complete')


@cli.command()
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.option('--repo', default='leobuskin/claude-desktop-linux', help='GitHub repository')
def monitor(*, output_json: bool, repo: str) -> None:
    """Check Claude Desktop version status."""
    mon = VersionMonitor(repo)
    status = mon.check_for_update()

    if output_json:
        click.echo(json.dumps(status, indent=2))
    else:
        click.echo(f'Upstream version: {status["upstream_version"]}')
        click.echo(f'Built version: {status["built_version"] or "None"}')
        click.echo(f'Update available: {"Yes" if status["update_available"] else "No"}')
        if status.get('message'):
            click.echo(f'Status: {status["message"]}')


# ============================================================================
# Mac-based build commands
# ============================================================================


@cli.command('mac-info')
@click.option('--force', is_flag=True, help='Force re-download of DMG')
@click.option('--dmg', type=click.Path(exists=True, path_type=Path), help='Path to DMG file')
def mac_info(*, force: bool, dmg: Path | None) -> None:
    """Show information about the Mac Claude Desktop version."""
    detector = MacDmgDetector(dmg)

    try:
        if not detector.has_dmg():
            click.echo('Downloading Mac DMG...')
            detector.download_dmg(force=force)
        elif force:
            click.echo('Re-downloading Mac DMG...')
            detector.download_dmg(force=True)

        metadata = detector.get_version_info()

        click.echo(f'Claude Desktop Version: {metadata["version"]}')
        click.echo(f'Electron Version: {metadata["electron_version"]}')
        click.echo(f'Node Requirement: {metadata.get("node_requirement", "Not specified")}')
        click.echo(f'Application Name: {metadata["app_name"]}')
        click.echo(f'Bundle ID: {metadata.get("bundle_id", "N/A")}')
        click.echo(f'Source: {metadata["source"]}')
        click.echo(f'DMG Hash: {metadata["dmg_hash"]}')

    except (OSError, RuntimeError, KeyError) as e:
        click.echo(f'Error: {e!s}', err=True)
        sys.exit(1)


@cli.command('mac-build')
@click.option('--work-dir', type=click.Path(path_type=Path), help='Working directory for build')
@click.option('--output-dir', type=click.Path(path_type=Path), help='Output directory for built files')
@click.option('--dmg', type=click.Path(exists=True, path_type=Path), help='Path to DMG file')
@click.option('--skip-deps', is_flag=True, help='Skip dependency check')
@click.option('--no-download', is_flag=True, help='Do not download DMG if not found')
def mac_build(
    work_dir: Path | None,
    output_dir: Path | None,
    dmg: Path | None,
    *,
    skip_deps: bool,
    no_download: bool,
) -> None:
    """Build Claude Desktop for Linux from Mac DMG.

    This uses the Mac version which is typically newer than Windows.
    The DMG will be downloaded automatically if not found locally.
    """
    builder = MacClaudeDesktopBuilder(dmg)

    # Override directories if specified
    if work_dir:
        builder.work_dir = work_dir
    if output_dir:
        builder.output_dir = output_dir

    try:
        if not skip_deps:
            builder.check_dependencies()

        builder.build(download=not no_download)

    except (OSError, RuntimeError) as e:
        click.echo(f'Error: {e!s}', err=True)
        sys.exit(1)


@cli.command('mac-download')
@click.option('--force', is_flag=True, help='Force re-download even if cached')
@click.option('--output', '-o', type=click.Path(path_type=Path), help='Output path for DMG')
def mac_download(*, force: bool, output: Path | None) -> None:
    """Download the Mac DMG file."""
    detector = MacDmgDetector()

    try:
        click.echo('Downloading Claude Desktop DMG...')
        dmg_path = detector.download_dmg(force=force)

        if output:
            shutil.copy2(dmg_path, output)
            click.echo(f'DMG saved to: {output}')
        else:
            click.echo(f'DMG cached at: {dmg_path}')

        click.echo('Download complete!')

    except (OSError, RuntimeError) as e:
        click.echo(f'Error: {e!s}', err=True)
        sys.exit(1)


@cli.command('compare')
def compare_versions() -> None:
    """Compare Windows and Mac Claude Desktop versions."""
    click.echo('Fetching version information...\n')

    # Windows version
    click.echo('Windows version:')
    try:
        win_detector = ClaudeVersionDetector()
        win_detector.download_exe()
        win_meta = win_detector.get_version_info()
        click.echo(f'  Version: {win_meta["version"]}')
        click.echo(f'  Electron: {win_meta["electron_version"]}')
    except (OSError, RuntimeError, KeyError) as e:
        click.echo(f'  Error: {e!s}')
        win_meta = None

    click.echo()

    # Mac version
    click.echo('Mac version:')
    try:
        mac_detector = MacDmgDetector()
        if not mac_detector.has_dmg():
            mac_detector.download_dmg()
        mac_meta = mac_detector.get_version_info()
        click.echo(f'  Version: {mac_meta["version"]}')
        click.echo(f'  Electron: {mac_meta["electron_version"]}')
    except (OSError, RuntimeError, KeyError) as e:
        click.echo(f'  Error: {e!s}')
        mac_meta = None

    click.echo()

    # Recommendation
    if win_meta and mac_meta:
        click.echo('Recommendation:')
        # Simple version comparison (Mac versions are like 1.0.1217)
        if mac_meta['version'] > win_meta['version']:
            click.echo('  Use Mac source (mac-build) - newer version available')
        elif mac_meta['version'] < win_meta['version']:
            click.echo('  Use Windows source (build) - newer version available')
        else:
            click.echo('  Both sources have the same version')


def main() -> None:
    """Entry point for the CLI."""
    cli(auto_envvar_prefix='CLAUDE_DESKTOP')


if __name__ == '__main__':
    main()
