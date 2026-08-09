"""
generator.py

by Devon "Hyomoto" Mullane, 2025

Main entry point for the Vintage Story Python Toolkit generators. This script
coordinates the execution of batch-capable generators using a shared interface
and optional configuration file.

Features:
---------
- Executes one or more generators (e.g., shapes, recipes) in batch mode
- Supports dry-run, verbose logging, absolute path resolution, and debug output
- Loads settings from settings.json, with CLI arguments taking precedence
- Automatically detects and uses JSON5 if available, with optional strict fallback

Usage:
------
    python generator.py <project_dir> [--dry-run] [--verbose] [--strict] [--generate <name>]
    python generator.py --input <dir> --output <dir> [--generate <name>]

Notes:
------
- Prefer a project directory containing vspythontk.json
- Legacy settings.json (cwd) is used only when no project path is given
- Strict mode enforces standard JSON and may improve performance but files must adhere
  to strict JSON rules (e.g., no comments, trailing commas)
"""
from pydantic import ValidationError, BaseModel
from typing import List, Optional
from utils import Ansi
from utils import load_ignore_rules
from utils import matches_buildignore
from utils import scanForDirectories
from utils import scanForFiles
from logger import logger
from logger import Error_Level
from shutil import copy2
from abc import ABC, abstractmethod
from pathlib import Path
import argparse
import fnmatch
import os
import re

VERSION = "0.4.0"
MODULE_NAME = f"{os.path.basename(__file__)}-{VERSION}".strip()
GENERATORS = ["shapes", "recipes"]

def hello() -> str:
    return (f"{MODULE_NAME}: Running VS Python Generators...", Ansi.CYAN, "🏭")

class BaseGrammarJSON(ABC):
    def __init__(self):
        self.grammars = {}

    @property
    @abstractmethod
    def GRAMMAR(self) -> "BaseGrammar":
        pass

    @property
    @abstractmethod
    def STATIC_FIELDS(self) -> list[str]:
        pass

    @property
    @abstractmethod
    def VALIDATE(self) -> BaseModel:
        pass

    def load(self, data: list[dict]):
        def sortGrammars(data: list[dict]) -> list[int]:
            nonlocal staticDict
            staticList = []

            for i, grammar in enumerate(data):
                if grammar.get("static"):
                    staticList.append(grammar["static"])
                    continue

                grammarId = grammar.get("name")
                if grammarId:
                    if grammarId in indexByKey:
                        raise ValueError(f"Duplicate grammar ID found: '{grammarId}'")
                    indexByKey[grammarId] = i
                    grammar.pop("name", None)
                indexByKey[i] = i

            if len(staticList) > 1:
                logger.warning("Multiple static grammars found. Only the first one will be used.")

            if staticList:
                staticDict.update(staticList[0])

            visited = set()
            stack = set()

            def visit(idx):
                if idx in visited:
                    return
                if idx in stack:
                    raise ValueError("Circular grammar inheritance detected.")
                if data[idx].get("static"):
                    return

                stack.add(idx)
                base = data[idx].get("copyFrom")
                if base:
                    if base not in indexByKey:
                        raise ValueError(f"'copyFrom' refers to unknown grammar: '{base}'")
                    visit(indexByKey[base])

                stack.remove(idx)
                visited.add(idx)
                sortedList.append(idx)

            for i in range(len(data)):
                visit(i)

            return sortedList

        sortedList = []
        indexByKey = {}
        staticDict = {}

        sortGrammars(data)
        
        for i in sortedList:
            source = data[i]
            base = data[indexByKey[source["copyFrom"]]] if source.get("copyFrom") is not None else {}
            merged = {**base, **source}

            for field in self.STATIC_FIELDS:
                if field not in merged and field in staticDict:
                    merged[field] = staticDict[field]

            try:
                validated = self.VALIDATE.model_validate(merged)
            except ValidationError as e:
                logger.warning(f"[Grammar Validation] Errors in grammar at index {i}:")
                for err in e.errors():
                    logger.warning(f"  → {err['loc']}: {err['msg']}")
                continue

            grammar = self.GRAMMAR(validated, staticDict)
            keys = validated.applyTo if isinstance(validated.applyTo, list) else [validated.applyTo]
            for key in keys:
                self.grammars[key] = grammar

        return self
    
