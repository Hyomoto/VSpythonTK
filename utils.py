import os
import fnmatch
from pathlib import Path
import time

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

class GeneratorError(Exception):
    """Base class for all generator-related exceptions."""
    pass

class FileReadError(GeneratorError):
    """Raised when the input file cannot be read."""
    pass

class FileWriteError(GeneratorError):
    """Raised when the output file cannot be written."""
    pass

class JSONParseError(GeneratorError):
    """Raised when the input JSON is invalid or missing keys."""
    pass

class InvalidPathError(GeneratorError):
    """Raised when input and output paths are the same or invalid."""
    pass

class MissingKeyError(JSONParseError):
    """Raised when a required key is missing from JSON."""
    def __init__(self, key: str):
        super().__init__(f"Missing required key: {key}")
        self.key = key

def warning(message: str) -> str:
    return f"{Ansi.YELLOW}[⚠️ ]{Ansi.RESET} {message}"

def error(message: str) -> str:
    return f"{Ansi.RED}[❗]{Ansi.RESET} {message}"

def info(message: str) -> str:
    return f"{Ansi.BLUE}[ℹ️ ]{Ansi.RESET} {message}"

def success(message: str) -> str:
    return f"{Ansi.GREEN}[✅]{Ansi.RESET} {message}"

def debug(message: str) -> str:
    return f"{Ansi.GRAY}[🔍]{Ansi.RESET} {message}"

def custom(message: str, color: str, icon: str) -> str:
    return f"{color}[{icon}]{Ansi.RESET} {message}"

def load_ignore_rules(ignore_file=".buildignore"):
    patterns = []
    path = Path(ignore_file)
    if path.exists():
        with open(path) as f:
            patterns = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return patterns

def scanForDirectories(
    directory: str,
    folders: str | list[str],
    exclude: list[str] = []
) -> list[str]:
    def walk_dir(base_path: Path):
        ignore_file = base_path / ".buildignore"
        local_exclude = exclude + load_ignore_rules(ignore_file) if ignore_file.exists() else exclude

        for entry in base_path.iterdir():
            if entry.is_dir() and not any(fnmatch.fnmatch(entry.name, pat) for pat in local_exclude):
                rel = entry.relative_to(directory)
                output.append(str(rel))
                walk_dir(entry)
    
    if isinstance(folders, str):
        folders = [folders]

    ignore_file = Path(directory) / ".buildignore"
    if ignore_file.exists():
        exclude.extend(load_ignore_rules(ignore_file))
    
    output = []

    for dir in Path(directory).iterdir():
        if not dir.is_dir() or any(fnmatch.fnmatch(dir.name, pat) for pat in exclude):
            continue
        for name in folders:
            start_path = Path(dir) / name
            if start_path.exists() and start_path.is_dir():
                walk_dir(start_path)
    return output

def scanForFiles(
    directory: str,
    folders: str | list[str] | None = None,
    filetypes: tuple[str] = (".json", ".json5"),
    exclude: list[str] = []
) -> list[str]:
    """
    Collects all JSON files within a directory structure and returns their full and relative paths.

    Used to retrieve a list of every file under a given directory or set of directories. If a single
    folder is given, a flat list is returned. If multiple folders are passed, a dictionary is
    returned mapping each folder name to its list.

    Directories listed in 'exclude' will be skipped. Default is ['__pycache__'].
    """
    if folders:
        search = scanForDirectories(directory, folders, exclude)
        search = [Path(directory) / folder for folder in search]
    else:
        search = [directory]
    output = []
    
    ignore_file = Path(directory) / ".buildignore"
    local_exclude = exclude + load_ignore_rules(ignore_file) if ignore_file.exists() else exclude
    
    for dir in search:
        for entry in Path(dir).iterdir():
            # if the entry is a file and has the correct extension, add it to the list
            if entry.is_file() and entry.suffix in filetypes and not any(fnmatch.fnmatch(entry.name, pat) for pat in local_exclude):
                rel = entry.relative_to(directory)
                output.append(str(rel))
    return output

def deep_remove(data: dict, path: str):
    parts = path.split(".")
    current = data
    
    for part in parts[:-1]:
        if part not in current:
            raise KeyError(f"Cannot remove '{Ansi.YELLOW}{path}{Ansi.RESET}': '{part}' does not exist.")
        if not isinstance(current[part], dict):
            raise KeyError(f"Cannot remove '{Ansi.YELLOW}{path}{Ansi.RESET}': '{part}' is not a dictionary.")
        current = current[part]

    if parts[-1] not in current:
        raise KeyError(f"Cannot remove '{Ansi.YELLOW}{path}{Ansi.RESET}': final key '{parts[-1]}' does not exist.")

    current.pop(parts[-1])

def deep_set(data: dict, path: str, value):
    parts = path.split(".")
    for part in parts[:-1]:
        if part not in data or not isinstance(data[part], dict):
            data[part] = {}
        data = data[part]
    data[parts[-1]] = value

class Timer:
    def __init__(self):
        self.start_time = None
        self.end_time = None

    def start(self):
        self.start_time = time.perf_counter()
        return self

    def stop(self):
        self.end_time = time.perf_counter()
        return self

    def elapsed(self):
        if self.start_time is None or self.end_time is None:
            raise ValueError("Timer has not been started and stopped properly.")
        return self.end_time - self.start_time