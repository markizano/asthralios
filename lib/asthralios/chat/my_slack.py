'''
This is an adapter interface that will enable us to take the rough edges off of talking
to the Slack API's.

Register the functions needed in order to send and receive messages and DM's from Slack.
'''

import asyncio
from collections.abc import Callable
from datetime import datetime

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from typing import Iterable
from openai.types.chat import ChatCompletionMessageParam

from asthralios.chat.adapter import ChatAdapter, debug_event

class ChatAdapterSlack(ChatAdapter):
    '''
    Adapter interface to take the "rough edges" off of talking to Slack.
    '''

    def init(self):
        self.bot = App(token=self.config.slack_bot_token)
        self.web = WebClient(token=self.config.slack_bot_token)
        self.register()

    def start(self):
        handler = SocketModeHandler(self.bot, self.config.slack_app_token)
        handler.start()

    def register(self):
        '''
        Register the event handlers so the bot gets connected to the server.
        '''
        @self.bot.event('app_mention')
        async def handle_app_mention(event, say):
            await self._handle_message_event(event, say, is_mention=True)

        @self.bot.event('message')
        def handle_message(event, say):
            asyncio.run(self._handle_message_event(event, say, is_mention=False))

    async def _handle_message_event(self, event: dict, say: Callable, is_mention: bool = False):
        '''
        Common handler for message events.
        '''
        debug_event(
            "slack_message:start",
            user=event.get("user"),
            channel=event.get("channel"),
            text=event.get("text", ""),
            ts=event.get("ts"),
            is_mention=is_mention,
            is_dm=event.get("channel_type") == "im",
            thread_ts=event.get("thread_ts"),
        )

        async def async_say(_m: str):
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, say, _m)


        # Skip bot messages and messages without text
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            debug_event('slack_message:skip', notice='Skipping bot message')
            return

        if not event.get("text"):
            debug_event('slack_message:text', notice='No text content')
            return

        # Only respond if we have an LLM configured
        if self.llm:
            # Store current event for history context
            self.current_event = event
            role, content = self.format_message(event)
            reply = await self.on_message_received(content)
            await self.do_message_send(async_say, reply)

    def format_message(self, event: dict) -> tuple[str, str]:
        '''
        Format a Slack event into a "user|assistant": "content" format that can be used in
        LLM API calls.
        '''
        # Slack events don't have bot user info directly, so we assume user messages
        role = "user"
        content_parts = []

        # Add timestamp and user info for context
        ts = event.get("ts", "")
        user = event.get("user", "unknown")
        if ts:
            try:
                # Convert Slack timestamp to readable format
                timestamp = datetime.fromtimestamp(float(ts))
                content_parts.append(f"[{timestamp}] @{user}: ")
            except (ValueError, TypeError):
                content_parts.append(f"@{user}: ")
        else:
            content_parts.append(f"@{user}: ")

        # Add the message text
        text = (event.get("text", "")).strip()
        if text:
            content_parts.append(text)

        # Include info about attachments if present
        if event.get("files"):
            files_desc = ", ".join([f.get("name", "file") for f in event.get("files", [])])
            content_parts.append(f"[attachments: {files_desc}]")

        content = "\n".join(content_parts) or "[no text]"
        return role, content

    async def get_message_history(self) -> Iterable[ChatCompletionMessageParam]:
        '''
        Get recent message history from the Slack channel for context.
        '''
        chat_history: list[ChatCompletionMessageParam] = []

        # Use the stored current event for context
        if not hasattr(self, 'current_event') or not self.current_event:
            return chat_history

        try:
            channel = self.current_event.get("channel")
            thread_ts = self.current_event.get("thread_ts")
            current_ts = self.current_event.get("ts")

            if not channel:
                return chat_history

            # Fetch conversation history using Slack Web API
            if thread_ts:
                # If we're in a thread, get thread replies
                response = self.web.conversations_replies(
                    channel=channel,
                    ts=thread_ts,
                    limit=self.config.chat_context + 1,  # +1 to account for current message
                    oldest=False
                )
                messages = response.get("messages", [])
            else:
                # Get channel history
                response = self.web.conversations_history(
                    channel=channel,
                    limit=self.config.chat_context + 1,  # +1 to account for current message
                    oldest=False
                )
                messages = response.get("messages", [])

            # Process messages into chat history format
            for msg in reversed(messages):  # Reverse to get chronological order
                # Skip the current message to avoid duplication
                if msg.get("ts") == current_ts:
                    continue

                # Skip bot messages and system messages
                if msg.get("bot_id") or msg.get("subtype") in ["bot_message", "channel_join", "channel_leave"]:
                    continue

                # Format message and add to history
                role, content = self._format_history_message(msg)
                if content.strip():  # Only add non-empty messages
                    chat_history.append({'role': role, 'content': content})

                # Stop if we have enough history
                if len(chat_history) >= self.config.chat_context:
                    break

            debug_event(
                "slack_history_fetched",
                channel=channel,
                thread_ts=thread_ts,
                total_messages=len(messages),
                history_count=len(chat_history)
            )

        except SlackApiError as e:
            debug_event("slack_api_error", error=f"Error code: {e.response['error']}")
        except Exception as exc:
            debug_event("slack_history_error", error=repr(exc))

        return chat_history

    def _format_history_message(self, msg: dict) -> tuple[str, str]:
        '''
        Format a Slack message from history into role/content format.
        Similar to format_message but for historical messages.
        '''
        role = "user"  # Assume user messages for history
        content_parts = []

        # Add user info for context
        user = msg.get("user", "unknown")
        ts = msg.get("ts", "")

        if ts:
            try:
                timestamp = datetime.fromtimestamp(float(ts))
                content_parts.append(f"[{timestamp}] @{user}: ")
            except (ValueError, TypeError):
                content_parts.append(f"@{user}: ")
        else:
            content_parts.append(f"@{user}: ")

        # Add message text
        text = (msg.get("text", "")).strip()
        if text:
            content_parts.append(text)

        # Include file info if present
        if msg.get("files"):
            files_desc = ", ".join([f.get("name", "file") for f in msg.get("files", [])])
            content_parts.append(f"[attachments: {files_desc}]")

        content = "\n".join(content_parts) or "[no text]"
        return role, content
