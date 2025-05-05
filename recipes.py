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

Grammar JSON Structure:
---------------------
[
  {
    "applyTo": "sword-*",                 # Required
    "records": [                          # Required
      "keys": [                           # Required
        { "key": "metal", "value": ["@metal"] },
        { "key": "type,blade", "value": ["dagger,broad", "sword,long"] }
      ],
      "code": "%type%-%blade%-%metal%",   # Optional; falls back to static.code
      "format": "%blade%-%metal%",        # Optional; falls back to static.format
      "remove": ["output.attributes.oldProperty"],
      "substitute": [{ "key": "output.quantity", "value": 2 }],
      "allow": ["*-copper"],              # Optional whitelist
      "skip": ["*steel*"]                 # Optional blacklist
    ]
  }
  {
    "static": {
        "metal": ["copper", "tinbronze", "steel"],
        "format": "{ ... }",                  # Optional default for grammars
        "code": "%metal%"                     # Optional default for grammars
    }
  }
]

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
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
import fnmatch
import os
import copy

from utils import Ansi
from utils import deep_remove
from utils import deep_set
from logger import logger
from logger import Error_Level
from generator import BaseGenerator
from generator import BaseGrammarJSON
from generator import BaseGrammar
from generator import CLI

VERSION = "0.3.0"
MODULE_NAME = f"{os.path.basename(__file__)}-{VERSION}".strip()

def hello() -> str:
    return (f"{MODULE_NAME}: Performing recipe expansion...", Ansi.CYAN, "🍲")

class RecipeJSON(BaseModel):
    ingredientPattern: str = Field(..., description="Pattern for matching ingredients")
    ingredients: Dict[str, Dict[str, int | str]] = Field(..., description="Dictionary of ingredients with their properties")
    copyAttributesFrom: str = Field(..., description="Ingredient to copy attributes from to resulting item")
    width: int = Field(..., description="Width of the recipe grid")
    height: int = Field(..., description="Height of the recipe grid")
    output: Dict = Field(..., description="Output details of the recipe")

class GrammarKey(BaseModel):
    key: str = Field(..., description="The key to be replaced in the recipe")
    value: list[str] = Field(..., description="The values to replace the key with")

class GrammarRecord(BaseModel):
    keys: list[GrammarKey] = Field(..., description="A list of keys to replace in the recipe")
    code: Optional[str] = Field(None, description="The the item code string for the recipe")
    format: Optional[str] = Field(None, description="The format string for the recipe")
    remove: Optional[list[str]] = Field(None, description="Keys to remove from the recipe")
    substitute: Optional[list[dict[str, int | str | List | Dict]]] = Field(None, description="Key-value pairs to substitute in the recipe")
    allow: Optional[list[str]] = Field(None, description="Item codes to allow in the recipe")
    skip: Optional[list[str]] = Field(None, description="Item codes to skip in the recipe")
    itemCodes: Optional[list[tuple[str, dict[str, str]]]] = Field(None, description="List of item codes generated from the grammar")

class Grammar(BaseModel):
    applyTo: list[str] = Field(..., description="The recipe files to apply this grammar to")
    copyFrom: Optional[str | int] = Field(None, description="The grammar to copy from")
    records: list[GrammarRecord] = Field(..., description="A list of grammar records to apply")
    code: str = Field(None, description="The item code string for the recipe")
    format: str = Field(..., description="The format string for the recipe")
    allow: Optional[list[str]] = Field(None, description="Item codes to allow in the recipe")
    skip: Optional[list[str]] = Field(None, description="Item codes to skip in the recipe")

class RecipeGrammarJSON(BaseGrammarJSON):
    @property
    def GRAMMAR(self):
        return RecipeGrammar
    
    @property
    def STATIC_FIELDS(self):
        return ["code", "format", "allow", "skip" ]
    
    @property
    def VALIDATE(self):
        return Grammar

