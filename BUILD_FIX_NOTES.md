# Claude Desktop Linux Build Process - Fixed

## Problem Solved
The build process was hanging during the "Extracting version information..." step when using `7z` to extract the Windows installer.

## Root Cause
The `subprocess.run()` calls in `src/claude_desktop_linux/detector.py` were using `capture_output=True` without timeouts, causing the process to hang indefinitely when extracting large files.

## Fix Applied
Modified `src/claude_desktop_linux/detector.py` to add:
1. **Timeouts**: Added 60-second timeout for exe extraction, 30-second timeouts for other extractions
2. **Better error handling**: Added try/except blocks to catch TimeoutExpired and CalledProcessError
3. **Debug logging**: Added logging to track extraction progress
4. **Text mode**: Added `text=True` parameter for better output handling

## Complete Build Process

### Prerequisites
```bash
# System dependencies
sudo apt-get install p7zip-full npm nodejs python3-pip

# Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### Build Steps
1. **Initialize git submodules** (required for native module build):
   ```bash
   git submodule update --init --recursive
   ```

2. **Run the build**:
   ```bash
   source venv/bin/activate
   claude-desktop-build build
   ```

3. **Install the package**:
   ```bash
   sudo dpkg -i packages/claude-desktop_*.deb
   ```

## Running with Proxy
Since the app requires a proxy to connect, use the provided launcher:
```bash
./claude-with-proxy.sh
```

Or modify the proxy URL in the script if needed:
```bash
PROXY_URL="http://your-proxy:port"
```

## Build Output
The build creates:
- Debian package: `packages/claude-desktop_VERSION_amd64.deb`
- Native module: `patchy-cnb` (built from Rust)
- Patched Electron app with Linux-specific modifications

## Key Components
- **detector.py**: Downloads and extracts version info from Windows installer
- **builder.py**: Main build orchestration
- **native-module/**: Rust-based native bindings for Electron
- **claude-desktop-linux-flake/**: Git submodule with additional build resources