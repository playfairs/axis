import copy

import asyncpg

from discord import app_commands

from bot.base.imports import commands, discord, logger
from bot.core.client.help import help_command

VERIFY_BUTTON_ID = "axis:verify"


def _database_pool(bot: object) -> asyncpg.Pool:
    pool = getattr(bot, "database_pool", None)
    if pool is None:
        raise RuntimeError("The verify command requires the bot's database pool.")
    return pool


def _read_only_channel_overwrite() -> discord.PermissionOverwrite:
    allowed = discord.Permissions(
        view_channel=True,
        read_message_history=True,
    )
    denied = discord.Permissions.all_channel() ^ allowed
    return discord.PermissionOverwrite.from_pair(allowed, denied)


async def _restore_overwrites(
    snapshots: list[
        tuple[
            discord.abc.GuildChannel,
            discord.Role,
            discord.PermissionOverwrite,
        ]
    ],
    *,
    reason: str,
) -> None:
    for channel, role, overwrite in reversed(snapshots):
        try:
            await channel.set_permissions(
                role,
                overwrite=None if overwrite.is_empty() else overwrite,
                reason=reason,
            )
        except discord.HTTPException:
            logger.exception(
                "Could not restore verification permissions on channel %s.",
                channel.id,
            )


async def _load_settings(
    bot: object,
    guild_id: int,
) -> asyncpg.Record | None:
    return await _database_pool(bot).fetchrow(
        """
        SELECT channel_id, unverified_role_id, verified_role_id, message_id
        FROM verification_settings
        WHERE guild_id = $1
        """,
        guild_id,
    )


async def on_member_join(bot: commands.Bot, member: discord.Member) -> None:
    settings = await _load_settings(bot, member.guild.id)
    if settings is None:
        return

    unverified_role = member.guild.get_role(settings["unverified_role_id"])
    if unverified_role is None:
        logger.error(
            "The configured unverified role is missing in guild %s.",
            member.guild.id,
        )
        return

    try:
        await member.add_roles(
            unverified_role,
            reason="Member joined a server with verification enabled.",
        )
    except discord.HTTPException:
        logger.exception(
            "Could not give the unverified role to member %s in guild %s.",
            member.id,
            member.guild.id,
        )


class VerificationControls(discord.ui.ActionRow):
    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.success,
        custom_id=VERIFY_BUTTON_ID,
    )
    async def verify_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        del _button
        view = self.view
        if not isinstance(view, VerificationView):
            raise RuntimeError("Verification controls are not attached correctly.")
        await view.verify_member(interaction)


class VerificationView(discord.ui.LayoutView):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "Click **Verify** below to finish verification and get "
                    "access to the server."
                ),
                discord.ui.Separator(),
                VerificationControls(),
            )
        )

    async def verify_member(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Verification can only be used inside a server.",
                ephemeral=True,
            )
            return

        settings = await _load_settings(interaction.client, guild.id)
        if settings is None:
            await interaction.response.send_message(
                "Verification isn't configured in this server. Please contact "
                "a server administrator.",
                ephemeral=True,
            )
            return
        if (
            interaction.message is None
            or interaction.message.id != settings["message_id"]
            or interaction.channel_id != settings["channel_id"]
        ):
            await interaction.response.send_message(
                "This verification panel is no longer active.",
                ephemeral=True,
            )
            return

        unverified_role = guild.get_role(settings["unverified_role_id"])
        verified_role_id = settings["verified_role_id"]
        verified_role = (
            guild.get_role(verified_role_id)
            if verified_role_id is not None
            else None
        )
        if unverified_role is None or (
            verified_role_id is not None and verified_role is None
        ):
            logger.error(
                "A configured verification role is missing in guild %s.",
                guild.id,
            )
            await interaction.response.send_message(
                "A verification role is missing. Please contact a server "
                "administrator.",
                ephemeral=True,
            )
            return

        member = interaction.user
        await interaction.response.defer(ephemeral=True)
        try:
            if unverified_role in member.roles:
                await member.remove_roles(
                    unverified_role,
                    reason="Member completed server verification.",
                )
            if verified_role is not None and verified_role not in member.roles:
                await member.add_roles(
                    verified_role,
                    reason="Member completed server verification.",
                )
        except discord.HTTPException:
            logger.exception(
                "Could not complete verification for member %s in guild %s.",
                member.id,
                guild.id,
            )
            await interaction.followup.send(
                "I couldn't update your roles. Please contact a server "
                "administrator.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "You're verified! You should now have access to the server.",
            ephemeral=True,
        )


persistent_views = (VerificationView(),)
listeners = {"on_member_join": on_member_join}


