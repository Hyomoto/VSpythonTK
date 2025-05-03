import os

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

def scanForDirectories(
    directory: str,
    folders: str | list[str],
    exclude: list[str] = ["__pycache__"]
) -> list[str]:
    if isinstance(folders, str):
        folders = [folders]
    output = []
    # Walk input directories to search for recipes
    for base_folder in os.listdir(directory):
        if base_folder in exclude:
            continue
        
        base_path = os.path.join(directory, base_folder)

        for folder in folders:
            # If no folder exists, continue
            derived_path = os.path.join(base_path, folder)
            if not os.path.isdir(derived_path):
                continue
            output.append(os.path.relpath(derived_path, directory))

            # Collect folders in subdirectories
            for root, dirs, _ in os.walk(derived_path):
                dirs[:] = [d for d in dirs if d not in exclude]
                output.extend([os.path.relpath(os.path.join(root, d), directory) for d in dirs])
    return output

def scanForFiles(
    directory: str,
    folders: str | list[str],
    filetypes: tuple[str] = (".json", ".json5"),
    exclude: list[str] = ["__pycache__"]
) -> list[str] | dict[str, list[str]]:
    """
    Collects all JSON files within a directory structure and returns their full and relative paths.

    Used to retrieve a list of every file under a given directory or set of directories. If a single
    folder is given, a flat list is returned. If multiple folders are passed, a dictionary is
    returned mapping each folder name to its list.

    Directories listed in 'exclude' will be skipped. Default is ['__pycache__'].
    """
    if isinstance(folders, str):
        folders = [folders]
    output = []

    dirList = scanForDirectories(directory, folders, exclude)
    for dir in dirList:
        full_path = os.path.join(directory, dir)
        for file in os.listdir(full_path):
            if file.endswith(filetypes):
                full_file = os.path.join(full_path, file)
                rel_path = os.path.relpath(full_file, directory)
                output.append(rel_path)
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