# Vintage Story Python Toolkit

A modular toolkit for transforming and packaging JSON assets in [Vintage Story](https://www.vintagestory.at/). Point the toolkit at a mod project directory containing `vspythontk.json` to generate recipes/shapes, optionally compile a DLL, and produce a release ZIP—with hash-based skip for unchanged content vs code.

> Created by Devon "Hyomoto" Mullane, 2025

---

## Features

- **Recipe generation** — template expansion with `@tables`, `%tokens%`, `copyFrom`, allow/skip
- **Shape mutation / composition** — grammar-driven texture and face fixes, plus optional cleanup + part compositing (`generate` / `mods`)
- **Project-rooted builds** — one config file in the mod; toolkit runs from its own install
- **Packaging** — stage assets, compile DLL, zip for distribution
- **Hash cache** — separate content and DLL lanes; skip work when inputs are unchanged
- **Dry run** — preview generator output without writing files

---

## Getting Started

### 1. Install dependencies

```bash
cd VSpythonTK
pip install -r requirements.txt
```

### 2. Add `vspythontk.json` to your mod root

See [examples/vspythontk.json](examples/vspythontk.json). Paths are relative to the project directory (the folder that contains the config).

### 3. Run the toolkit (from the VSpythonTK folder)

```bash
# Full pipeline: stage → generate → compile → zip
python build.py path/to/mod

python build.py path/to/mod --config Release --version Minor
python build.py path/to/mod --force
python build.py path/to/mod --generate-only
python build.py path/to/mod --copy-to path/to/Mods/mymod.zip
python build.py path/to/mod --clean

# Generators only
python generator.py path/to/mod
python generator.py path/to/mod --dry-run --generate recipes
python generator.py --input path/to/mod/assets --output path/to/mod/dist/stage/assets --absolute
```

Playtest by pointing Vintage Story at `dist/stage` (or whatever you set as `stage`). The ZIP is written under `package.dir`. Use `--copy-to` to also copy that zip to a file path or directory (e.g. your Mods folder) after packaging.

---

## Project layout

```
mymod/
├── vspythontk.json      # Toolkit project config
├── mymod.csproj         # Optional; disable compile if content-only
├── assets/              # Authoring source (grammars, templates, patches, …)
│   └── modinfo.json     # Or at project root; optional sibling modicon.png
└── dist/                # Build output (created by toolkit)
    ├── stage/           # Playable mod tree
    ├── mymod-v1.0.0.zip
    └── .vspythontk-cache.json
```

`modinfo.json` is staged at the mod root. If `modicon.png` sits beside it, it is staged too.

Grammars stay co-located with the files they transform (`grammar*.json` beside templates/shapes). Grammar files are excluded from the staged package.

A folder may include `.buildignore` (fnmatch patterns, stem-aware — e.g. `thin` matches `thin.json`). That file only excludes paths from dumb copy / `stageExtra` staging; grammar discovery, `applyTo`, and `generate` still see ignored inputs and can emit mutated/composited outputs. `.buildignore` itself is never staged.

---

## Config overview

| Field | Purpose |
|-------|---------|
| `content.input` / `content.output` | Generator source and destination |
| `stage` | Full staged mod directory (zip root) |
| `package.dir` / `zipName` | Where to write `{name}-v{version}.zip` |
| `compile` | `enabled`, `csproj`, `targetFramework`, `dllOut`, … |
| `hash.cache` | Persisted content/dll SHA-256 digests |
| `generators` | `recipes` and/or `shapes` |
| `stageExtra` | Copy rules into stage (`exclude` defaults to `**/grammar*`) |

Set `"compile": { "enabled": false }` (or omit `csproj`) for content-only mods.

---

## Hash lanes

| Lane | When it runs | Skipped when |
|------|--------------|--------------|
| **content** | Stage copies + recipe/shape generators | Content inputs unchanged |
| **dll** | `dotnet build` + copy DLL into stage | C# / csproj inputs unchanged |

`--force` rebuilds both. If both are skipped and the ZIP already exists, the build reports up to date.

---

## Toolkit modules

```
.
├── build.py           # Project build / package orchestrator
├── generator.py       # Content generators entry point
├── project.py         # vspythontk.json load + path resolve
├── packaging.py       # Stage copy, DLL place, zip
├── hashing.py         # Content / DLL hash cache
├── shapes.py          # Shape grammar processor
├── recipes.py         # Recipe generator
├── utils.py           # Scanning and deep mutation helpers
├── logger.py          # Logging
└── examples/          # Sample project config
```

Low-level per-folder CLIs still work:

```bash
python recipes.py input_dir output_dir --batch
python shapes.py input_dir output_dir --batch --dry-run
```

Legacy cwd `settings.json` is only used when `generator.py` is run without a project path.

---

## Grammar overview

### Shape grammar

Mutate matching inputs into the output folder (`applyTo`):

```json
[
  {
    "applyTo": ["sword-*"],
    "textures": { "metal": "game:block/metal/ingot/iron" },
    "elements": {
      "faces": [
        {
          "keys": ["#metal"],
          "add": { "reflectiveMode": 2 },
          "remove": ["windMode"]
        }
      ]
    }
  }
]
```

Compose finished shapes from part files in the same folder (`cleanup` / `generate` / `mods`). Cleanup deletes matching files in the **output** directory only. Generate writes composites to output and does not copy unmatched source parts when `generate` is present. Named `mods` are reusable mutation blocks; `"mods": ["*"]` applies all of them in definition order.

```json
[
  { "cleanup": ["sword-*", "sword-rapier"] },
  {
    "generate": [
      {
        "name": "sword-{handle}-{blade}",
        "targets": {
          "blade": ["broad", "long", "thin"],
          "handle": ["cross", "curve", "flat"]
        },
        "mods": ["*"]
      },
      {
        "name": "sword-rapier",
        "targets": { "blade": ["thin"], "handle": ["rapier"] },
        "mods": ["base"]
      }
    ],
    "mods": {
      "base": {
        "textures": { "metal": "game:block/metal/ingot/iron" },
        "elements": {
          "faces": [
            {
              "keys": ["#metal"],
              "add": { "reflectiveMode": 2 },
              "remove": ["windMode"]
            }
          ]
        }
      }
    }
  }
]
```

### Recipe grammar

See the README history / `recipes.py` docstring for full `records`, `static`, `copyFrom`, `remove`, and `substitute` examples. Templates are normal Vintage Story recipe objects with `%key%` placeholders.

---

## License

MIT
