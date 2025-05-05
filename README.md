# Vintage Story Python Toolkit

A modular toolkit for transforming and managing JSON assets in [Vintage Story](https://www.vintagestory.at/). Designed to streamline content creation through grammar-driven logic for both shape and recipe files, with a build interface suitable for mod packaging and distribution.

> Created by Devon "Hyomoto" Mullane, 2025

---

## ✨ Features

- 🔧 **Recipe Generation**
  - Pure template-based recipe generation (no embedded grammars)
  - Key substitution and grouped injection with wildcard filtering
  - Grammar inheritance via `copyFrom`

- 📐 **Shape Mutation**
  - Grammar-driven transformation for correcting texture paths and element properties
  - Handles common ModelCreator issues (e.g., stripped face data)
  - Supports wildcard-based targeting and deep mutation

- 🧪 **Dry Run Mode**
  - Preview transformations without modifying files

- 🧰 **Build Integration**
  - CLI support for full build process, semantic versioning, and release packaging

- 🔍 **Strict & Relaxed Parsing**
  - Defaults to JSON; uses JSON5 if installed
  - Controlled via `settings.json`

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/Hyomoto/VSpythonTK.git
cd VSpythonTK
````

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

> Or install individually:

```bash
pip install json5 pydantic
```

### 3. Create `settings.json`

```json
{
  "input": "./input/",
  "output": "./output/",
  "absolute": false
}
```

### 4. Run the Toolkit

Use `generator.py` to run individual generators:

```bash
python generator.py --generate "shapes"
```

Use `build.py` to run the full project build pipeline:

```bash
python build.py --config Release --version Minor
```

---

## 📁 Project Structure

```
.
├── build.py           # High-level build and release script
├── generator.py       # Unified content generation interface
├── shapes.py          # Shape grammar processor
├── recipes.py         # Recipe generator from templates
├── utils.py           # Utility functions and ANSI formatting
├── logger.py          # Logging system with verbosity levels
├── settings.json      # Input/output configuration
```

---

## 📚 Grammar Overview

### 📐 Shape Grammar

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

* Uses `applyTo` with wildcards
* Targets specific faces or elements
* Optional `copyFrom` inheritance for reuse

### 🍲 Recipe Grammar

```json
[
    {
        "applyTo" : [ "sword.json" ],
        "records" : [
            {
                "keys" : [
                    { "key": "type", "value" : [ "sword" ] },
                    { "key": "hilt", "value" : [ "@types" ] },
                    { "key": "blade", "value" : [ "@guard" ] },
                    { "key": "metal", "value" : [ "@metal" ] }
                ]
            },
            {
                "copyFrom": 0,
                "keys": [
                    { "key": "type", "value": ["sword"] },
                    { "key": "hilt", "value": ["@types"] },
                    { "key": "blade", "value": ["@guard"] }
                ],
                "remove": [ "output.attributes" ],
                "substitute": [
                    { "key": "ingredients.M.code", "value": "pommel-guard-%hilt%-*" }
                ]
            }
        ]
    },
    {
        "static" : {
            "format": "\t{\n\t\t%ingredientPattern%, %copyAttributesFrom%, %width%, %height%,\n\t\t%ingredients%,\n\t\t%output%\n\t}",
            "code" : "%type%-%hilt%-%blade%-{material}",
            "types": [ "cross","curve","flat","rapier" ],
            "guard": [ "broad","long","thin" ],
            "metal": [ "copper", "tinbronze", "bismuthbronze", "blackbronze", "iron", "meteoriciron", "steel", "silver", "gold", "brass", "cupronickel", "electrum", "molybdochalkos", "chromium" ],
            "skip": [
                "*-long-copper",
                "*-long-bismuthbronze",
                "*-long-blackbronze",
                "*-long-cupronickel",
                "*-thin-copper",
                "*-curve-thin-*",
                "*-rapier-broad-*",
                "*-rapier-long-*"
            ]
        }
    }
]
```

* Grammars are cleanly separated from the files they operate on
---

## 📝 Notes

* By default paths are relative, setting absolute to True enables absolute paths
* Outputs are written to the paths in `settings.json`
* Use `--dry-run` to validate grammar logic before committing changes
* Shape and recipe generators can still be used independently for low-level debugging
* Top-level build interface (`build.py`) handles everything else

---

## 📜 License

MIT