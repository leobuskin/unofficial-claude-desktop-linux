"""Download helper for Claude Desktop installers with Cloudflare bypass."""

import json
import logging
import re
from pathlib import Path

import requests
from playwright.sync_api import Request, sync_playwright
from playwright_stealth import Stealth  # type: ignore[import-untyped]
from tqdm import tqdm

logger = logging.getLogger(__name__)


def extract_version_from_url(url: str) -> str | None:
    """Extract version from download URL.

    The resolved URL contains version info like:
    - https://downloads.claude.ai/releases/win32/x64/1.0.1217/Claude-...
    - https://downloads.claude.ai/releases/darwin/universal/1.0.1217/Claude-...

    Args:
        url: The resolved download URL

    Returns:
        Version string or None if not found

    """
    # Match version number in path (e.g., /1.0.1217/)
    match = re.search(r'/(\d+\.\d+\.\d+)/', url)
    if match:
        return match.group(1)
    return None


def resolve_cloudflare_url(url: str, timeout: int = 30000) -> str:
    """Resolve a Cloudflare-protected redirect URL using headless browser.

    Args:
        url: The redirect URL to resolve
        timeout: Timeout in milliseconds for page load

    Returns:
        The final resolved URL after all redirects

    """
    logger.info('Resolving Cloudflare-protected URL...')

    stealth = Stealth(
        navigator_platform_override='Linux x86_64',
        navigator_vendor_override='Google Inc.',
    )

    final_url = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        user_agent = (
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'
        )
        context = browser.new_context(
            user_agent=user_agent,
            accept_downloads=True,
        )
        page = context.new_page()

        # Apply stealth to avoid detection
        stealth.apply_stealth_sync(page)

        # Intercept requests to capture the final download URL
        def handle_request(request: Request) -> None:
            nonlocal final_url
            req_url = request.url
            # Check if this is the actual download URL (storage URL)
            if 'storage.googleapis.com' in req_url or req_url.endswith(('.exe', '.dmg')):
                final_url = req_url
                logger.info('Captured download URL: %s', req_url)

        page.on('request', handle_request)

        try:
            # Navigate - this will trigger the redirect chain
            page.goto(url, timeout=timeout, wait_until='domcontentloaded')
            page.wait_for_timeout(2000)
        except Exception as e:
            # Download starting is expected - we should have captured the URL
            if 'Download is starting' in str(e) and final_url:
                logger.info('Download triggered, URL captured successfully')
            else:
                # Try to get URL from page anyway
                if not final_url:
                    final_url = page.url
                if final_url == url:
                    raise

        if not final_url:
            final_url = page.url

        logger.info('Resolved to: %s', final_url)
        browser.close()

        return final_url


def get_cached_url(cache_dir: Path, cache_key: str) -> str | None:
    """Get cached resolved URL.

    Args:
        cache_dir: Directory containing cache files
        cache_key: Key to identify the cached URL (e.g., 'windows', 'mac')

    Returns:
        Cached URL or None if not found

    """
    url_cache_file = cache_dir / f'{cache_key}_url.json'
    if url_cache_file.exists():
        try:
            data: dict[str, str] = json.loads(url_cache_file.read_text())
            return data.get('url')
        except (json.JSONDecodeError, OSError):
            pass
    return None


def save_cached_url(cache_dir: Path, cache_key: str, url: str) -> None:
    """Save resolved URL to cache.

    Args:
        cache_dir: Directory to save cache file
        cache_key: Key to identify the cached URL
        url: The resolved URL to cache

    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    url_cache_file = cache_dir / f'{cache_key}_url.json'
    url_cache_file.write_text(json.dumps({'url': url}))


def download_file(
    url: str,
    dest_path: Path,
    *,
    resolve_cloudflare: bool = True,
    cache_dir: Path | None = None,
    cache_key: str | None = None,
) -> tuple[Path, str]:
    """Download a file, optionally resolving Cloudflare protection first.

    Args:
        url: URL to download from (may be Cloudflare-protected redirect)
        dest_path: Destination path for the downloaded file
        resolve_cloudflare: Whether to resolve Cloudflare redirects first
        cache_dir: Optional directory for URL caching
        cache_key: Optional key for URL cache (e.g., 'windows', 'mac')

    Returns:
        Tuple of (path to downloaded file, resolved download URL)

    """
    download_url = url

    if resolve_cloudflare:
        try:
            download_url = resolve_cloudflare_url(url)
            # Save resolved URL to cache for future validation
            if cache_dir and cache_key:
                save_cached_url(cache_dir, cache_key, download_url)
        except (OSError, RuntimeError) as e:
            logger.warning('Failed to resolve Cloudflare URL: %s', e)
            logger.info('Attempting direct download...')

    logger.info('Downloading from: %s', download_url)

    response = requests.get(download_url, stream=True, timeout=60)
    response.raise_for_status()

    total_size = int(response.headers.get('Content-Length', 0))

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with (
        dest_path.open('wb') as f,
        tqdm(total=total_size, unit='B', unit_scale=True, desc='Downloading') as pbar,
    ):
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            pbar.update(len(chunk))

    return dest_path, download_url


def get_latest_version(redirect_url: str) -> str | None:
    """Get the latest version by resolving the redirect URL.

    This only resolves the URL to extract the version, no download.

    Args:
        redirect_url: The Cloudflare-protected redirect URL

    Returns:
        Version string or None if not found

    """
    try:
        resolved_url = resolve_cloudflare_url(redirect_url)
        return extract_version_from_url(resolved_url)
    except (OSError, RuntimeError) as e:
        logger.warning('Failed to get latest version: %s', e)
        return None


def check_for_update(
    redirect_url: str,
    cache_dir: Path,
    cache_key: str,
) -> tuple[bool, str | None, str | None]:
    """Check if a new version is available by comparing resolved URLs.

    This resolves the redirect URL and compares with cached URL to detect updates
    without downloading the full file.

    Args:
        redirect_url: The Cloudflare-protected redirect URL
        cache_dir: Directory containing cache files
        cache_key: Key to identify the cached URL

    Returns:
        Tuple of (update_available, new_version, cached_version)

    """
    cached_url = get_cached_url(cache_dir, cache_key)
    cached_version = extract_version_from_url(cached_url) if cached_url else None

    try:
        resolved_url = resolve_cloudflare_url(redirect_url)
        new_version = extract_version_from_url(resolved_url)
    except (OSError, RuntimeError) as e:
        logger.warning('Failed to check for update: %s', e)
        return False, None, cached_version
    else:
        if cached_url and resolved_url == cached_url:
            logger.info('Cache is up to date (version %s)', cached_version)
            return False, new_version, cached_version

        logger.info('New version available: %s (cached: %s)', new_version, cached_version)
        return True, new_version, cached_version