class RecipeGrammar(BaseGrammar):
    keys: dict[str, GrammarKey]
    code: str
    format: str
    allow: Optional[list[str]]
    skip: Optional[list[str]]
    itemCodes: list[tuple[str, dict[str, str]]]

    def getCode(self, record: GrammarRecord) -> str:
        """Returns the item code for the given record."""
        if record.code:
            return record.code
        return self.code
    
    def getAllow(self, record: GrammarRecord) -> list[str]:
        """Returns the allow list for the given record."""
        if record.allow:
            return record.allow
        return self.allow or []
    
    def getSkip(self, record: GrammarRecord) -> list[str]:
        """Returns the skip list for the given record."""
        if record.skip:
            return record.skip
        return self.skip or []

    def __init__(self, data: Grammar, static: dict[str, any] = None):
        super().__init__()

        def buildItemCodes(record: GrammarRecord, table={}, depth=0):
            if depth == len(record.keys):
                code = self.doWildcardReplacement(self.getCode(record), table)
                allow = self.getAllow(record)
                skip = self.getSkip(record)

                if isAllowed(code, allow, skip):
                    logger.debug(f"Generating code: {code} with table: {table}")
                    record.itemCodes.append((code, table.copy()))
                else:
                    logger.debug(f"Skipping code: {code} due to allow/skip rules")
            else:
                entry = record.keys[depth]
                key = entry.key
                values = entry.value
                
                # Normalize keys to a list
                keyList = [k.strip() for k in key.split(",")]

                for value in values:
                    if not isinstance(value, list):
                        value = [value]

                    if len(keyList) != len(value):
                        raise ValueError(f"Key length ({len(keyList)}) and value length ({len(value)}) mismatch at depth {depth}")

                    newTable = table.copy()
                    for k, v in zip(keyList, value):
                        newTable[k] = v

                    buildItemCodes(record, newTable, depth + 1)

        def isAllowed(entry: str, allow: list[str], skip: list[str]) -> bool:
            for pattern in skip:
                if fnmatch.fnmatch(entry, pattern):
                    return False
            if allow:
                return any(fnmatch.fnmatch(entry, pattern) for pattern in allow)
            return True  # No allowed list means allow all

        self.itemCodes = []
        self.records = data.records
        self.code = data.code or static.get("code", None)
        self.format = data.format or static.get("format", None)
        self.allow = data.allow or static.get("allow", None)
        self.skip = data.skip or static.get("skip", None)

        if self.format:
            self.format = self.doStaticReplacement(self.format, static)
        if self.code:
            self.code = self.doStaticReplacement(self.code, static)
        if self.allow:
            self.allow = [self.doStaticReplacement(item, static) for item in self.allow]
        if self.skip:
            self.skip = [self.doStaticReplacement(item, static) for item in self.skip]

        for record in self.records:
            for key in record.keys:
                key.value = self.doStaticReplacement(key.value, static)
            record.code = self.doStaticReplacement(record.code, static) if record.code else None
            record.format = self.doStaticReplacement(record.format, static) if record.format else None
            record.remove = self.doStaticReplacement(record.remove, static) if record.remove else None
            record.substitute = self.doStaticReplacement(record.substitute, static) if record.substitute else None
            record.allow = self.doStaticReplacement(record.allow, static) if record.allow else None
            record.skip = self.doStaticReplacement(record.skip, static) if record.skip else None
            record.itemCodes = []
            buildItemCodes(record)

    def apply(self, recipe: RecipeJSON, json):
        """Mutates the input recipe by applying the grammar rules."""
        recipes = [] # List of generated recipes
        for record in self.records:
            for code, table in record.itemCodes:
                logger.verbose(f"Generating recipe for '{code}' with '{table}'")
                # Create a copy of the template for mutation
                if record.remove or record.substitute:
                    template = copy.deepcopy(recipe)
                    # Do removals and substitutions
                else:
                    template = recipe
                if record.remove:
                    for path in record.remove:
                        deep_remove(template, path)
                if record.substitute:
                    for item in record.substitute:
                        deep_set(template, item["key"], item["value"])
                # Duplicate the output format string
                recipeString = self.format
                
                unused_keys = [key for key in recipe if f"%{key}%" not in recipeString]
                if unused_keys:
                    logger.warning(f"Grammar template has unused keys: {Ansi.YELLOW}{unused_keys}{Ansi.RESET}")
                for key, value in template.items():
                    recipeString = recipeString.replace(f"%{key}%",f"\"{key}\":{json.dumps(value, separators=(",", ":"))}")
                try:
                    recipes.append(self.doWildcardReplacement(recipeString, table))
                except KeyError as e:
                    logger.error(f"KeyError: {e} in recipe: {recipeString}")
        logger.custom(Error_Level.VERBOSE, f"Generated {len(recipes)} recipes", Ansi.GREEN, "📜")
        return f"[\n{",\n".join(recipes)}\n]"

class Generator(BaseGenerator):
    @property
    def FOLDERS(self):
        return ["recipes"]

    @property
    def NAME(self):
        return "recipes"
    
    @property
    def GRAMMAR_JSON(self):
        return RecipeGrammarJSON

if __name__ == "__main__":
    CLI(Generator, hello)