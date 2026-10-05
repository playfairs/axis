Axis change log
===============

This is an implementation history, rather than a list of intentions. It
records changes represented by commits on the current repository history.
Dates are commit dates as shown by Git. Uncommitted work is not listed.

2026-09-30: Axis foundation and user information
------------------------------------------------

* ``c0b19e4`` - Established the Axis project foundation, including its
  configuration, environment setup, package structure, schema, README, and
  Unlicense.
* ``e639978`` - Added the Discord bot runtime, startup, event handling, and
  logging.
* ``d8b307e`` - Added user information commands for avatars, banners, user
  IDs, and profile details.
* ``c022322`` - Commit subject: ``hi lol``. was goofing off with git authors
* ``85b0714`` - Commit subject: ``Hi lol``. was goofing off with git authors
* ``d00674c`` - Added a user-facing response when a command is not found.

2026-10-01: Server commands and runtime refinements
----------------------------------------------------

* ``d0a6c25`` - Added server commands for bots, channel IDs, roles, and server
  IDs; added Last.fm activity integration and Ruff formatting.
* ``eb1d410`` - Prevented event dispatch after bot shutdown.

2026-10-02: Role and server information
---------------------------------------

* ``c0f3d9e`` - Added role ID and detailed role information commands, plus
  detailed server information.

2026-10-04: Command, API, and logging additions
------------------------------------------------

* ``95b5e76`` - Kept help pagination usable when a command's help details
  cannot be rendered.
* ``e6b5d83`` - Commit subject: ``ok``.
* ``aa85509`` - Added the channel administration command group, server-name
  command, GitHub profile command, and Nox development tooling; expanded
  command registration and related information commands.
* ``aa453be`` - Added the C/libcurl HTTP transport and CFFI integration, moved
  GitHub and Last.fm API work behind the native transport, and updated the
  development environment and dependencies.
* ``2e742bb`` - Refactored logging across the bot and API modules.
* ``e13f6a1`` - Removed the ``discord_ios`` dependency.
