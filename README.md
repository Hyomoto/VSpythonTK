# Vintage Story Python Toolkit

A modular toolset for transforming and managing JSON assets in [Vintage Story](https://www.vintagestory.at/), designed to streamline content creation by applying flexible grammar-driven logic to both recipe and shape files.

> Created by Devon "Hyomoto" Mullane, 2025

## Features

- 🔧 **Recipe Expansion**
  - Grammar-driven template-based recipe generation
  - Support for grouped key injection and deep field mutation
  - Wildcard filtering (`allow`, `skip`) and template inheritance (`copyFrom`)

- 📐 **Shape Mutation**
- - Handles common ModelCreator issues (e.g., texture mismatch or stripped properties)
  - Grammar-driven shape editing for correcting texture paths and face properties
  - Grammar inheritance ('copyFrom')

- 🧪 **Dry Run Support**
  - Preview generated output without modifying files

- 🔍 **Strict or Relaxed Parsing**
  - Supports [JSON5](https://json5.org/) if installed, defaults to standard JSON parsing

---

## Quick Start

### 1. Clone or Download

```bash
git clone https://github.com/Hyomoto/VSpythonTK.git
cd VSpythonTK
````

### 2. Setup

Optional (for JSON5 support):

```bash
pip install json5
```

### 3. Create a `settings.json`

```json
{
  "input": "./input/",
  "output": "./output/",
  "absolute": false
}
```

### 4. Run the Toolkit

```bash
python generator.py --strict --verbose
```

Use `--dry` to preview the generation process without writing output files.  Useful for making sure you've set things up correctly and your files are being found properly.

---

## File Structure

```
.
├── generator.py       # Entry point
├── shapes.py          # Shape grammar processor
├── recipes.py         # Recipe grammar processor
├── utils.py           # Utility functions and ANSI formatting
├── settings.json      # Configuration for input/output paths
```

---

## Grammar Overview

### Recipe Grammar

See `recipes.py` for full documentation. Recipes use `%key%` syntax and allow:

```json
{
  "template": { ... },
  "grammars": [
    {
      "keys": [ { "key": "metal", "value": ["copper", "steel"] } ],
      "remove": [ ... ],
      "substitute": [ ... ]
    }
  ]
}
```

### Shape Grammar

Shape grammars define what to modify and how:

```json
[
  {
    "applyTo": "sword-*",
    "textures": { "metal": "game:block/metal/ingot/iron" },
    "elements": {
      "faces": {
        "keys": ["#metal"],
        "add": { "reflectiveMode": 2 },
        "remove": ["windMode"]
      }
    }
  }
]
```

You may use `copyFrom` to extend an existing grammar.

---

## Notes

* The toolkit does not modify the original files, no outputs are written when `-dry` is used.
* Shape grammars affect only files whose name matches the `applyTo` field using Unix-style wildcards.
* Output is written to the path defined in `settings.json`, preserving structure.
* The individual generators can be run by themselves with additional options.

---

## License
MIT
