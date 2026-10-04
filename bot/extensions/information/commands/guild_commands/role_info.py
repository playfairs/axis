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


from bot.base.imports import app_commands, commands, discord

PERMISSION_DISPLAY_LIMIT = 3500


def _split_permissions(permissions: list[str]) -> list[str]:
    chunks: list[str] = []
    current_chunk = ""

    for permission in permissions:
        entry = f"`{permission}`"
        next_chunk = f"{current_chunk}, {entry}" if current_chunk else entry
        if len(next_chunk) > PERMISSION_DISPLAY_LIMIT and current_chunk:
            chunks.append(current_chunk)
            current_chunk = entry
        else:
            current_chunk = next_chunk

    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def _role_type(role: discord.Role) -> str:
    if role.is_default():
        return "Default (@everyone)"
    if role.is_bot_managed():
        return "Bot-managed"
    if role.is_integration():
        return "Integration-managed"
    if role.is_premium_subscriber():
        return "Server Booster"
    return "Normal"


class RoleInfoView(discord.ui.LayoutView):
    def __init__(self, role: discord.Role) -> None:
        super().__init__()
        details = discord.ui.TextDisplay(
            f"**ID:** `{role.id}`\n"
            f"**Mention:** {role.mention}\n"
            f"**Created:** <t:{int(role.created_at.timestamp())}:F> "
            f"(<t:{int(role.created_at.timestamp())}:R>)\n"
            f"**Type:** {_role_type(role)}\n"
            f"**Members:** {len(role.members)}"
        )
        appearance_and_settings = discord.ui.TextDisplay(
            "### Appearance\n"
            f"**Color:** `#{role.color.value:06X}`\n"
            f"**Position:** {role.position}\n"
            f"**Icon:** {'Set' if role.icon is not None else 'None'}\n"
            f"**Emoji:** {role.unicode_emoji or 'None'}\n\n"
            "### Settings\n"
            f"**Hoisted:** {'Yes' if role.hoist else 'No'}\n"
            f"**Mentionable:** {'Yes' if role.mentionable else 'No'}\n"
            f"**Managed:** {'Yes' if role.managed else 'No'}\n"
            f"**Permission value:** `{role.permissions.value}`"
        )

        permissions = [
            name.replace("_", " ").title()
            for name, enabled in role.permissions
            if enabled
        ]
        permission_chunks = _split_permissions(permissions)
        permission_displays = [
            discord.ui.TextDisplay(
                f"### Permissions ({index}/{len(permission_chunks)})\n{chunk}"
            )
            for index, chunk in enumerate(permission_chunks, start=1)
        ]
        if not permission_displays:
            permission_displays.append(
                discord.ui.TextDisplay("### Permissions\nNone")
            )

        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay(f"## {role.name}"),
            discord.ui.Separator(),
        ]
        if role.icon is not None:
            items.append(
                discord.ui.Section(
                    details,
                    accessory=discord.ui.Thumbnail(
                        role.icon.url,
                        description=f"{role.name} role icon",
                    ),
                )
            )
        else:
            items.append(details)
        items.extend(
            (
                discord.ui.Separator(),
                appearance_and_settings,
                discord.ui.Separator(),
                *permission_displays,
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"-# Role in {role.guild.name}"),
            )
        )

        self.add_item(
            discord.ui.Container(
                *items,
                accent_color=role.color if role.color.value else None,
            )
        )


@commands.hybrid_command(name="roleinfo", aliases=("ri",))
@app_commands.describe(role="The role to show information about.")
@app_commands.guild_only()
async def role_info(ctx: commands.Context, role: discord.Role) -> None:
    """Show detailed information about a server role."""
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    await ctx.send(
        view=RoleInfoView(role),
        allowed_mentions=discord.AllowedMentions.none(),
    )