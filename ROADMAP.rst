Axis command reference and roadmap
==================================

This document describes commands loaded by the current default configuration,
followed by proposed commands that are not available yet. Prefix commands can
use any configured prefix: ```,``, ``!``, or ``;``. Commands registered as
hybrid commands are also available as Discord slash commands where their
context allows it.

Available commands
------------------

General
~~~~~~~

``help [command]`` (alias: ``h``)
  Shows an interactive Components V2 help menu built from the commands
  currently loaded by the bot. Select a category to browse its command names;
  groups are marked with ``*``. Supply a command name or alias for its usage,
  arguments, aliases, required permissions, and group subcommands.

``where <command>`` (alias: ``which``)
  Shows the Python module defining a loaded command and, for extension
  commands, the extension that contains it. Accepts command names, aliases,
  and nested group subcommands.

Information
~~~~~~~~~~~

User commands
^^^^^^^^^^^^^

``avatar [user]`` (alias: ``av``)
  Displays the selected user's avatar. With no argument, displays the author's
  avatar. If the user has no custom avatar, their default avatar is shown.

``banner [user]``
  Displays the selected user's profile banner, or the author's banner when no
  user is supplied. Replies with a plain message if the user has no banner.

``whois [user]``
  Shows a Components V2 profile card with the user's display name, username,
  ID, account creation time, mutual-server count, user/bot type, avatar, and
  banner when available. Defaults to the author.

``userid [user_id]`` (aliases: ``uid``, ``whoid``, ``id``)
  With no argument, shows the author's ID. Accepts a user ID, mention, or
  resolvable name and responds with the matching ID and user reference.
  Multiple whitespace-separated inputs can be looked up in one invocation;
  duplicate resolved users are only reported once.

Server and channel commands
^^^^^^^^^^^^^^^^^^^^^^^^^^^

``bots``
  Lists the server's bot accounts in a paginated Components V2 view, 15 bots
  per page. Shows a no-bots message when the server has none.

``channelid [channel_id]`` (alias: ``cid``)
  With no argument, shows the current channel's ID. Accepts a channel ID or
  mention to look up a channel; reports a not-found response when it cannot
  resolve the channel.

``roleid <role_id>`` (alias: ``rid``)
  Accepts a role mention or ID in the current server. A mention is answered
  with the role's ID; an ID is answered with the role mention and name.

``roles``
  Lists all server roles in a paginated Components V2 view, 15 roles per page,
  ordered from higher to lower position. Each entry includes its mention and
  ID.

``serverid`` (aliases: ``guildid``, ``sid``)
  Shows the current server's ID. Server-only.

``serverinfo`` (aliases: ``guildinfo``, ``si``)
  Shows a Components V2 server card with its ID, owner, creation time, member
  and role counts, channel counts, emoji and sticker counts, settings,
  features, icon, and banner when available.

``servername [name]`` (aliases: ``sname``, ``guildname``, ``gname``)
  With no name, shows the current server name. With a name, renames the
  server. Requires the author to have Manage Server permission.

``roleinfo <role>`` (alias: ``ri``)
  Displays a Components V2 role card containing the role's ID, mention,
  creation date, type, member count, color, position, icon/emoji, settings,
  permission value, and enabled permissions.

Social
~~~~~~

``github <username-or-owner/repository>`` (aliases: ``git``, ``gh``)
  With a username, looks up a GitHub account and displays profile details in a
  Components V2 card with a link to the GitHub profile. With an
  ``owner/repository`` path (for example, ``github playfairs/nox``), displays
  repository details such as its description, language, license, branch,
  topics, timestamps, stars, forks, open issues, and open pull requests, with a
  link to the repository. Available as a prefix or slash command. Reports
  not-found and API/network failures as messages.

Administration
~~~~~~~~~~~~~~

Channel group
^^^^^^^^^^^^^

All channel-management subcommands require Manage Channels from both the
author and the bot.

``channel create [name] [category_id]`` (subcommand alias: ``new``)
  Creates a text channel. The default name is ``new-channel``. An optional
  category ID or category channel mention places it under that category; when
  a category is supplied, Discord synchronizes the new channel's permissions
  with the category.

``channel rename <name>``
  Renames the channel where the command was invoked.

``channel rename <channel_id/channel_mention> <name>``
  Renames the specified channel in the current server.

``channel delete``
  Deletes the channel where the command was invoked. The command sends a
  short status notice before deleting that channel.

``channel delete <channel_id/channel_mention>``
  Deletes the specified channel in the current server.

Role group
^^^^^^^^^^

Role creation, deletion, editing, assignment, and removal require Manage
Roles from both the author and the bot. The author must also have
Administrator to change a role assignment for a role that grants
Administrator. Discord's role hierarchy applies; a user cannot give themself
a role equal to or above their highest role. For role arguments, exact names,
mentions, and IDs are checked first; if an exact name is not found,
RapidFuzz selects the closest matching role name when its score is above 60.
Giving a fuzzy-matched role with powerful permissions requires confirmation
from the command invoker.

``role`` (alias: ``r``)
  Without arguments, displays the role command usage.

``role <member> <role>``
  Gives the role to the member. This shorthand is equivalent to
  ``role give <member> <role>``.

``role create [name] [perms=<value>] [color=<value>]``
  Creates a role, defaulting to ``new-role`` with no permissions and the
  default color. The optional ``perms=`` value is a non-negative numeric
  Discord permission bitfield; for example, ``role create moderators perms=8``
  grants the Administrator permission. The bitfield must not exceed
  ``9007199254740991``. ``perms=`` and ``color=`` are independent optional
  arguments, so either can be supplied without the other. The optional
  ``color=`` value accepts hex colors with
  no prefix, ``#`` or ``0x`` (including three-digit shorthand), or a named
  Discord color, such as ``color=yellow``, ``color=C4A7E7``, ``color=#C4A7E7``,
  ``color=0xC4A7E7``, ``color=CAE``, or ``color=Purple``. The options can be
  supplied in either order. The slash command exposes ``name``, ``perms``, and
  ``color`` as separate options. For prefix commands, quote names containing
  spaces, for example ``role create "new moderators" perms=8``.

``role delete <role>``
  Deletes the specified role. The default ``@everyone`` role and managed
  roles cannot be deleted.

``role give <member> <role>`` (alias: ``add``)
  Gives the role to the member, subject to permission and hierarchy checks.

``role remove <member> <role>`` (alias: ``revoke``)
  Removes the role from the member, subject to permission and hierarchy
  checks.

``role human <role>``
  Adds the role to every non-bot member who does not already have it.

``role bot <role>``
  Adds the role to every bot member who does not already have it.

``role rename <role> <name>``
  Renames the specified role. Names must contain 1 to 100 characters;
  managed roles and ``@everyone`` cannot be renamed.

``role color <role> <color>`` (alias: ``colour``)
  Changes the role color. Accepts hex values with no prefix, ``#`` or ``0x``
  (including three-digit shorthand) or a named Discord color, such as
  ``Purple``.
  Managed roles and ``@everyone`` cannot be recolored.

``role hoist <role>``
  Toggles whether the role is displayed separately in the member list.

``role info <role>`` (alias: ``information``)
  Shows the same role information as ``roleinfo <role>``.

Future commands
---------------

The following command contracts are planned proposals, not commands currently
loaded by Axis. They are written here to make their intended syntax,
permissions, and behavior explicit before implementation.

Moderation
~~~~~~~~~~

``ban <member> [--delete-days <0-7>] [reason...]``
  Bans the member from the current server. Requires Ban Members from both the
  author and the bot. ``--delete-days`` controls how many days of the member's
  recent messages Discord removes and defaults to ``0``; valid values are
  ``0`` through ``7``. The remaining text is recorded as the audit-log reason.
  The bot must refuse to ban the server owner, itself, or a member protected
  by the author's or bot's role hierarchy. On success, it confirms the banned
  member and reason.

``kick <member> [reason...]``
  Kicks the member from the current server. Requires Kick Members from both
  the author and the bot. The remaining text is recorded as the audit-log
  reason. The bot must refuse to kick the server owner, itself, or a member
  protected by the author's or bot's role hierarchy. On success, it confirms
  the kicked member and reason.

``timeout <member> <duration> [reason...]``
  Applies a communication timeout in the current server. Requires Moderate
  Members from both the author and the bot. Duration uses a positive integer
  and one unit suffix: ``s`` (seconds), ``m`` (minutes), ``h`` (hours), or
  ``d`` (days), such as ``30m`` or ``2h``. Durations cannot exceed 28 days.
  The remaining text is recorded as the audit-log reason. The bot must refuse
  to timeout the server owner, itself, or a member protected by the author's
  or bot's role hierarchy. On success, it reports the timeout end time.

``purge <count> [user]``
  Deletes between 1 and 100 recent messages from the current channel.
  Supplying a user limits deletion to that user's messages; omitting the user
  considers messages from anyone. Requires Manage Messages from both the
  author and the bot. Messages older than Discord's bulk-delete age limit are
  left untouched. On success, it reports the number of messages removed.

See :doc:`CHANGES` for the project change log.
