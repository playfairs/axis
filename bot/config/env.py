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

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values, load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class EnvironmentConfig:
    discord_token: str
    database_url: str

    @classmethod
    def load(cls) -> "EnvironmentConfig":
        env_file = PROJECT_ROOT / ".env"
        file_values = dotenv_values(env_file)
        load_dotenv(env_file)
        token = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
        if not token:
            raise RuntimeError(
                "DISCORD_TOKEN or TOKEN must be set in the project-root .env or process environment"
            )

        database_url = os.getenv("DATABASE_URL") or file_values.get("DATABASE_URL")
        if not database_url:
            host = os.getenv("HOST") or file_values.get("HOST")
            user = os.getenv("DB_USER") or file_values.get("USER")
            password = os.getenv("DB_PASSWORD") or file_values.get("PASSWORD")
            database = os.getenv("DB_NAME") or file_values.get("DB")
            if not all((host, user, password, database)):
                raise RuntimeError(
                    "Set DATABASE_URL or HOST, USER, PASSWORD, and DB in the project-root .env or process environment"
                )
            database_url = (
                f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
                f"@{host}/{quote(database, safe='')}"
            )

        return cls(
            discord_token=token,
            database_url=database_url,
        )
