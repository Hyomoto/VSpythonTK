"""
generator.py

by Devon "Hyomoto" Mullane, 2025

Main entry point for the Vintage Story Python Toolkit. This script coordinates
the shape and recipe generators, applying batch transformations to input files
based on user-defined grammar rules.

Features:
---------
- Invokes all generators in batch mode in a single run
- Supports dry run, verbose output, and strict JSON parsing
- Reads user-defined settings from settings.json for convenience
- Automatically falls back to strict JSON if JSON5 is unavailable

Usage:
------
    python generator.py [--dry] [--verbose] [--strict] [--absolute]

Notes:
------
- Input/output paths and absolute mode can be configured via settings.json
"""
from shapes import ShapeGenerator
from recipes import RecipeGenerator
from utils import Ansi
from shapes import hello as hello_shapes
from recipes import hello as hello_recipes
import utils
import argparse
import os

VERSION = "0.1.0"
MODULE_NAME = f"{os.path.basename(__file__)}-{VERSION}".strip()
DEBUG = False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Expands recipe grammar definitions into full recipe files for Vintage Story mods.")
    parser.add_argument("-dry", "-d", action="store_true", help="Dry run: preview generated outputs without writing files.")
    parser.add_argument("-verbose", "-v", action="store_true", help="Enable verbose output, shows internal recipe states.")
    parser.add_argument("-strict", "-s", action="store_true", help="Force strict JSON parsing (even if JSON5 support is available).")
    parser.add_argument("-absolute", "-a", action="store_true", help="Allow absolute paths for input and output directories.")
    args = parser.parse_args()

    print(utils.custom(f"{MODULE_NAME}: VS Python Toolkit Running...", Ansi.CYAN, "🛠️ "))
    # Check if JSON5 is available and not in strict mode
    if not args.strict:
        try:
            import json5
            json = json5
            print(utils.info("JSON5 detected: relaxed parsing is available."))
        except ImportError:
            print(utils.warning("JSON5 not available. Using strict JSON parsing.\n     To enable relaxed parsing, install with: pip install json5"))
            json = __import__("json")
    else:
        print(utils.custom("Enforcing strict JSON parsing mode.", Ansi.GREEN,"🚀"))
        json = __import__("json")

    # Check if settings.json exists
    if not os.path.exists("settings.json"):
        settings = {}
        print(utils.warning(f"{Ansi.YELLOW}settings.json{Ansi.RESET} not found, using default paths."))
    else:
        with open("settings.json", "r") as f:
            settings = json.load(f)
        print(utils.custom(f"Loaded settings from {Ansi.YELLOW}settings.json{Ansi.RESET}.", Ansi.GREEN, "📄"))

    input = settings.get("input", "./input/")
    output = settings.get("output", "./output/")
    absolute = settings.get("absolute", False)

    shapes = ShapeGenerator(json, args.verbose)
    recipes= RecipeGenerator(json, args.verbose)

    # Check if input and output directories exist
    if not os.path.exists(input):
        print(utils.error(f"Input directory {input} does not exist."))
        exit(1)
    if not os.path.exists(output):
        print(utils.error(f"Output directory {output} does not exist."))
        exit(1)
    print(hello_shapes())
    shapes.batch(input, output, args.dry, absolute)
    print(hello_recipes())
    recipes.batch(input, output, args.dry, absolute)