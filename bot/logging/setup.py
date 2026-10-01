import logging
import sys
from typing import Literal

from loguru import logger

BoxColor = Literal["green", "yellow", "red"]

ANSI_COLORS = {
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "red": "\033[31m",
    "white": "\033[37m",
}
RESET = "\033[0m"


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


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        level = (
            record.levelname
            if record.levelname in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
            else record.levelno
        )
        logger.opt(
            exception=record.exc_info,
            depth=6,
        ).log(level, record.getMessage())


def configure_logging() -> None:
    logger.remove()
    logger.level("DEBUG", color="<cyan>")
    logger.level("INFO", color="<green>")
    logger.level("WARNING", color="<yellow>")
    logger.level("ERROR", color="<red>")
    logger.level("CRITICAL", color="<magenta>")
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> - <blue>{name}</blue> - "
        "<level>{level.name}</level> - {message}",
        colorize=True,
        filter=lambda record: not record["extra"].get("axis_box", False),
    )
    logger.add(
        sys.stderr,
        level="INFO",
        format="{message}",
        colorize=False,
        filter=lambda record: record["extra"].get("axis_box", False),
    )
    logging.basicConfig(
        handlers=[InterceptHandler()],
        level=logging.INFO,
        force=True,
    )
