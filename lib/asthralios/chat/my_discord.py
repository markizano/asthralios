'''
This is an adapter interface that will enable us to take the rough edges off of talking
to the Discord API's.

Register the functions needed in order to send and receive messages and DM's from Discord.

Implement Decorator functions that will register handlers for messages received and what to send.
'''
import discord
from discord.ext import commands

from asthralios.config import Configuration
from asthralios.chat.adapter import ChatAdapter

from kizano import getLogger
log = getLogger(__name__)

def debug_event(event_name: str, **kwargs) -> None:
    log.debug(f"[DEBUG] {event_name}")
    for key, value in kwargs.items():
        log.debug(f"  - {key}: {value}")


class ChatAdapterDiscord(ChatAdapter):
    def init(self):
        self.config = Configuration.getInstance()
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        intents.messages = True
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self.registerBot()

    def start(self):
        # Run the bot
        self.bot.run(self.config.discord_bot_token)

    def registerBot(self):
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

            # Avoid responding to ourselves
            if message.author == self.bot.user:
                debug_event('on_message', notice='Avoiding talking to ourselves.')
                return

            # Simple text trigger example kept for manual testing
            if message.content.strip().lower() == "$hello":
                await message.channel.send("Hello!")
                await self.bot.process_commands(message)
                return

            # Respond if DM or mentioned
            is_dm = isinstance(message.channel, discord.DMChannel)
            mentioned_bot = self.bot.user.mentioned_in(message) if self.bot.user else False

            # if (is_dm or mentioned_bot) and oui_client:
            if self.oui_client:

                async with message.channel.typing() as typing_ctx:
                    chat_messages = await self.build_chat_context(message)
                    debug_event(
                        "chat_context_built",
                        context=chat_messages,
                    )

                    try:
                        # Choose model: env override -> client default -> library default
                        response = self.oui_client.chat.completions.create(
                            messages=chat_messages,
                            model=self.oui_client.default_model,
                            stream=False,

                        )

                        reply_text = None
                        try:
                            reply_text = response.choices[0].message.content  # type: ignore[attr-defined]
                        except Exception:
                            reply_text = str(response)

                        debug_event("openwebui_response", reply_preview=(reply_text or "")[:200])
                        if reply_text:
                            if len(reply_text) > 5000:
                                # Paginate the response.
                                for i in range(0, len(reply_text), 5000):
                                    await message.channel.send(reply_text[i:i+5000])
                            else:
                                await message.channel.send(reply_text)
                    except Exception as exc:
                        debug_event("openwebui_error", error=repr(exc))
                        await message.channel.send("Sorry, I couldn't get a response right now.")

            # Ensure commands extension still receives the message
            await self.bot.process_commands(message)


    def message_to_role_and_content(self, m: discord.Message) -> tuple[str, str]:
        role = "assistant" if (m.author.bot or (self.bot.user and m.author.id == self.bot.user.id)) else "user"
        content_parts = []
        # Prefix user messages with their name for context
        if role == "user":
            content_parts.append(f"[@{m.author.name}]: ")
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
                embeds_desc = ", ".join([e.url for e in m.embeds if getattr(e, "url", None)])
            except Exception:
                embeds_desc = str(len(m.embeds)) + " embed(s)"
            if embeds_desc:
                content_parts.append(f"[embeds: {embeds_desc}]")
        content = " \n".join(content_parts) or "[no text]"
        return role, content

    # Build conversational context from recent messages in the same channel/thread
    async def get_chat_context(self, m: discord.Message) -> list[str]:
        history_messages: list[discord.Message] = []
        history_context = int(self.config.oui_chat_context)
        try:
            async for m in m.channel.history(limit=history_context, before=m):
                history_messages.append(m)
        except Exception as exc:
            debug_event("history_fetch_error", error=repr(exc))

        # Oldest -> newest for chronological conversation
        history_messages.reverse()
        return history_messages

    async def build_chat_context(self, m: discord.Message):
        history_messages = await self.get_chat_context(m)
        # Compose chat history entries
        chat_messages = []
        # System prompt must be first
        chat_messages.append({"role": "system", "content": open(self.config.oui_system_prompt_file).read()})

        for m in history_messages:
            role, content = self.message_to_role_and_content(m)
            chat_messages.append({"role": role, "content": content})

        # Current user message last
        chat_messages.append({"role": "user", "content": f'[@{m.author.name}]: {m.content}'})
        return chat_messages

