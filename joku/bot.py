"""
Main bot class.
"""
import asyncio
import os
import sys
import traceback
from collections import OrderedDict
import time
import random

import discord
import itertools
import logbook
import logging

from asyncio_extras import threadpool
from discord import Message
from discord.ext import commands
from discord.ext.commands import Bot, CommandInvokeError, CheckFailure, MissingRequiredArgument, CommandOnCooldown, \
    UserInputError, AutoShardedBot
from discord.gateway import DiscordWebSocket, ResumeWebSocket
from discord.state import ConnectionState
from logbook.compat import redirect_logging
from logbook import StreamHandler

from joku.db.interface import DatabaseInterface
from joku.utils import paginate_large_message

from joku.redis import RedisAdapter

try:
    import yaml
except ImportError:
    import ruamel.yaml as yaml

redirect_logging()

StreamHandler(sys.stderr).push_application()


class Jokusoramame(AutoShardedBot):
    def __init__(self, config: dict, *args, **kwargs):
        """
        Creates a new instance of the bot.

        :param config: The config to create this with.
        """
        self.config = config

        # Logging stuff
        self.logger = logbook.Logger("Jokusoramame")
        self.logger.level = logbook.INFO

        logging.root.setLevel(logging.INFO)

        # Call init.
        super().__init__(command_prefix=self.get_command_prefix, *args, **kwargs)

        # Used later on.
        self.app_id = 0
        self.owner_id = 0

        self.startup_time = time.time()

        # Create our connections.
        self.database = DatabaseInterface(self)
        self.redis = RedisAdapter(self)

        # Re-assign commands and extensions.
        self.commands = OrderedDict()
        self.extensions = OrderedDict()
        self.cogs = OrderedDict()

        # Is the bot fully loaded yet?
        self.loaded = False

    # Utility functions.
    def get_member(self, id: int):
        """
        Gets a member from all members.
        """
        return discord.utils.get(self.get_all_members(), id=id)

    @staticmethod
    async def get_command_prefix(self: 'Jokusoramame', message: discord.Message):
        if self.config.get("developer_mode", False):
            # Use `jd!` prefix.
            return "jd!"

        return ["j" + s for s in "!?^&$}#~:"] + ["J" + s for s in "!?^&$}#~:"]

    async def rotate_game_text(self):
        for i in itertools.cycle(self.config.get("game_rotation", [])):
            await self.change_presence(
                game=discord.Game(name=i), status=discord.Status.online
            )
            await asyncio.sleep(15)

    async def on_command_error(self, exception, context: 'Context'):
        """
        Handles command errors.
        """
        if isinstance(exception, CommandInvokeError):
            # Regular error.

            lines = traceback.format_exception(type(exception),
                                               exception.__cause__, exception.__cause__.__traceback__)
            self.logger.error(''.join(lines))

            if self.config.get("developer_mode", False) is False:
                await context.channel.send("\U0001f6ab This kills the bot (An error has happened "
                                           "and has been logged.)")
            else:
                await context.channel.send("```py\n{}```".format(''.join(lines)))
                return

            # Log to the error channel.
            error_channel_id = self.config.get("log_channels", {}).get("error_channel", "")
            error_channel = self.get_channel(error_channel_id)

            if not error_channel:
                self.logger.error("Could not find error channel!")
            else:
                fmt = "Server: {}\nChannel: {}\nCommand: {}\n\n{}".format(context.message.server.name,
                                                                          context.message.channel.name,
                                                                          context.invoked_with,
                                                                          ''.join(lines))
                await context.channel.send(fmt, use_codeblocks=True)
            return

        # Switch based on isinstance.
        if isinstance(exception, CheckFailure):
            channel = context.message.channel
            await context.channel.send("\U0001f6ab Check failed: {}".format(' '.join(exception.args)))

        elif isinstance(exception, MissingRequiredArgument):
            await context.channel.send("\U0001f6ab Error: {}".format(' '.join(exception.args)))

        elif isinstance(exception, CommandOnCooldown):
            await context.channel.send("\U0001f6ab Command is on cooldown. Retry after {} "
                                       "seconds.".format(round(exception.retry_after, 1)))

        elif isinstance(exception, UserInputError):
            await context.channel.send("\U0001f6ab Error: {}".format(' '.join(exception.args)))

    async def on_connect(self):
        await self.change_presence(game=discord.Game(name="Type j!help for help!"))

    async def on_ready(self):
        # Only ever load once.
        if self.loaded is True:
            return

        self.loaded = False

        self.logger.info("Loaded Jokusoramame, logged in as {}#{}.".format(self.user.name, self.user.discriminator))
        self.logger.info("Guilds: {}".format(len(self.guilds)))
        self.logger.info("Users: {}".format(len(set(self.get_all_members()))))

        app_info = await self.application_info()
        self.app_id = app_info.id
        self.owner_id = app_info.owner.id

        self.logger.info("I am owned by {}#{} ({}).".format(app_info.owner.name, app_info.owner.discriminator,
                                                            self.owner_id))
        self.logger.info("Invite link: {}".format(discord.utils.oauth_url(self.app_id)))

        try:
            await self.database.connect(self.config.get("dsn", None))
        except Exception:
            self.logger.error("Unable to connect to PostgreSQL!")
            traceback.print_exc()
            await self.logout()
            return

        try:
            await self.redis.connect(**self.config.get("redis", {}))
        except ConnectionRefusedError:
            self.logger.error("Unable to connect to Redis!")
            traceback.print_exc()
            await self.logout()
            return

        for cog in self.config.get("autoload", []):
            try:
                self.load_extension(cog)
            except Exception as e:
                self.logger.error("Failed to load cog {}!".format(cog))
                self.logger.exception()
            else:
                self.logger.info("Loaded cog {}.".format(cog))

        self.logger.info("Loaded {} cogs.".format(len(self.cogs)))
        self.logger.info("Running with {} commands.".format(len(self.commands)))

        for name, cog in self.cogs.items():
            if hasattr(cog, "ready"):
                self.loop.create_task(cog.ready())

        new_time = time.time() - self.startup_time

        self.logger.info("Bot ready in {} seconds.".format(new_time))

    async def on_message(self, message: Message):
        self.logger.info("Recieved message: {message.content} "
                         "from {message.author.display_name} ({message.author.name}){bot}"
                         .format(message=message, bot=" [BOT]" if message.author.bot else ""))
        self.logger.info(" On channel: #{message.channel.name}".format(message=message))

        if message.guild is not None:
            self.logger.info(" On server: {} ({})".format(message.guild.name, message.guild.id))


        #if await self.database.is_channel_ignored(message.channel, type_="commands"):
        #    return

        await super().on_message(message)

    def run(self):
        token = self.config["bot_token"]
        super().run(token)

    async def login(self, *args, **kwargs):
        token = self.config["bot_token"]
        return await super().login(token)

    @asyncio.coroutine
    def connect(self):
        """|coro|

        Creates a websocket connection and lets the websocket listen
        to messages from discord.

        Raises
        -------
        GatewayNotFound
            If the gateway to connect to discord is not found. Usually if this
            is thrown then there is a discord API outage.
        ConnectionClosed
            The websocket connection has been terminated.
        """
        yield from self.launch_shards()

        while not self.is_closed():
            pollers = [shard.get_future() for shard in self.shards.values()]
            yield from asyncio.wait(pollers, loop=self.loop, return_when=asyncio.FIRST_COMPLETED)


class Context(commands.Context):
    def __init__(self, *args, **kwargs):
        self._bot = None
        super().__init__(*args, **kwargs)

    @property
    def bot(self) -> Jokusoramame:
        return self._bot

    @bot.setter
    def bot(self, i):
        self._bot = i
