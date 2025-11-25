"""CLI interface for Claude Desktop Linux builder."""

import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path

import click

from . import __version__
from .builder import ClaudeDesktopBuilder
from .config import CACHE_DIR, PACKAGE_DIR, WORK_DIR
from .sources import get_source_handler


@click.group()
@click.version_option(version=__version__, prog_name='claude-desktop-build')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.option('--debug', is_flag=True, help='Enable debug output')
def cli(*, verbose: bool, debug: bool) -> None:
    """Build Claude Desktop for Linux from Windows or Mac installer."""
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
@click.option(
    '--source', '-s',
    type=click.Choice(['windows', 'macos']),
    default='windows',
    help='Source platform to build from',
)
@click.option('--work-dir', type=click.Path(path_type=Path), help='Working directory for build')
@click.option('--output-dir', type=click.Path(path_type=Path), help='Output directory for built files')
@click.option('--skip-deps', is_flag=True, help='Skip dependency check')
@click.option('--no-download', is_flag=True, help='Do not download installer if not found')
@click.option('--force-download', is_flag=True, help='Force re-download even if cached')
@click.option(
    '--patch-claude-code-platforms',
    is_flag=True,
    help='Enable Linux platform support in Claude Code mode',
)
def build(  # noqa: PLR0913
    source: str,
    work_dir: Path | None,
    output_dir: Path | None,
    *,
    skip_deps: bool,
    no_download: bool,
    force_download: bool,
    patch_claude_code_platforms: bool,
) -> None:
    """Build Claude Desktop for Linux.

    By default, builds from the Windows installer. Use --source macos to build
    from the Mac DMG instead (recommended for Claude Code support).
    """
    builder = ClaudeDesktopBuilder(
        source=source,
        patch_claude_code_platforms=patch_claude_code_platforms,
    )

    if work_dir:
        builder.work_dir = work_dir
    if output_dir:
        builder.output_dir = output_dir

    try:
        if not skip_deps:
            builder.check_dependencies()

        package = builder.build(
            download=not no_download,
            force_download=force_download,
        )

        if package:
            click.echo(f'Package built: {package}')
            click.echo('Install with:')
            if package.suffix == '.deb':
                click.echo(f'  sudo dpkg -i {package}')
            else:
                click.echo(f'  sudo rpm -i {package}')

    except (OSError, RuntimeError) as e:
        click.echo(f'Error: {e!s}', err=True)
        sys.exit(1)


@cli.command()
@click.option(
    '--source', '-s',
    type=click.Choice(['windows', 'macos']),
    default='windows',
    help='Source platform',
)
@click.option('--force', is_flag=True, help='Force re-download of installer')
def info(source: str, *, force: bool) -> None:
    """Show information about the latest Claude Desktop version."""
    handler = get_source_handler(source)

    try:
        if not handler.has_installer() or force:
            click.echo(f'Downloading {source} installer...')
            handler.download(force=force)

        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            resources_dir = handler.extract(work_dir)
            metadata = handler.extract_metadata(resources_dir)

        click.echo(f'Source: {source}')
        click.echo(f'Claude Desktop Version: {metadata["version"]}')
        click.echo(f'Electron Version: {metadata["electron_version"]}')
        click.echo(f'Application Name: {metadata.get("app_name", "Claude")}')

        if 'bundle_id' in metadata:
            click.echo(f'Bundle ID: {metadata["bundle_id"]}')

    except (OSError, RuntimeError, KeyError) as e:
        click.echo(f'Error: {e!s}', err=True)
        sys.exit(1)


@cli.command()
@click.option(
    '--source', '-s',
    type=click.Choice(['windows', 'macos']),
    default='windows',
    help='Source platform to download',
)
@click.option('--force', is_flag=True, help='Force re-download even if cached')
@click.option('--output', '-o', type=click.Path(path_type=Path), help='Output path for installer')
def download(source: str, *, force: bool, output: Path | None) -> None:
    """Download the installer file."""
    handler = get_source_handler(source)

    try:
        click.echo(f'Downloading {source} installer...')
        installer_path = handler.download(force=force)

        if output:
            shutil.copy2(installer_path, output)
            click.echo(f'Installer saved to: {output}')
        else:
            click.echo(f'Installer cached at: {installer_path}')

        click.echo('Download complete!')

    except (OSError, RuntimeError) as e:
        click.echo(f'Error: {e!s}', err=True)
        sys.exit(1)


@cli.command()
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
def compare(*, output_json: bool) -> None:
    """Compare Windows and Mac Claude Desktop versions."""
    results: dict[str, dict[str, str]] = {}

    for source in ['windows', 'macos']:
        click.echo(f'Checking {source} version...')
        try:
            handler = get_source_handler(source)
            if not handler.has_installer():
                handler.download()

            with tempfile.TemporaryDirectory() as tmpdir:
                work_dir = Path(tmpdir)
                resources_dir = handler.extract(work_dir)
                metadata = handler.extract_metadata(resources_dir)

            results[source] = {
                'version': metadata['version'],
                'electron': metadata['electron_version'],
            }

        except (OSError, RuntimeError, KeyError) as e:
            results[source] = {'error': str(e)}

    if output_json:
        click.echo(json.dumps(results, indent=2))
    else:
        click.echo()
        for source, data in results.items():
            click.echo(f'{source.capitalize()} version:')
            if 'error' in data:
                click.echo(f'  Error: {data["error"]}')
            else:
                click.echo(f'  Version: {data["version"]}')
                click.echo(f'  Electron: {data["electron"]}')
            click.echo()

        # Recommendation
        if 'error' not in results.get('windows', {}) and 'error' not in results.get('macos', {}):
            win_ver = results['windows']['version']
            mac_ver = results['macos']['version']

            click.echo('Recommendation:')
            if mac_ver > win_ver:
                click.echo('  Use --source macos (newer version)')
            elif mac_ver < win_ver:
                click.echo('  Use --source windows (newer version)')
            else:
                click.echo('  Both sources have the same version')
                click.echo('  Use --source macos for better Claude Code support')


@cli.command('check-update')
@click.option(
    '--source', '-s',
    type=click.Choice(['windows', 'macos']),
    help='Only check specific source',
)
def check_update(source: str | None) -> None:
    """Check for new versions without downloading full installer."""
    sources = [source] if source else ['windows', 'macos']

    for src in sources:
        handler = get_source_handler(src)
        click.echo(f'{src.capitalize()}:')

        try:
            version = handler.get_latest_version()
            if version:
                click.echo(f'  Latest version: {version}')
            else:
                click.echo('  Could not determine version')
        except (OSError, RuntimeError) as e:
            click.echo(f'  Error: {e!s}')

        click.echo()


@cli.command()
def clean() -> None:
    """Clean build artifacts and cache."""
    dirs_to_clean = [WORK_DIR, PACKAGE_DIR]

    for dir_path in dirs_to_clean:
        if dir_path.exists():
            click.echo(f'Removing {dir_path}...')
            shutil.rmtree(dir_path)

    if CACHE_DIR.exists() and click.confirm('Also remove download cache?'):
        click.echo(f'Removing {CACHE_DIR}...')
        shutil.rmtree(CACHE_DIR)

    click.echo('Cleanup complete')


def main() -> None:
    """Entry point for the CLI."""
    cli(auto_envvar_prefix='CLAUDE_DESKTOP')


if __name__ == '__main__':
    main()
