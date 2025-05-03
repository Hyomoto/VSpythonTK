"""
recipes.py

by Devon "Hyomoto" Mullane, 2025

This script expands compact JSON recipe grammar definitions into fully realized
Vintage Story recipe files. It supports powerful, data-driven generation of
recipes via templates, substitution grammars, and flexible output formatting.

Features:
---------
- Template-based recipe generation using raw JSON structures
- Per-grammar substitutions across multiple material or structural variants
- Static lookup tables using '@key' injection (e.g., @metal, @skip)
- Wildcard filtering via `allow` and `skip` patterns (fnmatch-style)
- Template inheritance with `copyFrom` to avoid duplication
- Dotted key support for deep mutation using `remove` and `substitute`
- Grouped key expansion (e.g., "metal,bits") with synchronized values
- Dry-run mode to preview output codes without writing files
- Strict JSON parsing mode (`--strict`) for validation and performance

Input JSON Structure:
---------------------
{
  "template": {
    "default": {
      ... full recipe JSON with substitution markers like "%metal%" ...
    },
    "alt": {
      "copyFrom": "default",
      "output": {
        "code": "%weapon%-%style%-%metal%"
      }
    }
  },

  "grammars": [
    {
      "template": "default",           # Optional (defaults to "default")
      "keys": [                        # Required
        { "key": "metal", "value": ["@metal"] },
        { "key": "type,blade", "value": ["dagger,broad", "sword,long"] }
      ],
      "code": "%type%-%blade%-%metal%",   # Optional; falls back to static.code
      "format": "%blade%-%metal%",        # Optional; falls back to static.format
      "remove": ["output.attributes.oldProperty"],
      "substitute": [{ "key": "output.quantity", "value": 2 }],
      "allow": ["*-copper"],              # Optional whitelist
      "skip": ["*steel*"]                 # Optional blacklist
    }
  ],

  "static": {
    "metal": ["copper", "tinbronze", "steel"],
    "format": "{ ... }",                  # Optional default for grammars
    "code": "%metal%"                     # Optional default for grammars
  }
}

Usage:
------
To generate a recipe file:
    python generation.py input.json output.json

To preview only (dry run):
    python generation.py input.json output.json --dry

To force strict JSON parsing:
    python generation.py input.json output.json --strict

Notes:
------
- Templates are raw Vintage Story recipe objects, using `%key%` placeholders
- The `format` string defines how each final recipe is serialized
- All output is written to a single file (batching or directory output is external)
- This tool is compatible with both standard JSON and JSON5 (if installed)

"""
from typing import TypedDict, Dict, List
import fnmatch
import argparse
import os
import copy
import re
from utils import Ansi
import utils
from logger import logger
from logger import Error_Level

VERSION = "0.2.1"
MODULE_NAME = f"{os.path.basename(__file__)}-{VERSION}".strip()

def hello() -> str:
    return (f"{MODULE_NAME}: Performing recipe expansion...", Ansi.CYAN, "📜")

class TemplateJSONTemplate(TypedDict):
    ingredientPattern : str
    ingredients : Dict[str,Dict[str,str]]
    width : int
    height : int
    output : Dict[str,Dict[str,str]]

class TemplateJSONGrammar(TypedDict, total=False):
    template: str
    keys: List[Dict[str,List[str]]]
    code: str
    allow: List[str]
    skip: List[str]
    substitute : List[Dict[str,str]]
    remove : List[str]

class TemplateJSON(TypedDict):
    template : TemplateJSONTemplate
    grammars : List[TemplateJSONGrammar]
    static : Dict[str,List[str]]

