# 🛠️ Vintage Story Recipe Expander

**by Devon "Hyomoto" Mullane, 2025**

A powerful script to expand compact **recipe grammar definitions** into fully realized **Vintage Story** mod JSON recipes.

---

## ✨ Features

- **Template-based generation**  
  Define reusable recipe templates with minimal duplication.
- **Dynamic substitution**  
  Use named fields and static lookups to create massive variant sets.
- **Wildcard allow/skip**  
  Fine-grained control over which outputs are created.
- **Template inheritance**  
  Use `copyFrom` to clone and modify templates easily.
- **Smart remove/substitute**  
  Mutate nested template fields dynamically per grammar.
- **Strict or relaxed JSON parsing**  
  Use `-strict` to enforce JSON, or auto-detect JSON5 support.
- **Colorized output and rich warnings**  
  Built-in friendly CLI output for easy debugging.

---

## 📦 Installation

> Requires Python 3.10+ (for type hinting improvements).

Install `json5` for relaxed grammar file parsing:
```bash
pip install json5
```
*(Optional but allows parity with VS recipe definitions.)*

---

## 🚀 Usage

Expand recipes from a grammar file:

```bash
python generation.py path/to/grammar.json
```

Dry-run mode (preview only):

```bash
python generation.py path/to/grammar.json -dry
```

Force strict JSON parsing:

```bash
python generation.py path/to/grammar.json -strict
```

Verbose mode (show detailed outputs):

```bash
python generation.py path/to/grammar.json -verbose
```

---

## 📜 Grammar File Structure

**Top-level fields:**

| Field | Purpose |
|:------|:--------|
| `template` | Dictionary of recipe templates (direct VS recipe structure). |
| `grammars` | List of grammar expansions defining substitutions and output format. |
| `output` | Destination file path for the expanded JSON array. |
| `static` | Lookup table for dynamic value injection (e.g., metal types). |

---

### 🛠 Template Example

```json
"template": {
  "default": {
    "ingredientPattern": "SH,M_,T_",
    "ingredients": {
      "T": { "type": "item", "code": "blade-%type%-%blade%-*" },
      "M": { "type": "item", "code": "pommel-guard-%hilt%-%metal%" },
      "H": { "type": "item", "code": "game:hammer-*", "isTool": true }
    },
    "width": 2,
    "height": 3,
    "output": { "type": "item", "code": "%type%-%hilt%-%blade%-{material}" }
  }
}
```

---

### 🧩 Grammar Example

```json
"grammars": [
  {
    "keys": [
      { "key": "type", "value": ["sword", "dagger"] },
      { "key": "hilt", "value": ["cross", "curve"] },
      { "key": "blade", "value": ["broad", "thin"] },
      { "key": "metal", "value": ["copper", "steel"] }
    ]
  }
]
```

---

## ⚙️ Advanced Features

| Feature | Syntax Example | Purpose |
|:--------|:----------------|:--------|
| **Multi-key mapping** | `"key": "size,cost"` + paired list of values | Swap multiple fields together. |
| **Remove fields** | `"remove": ["output.attributes"]` | Strip nested fields from templates during generation. |
| **Substitute fields** | `"substitute": [{"key": "ingredients.L", "value": {...}}]` | Overwrite specific nested fields dynamically. |
| **Template inheritance** | `"copyFrom": "baseTemplate"` | Clone and extend existing templates easily. |

---

## 📋 License

MIT License (or feel free to modify for your own use!)

---

## ✨ Final Tip

Need help writing grammars, debugging weird expansions, or adding future features?  
Feel free to reach out — **good tools deserve good maintenance!**
