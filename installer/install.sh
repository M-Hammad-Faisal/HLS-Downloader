#!/bin/bash

# HLS Downloader - Smart macOS/Linux Installer
# This script downloads, builds, and installs HLS Downloader automatically

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_status() {
    echo -e "${BLUE}[$1/8]${NC} $2"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        PYTHON_URL="https://www.python.org/ftp/python/3.11.7/python-3.11.7-macos11.pkg"
        INSTALL_DIR="$HOME/Applications/HLS-Downloader"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        PYTHON_URL="https://www.python.org/ftp/python/3.11.7/Python-3.11.7.tgz"
        INSTALL_DIR="$HOME/.local/share/HLS-Downloader"
    else
        print_error "Unsupported operating system: $OSTYPE"
        exit 1
    fi
}

# Check dependencies
check_dependencies() {
    print_status "1" "Checking system dependencies..."
    
    # Check for curl or wget
    if command -v curl >/dev/null 2>&1; then
        DOWNLOAD_CMD="curl -L -o"
    elif command -v wget >/dev/null 2>&1; then
        DOWNLOAD_CMD="wget -O"
    else
        print_error "Neither curl nor wget found. Please install one of them."
        exit 1
    fi
    
    # Check for unzip
    if ! command -v unzip >/dev/null 2>&1; then
        print_error "unzip not found. Please install unzip."
        exit 1
    fi
    
    print_success "System dependencies OK"
}

# Setup directories
setup_directories() {
    print_status "2" "Setting up installation directories..."
    
    TEMP_DIR=$(mktemp -d)
    
    # Remove existing installation
    if [ -d "$INSTALL_DIR" ]; then
        print_warning "Removing existing installation..."
        rm -rf "$INSTALL_DIR"
    fi
    
    mkdir -p "$INSTALL_DIR"
    print_success "Directories created"
}

# Install Python
install_python() {
    print_status "3" "Installing portable Python..."
    
    cd "$TEMP_DIR"
    
    if [[ "$OS" == "macos" ]]; then
        # For macOS, use pyenv or download portable Python
        if command -v brew >/dev/null 2>&1; then
            print_status "3" "Installing Python via Homebrew..."
            brew install python@3.11 >/dev/null 2>&1 || true
            PYTHON_CMD="python3.11"
        else
            # Use system Python or install via pyenv
            if command -v python3 >/dev/null 2>&1; then
                PYTHON_CMD="python3"
            else
                print_error "Python 3 not found. Please install Python 3.8+ or Homebrew."
                exit 1
            fi
        fi
    else
        # For Linux, compile Python from source
        print_status "3" "Downloading Python source..."
        $DOWNLOAD_CMD "python.tgz" "$PYTHON_URL"
        
        print_status "3" "Extracting and compiling Python..."
        tar -xzf python.tgz
        cd Python-3.11.7
        
        ./configure --prefix="$INSTALL_DIR/python" --enable-optimizations >/dev/null 2>&1
        make -j$(nproc) >/dev/null 2>&1
        make install >/dev/null 2>&1
        
        PYTHON_CMD="$INSTALL_DIR/python/bin/python3"
        cd "$TEMP_DIR"
    fi
    
    print_success "Python installed"
}

# Download source code
download_source() {
    print_status "4" "Downloading HLS Downloader source code..."
    
    cd "$TEMP_DIR"
    $DOWNLOAD_CMD "source.zip" "https://github.com/M-Hammad-Faisal/HLS-Downloader/archive/refs/heads/master.zip"
    
    unzip -q source.zip
    cd HLS-Downloader-master
    
    print_success "Source code downloaded"
}

# Install dependencies
install_dependencies() {
    print_status "5" "Installing Python dependencies..."
    
    # Install pip if needed
    if [[ "$OS" == "linux" ]]; then
        "$PYTHON_CMD" -m ensurepip --default-pip >/dev/null 2>&1 || true
    fi
    
    # Install requirements
    "$PYTHON_CMD" -m pip install -r requirements.txt >/dev/null 2>&1
    "$PYTHON_CMD" -m pip install pyinstaller >/dev/null 2>&1
    
    print_success "Dependencies installed"
}

# Install browsers
install_browsers() {
    print_status "6" "Installing Playwright browsers..."
    
    "$PYTHON_CMD" -m playwright install chromium >/dev/null 2>&1
    
    print_success "Browsers installed"
}

# Build application
build_app() {
    print_status "7" "Building HLS Downloader application..."
    
    if [[ "$OS" == "macos" ]]; then
        "$PYTHON_CMD" -m PyInstaller --onefile --windowed \
            --name "HLS-Downloader" \
            --icon "assets/icon.icns" \
            --add-data "assets:assets" \
            main.py >/dev/null 2>&1
    else
        "$PYTHON_CMD" -m PyInstaller --onefile \
            --name "HLS-Downloader" \
            --add-data "assets:assets" \
            main.py >/dev/null 2>&1
    fi
    
    if [ ! -f "dist/HLS-Downloader" ]; then
        print_error "Failed to build application"
        exit 1
    fi
    
    print_success "Application built"
}

