import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class EnvironmentConfig:
    discord_token: str
    database_url: Optional[str]

    @classmethod
    def load(cls) -> "EnvironmentConfig":
        load_dotenv(PROJECT_ROOT / ".env")
        token = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
        if not token:
            raise RuntimeError(
                "DISCORD_TOKEN or TOKEN must be set in the project-root .env or process environment"
            )

        return cls(
            discord_token=token,
            database_url=os.getenv("DATABASE_URL"),
        )
