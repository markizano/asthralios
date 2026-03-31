'''
This is an adapter interface that will enable us to take the rough edges off of talking
to the Slack API's.

Register the functions needed in order to send and receive messages and DM's from Slack.
'''

import asyncio
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Optional

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from asthralios.brain.rbac import UserIdentity
from asthralios.chat.adapter import ChatAdapter, debug_event

import asthralios
log = asthralios.getLogger(__name__)


def send_slack_message(config, channel: str, message: str) -> None:
    """
    Proactively send a message to a Slack channel without needing a prior event.
    Usable from CLI or cron jobs.
    """
    client = WebClient(token=config.slack.bot_token)
    client.chat_postMessage(channel=channel, text=message)


class ChatAdapterSlack(ChatAdapter):
    '''
    Adapter interface to take the "rough edges" off of talking to Slack.
    '''

    def mesgLimit(self):
        return 4000

    def init(self):
        self.bot = App(token=self.config.slack.bot_token)
        self.web = WebClient(token=self.config.slack.bot_token)
        self._current_channel: Optional[str] = None
        self._name_cache: dict = {}
        self.register()

    def start(self):
        handler = SocketModeHandler(self.bot, self.config.slack.app_token)
        handler.start()

    def register(self):
        '''
        Register the event handlers so the bot gets connected to the server.
        '''
        @self.bot.event('app_mention')
        def handle_app_mention(event, say):
            asyncio.run(self._handle_message_event(event, say, is_mention=True))

        @self.bot.event('message')
        def handle_message(event, say):
            asyncio.run(self._handle_message_event(event, say, is_mention=False))

    def extract_identity(self, event: dict) -> UserIdentity:
        user_id = event.get('user', 'unknown')
        display_name = self._resolve_display_name(user_id)
        return UserIdentity(
            platform='slack',
            platform_user_id=user_id,
            display_name=display_name,
        )

    def _resolve_display_name(self, user_id: str) -> str:
        """
        Cache display names for this process lifetime to avoid hammering the API.
        Slack rate limits users.info calls.
        """
        if user_id in self._name_cache:
            return self._name_cache[user_id]
        try:
            info = self.web.users_info(user=user_id)
            name = (
                info['user']['profile'].get('display_name')
                or info['user']['profile'].get('real_name')
                or user_id
            )
        except Exception:
            name = user_id
        self._name_cache[user_id] = name
        return name

    def _get_channel(self, event: dict) -> str:
        return event.get('channel', '')

    def _get_text(self, event: dict) -> str:
        """Return the formatted message text for LLM context."""
        _, content = self.format_message(event)
        return content

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

        # Skip bot messages and messages without text
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            debug_event('slack_message:skip', notice='Skipping bot message')
            return

        if not event.get("text"):
            debug_event('slack_message:text', notice='No text content')
            return

        if not self.llm:
            return

        channel = event.get("channel", '')
        thread_ts = event.get("thread_ts") or event.get("ts")
        text = event.get("text", "").strip()

        # Track current channel for get_thread_history
        self._current_channel = channel

        async def async_say(_m: str):
            loop = asyncio.get_event_loop()
            thread_kwarg = {"thread_ts": thread_ts} if thread_ts else {}
            await loop.run_in_executor(None, lambda: say(_m, **thread_kwarg))

        # Handle fix: commands (admin-only, checked here before RBAC gate)
        if re.match(r'^fix\s*:', text, re.IGNORECASE):
            identity = self.extract_identity(event)
            ctx = self.get_rbac().resolve(identity, channel, text)
            if not self.get_rbac().is_allowed(ctx, 'admin'):
                self.get_rbac().log_access(ctx, 'fix', 'denied', detail='non-admin fix attempt')
                await self.do_message_send(async_say, "Only the admin can use the fix command.")
                return
            await self._handle_fix_command(text, async_say, identity.platform_user_id, channel)
            self.get_rbac().log_access(ctx, 'fix', 'ok', detail=f'command: {text[:80]}')
            return

        # Delegate all other messages through RBAC gate in base class
        reply = await self.on_message_received(event, async_say, thread_id=thread_ts)
        if reply:
            await self.do_message_send(async_say, reply)

    async def _handle_fix_command(
        self,
        text: str,
        say: Callable,
        source_user: str,
        channel: str,
    ) -> None:
        """
        Parse 'fix: <category> [#entry_id]', move the file to the correct category,
        and update the DB status.
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

    def format_message(self, event: dict) -> tuple[str, str]:
        '''
        Format a Slack event into a "user|assistant": "content" format.
        '''
        role = "user"
        content_parts = []

        ts = event.get("ts", "")
        user = event.get("user", "unknown")
        if ts:
            try:
                timestamp = datetime.fromtimestamp(float(ts))
                content_parts.append(f"[{timestamp}] @{user}: ")
            except (ValueError, TypeError):
                content_parts.append(f"@{user}: ")
        else:
            content_parts.append(f"@{user}: ")

        text = (event.get("text", "")).strip()
        if text:
            content_parts.append(text)

        if event.get("files"):
            files_desc = ", ".join([f.get("name", "file") for f in event.get("files", [])])
            content_parts.append(f"[attachments: {files_desc}]")

        content = "\n".join(content_parts) or "[no text]"
        return role, content

    async def get_thread_history(self, thread_id: str) -> list[dict]:
        """Return thread-only message history capped at thread_context_limit."""
        limit = getattr(self.config.oui, 'thread_context_limit', 10)
        try:
            result = self.web.conversations_replies(
                channel=self._current_channel,
                ts=thread_id,
                limit=limit + 1,  # +1 because the parent message is included
            )
            messages = result.get('messages', [])
            history = []
            for msg in messages:
                if msg.get('bot_id') or msg.get('subtype') == 'bot_message':
                    role = 'assistant'
                else:
                    role = 'user'
                if msg.get('text'):
                    history.append({'role': role, 'content': msg['text']})
            return history[-limit:]
        except Exception as e:
            log.error(f'get_thread_history failed: {e}')
            return []