# Finalize installation
finalize_installation() {
    print_status "8" "Finalizing installation..."
    
    # Copy application
    cp "dist/HLS-Downloader" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/HLS-Downloader"
    
    # Copy browsers
    if [[ "$OS" == "macos" ]]; then
        BROWSER_PATH="$HOME/Library/Caches/ms-playwright"
    else
        BROWSER_PATH="$HOME/.cache/ms-playwright"
    fi
    
    if [ -d "$BROWSER_PATH" ]; then
        cp -r "$BROWSER_PATH" "$INSTALL_DIR/browsers"
    fi
    
    # Create launcher script
    cat > "$INSTALL_DIR/run.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
export PLAYWRIGHT_BROWSERS_PATH="$(pwd)/browsers"
./HLS-Downloader "$@"
EOF
    chmod +x "$INSTALL_DIR/run.sh"
    
    # Create desktop entry (Linux) or app bundle (macOS)
    if [[ "$OS" == "linux" ]]; then
        create_desktop_entry
    else
        create_app_bundle
    fi
    
    print_success "Installation finalized"
}

# Create Linux desktop entry
create_desktop_entry() {
    DESKTOP_DIR="$HOME/.local/share/applications"
    mkdir -p "$DESKTOP_DIR"
    
    cat > "$DESKTOP_DIR/hls-downloader.desktop" << EOF
[Desktop Entry]
Name=HLS Downloader
Comment=Download HLS video streams
Exec=$INSTALL_DIR/run.sh
Icon=$INSTALL_DIR/assets/icon.png
Terminal=false
Type=Application
Categories=AudioVideo;Video;
EOF
    
    # Also create desktop shortcut
    if [ -d "$HOME/Desktop" ]; then
        cp "$DESKTOP_DIR/hls-downloader.desktop" "$HOME/Desktop/"
        chmod +x "$HOME/Desktop/hls-downloader.desktop"
    fi
}

# Create macOS app bundle
create_app_bundle() {
    APP_DIR="$HOME/Applications/HLS Downloader.app"
    mkdir -p "$APP_DIR/Contents/MacOS"
    mkdir -p "$APP_DIR/Contents/Resources"
    
    # Create Info.plist
    cat > "$APP_DIR/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>HLS Downloader</string>
    <key>CFBundleDisplayName</key>
    <string>HLS Downloader</string>
    <key>CFBundleIdentifier</key>
    <string>com.hlsdownloader.app</string>
    <key>CFBundleVersion</key>
    <string>2.1.2</string>
    <key>CFBundleExecutable</key>
    <string>HLS Downloader</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>icon</string>
</dict>
</plist>
EOF
    
    # Create launcher
    cat > "$APP_DIR/Contents/MacOS/HLS Downloader" << EOF
#!/bin/bash
cd "$INSTALL_DIR"
export PLAYWRIGHT_BROWSERS_PATH="$INSTALL_DIR/browsers"
exec ./HLS-Downloader
EOF
    chmod +x "$APP_DIR/Contents/MacOS/HLS Downloader"
    
    # Copy icon
    if [ -f "$TEMP_DIR/HLS-Downloader-master/assets/icon.icns" ]; then
        cp "$TEMP_DIR/HLS-Downloader-master/assets/icon.icns" "$APP_DIR/Contents/Resources/icon.icns"
    fi
}

# Cleanup
cleanup() {
    print_status "8" "Cleaning up temporary files..."
    
    # Remove temp directory
    rm -rf "$TEMP_DIR"
    
    # Remove Python installation if we compiled it
    if [[ "$OS" == "linux" ]] && [ -d "$INSTALL_DIR/python" ]; then
        rm -rf "$INSTALL_DIR/python"
    fi
    
    print_success "Cleanup completed"
}

# Main installation function
main() {
    echo "========================================"
    echo "HLS Downloader - Smart Installer"
    echo "========================================"
    echo
    
    detect_os
    echo "Detected OS: $OS"
    echo "Installing to: $INSTALL_DIR"
    echo
    
    check_dependencies
    setup_directories
    install_python
    download_source
    install_dependencies
    install_browsers
    build_app
    finalize_installation
    cleanup
    
    echo
    echo "========================================"
    echo "Installation completed successfully!"
    echo "========================================"
    echo
    echo "HLS Downloader has been installed to:"
    echo "$INSTALL_DIR"
    echo
    
    if [[ "$OS" == "macos" ]]; then
        echo "You can run it from:"
        echo "- Applications folder: 'HLS Downloader'"
        echo "- Direct: $INSTALL_DIR/run.sh"
    else
        echo "You can run it from:"
        echo "- Applications menu: 'HLS Downloader'"
        echo "- Desktop shortcut"
        echo "- Direct: $INSTALL_DIR/run.sh"
    fi
    
    echo
    echo "The application includes all necessary browsers and dependencies."
    echo "No additional setup required!"
    echo
}

# Error handling
trap 'print_error "Installation failed! Check the error above."; exit 1' ERR

# Run main function
main "$@"