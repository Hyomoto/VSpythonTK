"""
build.py

by Devon "Hyomoto" Mullane, 2025

Project-rooted build and release interface for the Vintage Story Python Toolkit.
Point at a mod directory containing vspythontk.json to stage content, run
generators, compile the DLL (optional), and package a distributable ZIP.

Usage:
------
    python build.py <project_dir> [--config Release|Debug] [--version Major|Minor|X.Y.Z]
    python build.py <project_dir> --force
    python build.py <project_dir> --generate-only
    python build.py <project_dir> --copy-to path/to/dest.zip
    python build.py <project_dir> --clean
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

import utils
from generator import main as run_generator
from hashing import evaluate_lanes, save_cache, clear_cache
from logger import Error_Level, logger
from packaging import copy_dll, copy_package, handle_remove_readonly, stage_content, zip_stage
from project import TOOLKIT_VERSION, load_project
from utils import Ansi

VERSION = TOOLKIT_VERSION
MODULE_NAME = f"{os.path.basename(__file__)}-{VERSION}".strip()


def hello() -> tuple:
    return (f"{MODULE_NAME}: Starting project build...", Ansi.CYAN, "🛠️ ")


class BuildError(Exception):
    """Custom exception for build script failures."""


class MissingFileError(BuildError):
    """Raised when a required file is missing."""


class InvalidVersionError(BuildError):
    """Raised when the version string is invalid."""


def get_version(modInfoPath: Path) -> str:
    with open(modInfoPath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("version", "0.0.0")


def set_version(modInfoPath: Path, behavior: str) -> str:
    with open(modInfoPath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if behavior == "Major":
        version = get_version(modInfoPath).split(".")
        version[0] = str(int(version[0]) + 1)
        version[1] = "0"
        version[2] = "0"
    elif behavior == "Minor":
        version = get_version(modInfoPath).split(".")
        version[1] = str(int(version[1]) + 1)
        version[2] = "0"
    else:
        version = behavior.split(".")

    output = ".".join(version)
    data["version"] = output

    with open(modInfoPath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        f.write("\n")
    return output


def clean_project(project) -> None:
    targets = [project.root / "bin", project.root / "obj", project.package_dir]
    try:
        project.stage.relative_to(project.package_dir)
        stage_inside_package = True
    except ValueError:
        stage_inside_package = False
    if not stage_inside_package:
        targets.append(project.stage)

    for path in targets:
        path = path.resolve()
        if path == project.root.resolve() or not path.exists():
            continue
        logger.custom(Error_Level.INFO, f"Removing {path}", Ansi.YELLOW, "🗑️ ")
        if path.is_dir():
            shutil.rmtree(path, onexc=handle_remove_readonly)
        else:
            path.unlink()
    clear_cache(project.hash_cache)
    logger.custom(Error_Level.INFO, "Clean complete.", Ansi.GREEN, "🧹")


def run_dotnet_build(project, configuration: str) -> None:
    csproj = project.csproj
    if not csproj or not csproj.is_file():
        raise MissingFileError(f"csproj not found: {csproj}")
    logger.custom(Error_Level.INFO, f"Building {csproj.name} ({configuration})...", Ansi.YELLOW, "👷‍♀️")
    subprocess.run(
        ["dotnet", "build", str(csproj), "-c", configuration],
        check=True,
        cwd=project.root,
    )


def build_project(
    project_dir: str | Path,
    configuration: str | None = None,
    version_behavior: str | None = None,
    force: bool = False,
    generate_only: bool = False,
    copy_to: str | Path | None = None,
) -> None:
    project = load_project(project_dir)
    cfg = configuration or project.config.compile.configuration

    if not project.modinfo.is_file():
        raise BuildError(f"modinfo not found: {project.modinfo}")

    if version_behavior:
        if version_behavior not in ("Major", "Minor") and not all(
            part.isdigit() for part in version_behavior.split(".")
        ):
            raise InvalidVersionError(
                "Invalid version format. Use 'Major', 'Minor', or a version number (e.g. 1.0.0)."
            )
        version = set_version(project.modinfo, version_behavior)
    else:
        version = get_version(project.modinfo)

    lanes = evaluate_lanes(project, force=force)
    content_ran = False
    dll_ran = False

    if generate_only:
        if lanes.content_changed or force:
            stage_content(project, clean_stage=True)
            run_generator(
                absolute=True,
                strict=project.strict,
                dry=False,
                generators=project.generators,
                project_dir=str(project.root),
            )
            save_cache(project.hash_cache, content=lanes.content, dll=None)
            logger.success(f"Generate-only complete. Stage: {project.stage}")
        else:
            logger.success("Content unchanged; generate skipped.")
        return

    if lanes.content_changed or force:
        logger.custom(Error_Level.INFO, "Content lane changed; staging and generating...", Ansi.YELLOW, "📄")
        stage_content(project, clean_stage=True)
        run_generator(
            absolute=True,
            strict=project.strict,
            dry=False,
            generators=project.generators,
            project_dir=str(project.root),
        )
        content_ran = True
    else:
        logger.custom(Error_Level.INFO, "Content lane unchanged; skipping generate/stage.", Ansi.GREEN, "⏭️ ")

    compile_enabled = project.config.compile.enabled and project.csproj is not None
    if compile_enabled and (lanes.dll_changed or force):
        logger.custom(Error_Level.INFO, "DLL lane changed; compiling...", Ansi.YELLOW, "⚙️ ")
        # Ensure stage exists even if content was skipped (first-time dll-only change)
        project.stage.mkdir(parents=True, exist_ok=True)
        if not (project.stage / "modinfo.json").is_file() and project.modinfo.is_file():
            shutil.copy2(project.modinfo, project.stage / "modinfo.json")
            modicon = project.modinfo.parent / "modicon.png"
            if modicon.is_file() and not (project.stage / "modicon.png").is_file():
                shutil.copy2(modicon, project.stage / "modicon.png")
        run_dotnet_build(project, cfg)
        copy_dll(project, cfg)
        dll_ran = True
    elif not compile_enabled:
        logger.custom(Error_Level.INFO, "Compile disabled; skipping DLL build.", Ansi.GREEN, "⏭️ ")
    else:
        logger.custom(Error_Level.INFO, "DLL lane unchanged; skipping compile.", Ansi.GREEN, "⏭️ ")

    zip_path = project.zip_path(version)
    needs_zip = content_ran or dll_ran or force or not zip_path.is_file()
    # If content was skipped but stage is missing, force a content pass before zip
    if needs_zip and not project.stage.exists():
        logger.warning("Stage missing; running content stage/generate before zip.")
        stage_content(project, clean_stage=True)
        run_generator(
            absolute=True,
            strict=project.strict,
            dry=False,
            generators=project.generators,
            project_dir=str(project.root),
        )
        content_ran = True
        needs_zip = True

    if needs_zip:
        # Ensure a DLL is present in stage when compile is enabled
        if compile_enabled and not project.dll_stage_path().is_file():
            built = project.dll_build_path(cfg)
            if built.is_file():
                copy_dll(project, cfg)
            else:
                run_dotnet_build(project, cfg)
                copy_dll(project, cfg)
                dll_ran = True
        zip_stage(project, version)
    else:
        logger.custom(Error_Level.INFO, f"Package up to date: {zip_path.name}", Ansi.GREEN, "⏭️ ")

    if copy_to:
        copy_package(zip_path, Path(copy_to))

    save_cache(project.hash_cache, content=lanes.content, dll=lanes.dll)
    logger.success(f"Build complete! Stage: {project.stage} | Package: {zip_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build and package a VSpythonTK project.")
    parser.add_argument("project", help="Project directory containing vspythontk.json")
    parser.add_argument(
        "--config",
        choices=["Release", "Debug"],
        default=None,
        help="dotnet build configuration (default: from vspythontk.json)",
    )
    parser.add_argument(
        "--version",
        type=str,
        help="Set version: 'Major', 'Minor', or a version string (e.g. 1.2.3)",
    )
    parser.add_argument("--force", action="store_true", help="Ignore hash cache and rebuild all lanes")
    parser.add_argument("--generate-only", action="store_true", help="Only stage and run content generators")
    parser.add_argument(
        "--copy-to",
        type=str,
        default=None,
        help="Copy the built package zip to a file path or directory after packaging",
    )
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts and exit")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--time", action="store_true", help="Show elapsed time for the build process")
    args = parser.parse_args()

    if args.debug:
        logger.enableDebug = True
        logger.custom(Error_Level.INFO, "Debugging is enabled.", Ansi.YELLOW, "🐞")

    logger.custom(Error_Level.INFO, *hello())

    timer = None
    if args.time:
        timer = utils.Timer().start()

    try:
        project = load_project(args.project)
        if args.clean:
            clean_project(project)
            logger.success("Clean complete.")
        else:
            build_project(
                args.project,
                configuration=args.config,
                version_behavior=args.version,
                force=args.force,
                generate_only=args.generate_only,
                copy_to=args.copy_to,
            )
    except BuildError as e:
        logger.error(e)
        raise SystemExit(1) from e
    except FileNotFoundError as e:
        logger.error(e)
        raise SystemExit(1) from e
    except subprocess.CalledProcessError as e:
        logger.error(e)
        raise SystemExit(1) from e

    logger.save()

    if timer:
        timer.stop()
        logger.custom(Error_Level.INFO, f"Completed in {timer.elapsed()*1000:.2f} ms.", Ansi.YELLOW, "⏱️ ")
