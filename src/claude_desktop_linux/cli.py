"""CLI interface for Claude Desktop Linux builder."""

import logging
import shutil
import sys
from pathlib import Path

import click

from . import __version__
from .builder import ClaudeDesktopBuilder
from .detector import ClaudeVersionDetector
from .monitor import VersionMonitor


@click.group()
@click.version_option(version=__version__, prog_name='claude-desktop-build')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.option('--debug', is_flag=True, help='Enable debug output')
def cli(verbose: bool, debug: bool) -> None:
    """Build Claude Desktop for Linux from Windows installer."""
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
def info(force: bool) -> None:
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

    except Exception as e:
        click.echo(f'Error: {e!s}', err=True)
        sys.exit(1)


@cli.command()
@click.option('--work-dir', type=click.Path(path_type=Path), help='Working directory for build')
@click.option('--output-dir', type=click.Path(path_type=Path), help='Output directory for built files')
@click.option('--skip-deps', is_flag=True, help='Skip dependency check')
def build(work_dir: Path | None, output_dir: Path | None, skip_deps: bool) -> None:
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

    except Exception as e:
        click.echo(f'Error: {e!s}', err=True)
        sys.exit(1)


@cli.command()
def clean() -> None:
    """Clean build artifacts and cache."""
    from .config import CACHE_DIR, PACKAGE_DIR, WORK_DIR

    dirs_to_clean = [WORK_DIR, PACKAGE_DIR]

    for dir_path in dirs_to_clean:
        if dir_path.exists():
            click.echo(f'Removing {dir_path}...')
            shutil.rmtree(dir_path)

    # Optionally clean cache
    if CACHE_DIR.exists() and click.confirm('Also remove download cache?'):
        click.echo(f'Removing {CACHE_DIR}...')
        shutil.rmtree(CACHE_DIR)

    click.echo('✓ Cleanup complete')


@cli.command()
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.option('--repo', default='leobuskin/claude-desktop-linux', help='GitHub repository')
def monitor(output_json: bool, repo: str) -> None:
    """Check Claude Desktop version status."""
    import json as json_module
    
    monitor = VersionMonitor(repo)
    status = monitor.check_for_update()
    
    if output_json:
        click.echo(json_module.dumps(status, indent=2))
    else:
        click.echo(f'Upstream version: {status["upstream_version"]}')
        click.echo(f'Built version: {status["built_version"] or "None"}')
        click.echo(f'Update available: {"Yes" if status["update_available"] else "No"}')
        if status.get('message'):
            click.echo(f'Status: {status["message"]}')


def main() -> None:
    """Entry point for the CLI."""
    cli(auto_envvar_prefix='CLAUDE_DESKTOP')


if __name__ == '__main__':
    main()
