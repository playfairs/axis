Axis
=====

A discord bot that covers every angle.

Setup
-----

Enter the Nix development shell for the latest stable Python from
nixpkgs-unstable:

.. code-block:: console

   nix develop

Run Axis from the Nix development shell with the Nox task. It creates the
project virtual environment, installs or upgrades all declared dependencies
from PyPI, and starts the bot:

.. code-block:: console

   nox task start

You can install or upgrade the dependencies without starting the bot with
``nox task install``. Copy ``.env.example`` to the project-root ``.env`` and
set ``DISCORD_TOKEN`` before running Axis.

Axis requests all Discord gateway intents. In the Discord Developer Portal,
enable the privileged ``Server Members Intent``, ``Presence Intent``, and
``Message Content Intent`` for the bot application as well.

The bot stays connected until the process is stopped. Run ``nix flake update``
to refresh nixpkgs and use its latest Python release.

External API integrations
-------------------------

GitHub and Last.fm clients live under ``api/``. Their HTTP transport is
implemented in C with libcurl and loaded through CFFI. On first use, Axis
compiles the native transport to a cached ``.dylib`` on macOS or ``.so`` on
Linux. The compiled library is cached by source version, so subsequent runs
can load it without ``pkg-config`` or the compiler being on PATH. Run Axis
inside ``nix develop`` at least once to build it. The Nix shell provides CFFI,
a C compiler, pkg-config, and libcurl. Outside Nix, the first build requires
those native development tools and Python ``cffi``. Discord API calls remain
managed by discord.py.

Configuration and logging
-------------------------

Bot defaults and extension loading are configured in
``bot/config/__init__.py`` and ``bot/config/bot.py``. Add future extensions
to ``COGS.EXTENSIONS`` and exclude them by module name in ``COGS.SKIP``.
Shared Discord.py and Loguru imports are available from
``bot/base/imports.py``. Application and Discord.py logs are configured
centrally in ``bot/logging/setup.py``; command usage and failures are logged
with the invoking user, guild, and channel identifiers.
