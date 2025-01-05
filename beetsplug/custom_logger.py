import logging
from colorlog import ColoredFormatter
import re

# Color Dictionary
COLORS = {
    "GREEN": '\033[38;5;154m',
    "YELLOW": '\033[38;5;220m',
    "RED": '\033[31m',
    "PURPLE": '\033[35m',
    "ORANGE": '\033[33m',
    "RESET": '\033[0m'
}

# Platform Dictionary
PLATFORMS = {
    "SPOTIFY": COLORS["GREEN"],
    "YOUTUBE": COLORS["RED"],
    "SOUNDCLOUD": COLORS["ORANGE"]
}

class CustomLogger:
    def __init__(self, name, default_color='white', log_file=None):
        """
        Initialize the logger with default color and optional file logging.

        Args:
            name (str): Name of the logger.
            default_color (str): Default color for the logger.
            log_file (str, optional): Path to a log file. Defaults to None.
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)

        # Set up console handler with color
        console_handler = logging.StreamHandler()
        formatter = ColoredFormatter(
            "%(log_color)s%(asctime)s - %(name)s - [%(levelname)s] - %(message)s",
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': default_color,
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            },
        )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # Optional file handler
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - [%(levelname)s] - %(message)s"
            ))
            self.logger.addHandler(file_handler)

    def log(self, level, message):
        """
        Log a message at the specified level with custom formatting.

        Args:
            level (str): Logging level ('info', 'warning', 'error', etc.).
            message (str): The log message.
        """
        formatted_message = self._apply_custom_colors(message)
        getattr(self.logger, level.lower())(formatted_message)

    def _apply_custom_colors(self, message):
        """
        Apply custom color rules to a log message.

        Args:
            message (str): The original log message.

        Returns:
            str: The message with applied colors.
        """
        # Highlight items within curly braces
        message = re.sub(r"\{[^{}]+\}", lambda m: f"{COLORS['YELLOW']}{m.group()}{COLORS['RESET']}", message)

        # Highlight numbers
        message = re.sub(r"\d+", lambda m: f"{COLORS['PURPLE']}{m.group()}{COLORS['RESET']}", message)

        # Highlight success indicators
        message = re.sub(r"\b(success|successful)\b", lambda m: f"{COLORS['GREEN']}{m.group()}{COLORS['RESET']}", message, flags=re.IGNORECASE)

        # Highlight error indicators
        message = re.sub(r"\b(failure|error|failed)\b", lambda m: f"{COLORS['RED']}{m.group()}{COLORS['RESET']}", message, flags=re.IGNORECASE)

        # Highlight warning indicators
        message = re.sub(r"\b(warning|caution)\b", lambda m: f"{COLORS['ORANGE']}{m.group()}{COLORS['RESET']}", message, flags=re.IGNORECASE)

        # Highlight platforms
        for platform, color in PLATFORMS.items():
            message = re.sub(fr"\b{platform}\b", lambda m: f"{color}{m.group()}{COLORS['RESET']}", message, flags=re.IGNORECASE)

        return message
