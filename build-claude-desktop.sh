#!/bin/bash
set -euo pipefail

# Configuration
CLAUDE_VERSION="0.7.9"
ELECTRON_VERSION="34.0.0"  # Electron version that matches Claude Desktop
CLAUDE_HASH="sha256-raoKgJu55g7mmZ4K+eX7YWkXGHYVcFBm5qQWk+p9LE0="
CLAUDE_URL="https://storage.googleapis.com/osprey-downloads-c02f6a0d-347c-492b-a752-3e0651722e97/nest-win-x64/Claude-Setup-x64.exe"
WORK_DIR="$(pwd)/build"
CACHE_DIR="$(pwd)/.cache/downloads"
OUTPUT_DIR="$(pwd)/claude-desktop"
PACKAGE_DIR="$(pwd)/packages"

# Package definitions
DNF_PACKAGES="p7zip p7zip-plugins nodejs rust cargo ImageMagick icoutils"
DEBIAN_PACKAGES="p7zip-full nodejs cargo rustc imagemagick icoutils"

# Logging functions
log_info() {
    echo -e "ℹ️ \033[0;32m$1\033[0m"
}

log_error() {
    echo -e "❌ \033[0;31m$1\033[0m" >&2
}

log_warning() {
    echo -e "⚠️ \033[0;33m$1\033[0m"
}

log_success() {
    echo -e "✅ \033[0;32m$1\033[0m"
}

# Error handling
handle_error() {
    log_error "An error occurred on line $1"
    exit 1
}

trap 'handle_error $LINENO' ERR

# Detect package manager and set appropriate commands/packages
detect_package_manager() {
    if command -v dnf >/dev/null 2>&1; then
        log_info "DNF-based system detected"
        PKG_MANAGER="dnf"
        PKG_INSTALL="sudo dnf install -y"
        PACKAGES="$DNF_PACKAGES"
        BUILD_PACKAGE="build_rpm"
    elif command -v apt-get >/dev/null 2>&1; then
        log_info "Debian-based system detected"
        PKG_MANAGER="apt"
        PKG_INSTALL="sudo apt-get install -y"
        PACKAGES="$DEBIAN_PACKAGES"
        BUILD_PACKAGE="build_deb"
    else
        log_error "Unsupported package manager. This script supports dnf and apt (Debian/Ubuntu)"
        exit 1
    fi
}

# Check for required dependencies
check_dependencies() {
    local missing=()
    
    # Common dependencies
    local deps=("7z" "pnpm" "node" "cargo" "rustc" "wrestool" "icotool" "convert")
    
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" >/dev/null 2>&1; then
            missing+=("$dep")
        fi
    done
    
    if [ ${#missing[@]} -ne 0 ]; then
        log_warning "Missing required dependencies: ${missing[*]}"
        log_info "Installing dependencies..."
        
        if [ "$PKG_MANAGER" = "apt" ]; then
            sudo apt-get update
        fi
        
        $PKG_INSTALL $PACKAGES
        
        # Install pnpm and ensure it's available
        if ! command -v pnpm >/dev/null 2>&1; then
            curl -fsSL https://get.pnpm.io/install.sh | sh -
            export PNPM_HOME="$HOME/.local/share/pnpm"
            case ":$PATH:" in
                *":$PNPM_HOME:"*) ;;
                *) export PATH="$PNPM_HOME:$PATH" ;;
            esac
        fi
    fi

    # Install electron and asar as dev dependencies if not already installed
    if [ ! -d "node_modules/electron" ] || [ ! -d "node_modules/@electron/asar" ]; then
        log_info "Installing dev dependencies..."
        pnpm install -D electron@$ELECTRON_VERSION @electron/asar@latest
    fi
}

# Create and setup the native module
setup_native_module() {
    log_info "Setting up native module..."
    mkdir -p "$WORK_DIR/native-module"
    cd "$WORK_DIR/native-module"
    
    # Create Cargo.toml
    cat > Cargo.toml << 'EOF'
[package]
name = "claude-native"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]

