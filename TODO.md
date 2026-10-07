# TODO

Need to make the following

---

### Automod (bot.extensions.automod.commands.guild_commands.automod)

aliases: `am`

`automod alert` - Configure alert settings for Automod Rule
`automod config` - Shows the current Automod Rule configuration
`automod disable` - Disables the Automod Filter
`automod edit` - Edit the action of the Automod Filter
`automod enable` - Enable the Automod Filter
`automod exempt` - Exempt a role from the Automod Filer
`automod filter` - Filter a word or pattern via Automod Rule
`automod list` - List all filtered words
`automod remove` - Remove a word from the Automod Filter

### Blacklist (bot.extensions.blacklist.commands.global_commands.blacklist)

aliases: `bl`

`blacklist extend` - Blacklist more than one guild, user, or both at once
`blacklist guild` - Blacklist a specific guild
`blacklist list` - List all blacklisted Guilds and Users
`blacklist remove` - Remove a user or guild from the bkacklist
`blacklist user` - Blacklist a specific user
`blacklist view` - Get information about a user or guild in the blacklist

### Change (bot.extensions.owner.commands.*)

`change avatar` - Changes the bot's avatar via Attachment or URL
`change banner` - Changes the bot's banner via Attachment or URL

`change server avatar` - Changes the bot's server avatar via Attachment or URL
`change server banner` - Changes the bot's server banner via Attachment or URL
`change server bio` - Changes the bot's server bio

### Channel

`channel lock` - Locks a specific channel or the current one
`channel unlock` - Unlocks a specific channel or the current one
`channel hide` - Hides a specific channel or the current one
`channel unhide` - Unhides a specific channel or the current one


### Information

`inrole` - Displays all members in a specific role


### Purge (bot.extensions.moderation.commands.guild_commands.purge)

aliases: `c`, `clear`, `delete`

`purge <count>` - Purges a specific amount of messages
`purge bot [count]` - Purges the last 100 bot messages
`purge after <message_id` - Purges all messages after a specific message id
`purge from <user>` - Purges the last 100 messages from a specific user
`purge before <message_id>` - Purges the last 100 messages before a specific message id
`purge contains <content>` - Purges the last 100 messages containing specific text
`purge links` - Purges the last 100 messages containing any URLs (ignores gifs)
`purge gifs` - Purges the last 100 messages containing a gif
`purge stickers` - Purges the last 100 messages containing a sticker
`purge endswith <content>` - Purges the last 100 messages ending with specific text
`purge startswith <content>` - Purges the last 100 messages starting with specific text
`purge invites` - Purges the last 100 messages containing an invite link (discord.gg/*, .gg/*)
`purge mentions [user]` - Purges the last 100 messages containing user mentions, or a specific user if specified
`purge self` - Purges the last 100 messages from the command invoker
`purge reactions` - Purges reactions on the last 100 messages

### Utility

`define` - Searches for a word via the Merriam-Webster Dictionary
`urban` - Searches for a word via the Urban Dictionary API