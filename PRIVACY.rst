Privacy Policy
===================

Effective date: 4 October 2026

This policy describes information processed by the Axis Discord bot ("Axis"
or the "Bot") as implemented in this repository. Each person or organization
operating an instance of the Bot controls that instance and its hosting. The
operator of the instance serving your server is responsible for its
configuration, logs, and any additional processing they introduce.

Open-source transparency
-----------------------

Axis is open source. Anyone can review the code in the `Axis GitHub repository
<https://github.com/playfairs/axis>`_ to inspect how the Bot processes
information and assess privacy-related concerns. A running instance may have
operator-specific configuration or modifications, so the repository may not
fully describe every deployed instance.

Information processed
---------------------

When connected to Discord, the Bot receives Discord events and information
needed to provide its enabled features. Depending on where it is installed
and which commands are used, this may include:

* message content and command arguments, to recognize and process prefix
  commands;
* Discord user, guild, and channel identifiers, used in command processing
  and operational logs;
* Discord profile, member, role, channel, and server information requested
  by a command; and
* information returned by Discord when the Bot performs an action requested
  through an authorized command.

The Bot requests Discord gateway intents, including privileged member,
presence, and message-content intents. The data Discord makes available
depends on the Bot's configuration, authorization, installation context, and
Discord's own policies.

How information is used
-----------------------

Information is processed to detect and respond to commands, provide the
requested features, perform authorized server-management actions, and
diagnose operational errors. The current application code does not write
user or server records to a persistent application database. Information
needed while a command runs may be held temporarily in process memory or in
the Discord library's runtime cache.

Operational logs
----------------

The current application writes logs to a local ``logs.log`` file in append
mode. Command completion and failure logs can include the invoking user's
Discord identifier, guild and channel identifiers, the command name, and
error details. The application does not intentionally log every message's
full content as an activity record, but message or command details may be
included in an error emitted by a library or a particular feature.

The code does not set a log-retention period. The instance operator controls
access to the host and is responsible for securing, rotating, and deleting
logs. The Bot may also create a local cache containing its compiled native
HTTP transport library; that cache is not intended to contain Discord
account or server records.

Third-party services
--------------------

When you use the GitHub command, the GitHub username or repository name you
provide is sent to GitHub to retrieve the requested public information.
GitHub may process the request under its own privacy policy.

If the instance operator configures the optional Last.fm activity
integration, the Bot periodically requests publicly available track
information for the Last.fm username configured by that operator. In the
current source, that username is ``pdwk``. The retrieved track information
may be displayed as the Bot's Discord activity.

Discord processes information exchanged with the Bot under Discord's own
privacy policy. Hosting, network, or other infrastructure providers selected
by an operator may also process information on that operator's behalf. Axis
does not sell personal information.

Retention and requests
----------------------

Command data is generally processed to produce a response and is not written
to a persistent application database by the current code. Operational log
entries remain in the operator's local log file until the operator removes
or rotates them. Discord and third-party providers may retain information
under their own policies.

For questions, access, or deletion requests concerning a running instance,
contact that instance's operator. The operator is best placed to identify
the applicable logs, hosting systems, and legal obligations. For information
about the Axis source project, contact its maintainers through the `Axis
GitHub repository <https://github.com/playfairs/axis>`_. Do not post private
or sensitive information in a public issue.

Security and international processing
-------------------------------------

Operators are responsible for protecting their Bot token, host, and logs.
No online service can be guaranteed completely secure. Discord and other
service providers may process information in countries different from your
own, subject to their policies and applicable law.

Changes to this policy
----------------------

This policy may be updated as the Bot or its data practices change. A revised
version will be published with a new effective date. Operators should review
it when changing their deployments.

This policy is a general project template, not legal advice. Operators must
review it for their actual deployment, data practices, and jurisdiction;
additional integrations or storage may require further disclosures.
