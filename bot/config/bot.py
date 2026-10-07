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

from dataclasses import dataclass

from bot.config import COGS, DISCORD


@dataclass(frozen=True)
class BotConfig:
    command_prefixes: tuple[str, ...] = DISCORD.PREFIXES
    owner_ids: frozenset[int] = DISCORD.OWNER_IDS
    extensions: tuple[str, ...] = COGS.EXTENSIONS
    skipped_extensions: frozenset[str] = COGS.SKIP

    def prefixes_for(self, bot_id: int | None) -> tuple[str, ...]:
        if bot_id is not None and bot_id in DISCORD.PREFIX_OVERRIDES:
            return DISCORD.PREFIX_OVERRIDES[bot_id]
        return self.command_prefixes
