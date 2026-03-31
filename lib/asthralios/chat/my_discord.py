'''
This is an adapter interface that will enable us to take the rough edges off of talking
to the Discord API's.

Register the functions needed in order to send and receive messages and DM's from Discord.
'''

import re
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands

from asthralios.brain.rbac import UserIdentity
from asthralios.chat.adapter import ChatAdapter, debug_event

import asthralios
log = asthralios.getLogger(__name__)


async def send_discord_message(config, channel_id: str, message: str) -> None:
    """
    Proactively send a message to a Discord channel without needing a prior event.
    Usable from CLI or cron jobs. Handles the async event loop correctly.
    """
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


class ChatAdapterDiscord(ChatAdapter):
    '''
    Adapter interface to take the "rough edges" off of talking to Discord.
    '''

    def mesgLimit(self):
        return 2000

    def init(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        intents.messages = True
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self.register()

    def start(self):
        self.bot.run(self.config.discord.bot_token)

    def extract_identity(self, message: discord.Message) -> UserIdentity:
        return UserIdentity(
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

    def register(self):
        '''
        Register the decorator function events so the bot gets connected to the server.
        '''
        @self.bot.event
        async def on_connect():
            debug_event("on_connect", bot_user=str(self.bot.user))

        @self.bot.event
        async def on_ready():
            try:
                synced = await self.bot.tree.sync()
                debug_event(
                    "on_ready",
                    bot_user=str(self.bot.user),
                    num_commands=len(synced),
                    commands=[f"/{cmd.name}" for cmd in synced],
                )
            except Exception as exc:
                debug_event("on_ready_sync_error", error=repr(exc))

        @self.bot.event
        async def on_message(message: discord.Message):
            debug_event(
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
                debug_event('on_message', notice='Avoiding talking to ourselves.')
                return

            if not self.bot.user:
                debug_event('on_message', notice='Not logged in.')
                return

            if not self.llm:
                await self.bot.process_commands(message)
                return

            text = (message.content or "").strip()

            # Determine thread_id for history
            thread_id: Optional[str] = None
            if isinstance(message.channel, discord.Thread):
                thread_id = str(message.channel.id)

            # Handle fix: commands (admin-only)
            if re.match(r'^fix\s*:', text, re.IGNORECASE):
                identity = self.extract_identity(message)
                channel_str = self._get_channel(message)
                ctx = self.get_rbac().resolve(identity, channel_str, text)
                if not self.get_rbac().is_allowed(ctx, 'admin'):
                    self.get_rbac().log_access(ctx, 'fix', 'denied', detail='non-admin fix attempt')
                    await message.channel.send("Only the admin can use the fix command.")
                else:
                    await self._handle_fix_command(text, message.channel.send, identity.platform_user_id)
                    self.get_rbac().log_access(ctx, 'fix', 'ok', detail=f'command: {text[:80]}')
                await self.bot.process_commands(message)
                return

            # Store for get_thread_history fallback
            self.current_message = message

            # Delegate all other messages through RBAC gate in base class
            reply = await self.on_message_received(message, message.channel.send, thread_id=thread_id)
            if reply:
                await self.do_message_send(message.channel.send, reply)

            await self.bot.process_commands(message)

    async def _handle_fix_command(
        self,
        text: str,
        say,
        source_user: str,
    ) -> None:
        """
        Parse 'fix: <category> [#entry_id]', move the file, update DB.
        """
        from asthralios.brain import BrainDB

        match = re.match(r'^fix\s*:\s*(\w+)(?:\s+#(\d+))?', text, re.IGNORECASE)
        if not match:
            await say("Couldn't parse fix command. Format: `fix: <category>` or `fix: <category> #<entry_id>`")
            return

        new_category = match.group(1).lower()
        entry_id = int(match.group(2)) if match.group(2) else None

        valid_categories = {'people', 'projects', 'ideas', 'admin', 'musings'}
        if new_category not in valid_categories:
            await say(f"Unknown category `{new_category}`. Valid: {', '.join(sorted(valid_categories))}")
            return

        brain_cfg = self.config.brain
        db = BrainDB(brain_cfg.db_path)

        if entry_id:
            row = db.get_entry(entry_id)
        else:
            row = db.get_latest_for_user(source_user, ['filed', 'needs_review'])

        if not row:
            await say("No matching entry found to fix.")
            return

        original_category = row['category']
        old_path = row['filed_path']

        if old_path and Path(old_path).exists():
            new_path = Path(brain_cfg.vault_path) / new_category / Path(old_path).name
            Path(old_path).rename(new_path)
            db.update_filed_path(row['id'], str(new_path))
            db.update_status(row['id'], 'fix_applied', fix_original_cat=original_category)
            await say(f"Fixed: moved entry #{row['id']} from `{original_category}` to `{new_category}`.")
        else:
            db.update_status(row['id'], 'fix_applied', fix_original_cat=original_category)
            await say(f"Fixed category for entry #{row['id']} to `{new_category}` (no file to move).")

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

    async def get_thread_history(self, thread_id: str) -> list[dict]:
        """Return thread-only message history capped at thread_context_limit."""
        limit = getattr(self.config.oui, 'thread_context_limit', 10)
        history = []
        try:
            channel = self.bot.get_channel(int(thread_id))
            if isinstance(channel, discord.Thread):
                async for msg in channel.history(limit=limit, oldest_first=True):
                    role = 'assistant' if (msg.author.bot or msg.author.id == self.bot.user.id) else 'user'
                    if msg.content:
                        history.append({'role': role, 'content': msg.content})
            elif hasattr(self, 'current_message') and self.current_message:
                async for msg in self.current_message.channel.history(
                    limit=limit, before=self.current_message, oldest_first=True
                ):
                    role = 'assistant' if (msg.author.bot or msg.author.id == self.bot.user.id) else 'user'
                    if msg.content:
                        history.append({'role': role, 'content': msg.content})
        except Exception as exc:
            log.error(f'get_thread_history failed: {exc}')
        return history[-limit:]