[dependencies]
napi = { version = "2.14.1", default-features = false, features = ["napi4"] }
napi-derive = "2.14.1"
EOF

    # Create src/lib.rs with native bindings
    mkdir -p src
    cat > src/lib.rs << 'EOF'
#![deny(clippy::all)]

#[macro_use]
extern crate napi_derive;

#[napi]
pub fn get_windows_version() -> String {
    "10.0.0".to_string()
}

#[napi]
pub fn set_window_effect() {}

#[napi]
pub fn remove_window_effect() {}

#[napi]
pub fn get_is_maximized() -> bool {
    false
}

#[napi]
pub fn flash_frame() {}

#[napi]
pub fn clear_flash_frame() {}

#[napi]
pub fn show_notification() {}

#[napi]
pub fn set_progress_bar() {}

#[napi]
pub fn clear_progress_bar() {}

#[napi]
pub fn set_overlay_icon() {}

#[napi]
pub fn clear_overlay_icon() {}

#[napi]
pub enum KeyboardKey {
    Backspace = 43,
    Tab = 280,
    Enter = 261,
    Shift = 272,
    Control = 61,
    Alt = 40,
    CapsLock = 56,
    Escape = 85,
    Space = 276,
    PageUp = 251,
    PageDown = 250,
    End = 83,
    Home = 154,
    LeftArrow = 175,
    UpArrow = 282,
    RightArrow = 262,
    DownArrow = 81,
    Delete = 79,
    Meta = 187
}
EOF

    # Create package.json
    cat > package.json << EOF
{
  "name": "claude-native",
  "version": "0.1.0",
  "main": "index.js",
  "napi": {
    "name": "claude-native",
    "triples": {
      "defaults": false,
      "additional": [
        "x86_64-unknown-linux-gnu"
      ]
    }
  },
  "scripts": {
    "build": "napi build --platform --release"
  },
  "devDependencies": {
    "@napi-rs/cli": "^2.18.4"
  }
}
EOF

    log_info "Building native module..."
    pnpm install
    pnpm run build

    if [ ! -f "claude-native.linux-x64-gnu.node" ]; then
        log_error "Native module build failed - output file not found"
        exit 1
    fi
}

# Download and extract the Windows client
download_and_extract() {
    log_info "Downloading Claude Desktop..."
    mkdir -p "$WORK_DIR"
    mkdir -p "$CACHE_DIR"
    cd "$WORK_DIR"
    
    LOCAL_FILE="${CACHE_DIR}/Claude-Setup-x64-${CLAUDE_VERSION}.exe"
    
    if [ -f "$LOCAL_FILE" ]; then
        CURRENT_HASH=$(openssl dgst -sha256 -binary "$LOCAL_FILE" | openssl base64 | sed 's/^/sha256-/')
        if [ "$CURRENT_HASH" = "$CLAUDE_HASH" ]; then
            log_info "Using cached file with correct hash..."
        else
            log_warning "Cache hash mismatch, redownloading..."
            wget "$CLAUDE_URL" -O "$LOCAL_FILE"
        fi
    else
        log_info "Downloading to cache..."
        wget "$CLAUDE_URL" -O "$LOCAL_FILE"
    fi
    
    # Verify hash after download
    DOWNLOAD_HASH=$(openssl dgst -sha256 -binary "$LOCAL_FILE" | openssl base64 | sed 's/^/sha256-/')
    if [ "$DOWNLOAD_HASH" != "$CLAUDE_HASH" ]; then
        log_error "Hash verification failed! Expected: $CLAUDE_HASH, Got: $DOWNLOAD_HASH"
        exit 1
    fi
    
    log_info "Extracting from cache..."
    cp "$LOCAL_FILE" ./Claude-Setup.exe
    7z x -y "./Claude-Setup.exe"
    rm "./Claude-Setup.exe"
    
    NUPKG_FILE=$(find . -name "*.nupkg" | head -n 1)
    7z x -y "$NUPKG_FILE"
}

