# Generation.py
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
