"""
packaging.py

Stage authored assets, place compiled DLLs, and zip the staged mod tree.
"""
from __future__ import annotations

import fnmatch
import os
import shutil
import stat
import zipfile
from pathlib import Path
from typing import Iterable, List

from logger import Error_Level, logger
from project import ResolvedProject
from utils import Ansi


def handle_remove_readonly(func, path, _):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _matches_any(rel: str, patterns: Iterable[str]) -> bool:
    name = Path(rel).name
    posix = rel.replace("\\", "/")
    for pattern in patterns:
        if fnmatch.fnmatch(posix, pattern) or fnmatch.fnmatch(name, pattern):
            return True
    return False


def copy_tree_filtered(source: Path, dest: Path, exclude: List[str]) -> int:
    """Copy files from source to dest, skipping exclude patterns. Returns file count."""
    if not source.exists():
        raise FileNotFoundError(f"Stage source not found: {source}")

    copied = 0
    if source.is_file():
        rel = source.name
        if _matches_any(rel, exclude):
            return 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        return 1

    for path in source.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(source).as_posix()
        if _matches_any(rel, exclude):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def stage_content(project: ResolvedProject, clean_stage: bool = True) -> None:
    """Copy stageExtra sources into the stage tree, excluding grammar files by default."""
    if clean_stage and project.stage.exists():
        logger.custom(Error_Level.INFO, f"Cleaning stage {project.stage}", Ansi.YELLOW, "🗑️ ")
        shutil.rmtree(project.stage, onexc=handle_remove_readonly)

    project.stage.mkdir(parents=True, exist_ok=True)

    # Vintage Story expects modinfo.json (and optional modicon.png) at the mod root
    if project.modinfo.is_file():
        dest = project.stage / "modinfo.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project.modinfo, dest)
        logger.verbose(f"Staged modinfo -> {dest}")

        modicon = project.modinfo.parent / "modicon.png"
        if modicon.is_file():
            icon_dest = project.stage / "modicon.png"
            shutil.copy2(modicon, icon_dest)
            logger.verbose(f"Staged modicon -> {icon_dest}")

    for entry in project.stage_extra:
        src = entry["from"]
        dst = entry["to"]
        exclude = entry["exclude"]
        count = copy_tree_filtered(src, dst, exclude)
        logger.custom(
            Error_Level.INFO,
            f"Staged {count} files from {src} -> {dst}",
            Ansi.BLUE,
            "📦",
        )


def copy_dll(project: ResolvedProject, configuration: str | None = None) -> Path:
    source = project.dll_build_path(configuration)
    if not source.is_file():
        raise FileNotFoundError(f"Expected DLL not found: {source}")
    dest = project.dll_stage_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    logger.custom(Error_Level.INFO, f"Copied DLL {source.name} -> {dest}", Ansi.BLUE, "🚚")
    return dest


def copy_package(zip_path: Path, destination: Path) -> Path:
    """Copy a built package zip to destination (file path or directory)."""
    if not zip_path.is_file():
        raise FileNotFoundError(f"Package zip not found: {zip_path}")

    dest = Path(destination)
    as_dir = dest.is_dir() or str(destination).endswith(("/", "\\"))
    if as_dir:
        dest = dest / zip_path.name

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(zip_path, dest)
    logger.custom(Error_Level.INFO, f"Copied package {zip_path.name} -> {dest}", Ansi.BLUE, "🚚")
    return dest


def zip_stage(project: ResolvedProject, version: str) -> Path:
    zip_path = project.zip_path(version)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    logger.custom(Error_Level.INFO, f"Zipping stage to {zip_path.name}", Ansi.BLUE, "🧵")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for path in project.stage.rglob("*"):
            if not path.is_file():
                continue
            # Do not nest the zip inside itself if package.dir == stage parent and zip was under stage
            if path.resolve() == zip_path.resolve():
                continue
            arcname = path.relative_to(project.stage)
            zipf.write(path, arcname)
    return zip_path