# Process icons
process_icons() {
    log_info "Processing icons..."
    cd "$WORK_DIR"
    
    wrestool -x -t 14 "lib/net45/claude.exe" -o claude.ico
    icotool -x claude.ico
    
    # Process icons for both package and local installation
    for install_dir in "$OUTPUT_DIR" "$WORK_DIR/package-root/usr"; do
        mkdir -p "$install_dir/share/icons/hicolor"
        for size in 16 24 32 48 64 256; do
            icon_dir="$install_dir/share/icons/hicolor/${size}x${size}/apps"
            mkdir -p "$icon_dir"
            convert "claude_*${size}x${size}x32.png" "$icon_dir/claude.png"
        done
    done
}

# Process app.asar
process_asar() {
    log_info "Processing app.asar..."
    cd "$WORK_DIR"

    # Ensure electron is installed in the package-root directory
    if [ ! -d "package-root/usr/lib/claude-desktop/node_modules/electron" ]; then
        mkdir -p "package-root/usr/lib/claude-desktop"
        cd "package-root/usr/lib/claude-desktop"
        pnpm init
        pnpm install -D electron@$ELECTRON_VERSION @electron/asar@latest
        cd "$WORK_DIR"
    fi
    
    for target_dir in "$OUTPUT_DIR" "$WORK_DIR/package-root/usr"; do
        mkdir -p "$target_dir/lib/claude-desktop"
        cp "lib/net45/resources/app.asar" "$target_dir/lib/claude-desktop/"
        
        # Create unpacked directory but don't copy Windows native modules
        mkdir -p "$target_dir/lib/claude-desktop/app.asar.unpacked/node_modules/claude-native"
        
        # Copy our Linux native module
        cp "$WORK_DIR/native-module/claude-native.linux-x64-gnu.node" \
            "$target_dir/lib/claude-desktop/app.asar.unpacked/node_modules/claude-native/claude-native-binding.node"
        
        # Copy electron only if it's not already there
        if [ "$target_dir" != "$WORK_DIR/package-root/usr" ]; then
            mkdir -p "$target_dir/lib/claude-desktop/node_modules"
            cp -r "package-root/usr/lib/claude-desktop/node_modules/electron" "$target_dir/lib/claude-desktop/node_modules/"
        fi
    done
}

# Create desktop entry
create_desktop_entry() {
    for install_dir in "$OUTPUT_DIR" "$WORK_DIR/package-root/usr"; do
        mkdir -p "$install_dir/share/applications"
        cat > "$install_dir/share/applications/claude-desktop.desktop" << EOF
[Desktop Entry]
Name=Claude
Exec=claude-desktop %u
Icon=claude
Type=Application
Terminal=false
Categories=Office;Utility;
MimeType=x-scheme-handler/claude
StartupWMClass=Claude
EOF
    done
}

# Create launcher script
create_launcher() {
    for install_dir in "$OUTPUT_DIR" "$WORK_DIR/package-root/usr"; do
        mkdir -p "$install_dir/bin"
        cat > "$install_dir/bin/claude-desktop" << EOF
#!/bin/bash
"\${INSTALL_PREFIX:-/usr}/lib/claude-desktop/node_modules/electron/dist/electron" "\${INSTALL_PREFIX:-/usr}/lib/claude-desktop/app.asar" \
    \${WAYLAND_DISPLAY:+--ozone-platform-hint=auto --enable-features=WaylandWindowDecorations} "\$@"
EOF
        chmod +x "$install_dir/bin/claude-desktop"
    done
}

