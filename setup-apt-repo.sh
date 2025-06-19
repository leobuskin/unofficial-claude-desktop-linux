#!/bin/bash
# Setup script for Claude Desktop Linux APT repository

set -e

REPO_OWNER="${REPO_OWNER:-leobuskin}"
REPO_NAME="${REPO_NAME:-claude-desktop-linux}"

echo "Setting up Claude Desktop Linux APT repository..."

# Add repository to sources
echo "deb https://${REPO_OWNER}.github.io/${REPO_NAME}/ stable main" | \
  sudo tee /etc/apt/sources.list.d/claude-desktop.list

echo "Repository added successfully!"
echo ""
echo "To install Claude Desktop, run:"
echo "  sudo apt update"
echo "  sudo apt install claude-desktop"
echo ""
echo "To update Claude Desktop in the future, just run:"
echo "  sudo apt update && sudo apt upgrade"