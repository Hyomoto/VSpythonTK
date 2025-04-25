"""
generation.py

by Devon "Hyomoto" Mullane, 2025

This script expands compact JSON recipe grammar definitions into fully realized
recipe JSON entries for use in Vintage Story mods.

It supports:
- Template-based recipe definition using raw JSON structures.
- Substitution of named fields across multiple permutations of materials.
- Static lookup tables (`@metal`, `@skip`, etc.) for value injection.
- Optional wildcard filtering via `allow` and `skip` pattern rules (using fnmatch).
- Dry-run mode to preview results without generating output files.

Input Structure:
----------------
The source JSON must include the following top-level fields:

- "template": A dictionary of named templates, each with:
    - "raw":    A JSON dictionary representing the normal recipe structure with placeholders (e.g., %metal%).
    - "format": A string that defines how the keys from "raw" will be flattened and joined into final output.

- "grammars": A dictionary of substitution rules. Each grammar defines:
    - "template": (Optional) The template to use (default: "default").
    - "keys": A list of { "key": "name", "value": [...] } entries. Values may include static lookups like "@metal".
    - "code": Pattern matching isn't as robust as in-engine, but this is used to define the name that will be used in the allow/skip lists.
    - "allow": A list of wildcard patterns that must match the final code (optional).
    - "skip": A list of wildcard patterns that will exclude a code from output (optional).

- "output": The file path where the result will be written (e.g., "recipes/dagger.json").

- "static": A lookup table used to inject lists of values into grammars, such as:
    "metal": ["copper", "tinbronze", "steel"]

Usage:
------
To generate recipe files:
    python generation.py path/to/input.json

To preview outputs without writing files:
    python generation.py path/to/input.json -dry

Examples:
---------
Given a grammar with:
    "type": "dagger"
    "blade": "broad,thin"
    "metal": "@metal"

And a template with:
    "code": "%type%-%blade%-%metal%"

It will generate:
    dagger-broad-copper
    dagger-thin-copper
    dagger-broad-steel
    dagger-thin-steel
    ...

Tips/tricks:
------------
If you do not define code, allow or skip fields, it will attempt to use any static defined option.  This makes it easy to write
once, reuse everywhere if required.

"""
from typing import TypedDict, Dict, List
import fnmatch
import argparse
import platform
import os

try:
    import json5 as json
    json5 = True
except ImportError:
    import json as json
    json5 = False

class Ansi:
    RESET = "\033[0m"
    BOLD = "\033[1m"

    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"

class TemplateJSON(TypedDict):
    template : Dict[str,Dict[str, str]]
    grammars : Dict[str, str]
    output : str
    static : Dict[str,List[str]]

class Grammar():
    def __init__(self,definition : Dict[ str, List[Dict[str,str]]], static : Dict[str,List[str]] ):
        def substitute(list : list[str],static : Dict[str,List[str]],ignore=False ):
            output = []
            for token in list:
                if token.startswith("@"):
                    key = token[1:]
                    table = static.get(key)
                    if table:
                        output.extend(table)
                    elif not ignore:
                        raise ValueError(f"Static substitution failed: {Ansi.YELLOW}@{key}{Ansi.RESET} not found.")
                else:
                    output.append(token)
            return output
        
        self.template =  definition.get("template", "default")
        
        self.keys = []
        
        if "keys" not in definition or not isinstance(definition["keys"], list):
            raise ValueError(f"Grammar definition must contain a {Ansi.YELLOW}'keys'{Ansi.RESET} list.")

        for key in definition["keys"]:
            if "key" not in key or "value" not in key:
                raise ValueError(f"Each key entry must contain {Ansi.YELLOW}'key'{Ansi.RESET} and {Ansi.YELLOW}'value'{Ansi.RESET}: {json.dumps(key)}")
            self.keys.append({ "key" : key["key"], "value" : substitute(key["value"],static)})
        
        self.skip = substitute(definition.get("skip", [ "@skip" ]),static,True)
        self.allow = substitute(definition.get("allow", [ "@allow" ]),static,True)
        self.code   = substitute([definition.get("code", "@code")],static,True)[0]