class BaseGrammar(ABC):
    @abstractmethod
    def apply(self, target, json = None) -> str:
        pass

    def doStaticReplacement(self, input: str | list[str], static: dict):
        if not input:
            return None
        if isinstance(input, str):
            if input.startswith("@"):
                key = input[1:]
                table = static.get(key)
                if isinstance(table, list):
                    return table[0]
                return table if table else input
            return input
        output = []
        
        for token in input:
            if isinstance(token, str) and token.startswith("@"):
                key = token[1:]
                table = static.get(key)
                if isinstance(table, list):
                    output.extend(table)
                elif table:
                    output.append(table)
            else:
                output.append(token)
        return output
    
    def doWildcardReplacement(self, template: str, substitutions: dict[str,str]):
        missing = [part for part in template.split("%") if part.endswith("%") and part[:-1] not in substitutions]
        if missing:
            raise KeyError(f"Template contains missing substitutions: {Ansi.YELLOW}{missing}{Ansi.RESET}")

        for key, value in substitutions.items():
            substitution = f"%{key}%"
            if isinstance(value, (int,float)):
                template = re.sub(f'"{re.escape(substitution)}"', str(value), template)
                # fix for bad boys and girls who use numbers where strings are expected
                template = template.replace(substitution, str(value))
            else:
                template = template.replace(substitution, str(value))
        return template

class BaseGenerator(ABC):
    def __init__(self, json_module, absolute=False):
        self.json = json_module
        self.absolute = absolute
        self._folders_visited = 0
        self._folders_with_grammar = 0
    
    @property
    @abstractmethod
    def FOLDERS(self):
        pass
    @property
    @abstractmethod
    def NAME(self):
        pass

    @property
    @abstractmethod
    def GRAMMAR_JSON(self):
        pass

    def getDirectories(self, directory, exclude = []) -> list[str]:
        folders = scanForDirectories(directory, self.FOLDERS, exclude)
        return folders
    
    def getFiles(self, directory, exclude=[], filetypes=(".json", "json5")) -> list[str]:
        # Discover full folder; .buildignore only filters copy/stage, not grammar mutation
        files = scanForFiles(
            directory, filetypes=filetypes, exclude=exclude, apply_buildignore=False
        )
        return files
    
    def copySkippedFiles(self, skipped, input, output):
        ignore_patterns = load_ignore_rules(Path(input) / ".buildignore")
        for filename in skipped:
            name = Path(filename).name
            if name == ".buildignore" or matches_buildignore(name, ignore_patterns):
                logger.verbose(f"Copy skip (buildignore): '{filename}'")
                continue
            shape_path = os.path.join(input, filename)
            out_path = os.path.join(output, filename)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            try:
                copy2(shape_path, out_path)
                logger.verbose(f"Copied '{shape_path}' to '{out_path}'")
            except FileNotFoundError:
                logger.error(f"File not found: {Ansi.YELLOW}{shape_path}{Ansi.RESET}")
            except OSError as e:
                logger.error(f"Failed to copy '{filename}': {e}")

    def execute(self, source: str, output: str, dry: bool = False, batch: bool = False):
        if batch:
            self.batch(source, output, dry)
        else:
            self.run(source, output, dry)

    def batch(self, input: str, output: str, dryRun: bool = False):
        input_path = Path(input)
        output_path = Path(output)
        if not self.absolute:
            if input_path.is_absolute() or output_path.is_absolute():
                logger.error(
                    "An absolute path was provided, but absolute is set to false. "
                    "Pass --absolute or set absolute: true in vspythontk.json."
                )
                exit(1)

        folders = self.getDirectories(str(input_path))
        if not folders:
            logger.error(f"No {self.NAME} files found in '{input_path}'. Skipping.")
            return

        self._folders_visited = 0
        self._folders_with_grammar = 0
        for folder in folders:
            inputPath = os.path.join(str(input_path), folder)
            outputPath = os.path.join(str(output_path), folder)
            self.run(inputPath, outputPath, dryRun)

        logger.custom(
            Error_Level.INFO,
            f"{self.NAME}: {self._folders_visited} folder(s), "
            f"{self._folders_with_grammar} with grammar",
            Ansi.CYAN,
            "📂",
        )

    def run(self, input: str, output: str, dry: bool = False):
        if os.path.abspath(input) == os.path.abspath(output):
            raise ValueError("Input and output paths must not be the same.")

        self._folders_visited += 1
        files = self.getFiles(input, filetypes=(".json", ".json5"))
        grammars = [f for f in files if Path(f).name.startswith("grammar")]
        targets = [Path(f).name for f in files if not Path(f).name.startswith("grammar")]

        if grammars:
            self._folders_with_grammar += 1

        if not targets and not grammars:
            return

        if not grammars:
            self.copySkippedFiles(targets, input, output)
            return

        grammarObj = self.GRAMMAR_JSON()
        for grammar in grammars:
            grammarPath = os.path.join(input, Path(grammar).name)
            try:
                with open(grammarPath, "r", encoding="utf-8") as f:
                    grammarObj = grammarObj.load(self.json.load(f))
            except ValueError as e:
                logger.error(f"Error in {Ansi.YELLOW}{grammar}{Ansi.RESET}: {e}")

        matched = set()

        for pattern, grammar in grammarObj.grammars.items():
            for filename in targets:
                if fnmatch.fnmatch(filename, pattern):
                    matched.add(filename)
                    with open(Path(input) / filename, "r", encoding="utf-8") as sf:
                        raw = self.json.load(sf)
                        final = grammar.apply(raw, self.json)
                        if not dry:
                            outPath = Path(output) / filename
                            outPath.parent.mkdir(parents=True, exist_ok=True)
                            with open(outPath, "w", encoding="utf-8") as outf:
                                if isinstance(final, str):
                                    outf.write(final)
                                else:
                                    self.json.dump(final, outf, indent=2)
                                logger.verbose(f"Applied grammar '{pattern}' to '{outPath}'")

        logger.custom(Error_Level.INFO, f"Processed {len(matched)} files in '{input}'", Ansi.GREEN, "⚙️ ")

        skipped = [f for f in targets if f not in matched]
        if skipped:
            self.copySkippedFiles(skipped, input, output)
            copied = [
                f for f in skipped
                if not matches_buildignore(f, load_ignore_rules(Path(input) / ".buildignore"))
            ]
            if copied:
                logger.warning(f"   Skipped files: {', '.join(copied)}")

