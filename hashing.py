"""
hashing.py

Stable SHA-256 hashing for content and DLL build lanes, plus cache I/O.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, List, Optional

from project import TOOLKIT_VERSION, ResolvedProject

CONTENT_LANE = "content"
DLL_LANE = "dll"


def _iter_files(root: Path, patterns: Optional[List[str]] = None) -> List[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root]

    files: List[Path] = []
    if patterns:
        seen = set()
        for pattern in patterns:
            for match in root.glob(pattern):
                if match.is_file() and match not in seen:
                    # Skip common build junk under project when hashing sources
                    parts = set(match.parts)
                    if "bin" in parts or "obj" in parts or "dist" in parts:
                        continue
                    seen.add(match)
                    files.append(match)
        return sorted(files, key=lambda p: str(p).lower())

    for path in sorted(root.rglob("*"), key=lambda p: str(p).lower()):
        if path.is_file():
            files.append(path)
    return files


def hash_paths(paths: Iterable[Path], root: Optional[Path] = None, extra: Optional[str] = None) -> str:
    """Hash sorted relative paths and file bytes. Optional extra string is mixed in."""
    digest = hashlib.sha256()
    if extra:
        digest.update(extra.encode("utf-8"))
        digest.update(b"\0")

    normalized: List[tuple[str, Path]] = []
    for path in paths:
        path = path.resolve()
        if not path.is_file():
            continue
        if root is not None:
            try:
                rel = path.relative_to(root.resolve()).as_posix()
            except ValueError:
                rel = path.as_posix()
        else:
            rel = path.as_posix()
        normalized.append((rel, path))

    for rel, path in sorted(normalized, key=lambda item: item[0].lower()):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")

    return digest.hexdigest()


def content_hash(project: ResolvedProject) -> str:
    paths: List[Path] = []
    paths.extend(_iter_files(project.content_input))
    for entry in project.stage_extra:
        paths.extend(_iter_files(entry["from"]))
    if project.modinfo.is_file():
        paths.append(project.modinfo)
        modicon = project.modinfo.parent / "modicon.png"
        if modicon.is_file():
            paths.append(modicon)
    # De-dupe while preserving order for sorting inside hash_paths
    unique = list({p.resolve(): p for p in paths}.values())
    return hash_paths(unique, root=project.root, extra=f"toolkit:{TOOLKIT_VERSION}:content")


def dll_hash(project: ResolvedProject) -> str:
    if not project.config.compile.enabled or not project.csproj:
        return hash_paths([], root=project.root, extra=f"toolkit:{TOOLKIT_VERSION}:dll:disabled")

    paths: List[Path] = [project.csproj]
    for pattern in project.config.compile.sourceGlobs:
        # Patterns are relative to project root
        for match in project.root.glob(pattern):
            if match.is_file():
                parts = set(match.relative_to(project.root).parts)
                if "bin" in parts or "obj" in parts or "dist" in parts:
                    continue
                paths.append(match)
    unique = list({p.resolve(): p for p in paths}.values())
    return hash_paths(unique, root=project.root, extra=f"toolkit:{TOOLKIT_VERSION}:dll")


def load_cache(cache_path: Path) -> dict:
    if not cache_path.is_file():
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache_path: Path, content: Optional[str] = None, dll: Optional[str] = None) -> None:
    cache = load_cache(cache_path)
    if content is not None:
        cache[CONTENT_LANE] = content
    if dll is not None:
        cache[DLL_LANE] = dll
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)
        f.write("\n")


def clear_cache(cache_path: Path) -> None:
    if cache_path.is_file():
        cache_path.unlink()


class LaneStatus:
    def __init__(self, content_changed: bool, dll_changed: bool, content: str, dll: str):
        self.content_changed = content_changed
        self.dll_changed = dll_changed
        self.content = content
        self.dll = dll


def evaluate_lanes(project: ResolvedProject, force: bool = False) -> LaneStatus:
    current_content = content_hash(project)
    current_dll = dll_hash(project)
    if force:
        return LaneStatus(True, True, current_content, current_dll)

    cache = load_cache(project.hash_cache)
    content_changed = cache.get(CONTENT_LANE) != current_content
    dll_changed = cache.get(DLL_LANE) != current_dll
    return LaneStatus(content_changed, dll_changed, current_content, current_dll)
