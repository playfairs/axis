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

from pathlib import Path

import asyncpg

SCHEMA_PATH = Path(__file__).parent / "schema" / "schema.sql"


async def initialize_database(database_url: str) -> asyncpg.Pool:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    try:
        async with pool.acquire() as connection:
            await connection.execute(schema)
    except BaseException:
        await pool.close()
        raise
    return pool