def getJSON(strict: bool):
    if strict:
        logger.info("Strict JSON parsing enabled.")
        return __import__("json")
    try:
        import json5
        logger.info("Using JSON5 for relaxed parsing.")
        return json5
    except ImportError:
        logger.warning("JSON5 not available. Falling back to strict JSON parsing.")
        return __import__("json")
    
def getSettings(json, path="settings.json"):
    try:
        with open(path, "r") as f:
            settings = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing {Ansi.YELLOW}{path}{Ansi.RESET}: {e}")
        return {}
    except FileNotFoundError:
        logger.warning(f"{Ansi.YELLOW}{path}{Ansi.RESET} not found, using default paths.")
        return {}
    logger.custom(Error_Level.INFO, f"Loaded settings from {Ansi.YELLOW}{path}{Ansi.RESET}.", Ansi.GREEN, "📄")
    return settings

def CLI(use_generator, get_greeting):
    parser = argparse.ArgumentParser(
        description="Transforms Vintage Story ModelCreator files using grammar rules for formatting and bugfixes."
    )
    parser.add_argument("source", help="Input directory containing grammar JSON/JSON5 files.")
    parser.add_argument("output", help="Output directory for processed files.")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Preview changes without writing output.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output.")
    parser.add_argument("-s", "--strict", action="store_true", help="Use strict JSON parsing only.")
    parser.add_argument("-b", "--batch", action="store_true", help="Process all matching files in the input folder.")
    parser.add_argument("-a", "--absolute", action="store_true", help="Allow absolute paths for I/O.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    
    args = parser.parse_args()
    
    if args.debug:
        logger.enableDebug = True
        logger.custom(Error_Level.INFO, "Debugging is enabled.", Ansi.YELLOW, "🐞")

    if args.verbose:
        logger.level = Error_Level.VERBOSE
    
    logger.custom(Error_Level.INFO, *get_greeting())
    
    json_module = getJSON(args.strict)
    generator = use_generator(json_module, args.absolute)
    generator.execute(
        source=args.source,
        output=args.output,
        dry=args.dry_run,
        batch=args.batch,
    )
    logger.save()

def runGenerators(generators: List[str], json, input: str, output: str, absolute: bool = False, dry: bool = False):
    for next in generators:
        if next not in GENERATORS:
            logger.error(f"Unknown generator '{next}'. Available generators: {', '.join(GENERATORS)}")
            continue
        module = __import__(next)
        logger.custom(Error_Level.INFO, *module.hello())
        generator = getattr(module, "Generator", None)
        if not generator:
            logger.error(f"No 'Generator' class found in '{next}'. Skipping.")
            continue
        generator(json, absolute).batch(input, output, dry)

def main(
    absolute: bool = False,
    strict: bool = False,
    dry: bool = False,
    generators: Optional[List[str]] = None,
    project_dir: Optional[str] = None,
    input_path: Optional[str] = None,
    output_path: Optional[str] = None,
):
    logger.custom(Error_Level.INFO, *hello())

    import json

    input_dir = input_path
    output_dir = output_path
    absolute_flag = absolute
    strict_flag = strict
    selected = generators

    if project_dir:
        from project import load_project

        project = load_project(project_dir)
        input_dir = input_dir or str(project.content_input)
        output_dir = output_dir or str(project.content_output)
        absolute_flag = True if absolute else project.absolute
        strict_flag = strict or project.strict
        if selected is None:
            selected = project.generators
        logger.custom(
            Error_Level.INFO,
            f"Using project {project.root} ({project.name})",
            Ansi.GREEN,
            "📄",
        )
    elif input_dir is None or output_dir is None:
        settings = getSettings(json, "settings.json")
        input_dir = input_dir or settings.get("input", "./input/")
        output_dir = output_dir or settings.get("output", "./output/")
        absolute_flag = absolute_flag or settings.get("absolute", False)
        strict_flag = strict_flag or settings.get("strict", False)

    if selected is None:
        selected = GENERATORS

    json_module = getJSON(strict_flag)

    if not os.path.exists(input_dir):
        logger.error(f"Input directory {input_dir} does not exist.")
        exit(1)
    if not os.path.exists(output_dir):
        logger.info(f"Output directory {output_dir} does not exist, creating it.")
        os.makedirs(output_dir)

    runGenerators(selected, json_module, input_dir, output_dir, absolute_flag, dry)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run VSpythonTK content generators for a project or explicit paths."
    )
    parser.add_argument(
        "project",
        nargs="?",
        help="Project directory containing vspythontk.json",
    )
    parser.add_argument("-i", "--input", dest="input_path", help="Override content input directory")
    parser.add_argument("-o", "--output", dest="output_path", help="Override content output directory")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Preview changes without writing output.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output.")
    parser.add_argument("-s", "--strict", action="store_true", help="Use strict JSON parsing only.")
    parser.add_argument("-a", "--absolute", action="store_true", help="Allow absolute paths for I/O.")
    parser.add_argument("-g", "--generate", choices=["shapes", "recipes", "all"], help="Only run the specified generator.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    if args.debug:
        logger.enableDebug = True
        logger.custom(Error_Level.INFO, "Debugging is enabled.", Ansi.YELLOW, "🐞")

    if args.verbose:
        logger.level = Error_Level.VERBOSE

    selected = None
    if args.generate and args.generate != "all":
        selected = [args.generate]
    elif args.generate == "all":
        selected = GENERATORS

    main(
        absolute=args.absolute,
        strict=args.strict,
        dry=args.dry_run,
        generators=selected,
        project_dir=args.project,
        input_path=args.input_path,
        output_path=args.output_path,
    )
    logger.save()
