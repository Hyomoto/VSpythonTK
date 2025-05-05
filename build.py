"""
build.py

by Devon "Hyomoto" Mullane, 2025

High-level build and release interface for the Vintage Story Python Toolkit.
This script manages compilation, versioning, file staging, and packaging of
the project into a final distributable format.

Features:
---------
- Builds the .NET mod project using a specified configuration (Debug/Release)
- Handles semantic versioning via direct version string or auto-increment
- Supports cleanup of intermediate build artifacts
- Runs content generators with project-level settings
- Packages final release as a ZIP archive ready for deployment

Usage:
------
    python build.py [--config <Debug|Release>] [--version <Major|Minor|X.Y.Z>] [--clean] [--time]

Notes:
------
- Top-level build interface; configuration is expected via files, not CLI
- Version changes are written directly to assets/modinfo.json
- The development/ and release/ folders are expected to follow project structure
"""
import argparse
import json
import subprocess
import shutil
import zipfile
from pathlib import Path
import os
import stat
from logger import logger
from logger import Error_Level
from generator import main as run_generator
from utils import Ansi
import utils

PROJECT_NAME = "hmcpatch"
VERSION = "0.2.0"
MODULE_NAME = f"{os.path.basename(__file__)}-{VERSION}".strip()

ROOT = Path(__file__).resolve().parent.parent
MODINFO_PATH = ROOT / "assets" / "modinfo.json"

def hello() -> str:
    return (f"{MODULE_NAME}: Starting project build...", Ansi.CYAN, "🛠️ ")

def handle_remove_readonly(func, path, _):
    """Fallback for removing read-only or locked files on Windows."""
    os.chmod(path, stat.S_IWRITE)
    func(path)

class BuildError(Exception):
    """Custom exception for build script failures."""
    pass

class MissingFileError(BuildError):
    """Raised when a required file is missing."""
    pass

class InvalidVersionError(BuildError):
    """Raised when the version string is invalid."""
    pass

def get_version(modInfoPath):
    with open(modInfoPath, 'r') as f:
        data = json.load(f)
    return data.get('version', '0.0.0')

def set_version(modInfoPath, behavior):
    with open(modInfoPath, 'r') as f:
        data = json.load(f)
    version = data.get('version', '0.0.0').split('.')

    if behavior == "Major":
        version = get_version(modInfoPath).split('.')
        version[0] = str(int(version[0]) + 1)
        version[1] = '0'
        version[2] = '0'
    elif behavior == "Minor":
        version = get_version(modInfoPath).split('.')
        version[1] = str(int(version[1]) + 1)
        version[2] = '0'
    else:
        version = behavior.split('.')
    
    output = '.'.join(version)
    data['version'] = output

    with open(modInfoPath, 'w') as f:
        json.dump(data, f, indent=4)
    return output

def clean_build():
    targets = ["bin", "obj", "release"]

    for folder in targets:
        path = ROOT / folder
        if path.exists():
            logger.custom(Error_Level.INFO, f"Removing {folder}/", Ansi.YELLOW, "🗑️ ")
            shutil.rmtree(path, onexc=handle_remove_readonly)

    logger.custom(Error_Level.INFO, "Clean complete.", Ansi.GREEN, "🧹")

def run_build(config):
    logger.custom(Error_Level.INFO, f"Building project in {config} mode...", Ansi.YELLOW, "👷‍♀️")
    subprocess.run(["dotnet", "build", "-c", config], check=True, cwd=ROOT)

def copy_output(config, target_dir):
    source = ROOT / f"bin/{config}/net7/{PROJECT_NAME}.dll"
    
    if not source.exists():
        raise MissingFileError(f"Expected output file not found: {source}")

    dest = target_dir / f"{PROJECT_NAME}.dll"
    logger.custom(Error_Level.INFO, f"Copying {source} to {dest}",Ansi.BLUE, "🚚" )
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)

def zip_release(target_dir : Path, version):
    zip_name = target_dir / f"{PROJECT_NAME}-v{version}.zip"
    logger.custom(Error_Level.INFO, f"Zipping release folder to {zip_name.name}",Ansi.BLUE,"🧵")
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(target_dir):
            for file in files:
                full_path = Path(root) / file
                arcname = full_path.relative_to(target_dir)
                zipf.write(full_path, arcname)

def stage_release_folder():
    dev_dir = ROOT / "development"
    release_dir = ROOT / "release"
    
    if not dev_dir.exists():
        raise MissingFileError("Development folder is missing.")

    if release_dir.exists():
        shutil.rmtree(release_dir, onexc=handle_remove_readonly)

    logger.info("Staging release folder from development...")
    shutil.copytree(dev_dir, release_dir)

def build(config, version):
    target_dir = ROOT / ("release" if config == "Release" else "development")
    modinfo_path = modinfo_path = ROOT / "assets" / "modinfo.json"
    if not modinfo_path.exists():
        raise BuildError(f"Error: '{modinfo_path}' not found.")

    if version and version not in ["Major", "Minor"] and not all(x.isdigit() for x in version.split('.')):
        raise InvalidVersionError("Error: Invalid version format. Use 'Major', 'Minor' or a valid version number (e.g., 1.0.0).")
    
    if version:
        version = set_version(MODINFO_PATH, args.version)
    else:
        version = get_version(MODINFO_PATH)
    
    run_build(config)
    copy_output(config, target_dir)

    if config == "Release":
        run_generator( strict = True, dry = False )
        stage_release_folder()
        zip_release(target_dir, version)
    logger.success(f"Build complete! Output: {target_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build and package the project.")
    parser.add_argument('--config', choices=['Release', 'Debug'], default='Debug',
                        help='Build configuration (default: Debug)')
    parser.add_argument('--version', type=str,
                        help="Set version: 'Major', 'Minor', or a version string (e.g., 1.2.3)")
    parser.add_argument('--clean', action='store_true', help='Clean build artifacts and exit')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--time', action='store_true', help='Show elapsed time for the build process')
    args = parser.parse_args()

    if args.debug:
        logger.enableDebug = True
        logger.custom(Error_Level.INFO, "Debugging is enabled.", Ansi.YELLOW, "🐞")

    logger.custom(Error_Level.INFO, *hello())

    if args.time:
        timer = utils.Timer().start()

    try:
        if args.clean:
            clean_build()
            logger.success("Clean complete.")
        else:
            build(args.config, args.version)
    except BuildError as e:
        logger.error(e)
    except subprocess.CalledProcessError as e:
        logger.error(e)

    logger.save()

    if args.time:
        timer.stop()
        logger.custom(Error_Level.INFO, f"Completed in {timer.elapsed()*1000:.2f} ms.", Ansi.YELLOW, "⏱️ ")