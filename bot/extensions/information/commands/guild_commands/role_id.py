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


import re

from bot.base.imports import app_commands, commands, discord

ROLE_MENTION = re.compile(r"<@&(\d+)>")


@commands.hybrid_command(
    name="roleid",
    aliases=("rid",),
    description="Look up a role by ID or mention and show its ID.",
)
@app_commands.describe(role_id="The role mention or ID to look up.")
@app_commands.guild_only()
async def role_id(
    ctx: commands.Context,
    *,
    role_id: str,
) -> None:
    """Show a role's ID from its mention, or its mention from its ID."""
    guild = ctx.guild
    if guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    mention = ROLE_MENTION.fullmatch(role_id)
    is_mention = mention is not None
    if is_mention:
        assert mention is not None
        role_id = mention.group(1)
    elif not role_id.isdecimal():
        await ctx.send("Provide a role mention or role ID.")
        return

    if len(role_id) > 20:
        await ctx.send("Invalid role ID.")
        return

    target_id = int(role_id)
    role = guild.get_role(target_id)
    if role is None:
        await ctx.send("Role not found in this server.")
        return

    if is_mention:
        response = f"**{role.name}**'s role ID is: `{role.id}`"
    else:
        response = f"Role with ID `{role.id}`: {role.mention} (**{role.name}**)"

    await ctx.send(
        response,
        allowed_mentions=discord.AllowedMentions.none(),
    )