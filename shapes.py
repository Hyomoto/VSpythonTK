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
from typing import TypedDict
import fnmatch
import argparse
import os
import traceback
from utils import Ansi
import utils
from logger import logger
from logger import Error_Level
from json import JSONDecodeError

VERSION = "0.2.1"
MODULE_NAME = f"{os.path.basename(__file__)}-{VERSION}".strip()
DEBUG = False

def hello() -> tuple[str, Ansi, str]:
    return (f"{MODULE_NAME}: Performing shape mutation...", Ansi.CYAN, "📐")

class GrammarJSON(TypedDict):
    copyFrom: str
    applyTo: str
    textures: dict[str, str]
    elements: dict
    
class GrammarFaces(TypedDict):
    keys: list[str]
    add: dict[str, any]
    remove: list[str]

class GrammarElements(TypedDict):
    faces: GrammarFaces

class ShapeFace(TypedDict):
    texture: str
    uv: list[float]
    texture: str
    reflectiveMode: int
    windMode: list[float]

class ShapeElement(TypedDict):
    name: str
    faces: dict[str, ShapeFace]
    children: list["ShapeElement"]

class ShapeJSON(TypedDict):
    editor: dict[str, any] # type: ignore
    textureWidth: int
    textureHeight: int
    textureSizes: dict[str, int]
    textures: dict[str, str]
    elements: ShapeElement

class ShapeGrammarJSON():
    def __init__(self, data: list[GrammarJSON]):
        sorted = []
        index_by_key = {}

        for i, grammar in enumerate(data):
            keys = grammar.get("applyTo")
            if not keys:
                raise ValueError(f"Missing 'applyTo' key in grammar at index {i}.")
            
            if isinstance(keys, str):
                keys = [keys]
            
            for key in keys:
                if key in index_by_key:
                    raise ValueError(f"Duplicate 'applyTo' key '{key}' found in grammar at index {i}.")
                index_by_key[key] = i

        visited = set()
        stack = set()

        def visit(idx):
            nonlocal index_by_key
            if idx in visited:
                return
            if idx in stack:
                raise ValueError("Circular grammar inheritance detected.")

            stack.add(idx)

            grammar = data[idx]
            base = grammar.get("copyFrom")

            if base:
                if base not in index_by_key:
                    raise ValueError(f"'copyFrom' refers to unknown grammar: '{base}'")
                visit(index_by_key[base])

            visited.add(idx)
            stack.remove(idx)
            sorted.append(idx)

        for i in range(len(data)):
            visit(i)
        if DEBUG:
            logger.custom(Error_Level.INFO, f"Sorted grammar files: {repr(sorted)}", Ansi.CYAN, "🛠️ ")

        self.grammars = {}

        for i in sorted:
            source = data[i]
            extends = source.get("copyFrom")
            if extends:
                extends = data[index_by_key[extends]]

            grammar = ShapeGrammar(source, extends)
            
            keys = source.get("applyTo")
            if isinstance(keys, str):
                keys = [keys]
            for key in keys:
                self.grammars[key] = grammar

class ShapeGrammar():
    def __init__(self, data: GrammarJSON, extends: GrammarJSON = None):
        if extends:
            base = extends.copy()
            base.update(data)
        else:
            base = data.copy()
        base.pop("applyTo", None)
        self.__dict__.update(base)

    def matches(self, filename: str) -> bool:
        return fnmatch.fnmatch(filename, self.apply_to)

    def apply(self, shape: ShapeJSON) -> ShapeJSON:
        """Mutates the input shape by applying the grammar rules."""
        def applyTextures(shape: ShapeJSON):
            if not hasattr(self, "textures"):
                return  # nothing to apply

            if "textures" not in shape:
                return  # input shape has no textures to modify

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

