"""CLI interface for Claude Desktop Linux builder."""

import sys
from pathlib import Path

import click

from . import __version__
from .builder import ClaudeDesktopBuilder
from .detector import ClaudeVersionDetector


@click.group()
@click.version_option(version=__version__, prog_name='claude-desktop-build')
def cli() -> None:
    """Build Claude Desktop for Linux from Windows installer."""
    pass


@cli.command()
@click.option('--force', is_flag=True, help='Force re-download of installer')
def info(force: bool) -> None:
    """Show information about the latest Claude Desktop version."""
    detector = ClaudeVersionDetector()
    
    try:
        detector.download_exe(force=force)
        metadata = detector.get_version_info()
        
        click.echo(f"Claude Desktop Version: {metadata['version']}")
        click.echo(f"Electron Version: {metadata['electron_version']}")
        click.echo(f"Node Requirement: {metadata.get('node_requirement', 'Not specified')}")
        click.echo(f"Application Name: {metadata['app_name']}")
        click.echo(f"Installer Hash: {metadata['exe_hash']}")
        
    except Exception as e:
        click.echo(f'Error: {e}', err=True)
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
        click.echo(f'Error: {e}', err=True)
        sys.exit(1)


@cli.command()
def clean() -> None:
    """Clean build artifacts and cache."""
    from .config import CACHE_DIR, PACKAGE_DIR, WORK_DIR
    
    dirs_to_clean = [WORK_DIR, PACKAGE_DIR]
    
    for dir_path in dirs_to_clean:
        if dir_path.exists():
            click.echo(f'Removing {dir_path}...')
            import shutil
            shutil.rmtree(dir_path)
    
    # Optionally clean cache
    if CACHE_DIR.exists():
        if click.confirm('Also remove download cache?'):
            click.echo(f'Removing {CACHE_DIR}...')
            import shutil
            shutil.rmtree(CACHE_DIR)
    
    click.echo('✓ Cleanup complete')


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()