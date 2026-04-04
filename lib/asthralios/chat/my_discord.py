'''
This is an adapter interface that will enable us to take the rough edges off of talking
to the Discord API's.

Register the functions needed in order to send and receive messages and DM's from Discord.
'''

import asyncio
import re
from typing import Optional

import discord
from discord.ext import commands

from asthralios import brain
from asthralios.chat import adapter
from asthralios import getLogger

log = getLogger(__name__)

def send_discord_message(config, channel_id: str, message: str) -> None:
    """
    Proactively send a message to a Discord channel without needing a prior event.
    Usable from CLI or cron jobs.
    """
    async def _send():
        intents = discord.Intents.default()
        client = discord.Client(intents=intents)

        @client.event
        async def on_ready():
            channel = client.get_channel(int(channel_id))
            if channel is None:
                channel = await client.fetch_channel(int(channel_id))
            await channel.send(message)
            await client.close()

        await client.start(config.discord.bot_token)

    asyncio.run(_send())

class ChatAdapterDiscord(adapter.ChatAdapter):
    '''
    Adapter interface to take the "rough edges" off of talking to Discord.
    '''

    def mesgLimit(self) -> int:
        return 2000

    def init(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        intents.messages = True
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self._pending_thread_history: list[dict] = []
        self.register()

    def start(self):
        self.bot.run(self.config.discord.bot_token)

    def extract_identity(self, message: discord.Message) -> brain.rbac.UserIdentity:
        return brain.rbac.UserIdentity(
            platform='discord',
            platform_user_id=str(message.author.id),   # snowflake as string
            display_name=message.author.display_name or message.author.name,
        )

    def _get_channel(self, message: discord.Message) -> str:
        return str(message.channel)

    def _get_text(self, message: discord.Message) -> str:
        """Return the formatted message text for LLM context."""
        _, content = self.format_message(message)
        return content

    def get_thread_history(self, thread_id: str) -> list[dict]:
        """
        Return the thread history collected eagerly by on_message before sync dispatch.
        The async collection happens in on_message; this method just returns the result.
        """
        return self._pending_thread_history

    def register(self):
        '''
        Register the decorator function events so the bot gets connected to the server.
        '''
        @self.bot.event
        async def on_connect():
            adapter.debug_event("on_connect", bot_user=str(self.bot.user))

        @self.bot.event
        async def on_ready():
            # discord.py requires async here — tree.sync() is a coroutine.
            try:
                synced = await self.bot.tree.sync()
                adapter.debug_event(
                    "on_ready",
                    bot_user=str(self.bot.user),
                    num_commands=len(synced),
                    commands=[f"/{cmd.name}" for cmd in synced],
                )
            except Exception as exc:
                adapter.debug_event("on_ready_sync_error", error=repr(exc))

        @self.bot.event
        async def on_message(message: discord.Message):
            # discord.py requires async here — channel.send() and process_commands() are coroutines.
            adapter.debug_event(
                "on_message",
                id=message.id,
                author=str(message.author),
                author_id=message.author.id,
                channel=str(message.channel),
                channel_id=getattr(message.channel, "id", None),
                guild=str(message.guild) if message.guild else None,
                guild_id=message.guild.id if message.guild else None,
                content=message.content,
                is_dm=isinstance(message.channel, discord.DMChannel),
                is_thread=isinstance(message.channel, discord.Thread),
            )

            if message.author == self.bot.user:
                adapter.debug_event('on_message', notice='Avoiding talking to ourselves.')
                return

            if not self.bot.user:
                adapter.debug_event('on_message', notice='Not logged in.')
                return

            if not self.llm:
                await self.bot.process_commands(message)
                return

            text = (message.content or "").strip()

            # Determine thread_id
            thread_id: Optional[str] = None
            if isinstance(message.channel, discord.Thread):
                thread_id = str(message.channel.id)

            # Eagerly collect thread history here while we are in the async context.
            # This allows all downstream sync code to call get_thread_history() without
            # needing to be async themselves.
            limit = getattr(self.config.oui, 'thread_context_limit', 10)
            self._pending_thread_history = []
            try:
                source = message.channel if isinstance(message.channel, discord.Thread) else None
                if source:
                    async for msg in source.history(limit=limit, oldest_first=True):
                        role = 'assistant' if (msg.author.bot or msg.author.id == self.bot.user.id) else 'user'
                        if msg.content:
                            self._pending_thread_history.append({'role': role, 'content': msg.content})
                else:
                    async for msg in message.channel.history(limit=limit, before=message, oldest_first=True):
                        role = 'assistant' if (msg.author.bot or msg.author.id == self.bot.user.id) else 'user'
                        if msg.content:
                            self._pending_thread_history.append({'role': role, 'content': msg.content})
            except Exception as exc:
                log.error(f'thread history collection failed: {exc}')

            # Handle fix: commands (admin-only) — sync business logic, async send
            if re.match(r'^fix\s*:', text, re.IGNORECASE):
                identity = self.extract_identity(message)
                channel_str = self._get_channel(message)
                ctx = self.get_rbac().resolve(identity, channel_str, text)
                if not self.get_rbac().is_allowed(ctx, 'admin'):
                    self.get_rbac().log_access(ctx, 'fix', 'denied', detail='non-admin fix attempt')
                    await message.channel.send("Only the admin can use the fix command.")
                else:
                    reply = self._handle_fix_command(text, identity.platform_user_id)
                    self.get_rbac().log_access(ctx, 'fix', 'ok', detail=f'command: {text[:80]}')
                    await message.channel.send(reply)
                await self.bot.process_commands(message)
                return

            # Sync business logic: RBAC + LLM/brain routing
            reply = self.on_message_received(message, thread_id=thread_id)

            # Async send (discord.py requires await for channel.send)
            if reply:
                limit = self.mesgLimit()
                for i in range(0, len(reply), limit):
                    await message.channel.send(reply[i:i+limit])

            await self.bot.process_commands(message)

    def format_message(self, m: discord.Message) -> tuple[str, str]:
        '''
        Format a Discord.Message into a "user|assistant": "content" format.
        '''
        role = "assistant" if m.author.bot or m.author.id == self.bot.user.id else "user"
        content_parts = []
        if role == "user":
            content_parts.append(f"[{m.created_at}] @{m.author.name}: ")
        content_text = (m.content or "").strip()
        if content_text:
            content_parts.append(content_text)
        if m.attachments:
            attachments_desc = ", ".join([a.filename for a in m.attachments])
            content_parts.append(f"[attachments: {attachments_desc}]")
        if m.embeds:
            try:
                embeds_desc = ", ".join([e.url for e in m.embeds if hasattr(e, "url")])
            except Exception:
                embeds_desc = str(len(m.embeds)) + " embed(s)"
            if embeds_desc:
                content_parts.append(f"[embeds: {embeds_desc}]")
        content = " \n".join(content_parts) or "[no text]"
        return role, content