@commands.hybrid_group(
    name="verify",
    invoke_without_command=True,
    description="Configure server member verification.",
)
@commands.guild_only()
@commands.has_guild_permissions(manage_roles=True)
@commands.has_guild_permissions(manage_channels=True)
@commands.bot_has_guild_permissions(manage_roles=True, manage_channels=True)
@app_commands.guild_only()
@app_commands.default_permissions(manage_roles=True, manage_channels=True)
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.has_permissions(manage_channels=True)
async def verify(ctx: commands.Context) -> None:
    await ctx.invoke(help_command, command_name="verify")


@verify.command(
    name="setup",
    description="Post a verification button and set the member roles.",
)
@app_commands.describe(
    channel="The text channel where members will verify (defaults to #verify).",
    unverified_role="The role new members receive until they verify (defaults to @unverified).",
    verified_role="Optional role to give members after they verify.",
)
async def verify_setup(
    ctx: commands.Context,
    channel: discord.TextChannel | None = None,
    unverified_role: discord.Role | None = None,
    verified_role: discord.Role | None = None,
) -> None:
    guild = ctx.guild
    if guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    pool = _database_pool(ctx.bot)
    previous_settings = await _load_settings(ctx.bot, guild.id)

    created_role = False
    if unverified_role is None:
        previous_role_id = (
            previous_settings["unverified_role_id"]
            if previous_settings is not None
            else None
        )
        unverified_role = (
            guild.get_role(previous_role_id)
            if previous_role_id is not None
            else None
        )
        if unverified_role is None:
            unverified_role = discord.utils.get(
                guild.roles,
                name="unverified",
            )
        if unverified_role is None:
            try:
                unverified_role = await guild.create_role(
                    name="unverified",
                    permissions=discord.Permissions.none(),
                    reason=f"Created by {ctx.author} via verify setup",
                )
                created_role = True
            except discord.HTTPException as error:
                logger.warning(
                    "Could not create an unverified role in guild %s (%s).",
                    guild.id,
                    type(error).__name__,
                )
                await ctx.send(
                    "I couldn't create the unverified role. Check the bot's "
                    "Manage Roles permission and try again."
                )
                return

    if unverified_role.guild != guild or (
        verified_role is not None and verified_role.guild != guild
    ):
        await ctx.send("Choose roles from this server.")
        if created_role:
            try:
                await unverified_role.delete(
                    reason="Cleaning up an invalid verification setup"
                )
            except discord.HTTPException:
                logger.exception(
                    "Could not remove the unverified role created for failed "
                    "setup in guild %s.",
                    guild.id,
                )
        return
    if unverified_role.is_default() or unverified_role.managed:
        await ctx.send("Choose a regular, non-managed unverified role.")
        return
    if verified_role is not None and (
        verified_role.is_default() or verified_role.managed
    ):
        await ctx.send("Choose a regular, non-managed verified role.")
        return
    if verified_role == unverified_role:
        await ctx.send("The verified and unverified roles must be different.")
        return

    actor = ctx.author
    if not isinstance(actor, discord.Member):
        await ctx.send("Your server permissions couldn't be verified.")
        return
    if actor.id != guild.owner_id:
        selected_roles = [unverified_role]
        if verified_role is not None:
            selected_roles.append(verified_role)
        if any(role >= actor.top_role for role in selected_roles):
            await ctx.send(
                "You can only configure roles below your highest role."
            )
            if created_role:
                await unverified_role.delete(
                    reason="Cleaning up an unauthorized verification setup"
                )
            return

    bot_member = guild.me
    if (
        bot_member is None
        or not bot_member.guild_permissions.manage_roles
        or not bot_member.guild_permissions.manage_channels
    ):
        await ctx.send(
            "I need the Manage Roles and Manage Channels permissions to set up "
            "verification."
        )
        if created_role:
            await unverified_role.delete(
                reason="Cleaning up an incomplete verification setup"
            )
        return
    selected_roles = [unverified_role]
    if verified_role is not None:
        selected_roles.append(verified_role)
    if any(role >= bot_member.top_role for role in selected_roles):
        await ctx.send(
            "Move my highest role above the verification roles, then try again."
        )
        if created_role:
            await unverified_role.delete(
                reason="Cleaning up an incomplete verification setup"
            )
        return

    created_channel = False
    if channel is None:
        previous_channel_id = (
            previous_settings["channel_id"]
            if previous_settings is not None
            else None
        )
        saved_channel = (
            guild.get_channel(previous_channel_id)
            if previous_channel_id is not None
            else None
        )
        if isinstance(saved_channel, discord.TextChannel):
            channel = saved_channel
        else:
            channel = discord.utils.get(guild.text_channels, name="verify")

    if channel is not None and channel.guild != guild:
        await ctx.send("Choose a verification channel from this server.")
        if created_role:
            await unverified_role.delete(
                reason="Cleaning up an invalid verification setup"
            )
        return

    if channel is None:
        everyone_overwrite = _read_only_channel_overwrite()
        try:
            channel = await guild.create_text_channel(
                name="verify",
                overwrites={
                    guild.default_role: everyone_overwrite,
                    unverified_role: _read_only_channel_overwrite(),
                },
                reason=f"Created by {ctx.author} via verify setup",
            )
            created_channel = True
        except discord.HTTPException as error:
            logger.warning(
                "Could not create a verification channel in guild %s (%s).",
                guild.id,
                type(error).__name__,
            )
            await ctx.send(
                "I couldn't create the verification channel. Check the bot's "
                "Manage Channels permission and try again."
            )
            if created_role:
                await unverified_role.delete(
                    reason="Cleaning up an incomplete verification setup"
                )
            return

    channel_permissions = channel.permissions_for(bot_member)
    if (
        not channel_permissions.view_channel
        or not channel_permissions.send_messages
    ):
        await ctx.send(
            "I need permission to view and send messages in the verification "
            "channel."
        )
        if created_channel:
            await channel.delete(
                reason="Cleaning up an incomplete verification setup"
            )
        if created_role:
            await unverified_role.delete(
                reason="Cleaning up an incomplete verification setup"
            )
        return

    snapshots: list[
        tuple[
            discord.abc.GuildChannel,
            discord.Role,
            discord.PermissionOverwrite,
        ]
    ] = []
    panel: discord.Message | None = None
    try:
        if not created_channel:
            for role in (guild.default_role, unverified_role):
                snapshots.append((channel, role, channel.overwrites_for(role)))
            await channel.set_permissions(
                guild.default_role,
                overwrite=_read_only_channel_overwrite(),
                reason=f"Configured by {ctx.author} via verify setup",
            )
            await channel.set_permissions(
                unverified_role,
                overwrite=_read_only_channel_overwrite(),
                reason=f"Configured by {ctx.author} via verify setup",
            )

        for existing_channel in guild.channels:
            if existing_channel.id == channel.id:
                continue
            previous_overwrite = existing_channel.overwrites_for(unverified_role)
            snapshots.append(
                (
                    existing_channel,
                    unverified_role,
                    copy.copy(previous_overwrite),
                )
            )
            unverified_overwrite = copy.copy(previous_overwrite)
            unverified_overwrite.view_channel = False
            await existing_channel.set_permissions(
                unverified_role,
                overwrite=unverified_overwrite,
                reason=f"Restricted unverified members by {ctx.author}",
            )

        panel = await channel.send(
            view=VerificationView(),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await pool.execute(
            """
            INSERT INTO verification_settings (
                guild_id, channel_id, unverified_role_id, verified_role_id,
                message_id
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id)
            DO UPDATE SET
                channel_id = EXCLUDED.channel_id,
                unverified_role_id = EXCLUDED.unverified_role_id,
                verified_role_id = EXCLUDED.verified_role_id,
                message_id = EXCLUDED.message_id,
                updated_at = NOW()
            """,
            guild.id,
            channel.id,
            unverified_role.id,
            verified_role.id if verified_role is not None else None,
            panel.id,
        )
    except (discord.HTTPException, asyncpg.PostgresError) as error:
        logger.exception(
            "Verification setup failed in guild %s (%s).",
            guild.id,
            type(error).__name__,
        )
        if panel is not None:
            try:
                await panel.delete()
            except discord.HTTPException:
                logger.exception(
                    "Could not remove the verification panel after setup failed."
                )
        await _restore_overwrites(
            snapshots,
            reason="Rolling back failed verification setup",
        )
        if created_channel:
            try:
                await channel.delete(
                    reason="Cleaning up a failed verification setup"
                )
            except discord.HTTPException:
                logger.exception(
                    "Could not remove the verification channel after setup failed."
                )
        if created_role:
            try:
                await unverified_role.delete(
                    reason="Cleaning up a failed verification setup"
                )
            except discord.HTTPException:
                logger.exception(
                    "Could not remove the unverified role after setup failed."
                )
        await ctx.send(
            "Verification setup failed. I restored permissions where possible; "
            "please check the bot's permissions and try again."
        )
        return

    await ctx.send(
        f"Verification is set up in {channel}. New members will get "
        f"{unverified_role.mention} on join"
        + (
            f" and {verified_role.mention} after verifying."
            if verified_role is not None
            else "; no verified role will be added."
        ),
        allowed_mentions=discord.AllowedMentions.none(),
    )


@verify.command(name="disable", description="Turn off verification for this server.")
async def verify_disable(ctx: commands.Context) -> None:
    guild = ctx.guild
    if guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    removed_guild_id = await _database_pool(ctx.bot).fetchval(
        """
        DELETE FROM verification_settings
        WHERE guild_id = $1
        RETURNING guild_id
        """,
        guild.id,
    )
    if removed_guild_id is None:
        await ctx.send("Verification isn't configured in this server.")
        return
    await ctx.send(
        "Verification is disabled for new joins. Existing members keep their "
        "current roles; remove the unverified role from them manually if you "
        "want to unlock them.",
        allowed_mentions=discord.AllowedMentions.none(),
    )