class Grammar():
    def __init__(self,definition : TemplateJSONGrammar, static : Dict[str, List[str]], templates : Dict[ str, Dict ] ):
        def substitute(list : list[str],static : Dict[str,List[str]],ignore=False ):
            output = []
            for token in list:
                if token.startswith("@"):
                    key = token[1:]
                    table = static.get(key)
                    if table:
                        output.extend(table)
                    elif not ignore:
                        raise ValueError(f"Static substitution failed: '{Ansi.YELLOW}@{key}{Ansi.RESET}' not found.")
                else:
                    output.append(token)
            return output
        
        self.keys = []
        
        if "keys" not in definition or not isinstance(definition["keys"], list):
            raise ValueError(utils.error(f"Grammar definition must contain '{Ansi.YELLOW}keys{Ansi.RESET}' list."))
        
        for key in definition["keys"]:
            if "key" not in key or "value" not in key:
                raise ValueError(f"Each key entry must contain '{Ansi.YELLOW}key{Ansi.RESET}' and '{Ansi.YELLOW}value{Ansi.RESET}': {repr(key)}")
            keyNames = [k.strip() for k in key["key"].split(",")]
            exValues = substitute(key["value"], static)
            keyValues= []

            for v in exValues:
                if ( isinstance(v,list)):
                    keyValues.append(v)
                elif len(keyNames) == 1:
                    keyValues.append([v])
                else:
                    raise ValueError(f"Expected list of values for keys {Ansi.YELLOW}{keyNames}{Ansi.RESET}, but got single value '{v}'.")
            
            for v in keyValues:
                if len(v) != len(keyNames):
                    raise ValueError(f"Mismatch: keys {Ansi.YELLOW}{keyNames}{Ansi.RESET} expect {len(keyNames)} values but got {v}.")
            
            self.keys.append({ "key" : keyNames, "value" : keyValues })
        
        self.skip = substitute(definition.get("skip", [ "@skip" ]),static,True)
        self.allow = substitute(definition.get("allow", [ "@allow" ]),static,True)
        self.substitute = definition.get( "substitute", [] )
        self.remove = definition.get( "remove", [] )

        if not isinstance(self.remove, list):
            raise ValueError(f"Grammar '{Ansi.YELLOW}remove{Ansi.RESET}' must be a list, got {type(self.remove).__name__}.")

        if not isinstance(self.substitute, list):
            raise ValueError(f"Grammar '{Ansi.YELLOW}substitute{Ansi.RESET}' must be a list, got {type(self.substitute).__name__}.")

        # evil hack to convert to string because statics are lists, and code expects a string
        self.code = substitute([definition.get("code", "@code")],static,True)[0]

        templateFormat = definition.get("format")
        
        if templateFormat is None:
            templateFormat = static.get("format")
        elif templateFormat.startswith("@"):
            templateFormat = static.get(templateFormat[1:])
        if isinstance(templateFormat,list):
            templateFormat = templateFormat[0]
        
        if templateFormat is None:
            raise ValueError(f"Grammars require a {Ansi.YELLOW}'format'{Ansi.RESET} field.")
        
        self.templateFormat = templateFormat
        template =  definition.get("template", "default")
        
        if template is None or templates.get(template) is None:
            raise ValueError(f"Grammar definition must contain a {Ansi.YELLOW}'template'{Ansi.RESET} field.")
        self.template = template

class RecipeExpander:
    def __init__(self, data : TemplateJSON):
        self.error = False
        self.grammars : list[Grammar] = []
        self.templates = {}

        for templateName, template in data["template"].items():
            copyFrom = template.get("copyFrom")
            if copyFrom:
                baseTemplate = data["template"].get(copyFrom)
                if not baseTemplate:
                    raise ValueError(f"Template '{Ansi.YELLOW}{templateName}{Ansi.RESET}' tried to copy from unknown template '{Ansi.YELLOW}{copyFrom}{Ansi.RESET}'.")
                
                merged = copy.deepcopy(baseTemplate)
                local = {k: v for k, v in template.items() if k != "copyFrom"}  # Drop "copyFrom"
                merged.update(local)
                
                self.templates[templateName] = merged
            else:
                self.templates[templateName] = template
            
        try:
            index = 0
            for grammar in data["grammars"]:
                self.grammars.append( Grammar( grammar, data["static"], self.templates ))
                index += 1
        except ValueError as e:
            raise ValueError(f"Grammar {Ansi.YELLOW}{index}{Ansi.RESET} : {e}")

    def expand(self, json, dry: bool = False, verbose: bool = False, output: str | None = None):
        """Expands the grammar definitions into full recipes to the specified output file.

        Arguments:
            json: The JSON module to use for parsing (standard JSON or JSON5).
            dry: If True, only generates the keys for the recipes without writing them to a file.
            verbose: If True, prints the generated entries and their keys to the console.
            output: The path to the output file where the generated recipes will be written.
        """
        def substitute(template :str, substitutions: Dict[str,str]):
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
        
        def isAllowed(entry: str, allow: list[str], skip: list[str]) -> bool:
            for pattern in skip:
                if fnmatch.fnmatch(entry, pattern):
                    return False
            if allow:
                return any(fnmatch.fnmatch(entry, pattern) for pattern in allow)
            return True  # No allowed list means allow all
        
        def buildItemCodes( output: list, grammar: Grammar, table = {}, depth = 0 ):
            if depth == len(grammar.keys):
                # reached end of recursion, build the item code
                code = substitute(grammar.code, table)
                if isAllowed(code, grammar.allow, grammar.skip):
                    output.append(( code, table.copy()))
            elif len(grammar.keys) > 0:
                key = grammar.keys[depth]["key"]
                values = grammar.keys[depth]["value"]
                for item in values:
                    new_table = table.copy()
                    for i, swap in enumerate(key):
                        new_table[swap] = item[i]
                        buildItemCodes( output, grammar, new_table, depth + 1 )
            else:
                buildItemCodes( output, grammar, table.copy(), depth + 1 )
        
        outputKeys = []
        recipes = []

        for grammar in self.grammars:
            buildItemCodes( outputKeys, grammar )

        for code, table in outputKeys:
            logger.debug( f"{code}\t [{repr(table)}]" )
            if dry:
                continue
            # Create a copy of the template for mutation
            template = self.templates[grammar.template]
            if grammar.remove or grammar.substitute:
                template = copy.deepcopy(template)
                # Do removals and substitutions
                for path in grammar.remove:
                    utils.deep_remove(template, path)
                for item in grammar.substitute:
                    utils.deep_set(template, item["key"], item["value"])
            # Duplicate the output format string
            recipe = grammar.templateFormat
            
            unused_keys = [key for key in template if f"%{key}%" not in recipe]
            if unused_keys:
                logger.warning(f"Grammar template has unused keys: {Ansi.YELLOW}{unused_keys}{Ansi.RESET}")
            for key, value in template.items():
                recipe = recipe.replace(f"%{key}%",f"\"{key}\":{json.dumps(value, separators=(",", ":"))}")
            recipes.append(substitute(recipe, table))
        
        if not dry:
            try:
                with open(output, "w", encoding="utf-8") as file:
                    file.write(f"[\n{",\n".join(recipes)}\n]")
            except OSError as e:
                logger.error(f"Failed to write output file: {e}")
        return outputKeys
        
