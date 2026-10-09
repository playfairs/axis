# Command TODO

Planned commands are grouped by what they do. Commands that are already
implemented are not listed here.

## Moderation

### Automod

Module: `bot.extensions.automod.commands.guild_commands.automod`; alias: `am`

**Rules**

- `automod filter` - Add a word or pattern to an Automod rule
- `automod edit` - Change the action for an Automod rule
- `automod remove` - Remove a word or pattern from an Automod rule
- `automod list` - List the words and patterns being filtered
- `automod test <text>` - Check which rules match text without taking action

**Configuration**

- `automod config` - Show the current Automod configuration
- `automod enable` - Enable the Automod filter
- `automod disable` - Disable the Automod filter
- `automod alert` - Configure where Automod alerts are sent

**Exemptions**

- `automod exempt role <role>` - Exempt a role from Automod
- `automod exempt channel <channel>` - Exempt a channel from Automod
- `automod exempt list` - List roles and channels exempt from Automod

### Message cleanup

Module: `bot.extensions.moderation.commands.guild_commands.purge`; aliases: `c`, `clear`, `delete`

**By amount or author**

- `purge <count>` - Purge a specific number of messages
- `purge bot [count]` - Purge recent messages sent by bots
- `purge from <user>` - Purge recent messages from a specific user
- `purge mentions [user]` - Purge messages with mentions, optionally from or of a specific user
- `purge self` - Purge recent messages from the command invoker

**By message range**

- `purge after <message_id>` - Purge messages after a specific message
- `purge before <message_id>` - Purge messages before a specific message

**By content or attachment**

- `purge contains <content>` - Purge messages containing specific text
- `purge startswith <content>` - Purge messages starting with specific text
- `purge endswith <content>` - Purge messages ending with specific text
- `purge links` - Purge messages containing URLs, excluding GIFs
- `purge invites` - Purge messages containing Discord invite links
- `purge gifs` - Purge messages containing a GIF
- `purge stickers` - Purge messages containing a sticker
- `purge attachments` - Purge messages containing file attachments
- `purge embeds` - Purge messages containing embeds

**Other**

- `purge reactions` - Remove reactions from recent messages

### Member moderation

**Warnings**

- `warn <member> [reason]` - Issue a warning to a member
- `warnings <member>` - Show a member's warnings
- `warnings clear <member>` - Clear a member's warnings

**Timeouts**


**Moderation log**

- `modlog set <channel>` - Set the channel for moderation action logs
- `modlog disable` - Stop sending moderation action logs

### Global blacklist

Module: `bot.extensions.blacklist.commands.global_commands.blacklist`; alias: `bl`

- `blacklist user <user> [reason]` - Blacklist a user from using the bot
- `blacklist guild <guild> [reason]` - Blacklist a server from using the bot
- `blacklist extend` - Add multiple users or servers to the blacklist
- `blacklist list` - List blacklisted users and servers
- `blacklist view <user or guild>` - Show blacklist details
- `blacklist remove <user or guild>` - Remove a user or server from the blacklist

## Server administration

### Channels

Module: `bot.extensions.administration.commands.guild_commands.channel`

- `channel lock [channel]` - Prevent members from sending messages in a channel
- `channel unlock [channel]` - Restore member messaging permissions
- `channel hide [channel]` - Hide a channel from members
- `channel unhide [channel]` - Restore member access to a channel
- `channel slowmode <duration> [channel]` - Set or update a channel's slowmode
- `channel topic <text> [channel]` - Set a channel's topic

### Bot profile

Module: `bot.extensions.owner.commands.*`

- `change avatar` - Change the bot's avatar using an attachment or URL
- `change banner` - Change the bot's banner using an attachment or URL
- `change server avatar` - Change the bot's server avatar using an attachment or URL
- `change server banner` - Change the bot's server banner using an attachment or URL
- `change server bio` - Change the bot's server bio
- `change activity <text>` - Update the bot's activity or status text

## Information

- `permissions <member> [channel]` - Show a member's effective permissions

## Utility and community

- `poll <question> <options...>` - Create a poll with multiple choices
- `remind <duration> <message>` - Send the command invoker a reminder
- `steal emoji` - steal a single emoji
- `steal emojis` - steal more than one emoji
- `steal sticker` - Ok