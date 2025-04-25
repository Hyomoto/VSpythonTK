# Generation.py
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
