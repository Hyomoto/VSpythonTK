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
from utils import Ansi
from logger import logger
from logger import Error_Level
import argparse
import os

VERSION = "0.1.0"
MODULE_NAME = f"{os.path.basename(__file__)}-{VERSION}".strip()
DEBUG = False

def main(strict, verbose, dry, generators = ["shapes", "recipes"]):
    logger.custom(Error_Level.INFO, f"{MODULE_NAME}: VS Python Toolkit Running...", Ansi.CYAN, "🛠️ ")
    # Check if JSON5 is available and not in strict mode
    if not strict:
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

    # Check if settings.json exists
    if not os.path.exists("settings.json"):
        settings = {}
        logger.warning(f"{Ansi.YELLOW}settings.json{Ansi.RESET} not found, using default paths.")
    else:
        with open("settings.json", "r") as f:
            settings = json.load(f)
        logger.custom(Error_Level.INFO, f"Loaded settings from {Ansi.YELLOW}settings.json{Ansi.RESET}.", Ansi.GREEN, "📄")

    input = settings.get("input", "./input/")
    output = settings.get("output", "./output/")
    absolute = settings.get("absolute", False)
    
    # Check if input and output directories exist
    if not os.path.exists(input):
        logger.error(f"Input directory {input} does not exist.")
        exit(1)
    if not os.path.exists(output):
        logger.info(f"Output directory {output} does not exist, creating it.")
        os.makedirs(output)
    if "shapes" in generators:
        import shapes
        logger.custom(Error_Level.INFO, *shapes.hello())
        generator = shapes.ShapeGenerator(json, verbose)
        generator.batch(input, output, dry, absolute)
    if "recipes" in generators:
        import recipes
        logger.custom(Error_Level.INFO, *recipes.hello())
        generator = recipes.RecipeGenerator(json, verbose)
        generator.batch(input, output, dry, absolute)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Expands recipe grammar definitions into full recipe files for Vintage Story mods.")
    parser.add_argument("-dry", "-d", action="store_true", help="Dry run: preview generated outputs without writing files.")
    parser.add_argument("-verbose", "-v", action="store_true", help="Enable verbose output, shows internal recipe states.")
    parser.add_argument("-strict", "-s", action="store_true", help="Force strict JSON parsing (even if JSON5 support is available).")
    parser.add_argument("-absolute", "-a", action="store_true", help="Allow absolute paths for input and output directories.")
    parser.add_argument("-generator", "-g", choices=["shapes", "recipes"], help="Specify a generator to run.")
    args = parser.parse_args()

    strict = args.strict
    verbose = args.verbose
    dry = args.dry

    main(strict, verbose, dry, [ args.generator ] )
    