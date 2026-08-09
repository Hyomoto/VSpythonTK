"""
shapes.py

by Devon "Hyomoto" Mullane, 2025

This script mutates Vintage Story shape JSON files using grammar-based overrides
to correct formatting issues, remove unwanted data, and apply consistent texture
or attribute transformations. Shape grammars allow for inheritance and per-pattern
matching to automate the cleanup of exported Model Creator assets.

Features:
---------
- Pattern-matching with fnmatch-style `applyTo` values (e.g., "sword-*")
- Grammar inheritance using `copyFrom` for DRY definitions
- Texture overrides based on key presence in the source shape
- Per-face attribute mutation: `add` and `remove` fields for targeted cleanup
- Recursive shape traversal to apply changes to all child elements
- Output-folder cleanup patterns before regenerate
- Generative composition of part shapes into finished shapes (`generate`)
- Named reusable `mods` blocks applied (in order) to generated outputs
- Dry-run mode to preview without writing changes
- Strict JSON parsing mode (`--strict`) for validation

Grammar File Structure:
-----------------------
[
  {
    "applyTo": "sword-*",                  # Mutate matching input shapes into output
    "textures": {
      "handle": "game:block/wood/oak",
      "metal":  "game:block/metal/iron"
    },
    "elements": {
      "faces": [
        {
          "keys": ["#metal"],
          "add": { "reflectiveMode": 2 },
          "remove": ["windMode"]
        }
      ]
    }
  },
  {
    "cleanup": ["sword-*", "sword-rapier"]  # Delete matching files in OUTPUT only
  },
  {
    "generate": [
      {
        "name": "sword-{handle}-{blade}",
        "targets": {
          "blade": ["broad", "long", "thin"],
          "handle": ["cross", "curve", "flat"]
        },
        "mods": ["*"]
      }
    ],
    "mods": {
      "base": {
        "textures": { "metal": "game:block/metal/ingot/iron" },
        "elements": {
          "faces": [
            {
              "keys": ["#metal"],
              "add": { "reflectiveMode": 2 },
              "remove": ["windMode"]
            }
          ]
        }
      }
    }
  }
]

Usage:
------
To apply grammar rules to one folder:
    python shapes.py input_dir output_dir

To process all folders under a directory:
    python shapes.py input_dir output_dir --batch

To preview only (dry run):
    python shapes.py input_dir output_dir --dry

To enforce strict JSON parsing:
    python shapes.py input_dir output_dir --strict

Notes:
------
- Grammar filenames must begin with "grammar" and reside alongside shapes
- Only textures explicitly listed in both grammar and shape are modified
- Face rules operate on the `texture` value (e.g., "#metal") as keys
- JSON5 is supported if installed; otherwise falls back to standard JSON
- When `generate` is present, unmatched input files are not copied to output
- `.buildignore` filters copy/stage only; generate/applyTo still read ignored parts
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Any, Dict, List, Optional
from pathlib import Path
from itertools import product
from copy import deepcopy
import fnmatch
import os
import re

from utils import Ansi
from utils import load_ignore_rules
from utils import matches_buildignore
from logger import logger
from logger import Error_Level
from generator import BaseGenerator
from generator import BaseGrammarJSON
from generator import BaseGrammar
from generator import CLI

VERSION = "0.3.0"
MODULE_NAME = f"{os.path.basename(__file__)}-{VERSION}".strip()
DEBUG = False

_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


def hello() -> tuple[str, Ansi, str]:
    return (f"{MODULE_NAME}: Performing shape mutation...", Ansi.CYAN, "shapes")


class ShapeFace:
    texture: str
    uv: list[float]
    reflectiveMode: int
    windMode: list[float]


class ShapeElement:
    name: str
    faces: list[str, ShapeFace]
    children: list["ShapeElement"]


class ShapeJSON:
    editor: dict[str, any]  # type: ignore
    textureWidth: int
    textureHeight: int
    textureSizes: dict[str, int]
    textures: dict[str, str]
    elements: ShapeElement


class GrammarElementFaces(BaseModel):
    keys: List[str] = Field(..., description="List of texture keys to match against")
    add: Optional[Dict[str, str | int]] = Field(default_factory=dict, description="Attributes to add to matching faces")
    remove: Optional[List[str]] = Field(default_factory=list, description="Attributes to remove from matching faces")


class GrammarElements(BaseModel):
    faces: List[GrammarElementFaces] = Field(default_factory=list, description="List of face rules to apply")


class ModBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    textures: Optional[Dict[str, str]] = Field(default_factory=dict)
    elements: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ApplyGrammar(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    applyTo: List[str] | str = Field(..., description="Pattern to match against shape names")
    copyFrom: Optional[str | int] = Field(None, description="Name of grammar to inherit from")
    textures: Optional[Dict[str, str]] = Field(default_factory=dict)
    elements: Optional[Dict[str, Any]] = Field(default_factory=dict)


class CleanupGrammar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cleanup: List[str] = Field(..., description="fnmatch patterns of OUTPUT files to delete")


class GenerateRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Output stem; may include {targetKey} placeholders")
    targets: Dict[str, List[str]] = Field(..., description="Named part lists to cartesian-expand")
    mods: Optional[List[str]] = Field(default_factory=list, description="Ordered mod names; '*' = all mods")


class GenerateGrammar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generate: List[GenerateRule] = Field(..., description="Composite generation rules")
    mods: Optional[Dict[str, ModBlock]] = Field(default_factory=dict, description="Named reusable mutation blocks")


# Back-compat alias used by BaseGrammarJSON VALIDATE property for applyTo entries
class Grammar(ApplyGrammar):
    pass


def apply_shape_mods(shape: dict, textures: Optional[Dict[str, str]], elements: Optional[Dict[str, Any]]) -> dict:
    """Apply texture overrides and face add/remove rules to a shape dict (in place)."""
    if textures and "textures" in shape:
        for key, value in textures.items():
            if key in shape["textures"]:
                shape["textures"][key] = value

    face_rules = (elements or {}).get("faces") if elements else None
    if not face_rules or "elements" not in shape:
        return shape

    def apply_to_faces(faces: dict[str, dict], rules: dict):
        keys = rules.get("keys")
        if not keys:
            raise ValueError("Required field 'keys' in element.faces.")
        if isinstance(keys, str):
            keys = [keys]
        to_add = rules.get("add", {}) or {}
        to_remove = rules.get("remove", []) or []

        for _face_key, value in faces.items():
            if value.get("texture") in keys:
                for remove_key in to_remove:
                    value.pop(remove_key, None)
                for add_key, add_val in to_add.items():
                    value[add_key] = add_val

    def walk(elements_list):
        for element in elements_list:
            if "faces" in element:
                for rule in face_rules:
                    # pydantic models or plain dicts
                    rule_dict = rule if isinstance(rule, dict) else rule.model_dump()
                    apply_to_faces(element["faces"], rule_dict)
            if "children" in element and element["children"]:
                walk(element["children"])

    walk(shape["elements"])
    return shape


def compose_shapes(part_jsons: List[dict]) -> dict:
    """Merge part shapes: first part supplies metadata; elements concat; textures union (later wins)."""
    if not part_jsons:
        raise ValueError("compose_shapes requires at least one part")

    composed = deepcopy(part_jsons[0])
    composed["elements"] = list(composed.get("elements") or [])
    textures = dict(composed.get("textures") or {})

    for part in part_jsons[1:]:
        textures.update(part.get("textures") or {})
        composed["elements"].extend(deepcopy(part.get("elements") or []))

    composed["textures"] = textures
    return composed


def format_generate_name(template: str, substitutions: Dict[str, str]) -> str:
    def repl(match: re.Match) -> str:
        key = match.group(1)
        if key not in substitutions:
            raise KeyError(key)
        return substitutions[key]

    return _PLACEHOLDER_RE.sub(repl, template)


def expand_mod_names(requested: List[str], mod_table: Dict[str, ModBlock]) -> List[str]:
    if not requested:
        return []
    if "*" in requested:
        # Preserve table definition order; ignore other names when '*' present
        return list(mod_table.keys())
    return list(requested)


class ShapeGrammarJSON(BaseGrammarJSON):
    def __init__(self):
        super().__init__()
        self.cleanup_patterns: List[str] = []
        self.generate_rules: List[GenerateRule] = []
        self.mod_table: Dict[str, ModBlock] = {}

    @property
    def GRAMMAR(self):
        return ShapeGrammar

    @property
    def STATIC_FIELDS(self):
        return []

    @property
    def VALIDATE(self):
        return ApplyGrammar

    def load(self, data: list[dict]):
        """Load applyTo grammars plus cleanup / generate / mods entries."""
        if not isinstance(data, list):
            raise ValueError("Shape grammar must be a JSON array")

        apply_entries: List[dict] = []
        for entry in data:
            if not isinstance(entry, dict):
                logger.warning("Skipping non-object grammar entry")
                continue

            if "cleanup" in entry:
                try:
                    validated = CleanupGrammar.model_validate(entry)
                except ValidationError as e:
                    logger.warning("[Grammar Validation] Errors in cleanup entry:")
                    for err in e.errors():
                        logger.warning(f"  → {err['loc']}: {err['msg']}")
                    continue
                self.cleanup_patterns.extend(validated.cleanup)
                continue

            if "generate" in entry:
                try:
                    validated = GenerateGrammar.model_validate(entry)
                except ValidationError as e:
                    logger.warning("[Grammar Validation] Errors in generate entry:")
                    for err in e.errors():
                        logger.warning(f"  → {err['loc']}: {err['msg']}")
                    continue
                self.generate_rules.extend(validated.generate)
                if validated.mods:
                    # Later generate entries can extend/override named mods
                    for name, block in validated.mods.items():
                        self.mod_table[name] = block
                continue

            if "applyTo" in entry or "copyFrom" in entry or "static" in entry:
                apply_entries.append(entry)
                continue

            logger.warning(f"Unrecognized grammar entry keys: {list(entry.keys())}")

        if apply_entries:
            super().load(apply_entries)
        return self


class ShapeGrammar(BaseGrammar):
    def __init__(self, data: ApplyGrammar, static: dict[str, any] = None):
        super().__init__()
        self.textures = data.textures or None
        self.elements = data.elements or {}
        self.copyFrom = data.copyFrom

    def apply(self, shape: ShapeJSON, json=None) -> ShapeJSON:
        """Mutates the input shape by applying the grammar rules."""
        return apply_shape_mods(shape, self.textures, self.elements)


class Generator(BaseGenerator):
    @property
    def FOLDERS(self):
        return ["shapes"]

    @property
    def NAME(self):
        return "shapes"

    @property
    def GRAMMAR_JSON(self):
        return ShapeGrammarJSON

    def run(self, input: str, output: str, dry: bool = False):
        if os.path.abspath(input) == os.path.abspath(output):
            raise ValueError("Input and output paths must not be the same.")

        self._folders_visited += 1
        input_path = Path(input)
        output_path = Path(output)

        # Discover all JSON first; .buildignore only filters copy below
        files = self.getFiles(input, filetypes=(".json", ".json5"))
        grammars = [f for f in files if Path(f).name.startswith("grammar")]
        targets = [Path(f).name for f in files if not Path(f).name.startswith("grammar")]

        if grammars:
            self._folders_with_grammar += 1

        if not grammars:
            if targets:
                self.copySkippedFiles(targets, input, output)
            return

        grammar_obj = self.GRAMMAR_JSON()
        for grammar in grammars:
            grammar_path = input_path / Path(grammar).name
            if not grammar_path.exists():
                grammar_path = Path(input) / grammar
            try:
                with open(grammar_path, "r", encoding="utf-8") as f:
                    grammar_obj = grammar_obj.load(self.json.load(f))
            except ValueError as e:
                logger.error(f"Error in {Ansi.YELLOW}{grammar}{Ansi.RESET}: {e}")

        has_generate = bool(grammar_obj.generate_rules)

        # 1) cleanup output
        self._run_cleanup(output_path, grammar_obj.cleanup_patterns, dry)

        # 2) applyTo mutate (legacy) — can still emit ignored inputs
        matched: set[str] = set()
        if grammar_obj.grammars:
            for pattern, grammar in grammar_obj.grammars.items():
                for filename in targets:
                    if fnmatch.fnmatch(filename, pattern):
                        matched.add(filename)
                        with open(input_path / filename, "r", encoding="utf-8") as sf:
                            raw = self.json.load(sf)
                            final = grammar.apply(raw, self.json)
                            if not dry:
                                out_file = output_path / filename
                                out_file.parent.mkdir(parents=True, exist_ok=True)
                                with open(out_file, "w", encoding="utf-8") as outf:
                                    if isinstance(final, str):
                                        outf.write(final)
                                    else:
                                        self.json.dump(final, outf, indent=2)
                                logger.verbose(f"Applied grammar '{pattern}' to '{out_file}'")

            logger.custom(
                Error_Level.INFO,
                f"Processed {len(matched)} files in '{input}'",
                Ansi.GREEN,
                "⚙️ ",
            )

            skipped = [f for f in targets if f not in matched]
            if skipped and not has_generate:
                self.copySkippedFiles(skipped, input, output)
                ignore_patterns = load_ignore_rules(input_path / ".buildignore")
                copied = [f for f in skipped if not matches_buildignore(f, ignore_patterns)]
                if copied:
                    logger.warning(f"   Skipped files: {', '.join(copied)}")
            elif skipped and has_generate:
                logger.verbose(
                    f"   Not copying {len(skipped)} unmatched source(s) (generate mode): "
                    f"{', '.join(skipped)}"
                )
        elif targets and not has_generate:
            # No applyTo and no generate: copy non-ignored sources
            self.copySkippedFiles(targets, input, output)

        # 3) generate composites (parts may be buildignored for copy/stage only)
        if has_generate:
            self._run_generate(input_path, output_path, grammar_obj, dry)

    def _run_cleanup(self, output_path: Path, patterns: List[str], dry: bool):
        if not patterns:
            return
        if not output_path.exists():
            logger.verbose(f"Cleanup: output '{output_path}' does not exist yet; nothing to delete.")
            return

        deleted = 0
        for entry in output_path.iterdir():
            if not entry.is_file():
                continue
            if entry.suffix not in (".json", ".json5"):
                continue
            if entry.name.startswith("grammar"):
                continue
            if any(fnmatch.fnmatch(entry.name, pat) or fnmatch.fnmatch(entry.stem, pat) for pat in patterns):
                if dry:
                    logger.verbose(f"Cleanup (dry): would delete '{entry}'")
                else:
                    entry.unlink()
                    logger.verbose(f"Cleanup: deleted '{entry}'")
                deleted += 1

        logger.custom(
            Error_Level.INFO,
            f"Cleanup {'would remove' if dry else 'removed'} {deleted} file(s) from '{output_path}'",
            Ansi.YELLOW,
            "🧹",
        )

    def _run_generate(self, input_path: Path, output_path: Path, grammar_obj: ShapeGrammarJSON, dry: bool):
        emitted: Dict[str, str] = {}
        written = 0

        for rule_index, rule in enumerate(grammar_obj.generate_rules):
            target_keys = list(rule.targets.keys())
            if not target_keys:
                logger.warning(f"Generate rule {rule_index} has empty targets; skipping.")
                continue

            value_lists = [rule.targets[k] for k in target_keys]
            mod_names = expand_mod_names(rule.mods or [], grammar_obj.mod_table)

            for combo in product(*value_lists):
                substitutions = {key: value for key, value in zip(target_keys, combo)}
                try:
                    out_stem = format_generate_name(rule.name, substitutions)
                except KeyError as e:
                    logger.error(
                        f"Generate name '{rule.name}' missing placeholder value for {e}; skipping combo {substitutions}"
                    )
                    continue

                if out_stem in emitted:
                    logger.warning(
                        f"Generate would emit duplicate name '{out_stem}.json' "
                        f"(earlier from rule producing '{emitted[out_stem]}'; now rule {rule_index}). "
                        "Later write wins."
                    )
                emitted[out_stem] = rule.name

                part_jsons: List[dict] = []
                missing = False
                # Preserve targets key order for stable merge (blade then handle, etc.)
                for key in target_keys:
                    value = substitutions[key]
                    part_path = input_path / f"{value}.json"
                    if not part_path.exists():
                        # also allow .json5
                        alt = input_path / f"{value}.json5"
                        if alt.exists():
                            part_path = alt
                        else:
                            logger.error(
                                f"Generate '{out_stem}': missing part file '{value}.json' "
                                f"for target '{key}' in '{input_path}'"
                            )
                            missing = True
                            break
                    with open(part_path, "r", encoding="utf-8") as pf:
                        part_jsons.append(self.json.load(pf))

                if missing or not part_jsons:
                    continue

                composed = compose_shapes(part_jsons)

                for mod_name in mod_names:
                    block = grammar_obj.mod_table.get(mod_name)
                    if block is None:
                        logger.warning(
                            f"Generate '{out_stem}': unknown mod '{mod_name}'; skipping that mod."
                        )
                        continue
                    apply_shape_mods(composed, block.textures, block.elements)

                out_file = output_path / f"{out_stem}.json"
                if dry:
                    logger.verbose(f"Generate (dry): would write '{out_file}' from {substitutions}")
                else:
                    out_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(out_file, "w", encoding="utf-8") as outf:
                        self.json.dump(composed, outf, indent=2)
                    logger.verbose(f"Generate: wrote '{out_file}'")
                written += 1

        logger.custom(
            Error_Level.INFO,
            f"Generated {written} composite shape(s) into '{output_path}'",
            Ansi.GREEN,
            "🧩",
        )


if __name__ == "__main__":
    CLI(Generator, hello)
