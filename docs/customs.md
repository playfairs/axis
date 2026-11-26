# Server-specific bot customization

The `customs` extension stores whitelist status and the last confirmed profile
configuration per server. The bot owner manages access with:

- `,customs whitelist <guild_id>`
- `,customs blacklist <guild_id>`
- `,customs check <guild_id>`
- `,customs list`
- `,customs reset <guild_id>`

Customization commands are available only in explicitly whitelisted servers:

- `,customize avatar [image attachment]`
- `,customize banner [image attachment]`
- `,customize bio [text]`
- `,customize displayname [name]`
- `,customize displayname color <#RRGGBB> [#RRGGBB ...]`
- `,customize displayname reset <name|font|effect|colors|style|all>`

These commands are also registered as slash commands, such as `/customs list`,
`/customs whitelist guild_id:<id>`, and `/customize bio bio:<text>`.
`/customize displayname show` opens the style selectors; use
`/customize displayname show display_name:<name>` to set the server nickname.

Omitting the avatar, banner, or bio value resets that property. `displayname`
without a name shows the current style and interactive font/effect selectors.
One color is supported for Solid, Neon, Toon, and Pop; Gradient, Glow, Prism,
and Gummy support one to five colors. Discord validates style availability;
rejected changes are reported as errors.
All profile updates use the guild-member endpoint and do not edit the bot's
global account profile.

The per-guild avatar, banner, bio, and nickname fields are documented by
[Discord's Modify Current Member endpoint](https://docs.discord.com/developers/resources/guild#modify-current-member).
Style option IDs and labels follow the current
[Discord client user protobuf definitions](https://github.com/discord-userdoccers/discord-protos/blob/17ec728773485b7cf17ed7e8080589e19e2c1279/discord_protos/users/v1/User.proto);
deprecated fonts are omitted, and the verified color-count rules are from the
[current profile-style reference](https://github.com/discord-userdoccers/discord-userdoccers/blob/bbd05352523ca466e8a1b36cea7897aa5e6c941e/pages/resources/user.mdx#L426-L458).
Discord can reject values that are not enabled for the bot or server.