# Build DEB package
build_deb() {
    log_info "Building DEB package..."
    mkdir -p "$WORK_DIR/package-root/DEBIAN"
    
    cat > "$WORK_DIR/package-root/DEBIAN/control" << EOF
Package: claude-desktop
Version: $CLAUDE_VERSION
Architecture: amd64
Maintainer: Claude Desktop Linux Maintainers
Depends: nodejs
Description: Claude Desktop for Linux
 Claude is an AI assistant from Anthropic.
 This package provides the desktop interface for Claude.
EOF

    mkdir -p "$PACKAGE_DIR"
    dpkg-deb --build "$WORK_DIR/package-root" "$PACKAGE_DIR/claude-desktop_${CLAUDE_VERSION}_amd64.deb"
    log_success "DEB package created at $PACKAGE_DIR/claude-desktop_${CLAUDE_VERSION}_amd64.deb"
}

# Build RPM package
build_rpm() {
    log_info "Building RPM package..."
    mkdir -p "$WORK_DIR/rpmbuild"/{SPECS,SOURCES}
    
    # Create spec file
    cat > "$WORK_DIR/rpmbuild/SPECS/claude-desktop.spec" << EOF
Name:           claude-desktop
Version:        $CLAUDE_VERSION
Release:        1%{?dist}
Summary:        Claude Desktop for Linux
License:        Proprietary
URL:            https://anthropic.com

BuildRequires:  nodejs

%description
Claude is an AI assistant from Anthropic.
This package provides the desktop interface for Claude.

%install
cp -r %{_sourcedir}/package-root/* %{buildroot}/

%files
/usr/bin/claude-desktop
/usr/lib/claude-desktop
/usr/share/applications/claude-desktop.desktop
/usr/share/icons/hicolor/*/apps/claude.png
EOF

    # Build RPM
    rpmbuild -bb --define "_topdir $WORK_DIR/rpmbuild" \
             --define "_sourcedir $WORK_DIR" \
             "$WORK_DIR/rpmbuild/SPECS/claude-desktop.spec"
    
    mkdir -p "$PACKAGE_DIR"
    mv "$WORK_DIR/rpmbuild/RPMS/x86_64/"*.rpm "$PACKAGE_DIR/"
    log_success "RPM package created in $PACKAGE_DIR"
}

# Create installation instructions
create_install_instructions() {
    log_info "Build complete!"
    
    if [ -d "$PACKAGE_DIR" ]; then
        log_info "Package installation:"
        if [ "$PKG_MANAGER" = "dnf" ]; then
            echo "sudo dnf install $PACKAGE_DIR/claude-desktop-${CLAUDE_VERSION}-1.*.rpm"
        else
            echo "sudo dpkg -i $PACKAGE_DIR/claude-desktop_${CLAUDE_VERSION}_amd64.deb"
        fi
    fi
    
    log_info "Local installation available in: $OUTPUT_DIR"
    echo "To install locally, run:"
    echo "mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons"
    echo "cp -r $OUTPUT_DIR/* ~/.local/"
    echo "xdg-mime default claude-desktop.desktop x-scheme-handler/claude"
}

# Main execution
main() {
    log_info "Building Claude Desktop for Linux..."
    
    # Check for root
    if [ "$EUID" -eq 0 ] && [ -z "${ALLOW_ROOT:-}" ]; then
        log_error "Please do not run this script as root"
        exit 1
    fi
    
    detect_package_manager
    check_dependencies
    
    # Create clean build environment
    rm -rf "$WORK_DIR" "$OUTPUT_DIR" "$PACKAGE_DIR"
    mkdir -p "$WORK_DIR/package-root/usr" "$OUTPUT_DIR" "$PACKAGE_DIR"
    
    setup_native_module
    download_and_extract
    process_icons
    process_asar
    create_desktop_entry
    create_launcher
    
    # Build distribution package if supported
    if [ -n "${BUILD_PACKAGE:-}" ]; then
        $BUILD_PACKAGE
    fi
    
    create_install_instructions
    log_success "Build completed successfully!"
}

main "$@"
