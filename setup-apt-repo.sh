#!/bin/bash
# Claude Desktop Linux - Installation Notice

set -e

REPO_OWNER="${REPO_OWNER:-leobuskin}"
REPO_NAME="${REPO_NAME:-claude-desktop-linux}"

echo "Claude Desktop Linux Installation"
echo "=================================="
echo ""
echo "Due to GitHub's file size limitations, we cannot host packages in an APT repository."
echo "Please download packages directly from GitHub Releases."
echo ""
echo "To download the latest version:"
echo "  wget https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/latest/download/claude-desktop_VERSION_amd64.deb"
echo "  sudo dpkg -i claude-desktop_*.deb"
echo ""
echo "To get notified of new releases:"
echo "  Visit https://github.com/${REPO_OWNER}/${REPO_NAME}"
echo "  Click 'Watch' → 'Custom' → 'Releases'"
echo ""
echo "For more information, see:"
echo "  https://github.com/${REPO_OWNER}/${REPO_NAME}/releases"