class RecipeGenerator:
    def __init__(self, json, verbose: bool = False):
        """Initializes the RecipeGenerator with the specified JSON module and options.
        Args:
            json: The JSON module to use for parsing (standard JSON or JSON5).
            verbose: If True, enables verbose output for debugging.
        """
        self.verbose = verbose
        self.json = json

    def batch(self, input: str, output: str, dry: bool = False, absolute: bool = False):
        # Protect against unintentional absolute paths
        if not absolute:
            if input[0] == "/" or input[0] == "\\":
                logger.error("An absolute input path was provided, but absolute is not set.")
                exit(1)
            elif output[0] == "/" or output[0] == "\\":
                logger.error("An absolute output path was provided, but absolute is not set.")
                exit(1)
        
        files = utils.scanForFiles(input, "recipes", exclude=["modinfo.json"])
        if not files:
            logger.error(f"No recipe files found in '{input}'. Skipping.")
            return
        for file in files:
            input_path = os.path.join(input, file)
            output_path = os.path.join(output, file)
            output_dir = os.path.dirname(output_path)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            self.run(input_path, output_path, dry)

    def run(self, input: str, output: str, dry: bool = False):
        """Runs the recipe generation process, expanding the grammar definitions into full recipes.
        If dry is True, it will only generate the keys for the recipes without writing them to a file."""
        try:
            # Sanity check, prevent overwriting the input file
            if os.path.abspath(input) == os.path.abspath(output):
                raise ValueError("Input and output paths must not be the same.")
            
            with open(input, "r", encoding="utf-8") as file:
                data = self.json.load(file)
            expander = RecipeExpander(data)
            success = expander.expand(self.json, dry, self.verbose, output)
            logger.success(f"Generated {len(success)} recipes from '{input}'.")

        except FileNotFoundError:
            raise utils.FileReadError(f"File '{input}' not found. Skipping.")

        except PermissionError as e:
            raise utils.FileWriteError(f"Could not write output: {e}")

        except KeyError as e:
            raise utils.MissingKeyError(e.args[0])

        except ValueError as e:
            raise utils.JSONParseError(str(e))

        except utils.GeneratorError as e:
            logger.error(str(e))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Expands recipe grammar definitions into full recipe files for Vintage Story mods.")
    parser.add_argument("source", help="Path to the input grammar JSON (or JSON5) file.")
    parser.add_argument("output", help="Path to output the finished recipe JSON (or JSON5) file.")
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
        logger.custom("Enforcing strict JSON parsing mode.", Ansi.GREEN,"🚀")
        json = __import__("json")
    
    generator = RecipeGenerator(json, args.verbose)
    if args.batch:
        generator.batch(args.source, args.output, args.dry, args.absolute)
    else:
        generator.run(args.source, args.output, args.dry)