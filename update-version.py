#!/usr/bin/env python3
"""Update version in __init__.py based on latest Claude Desktop version."""

import sys
from pathlib import Path

# Add src to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from claude_desktop_linux.detector import ClaudeVersionDetector


def update_version():
    """Update the version in __init__.py."""
    detector = ClaudeVersionDetector()
    
    try:
        info = detector.get_version_info()
        new_version = info['version']
        
        init_file = Path('src/claude_desktop_linux/__init__.py')
        content = init_file.read_text()
        
        # Update version
        import re
        new_content = re.sub(
            r"__version__ = ['\"][\d.]+['\"]",
            f"__version__ = '{new_version}'",
            content
        )
        
        if new_content != content:
            init_file.write_text(new_content)
            print(f"Updated version to {new_version}")
        else:
            print(f"Version already up to date: {new_version}")
            
    except Exception as e:
        print(f"Error updating version: {e}")
        sys.exit(1)


if __name__ == '__main__':
    update_version()