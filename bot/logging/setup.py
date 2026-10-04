# This file is part of Axis.
#
# Copyright (c) 2026 playfairs
#
# This work is released into the public domain under the Unlicense.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# See the UNLICENSE file for details.

import copy
import logging
import sys
from typing import Literal

ANSI_COLORS = {
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "red": "\033[31m",
    "white": "\033[37m",
}

BoxColor = Literal["green", "yellow", "red"]
RESET = "\033[0m"
LEVEL_COLORS = {
    logging.DEBUG: ANSI_COLORS["cyan"],
    logging.INFO: ANSI_COLORS["green"],
    logging.WARNING: ANSI_COLORS["yellow"],
    logging.ERROR: ANSI_COLORS["red"],
    logging.CRITICAL: "\033[1;41m",
}

class ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record = copy.copy(record)
        color = LEVEL_COLORS.get(record.levelno, ANSI_COLORS["white"])
        record.levelname = f"{color}{record.levelname:<5}{RESET}"
        return super().format(record)
 
class Logger:
    @staticmethod
    def configure():
        logging.addLevelName(logging.WARNING, "WARN")
        logging.addLevelName(logging.CRITICAL, "FATAL")
        file_handler = logging.FileHandler("logs.log", "a", "utf-8")
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)-8s - %(name)s - %(message)s",
                datefmt="%H:%M:%S",
            )
        )

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            ColorFormatter(
                f"{ANSI_COLORS['green']}%(asctime)s{RESET} - "
                f"%(levelname)s - "
                f"{ANSI_COLORS['blue']}%(name)s{RESET} - %(message)s",
                datefmt="%H:%M:%S",
            )
        )

        logging.basicConfig(
            level=logging.DEBUG,
            handlers=[file_handler, console_handler],
        )

    def create_box(title: str, content_lines: list[str], color: BoxColor) -> str:
        width = max(len(title), *(len(line) for line in content_lines)) + 2
        top_border = f"┌─ {title}{'─' * (width - len(title))}┐"
        bottom_border = f"└{'─' * (width + 2)}┘"
        lines = [f"{ANSI_COLORS[color]}{top_border}{RESET}"]

        for line in content_lines:
            text_color = next(
                (
                    field_color
                    for field, field_color in (
                        ("User:", "cyan"),
                        ("Guild:", "yellow"),
                        ("Channel:", "blue"),
                        ("Command:", "magenta"),
                        ("Error:", "red"),
                    )
                    if field in line
                ),
                "white",
            )
            padding = " " * (width - len(line))
            lines.append(
                f"{ANSI_COLORS[color]}│{RESET} "
                f"{ANSI_COLORS[text_color]}{line}{padding}{RESET} "
                f"{ANSI_COLORS[color]}│{RESET}"
            )

        lines.append(f"{ANSI_COLORS[color]}{bottom_border}{RESET}")
        return "\n".join(lines)        
