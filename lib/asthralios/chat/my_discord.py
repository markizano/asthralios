'''
This is an adapter interface that will enable us to take the rough edges off of talking
to the Discord API's.

Register the functions needed in order to send and receive messages and DM's from Discord.
'''
import discord
from discord.ext import commands

from typing import Iterable
from openai.types.chat import ChatCompletionMessageParam

from asthralios.chat.adapter import ChatAdapter, debug_event

class ChatAdapterDiscord(ChatAdapter):
    '''
    Adapter interface to take the "rough edges" off of talking to Discord.
    '''

    def init(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        intents.messages = True
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self.register()

    def start(self):
        self.bot.run(self.config.discord.bot_token)

    def register(self):
        '''
        Register the decorator function events so the bot gets connected to the server.
        '''
        @self.bot.event
        async def on_connect():
            debug_event(
                "on_connect",
                bot_user=str(self.bot.user),
            )

        @self.bot.event
        async def on_ready():
            # Sync application (slash) commands on startup
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
                is_thread=isinstance(message.channel, (discord.Thread,)),
            )

            if message.author == self.bot.user:
                debug_event('on_message', notice='Avoiding talking to ourselves.')
                return

            if not self.bot.user:
                debug_event('on_message', notice='Not logged in.')
                return

            # Respond if DM or mentioned
            #@TODO: Determine not just if mentioned, but if the conversation is directed at us.
            # is_dm = isinstance(message.channel, discord.DMChannel)
            # mentioned_bot = self.bot.user.mentioned_in(message) \
            #     or self.bot.user.name.lower() in message.content.lower() \
            #     or self.bot.id.lower() in message.content.lower()

            # if (is_dm or mentioned_bot) and oui_client:
            if self.llm:
                async with message.channel.typing() as typing_ctx:
                    # Store current message for history context
                    self.current_message = message
                    role, content = self.format_message(message)
                    reply = await self.on_message_received(content)
                    await self.do_message_send(message.channel.send, reply)

            # Ensure commands extension still receives the message
            await self.bot.process_commands(message)

    def format_message(self, m: discord.Message) -> tuple[str, str]:
        '''
        Format a Discord.Message into a "user|assistant": "content" format that can be used in
        LLM API calls.
        '''
        role = "assistant" if m.author.bot or m.author.id == self.bot.user.id else "user"
        content_parts = []
        # Prefix user messages with their name for context
        if role == "user":
            content_parts.append(f"[{m.created_at}] @{m.author.name}: ")
        content_text = (m.content or "").strip()
        if content_text:
            content_parts.append(content_text)
        # Include basic info about attachments
        if m.attachments:
            attachments_desc = ", ".join([a.filename for a in m.attachments])
            content_parts.append(f"[attachments: {attachments_desc}]")
        # Include basic info about embeds
        if m.embeds:
            try:
                embeds_desc = ", ".join([e.url for e in m.embeds if hasattr(e, "url")])
            except Exception:
                embeds_desc = str(len(m.embeds)) + " embed(s)"
            if embeds_desc:
                content_parts.append(f"[embeds: {embeds_desc}]")
        content = " \n".join(content_parts) or "[no text]"
        return role, content

    # Build conversational context from recent messages in the same channel/thread
    async def get_message_history(self) -> Iterable[ChatCompletionMessageParam]:
        '''
        Ask Discord for the last $OUI_CHAT_CONTEXT number of messages to get context on the
        conversation. Return a list of messages we can use for context.
        '''
        chat_history: list[ChatCompletionMessageParam] = []

        # Use the stored current message for context
        if not hasattr(self, 'current_message') or not self.current_message:
            return chat_history

        try:
            async for msg in self.current_message.channel.history(limit=self.config.chat_context, before=self.current_message, oldest_first=True):
                role, content = self.format_message(msg)
                chat_history.append({'role': role, 'content': content})
        except Exception as exc:
            debug_event("history_fetch_error", error=repr(exc))

        return chat_history
