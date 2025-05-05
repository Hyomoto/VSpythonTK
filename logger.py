"""
logger.py

by Devon "Hyomoto" Mullane, 2025

A simple logging utility, provides control over logging levels and
exports a log file for later review.

Features:
---------
- Multiple logging levels: DEBUG, VERBOSE, INFO, SUCCESS, WARNING, ERROR
- Customizable log file path

Usage:
------
    from logger import logger, Error_Level

Notes:
------
- The logger defaults to INFO level, update logger.level to change.
"""
from pathlib import Path
from datetime import datetime
from utils import info, warning, error, success, debug, custom

class Error_Level:
    DEBUG = 10
    VERBOSE = 15
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
        self.enableDebug = False

    def _write(self, level, message):
        if not self.enableDebug and level <= Error_Level.DEBUG:
            return
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
    def verbose(self, msg): self._write(Error_Level.VERBOSE, msg)
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