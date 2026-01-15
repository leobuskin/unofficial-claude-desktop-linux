"""Templates for generated resource files."""

from pathlib import Path

LAUNCHER_SCRIPT = """\
#!/bin/bash
APP_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"

# Force Electron to report as packaged app (enables proper resource paths)
export ELECTRON_FORCE_IS_PACKAGED=true

# Build proxy arguments for Electron/Chromium
PROXY_ARGS=""

# Check for proxy environment variables (prefer lowercase, fallback to uppercase)
PROXY_URL="${https_proxy:-${HTTPS_PROXY:-${http_proxy:-${HTTP_PROXY:-}}}}"
NO_PROXY_LIST="${no_proxy:-${NO_PROXY:-}}"

if [ -n "$PROXY_URL" ]; then
    PROXY_ARGS="--proxy-server=$PROXY_URL"

    if [ -n "$NO_PROXY_LIST" ]; then
        PROXY_ARGS="$PROXY_ARGS --proxy-bypass-list=$NO_PROXY_LIST"
    fi
fi

# Fix for folder picker on older systems (Ubuntu 20.04 and similar)
# xdg-desktop-portal < 1.8.0 doesn't properly support openDirectory dialogs
# Setting required version to 4 forces fallback to native GTK dialogs
# See: https://github.com/electron/electron/issues/48356
XDG_PORTAL_FIX=""
if command -v dpkg &> /dev/null; then
    PORTAL_VERSION=$(dpkg -s xdg-desktop-portal 2>/dev/null | grep "^Version:" | sed 's/Version: //' | cut -d'-' -f1)
    if [ -n "$PORTAL_VERSION" ]; then
        REQUIRED_VERSION="1.8.0"
        if [ "$(printf '%s\\n' "$REQUIRED_VERSION" "$PORTAL_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
            XDG_PORTAL_FIX="--xdg-portal-required-version=4"
        fi
    fi
fi

# Launch with Wayland support if available
exec "$APP_DIR/lib/claude-desktop/node_modules/electron/dist/electron" \\
    "$APP_DIR/lib/claude-desktop/app.asar" \\
    ${WAYLAND_DISPLAY:+--ozone-platform-hint=auto --enable-features=WaylandWindowDecorations} \\
    $XDG_PORTAL_FIX \\
    $PROXY_ARGS "$@"
"""

DESKTOP_ENTRY = """\
[Desktop Entry]
Name=Claude
Comment=Unofficial Claude Desktop for Linux
Exec=claude-desktop %u
Icon=claude-desktop
Type=Application
Categories=Office;Utility;
Terminal=false
MimeTypes=x-scheme-handler/claude;
"""


def render_launcher_script() -> str:
    """Render the launcher shell script."""
    return LAUNCHER_SCRIPT


def render_desktop_entry() -> str:
    """Render the .desktop file."""
    return DESKTOP_ENTRY


def write_resources(output_dir: Path) -> None:
    """Write all generated resource files to the output directory.

    Args:
        output_dir: Base output directory (e.g., ./claude-desktop)

    """
    # Create bin directory and launcher script
    bin_dir = output_dir / 'bin'
    bin_dir.mkdir(parents=True, exist_ok=True)
    launcher = bin_dir / 'claude-desktop'
    launcher.write_text(render_launcher_script())
    launcher.chmod(0o755)

    # Create desktop entry
    apps_dir = output_dir / 'share' / 'applications'
    apps_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = apps_dir / 'claude-desktop.desktop'
    desktop_file.write_text(render_desktop_entry())