class RecipeExpander:
    def __init__(self, data : TemplateJSON):
        self.error = False
        self.grammars : list[Grammar] = []
        self.templates = {}

        for templateName, template in data["template"].items():
            if "format" not in template or "raw" not in template:
                raise ValueError(f"Template '{templateName}' must contain both {Ansi.YELLOW}'format'{Ansi.RESET} and {Ansi.YELLOW}'raw'{Ansi.RESET} fields.")
            templateFormat = template.get("format")

            unused_keys = [key for key in template["raw"] if f"%{key}%" not in templateFormat]
            if unused_keys:
                print(f"{Ansi.YELLOW}[!]{Ansi.RESET} Warning: Template {Ansi.YELLOW}'{templateName}'{Ansi.RESET} has unused keys in 'raw': {Ansi.YELLOW}{unused_keys}{Ansi.RESET}")
            for key, value in template["raw"].items():
                templateFormat = templateFormat.replace(f"%{key}%",f"\"{key}\":{json.dumps(value, separators=(",", ":"))}")
            self.templates[templateName] = templateFormat
            
        for grammar in data["grammars"]:
            self.grammars.append( Grammar( grammar, data["static"] ))
        
        self.output = data["output"]

    def expand(self, dry, verbose):
        def substitute(template :str, substitutions: Dict[str,str]):
            missing = [part for part in template.split("%") if part.endswith("%") and part[:-1] not in substitutions]
            if missing:
                raise KeyError(f"Template contains missing substitutions: {Ansi.YELLOW}{missing}{Ansi.RESET}")
            for key, value in substitutions.items():
                template = template.replace(f"%{key}%", value)
            return template
        
        def isAllowed(entry: str, allow: list[str], skip: list[str]) -> bool:
            for pattern in skip:
                if fnmatch.fnmatch(entry, pattern):
                    return False
            if allow:
                return any(fnmatch.fnmatch(entry, pattern) for pattern in allow)
            return True  # No allowed list means allow all
        
        def dryCallback(grammar, result, output):
            nonlocal count, verbose
            
            code = substitute(grammar.code, result)
            
            if( verbose and isAllowed(code, grammar.allow, grammar.skip)):
                print( f"  {code}\t [{json.dumps(result)}]" )
            count += 1

        def wetCallback(grammar, result, output):
            code = substitute(grammar.code, result)
            
            if( not isAllowed(code, grammar.allow, grammar.skip)):
                return
            if (verbose):
                print( f"  {code}\t [{json.dumps(result)}]" )
            
            template = self.templates.get(grammar.template)
            if not template:
                print( f"\tSkipped '{json.dumps(result)}' as '{Ansi.YELLOW}{grammar.template}{Ansi.RESET}' template didn't exist.")
                return
            output.append(substitute(template, result))

        def walkSubstitutions(grammar, depth, last, table,callback, output = None):
            key = grammar.keys[depth]["key"]
            for item in grammar.keys[depth]["value"]:
                table[key] = item
                if depth == last:
                    callback(grammar, table, output)
                else:
                    walkSubstitutions(grammar, depth + 1, last, table,callback, output)

        count = 0

        if (dry):
            print("Generating entry names...")
            if (verbose):
                print("Recipe item code\t\t\tRecipe Values")
            for grammar in self.grammars:
                walkSubstitutions( grammar, 0, len(grammar.keys) - 1, {}, dryCallback)
            print(f"Found {len(self.grammars)} grammars that produced {count} outputs.")
            
        else:
            print(f"Generating entries to {self.output}...")

            directory = os.path.dirname(self.output)

            if not os.access(os.path.dirname(self.output) or ".", os.W_OK):
                raise PermissionError(f"Cannot write to output directory: {Ansi.YELLOW}{self.output}{Ansi.RESET}")

            if directory:
                os.makedirs(directory, exist_ok=True)

            with open(self.output, "w", encoding="utf-8") as file:
                recipes = []

                for grammar in self.grammars:
                    walkSubstitutions( grammar, 0, len(grammar.keys) - 1,{}, wetCallback, recipes)

                file.write(f"[\n{",\n".join(recipes)}\n]")
                
                print(f"Found {len(self.grammars)} grammars that produced {len(recipes)} outputs.")

def main():
    def header(message: str, width: int = 60):
        if width < len(message) + 4:
            width = len(message) + 4

        horizontal = "-" * (width - 2)
        padding = (width - 2 - len(message)) // 2
        line = "|{}{}{}|".format(" " * padding, message, " " * (width - 2 - len(message) - padding))

        print(f"/{horizontal}\\")
        print(line)
        print(f"\\{horizontal}/")
    
    parser = argparse.ArgumentParser(description="Converts recipe grammar definitions into full recipe files.")
    parser.add_argument("source", help="Path to the JSON file containing recipe grammar definitions.")
    parser.add_argument("-dry", "-d", action="store_true", help="Dry run; only print outputs instead of writing files.")
    parser.add_argument("-quiet", "-q", action="store_false", help="Makes the output less verbose.")
    parser.add_argument("-strict", "-s", action="store_true", help="Enforces JSON for processing instead of JSON5.")
    args = parser.parse_args()
    
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")
    
    print(f"{Ansi.CYAN}")
    header("🛠️  Expanding Recipes...")
    print(f"{Ansi.RESET}")

    if ( json5 ):
        print( f"{Ansi.YELLOW}[!]{Ansi.RESET} JSON5 is available, this allows for a more relaxed format.")
    else:
        print( f"{Ansi.YELLOW}[!]{Ansi.RESET} Using strict JSON parsing, if you encounter problems\n  install json5: pip install json5")

    try:
        with open(args.source, "r", encoding="utf-8") as file:
            data = json.load(file)

        expander = RecipeExpander(data)
        expander.expand(args.dry,args.quiet)
    except FileNotFoundError:
        print(f"{Ansi.RED}[ ERROR ]{Ansi.RESET} File '{args.source}' not found.")
    except KeyError as e:
        print(f"{Ansi.RED}[ ERROR ]{Ansi.RESET} Missing required key: {e}")
    except ValueError as e:
        print(f"{Ansi.RED}[ ERROR ]{Ansi.RESET} {e}")
    except PermissionError as e:
        print(f"{Ansi.RED}[ ERROR ]{Ansi.RESET} Could not write output: {e}")

if __name__ == "__main__":
    main()