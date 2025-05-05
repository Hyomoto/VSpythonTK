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
- Dry-run mode to preview without writing changes
- Strict JSON parsing mode (`--strict`) for validation

Grammar File Structure:
-----------------------
[
  {
    "applyTo": "sword-*",                  # Required pattern match
    "textures": {
      "handle": "game:block/wood/oak",
      "metal":  "game:block/metal/iron"
    },
    "elements": {
      "faces": {
        "keys": ["#metal"],               # Match against face.texture
        "add": {
          "reflectiveMode": 2
        },
        "remove": ["windMode"]
      }
    }
  },
  {
    "copyFrom": "sword-*",                 # Inherit and override
    "applyTo": "dagger-*",
    "textures": {
      "metal": "game:block/metal/copper"
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
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import os
from utils import Ansi
from logger import logger
from generator import BaseGenerator
from generator import BaseGrammarJSON
from generator import BaseGrammar
from generator import CLI

VERSION = "0.2.1"
MODULE_NAME = f"{os.path.basename(__file__)}-{VERSION}".strip()
DEBUG = False

def hello() -> tuple[str, Ansi, str]:
    return (f"{MODULE_NAME}: Performing shape mutation...", Ansi.CYAN, "📐")

class ShapeFace:
    texture: str
    uv: list[float]
    texture: str
    reflectiveMode: int
    windMode: list[float]

class ShapeElement:
    name: str
    faces: list[str, ShapeFace]
    children: list["ShapeElement"]

class ShapeJSON:
    editor: dict[str, any] # type: ignore
    textureWidth: int
    textureHeight: int
    textureSizes: dict[str, int]
    textures: dict[str, str]
    elements: ShapeElement

class GrammarElementFaces(BaseModel):
    keys: List[str] = Field(..., description="List of texture keys to match against")
    add: Optional[Dict[str, str | int]] = Field({}, description="Attributes to add to matching faces")
    remove: Optional[List[str]] = Field([], description="Attributes to remove from matching faces")

class GrammarElements(BaseModel):
    faces: List[GrammarElementFaces] = Field([], description="List of face rules to apply")

class Grammar(BaseModel):
    applyTo: List[str] = Field(..., description="Pattern to match against shape names")
    copyFrom: Optional[str | int] = Field(None, description="Name of grammar to inherit from")
    textures: Optional[Dict[str, str]] = Field({}, description="Texture overrides for the shape")
    elements: Optional[Dict[str, List | Dict]] = Field({}, description="Element rules to apply")

    class Config:
        arbitrary_types_allowed = True
        extra = "forbid"  # Disallow extra fields not defined in the model

class ShapeGrammarJSON(BaseGrammarJSON):
    @property
    def GRAMMAR(self):
        return ShapeGrammar
    
    @property
    def STATIC_FIELDS(self):
        return []
    
    @property
    def VALIDATE(self):
        return Grammar

class ShapeGrammar(BaseGrammar):
    def __init__(self, data: Grammar, static: dict[str, any] = None):
        super().__init__()
        self.textures = data.textures or None
        self.elements = data.elements or {}
        self.copyFrom = data.copyFrom

    def apply(self, shape: ShapeJSON, json) -> ShapeJSON:
        """Mutates the input shape by applying the grammar rules."""
        def applyTextures(shape: ShapeJSON):
            if "textures" not in shape or not self.textures:
                return

            for key, value in self.textures.items():
                if key in shape["textures"]:
                    shape["textures"][key] = value

        def applyToFaces(faces: dict[str, dict], rules: dict):
            keys = rules.get("keys")
            if not keys:
                raise ValueError("Required field 'keys' in element.faces.")
            if isinstance(keys, str):
                keys = [keys]
            to_add = rules.get("add", {})
            to_remove = rules.get("remove", [])
            
            for key, value in faces.items():
                if value["texture"] in keys:
                    for remove_key in to_remove:
                        value.pop(remove_key, None)
                    for add_key, add_val in to_add.items():
                        value[add_key] = add_val

        def applyElements(elements: ShapeElement):
            rules = self.elements.get("faces")
            if not rules:
                return

            for element in elements:
                if "faces" in element:
                    for rule in rules:
                        applyToFaces(element["faces"], rule)
                if "children" in element:
                    applyElements(element["children"])

        applyTextures(shape)
        if "elements" in shape:
            applyElements(shape["elements"])
        return shape

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

if __name__ == "__main__":
    CLI(Generator, hello)