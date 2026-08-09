"""
project.py

Load and resolve VSpythonTK project configuration from vspythontk.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

CONFIG_FILENAME = "vspythontk.json"
TOOLKIT_VERSION = "0.4.0"


class ContentConfig(BaseModel):
    input: str = "assets"
    output: str = "dist/stage/assets"


class PackageConfig(BaseModel):
    dir: str = "dist"
    zipName: str = "{name}-v{version}.zip"


class CompileConfig(BaseModel):
    enabled: bool = True
    csproj: Optional[str] = None
    configuration: str = "Release"
    targetFramework: str = "net10"
    dllName: Optional[str] = None
    dllOut: str = "dist/stage"
    sourceGlobs: List[str] = Field(
        default_factory=lambda: ["**/*.cs", "**/*.csproj", "**/*.props", "**/*.targets"]
    )


class HashConfig(BaseModel):
    cache: str = "dist/.vspythontk-cache.json"


class StageExtra(BaseModel):
    from_: str = Field(..., alias="from")
    to: str
    exclude: List[str] = Field(default_factory=lambda: ["**/grammar*"])

    model_config = {"populate_by_name": True}


class ProjectConfig(BaseModel):
    name: str
    modinfo: str = "assets/modinfo.json"
    content: ContentConfig = Field(default_factory=ContentConfig)
    stage: str = "dist/stage"
    package: PackageConfig = Field(default_factory=PackageConfig)
    compile: CompileConfig = Field(default_factory=CompileConfig)
    hash: HashConfig = Field(default_factory=HashConfig)
    generators: List[str] = Field(default_factory=lambda: ["recipes", "shapes"])
    stageExtra: List[StageExtra] = Field(default_factory=list)
    absolute: bool = True
    strict: bool = True

    @field_validator("generators")
    @classmethod
    def validate_generators(cls, value: List[str]) -> List[str]:
        allowed = {"recipes", "shapes"}
        for name in value:
            if name not in allowed:
                raise ValueError(f"Unknown generator '{name}'. Allowed: {', '.join(sorted(allowed))}")
        return value

    @model_validator(mode="after")
    def apply_compile_defaults(self) -> "ProjectConfig":
        if self.compile.enabled and not self.compile.csproj:
            self.compile.enabled = False
        if self.compile.dllName is None and self.compile.csproj:
            self.compile.dllName = f"{self.name}.dll"
        if not self.stageExtra:
            self.stageExtra = [
                StageExtra.model_validate(
                    {"from": self.content.input, "to": self.content.output, "exclude": ["**/grammar*"]}
                )
            ]
        return self


class ResolvedProject:
    """Project config with paths resolved against the project root."""

    def __init__(self, root: Path, config: ProjectConfig):
        self.root = root.resolve()
        self.config = config
        self.name = config.name
        self.modinfo = self._resolve(config.modinfo)
        self.content_input = self._resolve(config.content.input)
        self.content_output = self._resolve(config.content.output)
        self.stage = self._resolve(config.stage)
        self.package_dir = self._resolve(config.package.dir)
        self.hash_cache = self._resolve(config.hash.cache)
        self.csproj = self._resolve(config.compile.csproj) if config.compile.csproj else None
        self.dll_out = self._resolve(config.compile.dllOut)
        self.generators = list(config.generators)
        self.absolute = config.absolute
        self.strict = config.strict
        self.stage_extra = [
            {
                "from": self._resolve(entry.from_),
                "to": self._resolve(entry.to),
                "exclude": list(entry.exclude),
            }
            for entry in config.stageExtra
        ]

    def _resolve(self, path: str | Path) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p.resolve()
        return (self.root / p).resolve()

    def zip_path(self, version: str) -> Path:
        name = self.config.package.zipName.format(name=self.name, version=version)
        return self.package_dir / name

    def dll_build_path(self, configuration: str | None = None) -> Path:
        cfg = configuration or self.config.compile.configuration
        dll_name = self.config.compile.dllName or f"{self.name}.dll"
        return self.root / "bin" / cfg / self.config.compile.targetFramework / dll_name

    def dll_stage_path(self) -> Path:
        dll_name = self.config.compile.dllName or f"{self.name}.dll"
        return self.dll_out / dll_name


def load_project(project_dir: str | Path, config_name: str = CONFIG_FILENAME) -> ResolvedProject:
    root = Path(project_dir).resolve()
    config_path = root / config_name
    if not config_path.is_file():
        raise FileNotFoundError(f"Project config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    config = ProjectConfig.model_validate(raw)
    return ResolvedProject(root, config)


def find_project_config(start: str | Path) -> Optional[Path]:
    """Walk upward from start looking for vspythontk.json."""
    current = Path(start).resolve()
    if current.is_file():
        current = current.parent
    for path in [current, *current.parents]:
        candidate = path / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None
