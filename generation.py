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
- Template inheritance using `copyFrom` for duplicating and modifying existing templates.
- Per-grammar template mutation using `remove` and `substitute` directives.
- Grouped multi-key substitutions (e.g., "metal,bits" mapped together).
- Dry-run mode to preview results without generating output files.
- Strict JSON mode (-strict) to enforce standard JSON parsing even if JSON5 is installed.

Input Structure:
----------------
The source JSON must include the following top-level fields:

- "template": A dictionary of named templates, each representing the Vintage Story recipe structure directly.
  - Templates may optionally specify a `copyFrom` field to clone and override an existing template.

- "grammars": A dictionary of substitution rules. Each grammar defines:
  - "keys": (Required) A list of { "key": "name", "value": [...] } entries. 
    - Keys may be comma-separated to allow grouped substitution (e.g., "metal,bits").
  - "code": (Optional) A format string defining the output item code. If not specified, looks for "code" in static.
  - "format": (Optional) A format string used to map template fields into the final JSON entry. If not specified, looks for "format" in static.
  - "template": (Optional) The template to use. If not specified, "default" is assumed.
  - "remove": (Optional) A list of dotted key paths to delete from the template.
  - "substitute": (Optional) A list of { "key": dotted_key, "value": replacement_value } entries to override fields before expansion.
  - "allow": (Optional) A list of wildcard patterns to include.
  - "skip": (Optional) A list of wildcard patterns to exclude.

- "output": The file path where the result will be written (e.g., "recipes/dagger.json").

- "static": A lookup table used to inject lists of values into grammars, such as:
  "metal": ["copper", "tinbronze", "steel"]
  - "format" : (Reserved) If specified, grammars missing a 'format' field will use this value.
  - "code" : (Reserved) If specified, grammars missing a 'code' field will use this value.

Usage:
------
To generate recipe files:
    python generation.py path/to/input.json

To preview outputs without writing files:
    python generation.py path/to/input.json -dry

To force strict JSON parsing mode:
    python generation.py path/to/input.json -strict

Examples:
---------
Given a grammar with:
    "template": "dagger"
    "keys": [ {"key": "metal", "value": ["@metal"]} ]
    "code": "%type%-%blade%-%metal%"
    "format": "%blade%-%metal%"

And a template with:
    {
        "blade": "%blade%",
        "metal": "%metal%"
    }

It will generate entries like:
    broad-copper
    thin-copper
    broad-steel
    thin-steel
    ...

