from pathlib import Path
from datetime import datetime
from utils import info, warning, error, success, debug, custom

class Error_Level:
    DEBUG = 10
    INFO = 20
    SUCCESS = 25
    WARNING = 30
    ERROR = 40
    NONE = 100  # for fully silent

class Logger:
    def __init__(self, log_file="build.log", level=Error_Level.INFO):
        self.log_path = Path(log_file)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.level = level
        self.log_lines = []

    def _write(self, level, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] [{level}] {message[0] if isinstance(message, tuple) else message}"
        self.log_lines.append(line)

        if level >= self.level:
            if isinstance(message, tuple):
                print(custom(*message))
            else:
                pfunc = {
                    Error_Level.DEBUG: debug,
                    Error_Level.INFO: info,
                    Error_Level.SUCCESS: success,
                    Error_Level.WARNING: warning,
                    Error_Level.ERROR: error
                }.get(level, lambda x: x)
                print(pfunc(message))

    def debug(self, msg):   self._write(Error_Level.DEBUG, msg)
    def info(self, msg):    self._write(Error_Level.INFO, msg)
    def success(self, msg): self._write(Error_Level.SUCCESS, msg)
    def warning(self, msg): self._write(Error_Level.WARNING, msg)
    def error(self, msg):   self._write(Error_Level.ERROR, msg)
    def custom(self, level, msg, color, icon):
        self._write(level, (msg, color, icon))

    def save(self):
        with self.log_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(self.log_lines) + "\n")

logger = Logger()