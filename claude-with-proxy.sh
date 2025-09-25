#!/bin/bash
# Comprehensive Claude Desktop Proxy Launcher

PROXY_URL="http://192.168.193.10:8185"
APP_DIR="/usr/lib/claude-desktop"

# Method 1: Environment variables (for fetch/axios)
export HTTPS_PROXY="$PROXY_URL"
export HTTP_PROXY="$PROXY_URL"
export https_proxy="$PROXY_URL"
export http_proxy="$PROXY_URL"
export ALL_PROXY="$PROXY_URL"
export ELECTRON_EXTRA_LAUNCH_ARGS="--proxy-server=$PROXY_URL"
export NO_PROXY="localhost,127.0.0.1,*.local"

# Method 2: Electron command line flags
echo "Starting Claude Desktop with proxy: $PROXY_URL"

# Check if running under Wayland
WAYLAND_FLAGS=""
if [ -n "$WAYLAND_DISPLAY" ]; then
    WAYLAND_FLAGS="--ozone-platform-hint=auto --enable-features=WaylandWindowDecorations"
fi

# Launch with all proxy configurations
exec "$APP_DIR/node_modules/electron/dist/electron" \
    "$APP_DIR/app.asar" \
    --proxy-server="$PROXY_URL" \
    --proxy-bypass-list="localhost,127.0.0.1,*.local,<local>" \
    --ignore-certificate-errors \
    --disable-http2 \
    $WAYLAND_FLAGS \
    "$@"