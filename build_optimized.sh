#!/bin/bash

# Build script for optimized HLS Downloader
# This script creates a smaller, optimized build of the application

echo "🚀 Starting optimized build process..."

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf dist/
rm -rf build/

# Install only Chromium browsers (not all browsers)
echo "📦 Installing only Chromium browsers..."
python -m playwright install chromium

# Check browser installation
echo "📊 Checking browser installation size..."
if [ -d ~/.cache/ms-playwright/ ]; then
    du -sh ~/.cache/ms-playwright/
else
    echo "Browser cache directory not found, checking alternative locations..."
    find ~ -name "*playwright*" -type d 2>/dev/null | head -5
fi

# Build with optimized spec
echo "🔨 Building with optimized PyInstaller spec..."
pyinstaller hls_downloader_optimized.spec

# Check build size
echo "📏 Checking build size..."
if [ -d "dist/HLS Downloader.app" ]; then
    echo "macOS App Bundle size:"
    du -sh "dist/HLS Downloader.app"
    
    echo "App Bundle contents:"
    du -sh "dist/HLS Downloader.app/Contents/"*
    
    # Ad-hoc sign the app
    echo "✍️ Signing the macOS app..."
    codesign --force --deep --sign - "dist/HLS Downloader.app"
    
    # Verify signature
    echo "🔍 Verifying signature..."
    codesign --verify --verbose "dist/HLS Downloader.app"
    
elif [ -d "dist/HLS Downloader" ]; then
    echo "Application directory size:"
    du -sh "dist/HLS Downloader"
fi

# Copy Playwright browsers to dist
echo "📋 Copying Playwright browsers..."
PLAYWRIGHT_CACHE_DIR=""

# Find the Playwright cache directory
if [ -d ~/.cache/ms-playwright/ ]; then
    PLAYWRIGHT_CACHE_DIR=~/.cache/ms-playwright/
elif [ -d ~/Library/Caches/ms-playwright/ ]; then
    PLAYWRIGHT_CACHE_DIR=~/Library/Caches/ms-playwright/
else
    echo "⚠️ Playwright cache directory not found, searching..."
    PLAYWRIGHT_CACHE_DIR=$(find ~ -name "*playwright*" -type d 2>/dev/null | grep -E "(cache|Cache)" | head -1)
fi

if [ -n "$PLAYWRIGHT_CACHE_DIR" ] && [ -d "$PLAYWRIGHT_CACHE_DIR" ]; then
    echo "Found Playwright cache at: $PLAYWRIGHT_CACHE_DIR"
    if [ "$(uname)" = "Darwin" ]; then
        # macOS
        mkdir -p "dist/HLS Downloader.app/Contents/Resources/pw-browsers"
        cp -r "$PLAYWRIGHT_CACHE_DIR"/* "dist/HLS Downloader.app/Contents/Resources/pw-browsers/" 2>/dev/null || echo "⚠️ No browsers to copy"
    else
        # Linux/Windows
        mkdir -p "dist/HLS Downloader/pw-browsers"
        cp -r "$PLAYWRIGHT_CACHE_DIR"/* "dist/HLS Downloader/pw-browsers/" 2>/dev/null || echo "⚠️ No browsers to copy"
    fi
else
    echo "⚠️ Could not find Playwright browsers. They may need to be installed manually."
fi

echo "✅ Optimized build complete!"

# Final size report
echo "📊 Final size report:"
if [ -d "dist/HLS Downloader.app" ]; then
    echo "Total app size: $(du -sh "dist/HLS Downloader.app" | cut -f1)"
    echo "Frameworks size: $(du -sh "dist/HLS Downloader.app/Contents/Frameworks" | cut -f1)"
    echo "Resources size: $(du -sh "dist/HLS Downloader.app/Contents/Resources" | cut -f1)"
    echo "Browsers size: $(du -sh "dist/HLS Downloader.app/Contents/Resources/pw-browsers" | cut -f1)"
elif [ -d "dist/HLS Downloader" ]; then
    echo "Total app size: $(du -sh "dist/HLS Downloader" | cut -f1)"
    echo "Browsers size: $(du -sh "dist/HLS Downloader/pw-browsers" | cut -f1)"
fi

echo "🎉 Build optimization complete! The application should now be significantly smaller."