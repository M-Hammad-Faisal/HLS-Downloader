#!/usr/bin/env python3
"""
Build complete installer bundle for HLS Video Downloader.
Creates a self-contained installer that includes all dependencies.
"""

import os
import sys
import platform
import subprocess
import shutil
import zipfile
import tempfile
from pathlib import Path

class InstallerBundleBuilder:
    def __init__(self):
        self.system = platform.system().lower()
        self.machine = platform.machine().lower()
        self.version = "1.0.0"
        self.app_name = "HLS-Video-Downloader"
        self.current_dir = Path.cwd()
        self.build_dir = self.current_dir / "build_bundle"
        self.dist_dir = self.current_dir / "dist_bundle"
        
    def log(self, message, level="INFO"):
        """Log build progress."""
        print(f"[{level}] {message}")
    
    def clean_build_dirs(self):
        """Clean previous build directories."""
        dirs_to_clean = [self.build_dir, self.dist_dir]
        for dir_path in dirs_to_clean:
            if dir_path.exists():
                shutil.rmtree(dir_path)
                self.log(f"Cleaned {dir_path}")
    
    def create_build_environment(self):
        """Create isolated build environment."""
        self.log("Creating build environment...")
        
        # Create build directories
        self.build_dir.mkdir(exist_ok=True)
        self.dist_dir.mkdir(exist_ok=True)
        
        # Create virtual environment for building
        venv_path = self.build_dir / "build_venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
        
        # Get venv python
        if self.system == "windows":
            python_exe = venv_path / "Scripts" / "python.exe"
            pip_exe = venv_path / "Scripts" / "pip.exe"
        else:
            python_exe = venv_path / "bin" / "python"
            pip_exe = venv_path / "bin" / "pip"
        
        # Install build dependencies
        build_deps = [
            "pyinstaller>=5.0.0",
            "PyQt5>=5.15.0",
            "aiohttp>=3.8.0",
            "playwright>=1.40.0",
            "pycryptodome>=3.15.0"
        ]
        
        for dep in build_deps:
            self.log(f"Installing {dep}...")
            subprocess.run([str(pip_exe), "install", dep], check=True)
        
        return python_exe, pip_exe
    
    def build_standalone_executable(self, python_exe):
        """Build standalone executable with PyInstaller."""
        self.log("Building standalone executable...")
        
        # Use existing build_executable.py
        cmd = [str(python_exe), "build_executable.py"]
        
        self.log(f"Running build: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            self.log("Executable built successfully!")
            return True
        else:
            self.log(f"Build failed: {result.stderr}", "ERROR")
            return False
    
    def create_installer_with_embedded_app(self):
        """Create installer that includes the built executable."""
        self.log("Creating installer with embedded application...")
        
        # Create installer directory
        installer_dir = self.build_dir / "installer_package"
        installer_dir.mkdir(exist_ok=True)
        
        # Copy built executable from dist directory
        dist_dir = self.current_dir / "dist"
        if self.system == "windows":
            exe_name = "HLS Downloader.exe"
            if (dist_dir / exe_name).exists():
                shutil.copy2(dist_dir / exe_name, installer_dir / exe_name)
        elif self.system == "darwin":
            app_name = "HLS Downloader.app"
            if (dist_dir / app_name).exists():
                shutil.copytree(dist_dir / app_name, installer_dir / app_name)
        else:
            exe_name = "HLS Downloader"
            if (dist_dir / exe_name).exists():
                shutil.copy2(dist_dir / exe_name, installer_dir / exe_name)
        
        # Copy installer files
        installer_files = [
            "installer.py",
            "install.bat", 
            "install.sh",
            "INSTALLER_README.md"
        ]
        
        for file_name in installer_files:
            src = self.current_dir / file_name
            if src.exists():
                shutil.copy2(src, installer_dir / file_name)
        
        return installer_dir
    
    def create_final_bundle(self, installer_dir):
        """Create final distribution bundle."""
        self.log("Creating final distribution bundle...")
        
        # Create platform-specific bundle name
        platform_name = self.system
        arch = self.machine
        bundle_name = f"{self.app_name}-{self.version}-{platform_name}-{arch}-bundle"
        
        # Create bundle archive
        if self.system == "windows":
            bundle_path = self.dist_dir / f"{bundle_name}.zip"
            with zipfile.ZipFile(bundle_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(installer_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(installer_dir)
                        zipf.write(file_path, arcname)
        else:
            import tarfile
            bundle_path = self.dist_dir / f"{bundle_name}.tar.gz"
            with tarfile.open(bundle_path, 'w:gz') as tarf:
                tarf.add(installer_dir, arcname=bundle_name)
        
        self.log(f"Bundle created: {bundle_path}")
        self.log(f"Size: {bundle_path.stat().st_size / 1024 / 1024:.1f} MB")
        
        return bundle_path
    
    def build(self):
        """Main build process."""
        self.log(f"Building installer bundle for {self.system} {self.machine}")
        self.log("=" * 60)
        
        try:
            # Clean previous builds
            self.clean_build_dirs()
            
            # Create build environment
            python_exe, pip_exe = self.create_build_environment()
            
            # Build standalone executable
            if not self.build_standalone_executable(python_exe):
                return False
            
            # Create installer with embedded app
            installer_dir = self.create_installer_with_embedded_app()
            
            # Create final bundle
            bundle_path = self.create_final_bundle(installer_dir)
            
            self.log("=" * 60)
            self.log("🎉 Installer bundle created successfully!")
            self.log(f"📦 Bundle: {bundle_path}")
            self.log("🚀 Ready for distribution!")
            self.log("=" * 60)
            
            return True
            
        except Exception as e:
            self.log(f"Build failed: {e}", "ERROR")
            return False

def main():
    """Main entry point."""
    print("🎬 HLS Video Downloader - Installer Bundle Builder")
    print("=" * 60)
    
    builder = InstallerBundleBuilder()
    success = builder.build()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())