class ShapeGenerator:
    def __init__(self, json_module, verbose: bool = False):
        self.json = json_module
        self.verbose = verbose

    def batch(self, input: str, output: str, dry: bool = False, absolute: bool = False):
        # Protect against unintentional absolute paths
        if not absolute:
            if input[0] == "/" or input[0] == "\\":
                logger.error("An absolute input path was provided, but absolute is set to false. Please check your settings.json file.")
                exit(1)
            elif output[0] == "/" or output[0] == "\\":
                logger.error("An absolute output path was provided, but absolute is set to false. Please check your settings.json file.")
                exit(1)

        folders = utils.scanForDirectories(input, "shapes")
        if not folders:
            logger.error(f"No shape files found in '{input}'. Skipping.")
            return
        for folder in folders:
            input_path = os.path.join(input, folder)
            output_path = os.path.join(output, folder)
            self.run(input_path, output_path, dry)

    def run(self, input: str, output: str, dry: bool = False ):
        # Sanity check, prevent overwriting the input file
        if os.path.abspath(input) == os.path.abspath(output):
            raise ValueError("Input and output paths must not be the same.")
        count = 0
        
        files = utils.scanForFiles(input, filetypes=[".json", ".json5"])
        grammars = [f for f in files if f.startswith("grammar")]
        shapes = [f for f in files if f not in grammars]
        
        if not grammars:
            logger.warning(f"No grammar file found in '{input}'. Ignoring.")
            skipped = shapes
        else:
                
            for grammar_file in grammars:
                grammar_path = os.path.join(input, grammar_file)
                try:
                    with open(grammar_path, "r", encoding="utf-8") as f:
                        grammar_json = ShapeGrammarJSON(self.json.load(f))
                except ValueError as e:
                    logger.error(f"Error in {Ansi.YELLOW}{grammar_file}{Ansi.RESET}: {e}")
                    continue
            
            skipped = []

            for filename in shapes:
                matched = False
                for pattern, grammar in grammar_json.grammars.items():
                    if fnmatch.fnmatch(filename, pattern):
                        matched = True
                        shape_path = os.path.join(input, filename)
                        if not dry:
                            out_path = os.path.join(output, filename)
                            os.makedirs(os.path.dirname(out_path), exist_ok=True)
                        try:
                            with open(shape_path, "r", encoding="utf-8") as sf:
                                shape = self.json.load(sf)
                                grammar.apply(shape)

                                if not dry:
                                    with open(out_path, "w", encoding="utf-8") as outf:
                                        self.json.dump(shape, outf, indent=2)
                                    if self.verbose:
                                        logger.info(f"Applied grammar '{pattern}' to '{out_path}'")
                                    count += 1
                                
                        except FileNotFoundError:
                            logger.error(f"File not found: {Ansi.YELLOW}{shape_path}{Ansi.RESET}")

                        except JSONDecodeError as e:
                            logger.error(f"Failed to parse shape file '{Ansi.YELLOW}{filename}{Ansi.RESET}': {e}")

                        except KeyError as e:
                            logger.error(f"Missing key {Ansi.YELLOW}{e}{Ansi.RESET} in shape file '{filename}'")

                        except Exception as e:
                            logger.error(f"Unexpected error processing '{Ansi.YELLOW}{filename}{Ansi.RESET}': {e}")
                            if self.verbose:
                                traceback.print_exc()
                if not matched:
                    skipped.append(filename)
                if DEBUG:
                    break # Debugging: stop after first match
        logger.custom(Error_Level.INFO, f"Processed {count} files in '{input}'", Ansi.GREEN, "✅")
        if skipped:
            # copy skipped files to output directory if not dry run
            if not dry:
                for filename in skipped:
                    shape_path = os.path.join(input, filename)
                    out_path = os.path.join(output, filename)
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    try:
                        with open(shape_path, "r", encoding="utf-8") as sf:
                            shape = self.json.load(sf)
                            with open(out_path, "w", encoding="utf-8") as outf:
                                self.json.dump(shape, outf, indent=2)
                            if self.verbose:
                                logger.info(f"Copied '{shape_path}' to '{out_path}'")
                            count += 1
                    except FileNotFoundError:
                        logger.error(f"File not found: {Ansi.YELLOW}{shape_path}{Ansi.RESET}")
                    except JSONDecodeError as e:
                        logger.error(f"Failed to parse shape file '{Ansi.YELLOW}{filename}{Ansi.RESET}': {e}")
            logger.warning(f"   Skipped files: {', '.join(skipped)}")
        return count

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mutates VS ModelCreator shape files using grammar definitions to fix bugs and fix formatting for use in-game.")
    parser.add_argument("source", help="Path to the input folder that contains a grammar JSON (or JSON5) file(s).")
    parser.add_argument("output", help="Path to write mutated shape JSON (or JSON5) file(s).")
    parser.add_argument("-dry", "-d", action="store_true", help="Dry run: preview generated outputs without writing files.")
    parser.add_argument("-verbose", "-v", action="store_true", help="Enable verbose output, shows internal recipe states.")
    parser.add_argument("-strict", "-s", action="store_true", help="Force strict JSON parsing (even if JSON5 support is available).")
    parser.add_argument("-batch", "-b", action="store_true", help="Batch process all recipe files in the input directory.")
    parser.add_argument("-absolute", "-a", action="store_true", help="Allow absolute paths for input and output directories.")
    args = parser.parse_args()

    logger.custom(Error_Level.INFO, *hello())
    
    # Check if JSON5 is available and not in strict mode
    if not args.strict:
        try:
            import json5
            json = json5
            logger.info("JSON5 detected: relaxed parsing is available.")
        except ImportError:
            logger.warning("JSON5 not available. Using strict JSON parsing.\n     To enable relaxed parsing, install with: pip install json5")
            json = __import__("json")
    else:
        logger.custom(Error_Level.INFO, "Enforcing strict JSON parsing mode.", Ansi.GREEN,"🚀")
        json = __import__("json")
    
    generator = ShapeGenerator(json, args.verbose)
    if args.batch:
        generator.batch(args.source, args.output, args.dry, args.absolute)
    else:
        generator.run(args.source, args.output, args.dry)
    logger.save()