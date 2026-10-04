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

# bot.extensions.information:servername
# Shows the server name, or renames the server
# if a name is specified.


from bot.base.imports import commands


@commands.command(name="servername", aliases=("sname", "guildname", "gname"))
@commands.has_guild_permissions(manage_guild=True)
async def server_name(
    ctx: commands.Context,
    name: str | None = None,
) -> None:
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    if name is None:
        await ctx.send(f"this servers name is: **{ctx.guild.name}**")
        return

    old_name = ctx.guild.name
    await ctx.guild.edit(name=name)

    await ctx.send(
        f"server name changed from **{old_name}** to **{name}**."
    )