import glob
import logging
import os
import pathlib
import random
import ssl
import time
import traceback
from collections import defaultdict
from datetime import (
    datetime,
    timedelta,
)
from pathlib import Path
from typing import (
    Dict,
    List,
    Optional,
    Union,
)

import asyncpg
import discord
import discord_ios
import jishaku
import psutil
from asyncpg import Pool, create_pool
from core.client.help import VortexHelp
from discord import (
    AllowedMentions,
    CustomActivity,
    Embed,
    Forbidden,
    Guild,
    Intents,
    Invite,
    Member,
    Message,
)
from discord.ext import commands
from discord.ext.commands import (
    AutoShardedBot,
    ChannelNotFound,
    CheckFailure,
    CommandError,
    CommandNotFound,
    CommandOnCooldown,
    ExtensionFailed,
    MinimalHelpCommand,
    MissingPermissions,
    NotOwner,
    RoleNotFound,
    ThreadNotFound,
    UserNotFound,
    when_mentioned_or,
)
from discord.utils import format_dt
from dotenv import load_dotenv
from psutil import Process