Notes:
------
Templates are now pure recipe structures and can be copied and extended using `copyFrom`.
Formats for template expansion are specified in the grammars.
Grouped key substitution and per-grammar template modifications (remove/substitute) allow highly flexible and efficient recipe generation.
Strict JSON parsing (-strict) is available for increased speed and validation.
"""
from typing import TypedDict, Dict, List
import fnmatch
import argparse
import platform
import os
import copy
import re

try:
    import json5 as json
    json5 = True
except ImportError:
    import json
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
    output : str
    static : Dict[str,List[str]]

def warning(message: str) -> str:
    return f"{Ansi.YELLOW}[⚠️]{Ansi.RESET} {message}"

def error(message: str) -> str:
    return f"{Ansi.RED}[❗]{Ansi.RESET} {message}"

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
            raise ValueError(error(f"Grammar definition must contain '{Ansi.YELLOW}keys{Ansi.RESET}' list."))
        
        for key in definition["keys"]:
            if "key" not in key or "value" not in key:
                raise ValueError(f"Each key entry must contain '{Ansi.YELLOW}key{Ansi.RESET}' and '{Ansi.YELLOW}value{Ansi.RESET}': {json.dumps(key)}")
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
        
        self.output = data["output"]

    def expand(self, dry, verbose):
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
        
        def dryCallback(grammar : Grammar, result, output):
            nonlocal count, verbose
            
            code = substitute(grammar.code, result)
            
            if( verbose and isAllowed(code, grammar.allow, grammar.skip)):
                print( f"  {code}\t [{json.dumps(result)}]" )
            count += 1

        def wetCallback(grammar : Grammar, result, output):
            def deep_remove(data: dict, dotted_key: str):
                parts = dotted_key.split(".")
                current = data
                
                for part in parts[:-1]:
                    if part not in current:
                        raise KeyError(f"Cannot remove '{Ansi.YELLOW}{dotted_key}{Ansi.RESET}': '{part}' does not exist.")
                    if not isinstance(current[part], dict):
                        raise KeyError(f"Cannot remove '{Ansi.YELLOW}{dotted_key}{Ansi.RESET}': '{part}' is not a dictionary.")
                    current = current[part]

                if parts[-1] not in current:
                    raise KeyError(f"Cannot remove '{Ansi.YELLOW}{dotted_key}{Ansi.RESET}': final key '{parts[-1]}' does not exist.")

                current.pop(parts[-1])

            def deep_set(data: dict, dotted_key: str, value):
                """Recursively set a dotted key inside a dict."""
                parts = dotted_key.split(".")
                for part in parts[:-1]:
                    if part not in data or not isinstance(data[part], dict):
                        data[part] = {}
                    data = data[part]
                data[parts[-1]] = value
            code = substitute(grammar.code, result)
            
            if( not isAllowed(code, grammar.allow, grammar.skip)):
                return
            if (verbose):
                print( f"  {code}\t [{json.dumps(result)}]" )
            template    = copy.deepcopy(self.templates[grammar.template])
            
            for key in grammar.remove:
                deep_remove(template, key)
            for item in grammar.substitute:
                deep_set(template, item["key"], item["value"])
            templateFormat = grammar.templateFormat

            unused_keys = [key for key in template if f"%{key}%" not in templateFormat]
            if unused_keys:
                print(warning(f"Grammar template has unused keys: {Ansi.YELLOW}{unused_keys}{Ansi.RESET}"))
            for key, value in template.items():
                templateFormat = templateFormat.replace(f"%{key}%",f"\"{key}\":{json.dumps(value, separators=(",", ":"))}")
            output.append(substitute(templateFormat, result))

        def walkSubstitutions(grammar, depth, last, table,callback, output = None):
            key = grammar.keys[depth]["key"]
            values = grammar.keys[depth]["value"]

            for item in values:
                for i, swap in enumerate(key):
                    table[swap] = item[i]
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
                    if (len(grammar.keys) == 0):
                        wetCallback(grammar,{},recipes)
                    else:
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
    
    parser = argparse.ArgumentParser(description="Expands recipe grammar definitions into full recipe files for Vintage Story mods.")
    parser.add_argument("source", help="Path to the input grammar JSON (or JSON5) file.")
    parser.add_argument("-dry", "-d", action="store_true", help="Dry run: preview generated outputs without writing files.")
    parser.add_argument("-verbose", "-v", action="store_true", help="Enable verbose output, shows internal recipe states.")
    parser.add_argument("-strict", "-s", action="store_true", help="Force strict JSON parsing (even if JSON5 support is available).")
    args = parser.parse_args()
    
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")
    
    print(f"{Ansi.CYAN}")
    header("🛠️  Expanding Recipes...")
    print(f"{Ansi.RESET}")

    if args.strict and json5:
        import json as strict_json
        global json
        json = strict_json
        print(f"{Ansi.GREEN}[🚀]{Ansi.RESET} Enforcing strict JSON parsing mode.")
    elif json5:
        print(f"{Ansi.CYAN}[ℹ️]{Ansi.RESET} JSON5 detected: relaxed parsing is available.")
    else:
        print(f"{Ansi.YELLOW}[⚡]{Ansi.RESET} JSON5 not available. Using strict JSON parsing.\n     To enable relaxed parsing, install with: pip install json5")

    error = False

    try:
        with open(args.source, "r", encoding="utf-8") as file:
            data = json.load(file)

        expander = RecipeExpander(data)
        expander.expand(args.dry,args.verbose)
    except FileNotFoundError:
        print(error(f"File '{args.source}' not found."))
    except KeyError as e:
        print(error(f"Missing required key: {e}"))
        error = True
    except ValueError as e:
        print(error(e))
        error = True
    except PermissionError as e:
        print(error(f"Could not write output: {e}"))
        error = True
    finally:
        if ( error ):
            print(error("Recipe generation failed. Please check the input grammar and try again."))
        else:
            print(f"{Ansi.GREEN}[🎉]{Ansi.RESET} Generation completed successfully!")

if __name__ == "__main__":
    main()
