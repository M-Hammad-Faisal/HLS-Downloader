#!/bin/bash

echo "========================================"
echo " HLS Video Downloader - Smart Installer"
echo "========================================"
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed!"
    echo "Please install Python 3.8 or higher:"
    echo "  - macOS: brew install python3 or download from https://python.org"
    echo "  - Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "  - CentOS/RHEL: sudo yum install python3 python3-pip"
    echo
    exit 1
fi

# Check Python version
python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "ERROR: Python $python_version found, but Python $required_version or higher is required!"
    exit 1
fi

echo "Python $python_version found. Starting installation..."
echo

# Run the Python installer
python3 installer.py

if [ $? -ne 0 ]; then
    echo
    echo "Installation failed!"
    exit 1
fi

echo
echo "Installation completed successfully!"
echo "You can now close this terminal."