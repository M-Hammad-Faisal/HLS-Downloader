#!/bin/bash

# HLS Downloader Smart Installer for macOS/Linux
# Target size: ~5-10MB instead of 800MB+

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo
    echo "========================================"
    echo "    HLS Downloader Smart Installer"
    echo "========================================"
    echo
    echo "This installer will:"
    echo "- Check for Python 3.8+"
    echo "- Download HLS Downloader"
    echo "- Set up environment"
    echo "- Install dependencies"
    echo "- Create application launcher"
    echo
    echo "Installation size: ~5-10MB (downloads ~50MB)"
    echo "Final app size: ~200MB (vs 800MB bundled)"
    echo
}

check_python() {
    print_status "Checking for Python..."
    
    # Try different Python commands
    for cmd in python3 python py; do
        if command -v $cmd >/dev/null 2>&1; then
            version=$($cmd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
            major=$(echo $version | cut -d. -f1)
            minor=$(echo $version | cut -d. -f2)
            
            if [ "$major" -ge 3 ] && [ "$minor" -ge 8 ]; then
                print_success "Python $version found with $cmd"
                PYTHON_CMD=$cmd
                return 0
            fi
        fi
    done
    
    print_error "Python 3.8+ is required but not found."
    echo
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "Please install Python from:"
        echo "1. https://python.org/downloads"
        echo "2. Or use Homebrew: brew install python3"
    else
        echo "Please install Python using your package manager:"
        echo "Ubuntu/Debian: sudo apt install python3 python3-pip"
        echo "CentOS/RHEL: sudo yum install python3 python3-pip"
        echo "Arch: sudo pacman -S python python-pip"
    fi
    echo
    exit 1
}

get_install_dir() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        INSTALL_DIR="$HOME/Applications/HLS Downloader"
    else
        # Linux
        INSTALL_DIR="$HOME/.local/share/hls-downloader"
    fi
}

download_installer() {
    print_status "Downloading installer script..."
    
    # Create installation directory
    mkdir -p "$INSTALL_DIR"
    
    # Download the Python installer script
    if command -v curl >/dev/null 2>&1; then
        curl -L -o "$INSTALL_DIR/install.py" "https://raw.githubusercontent.com/M-Hammad-Faisal/HLS-Downloader/master/installer/install.py"
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$INSTALL_DIR/install.py" "https://raw.githubusercontent.com/M-Hammad-Faisal/HLS-Downloader/master/installer/install.py"
    else
        print_error "Neither curl nor wget found. Please install one of them."
        exit 1
    fi
    
    if [ $? -ne 0 ]; then
        print_error "Failed to download installer script."
        print_error "Please check your internet connection."
        exit 1
    fi
    
    print_success "Installer script downloaded"
}

run_installer() {
    print_status "Running installation..."
    
    cd "$INSTALL_DIR"
    $PYTHON_CMD install.py
    
    if [ $? -ne 0 ]; then
        print_error "Installation failed."
        exit 1
    fi
}

main() {
    print_header
    
    # Ask for confirmation
    read -p "Do you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
    
    check_python
    get_install_dir
    
    print_status "Installing to: $INSTALL_DIR"
    
    download_installer
    run_installer
    
    echo
    echo "========================================"
    echo "    Installation Complete!"
    echo "========================================"
    echo
    print_success "HLS Downloader has been installed successfully."
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        print_status "You can find it in your Applications folder."
    else
        print_status "You can find it in your applications menu."
    fi
    echo
}

# Run main function
main "$@"