'''
Abstract Interface to describe the main methods any derived class should implement.

Describes a common unified interface such that all the chat apps can combine
themselves into this class instance.

'''

from datetime import datetime, timezone
from typing import Awaitable, Iterable, Optional

from easydict import EasyDict
from openai.types.chat import ChatCompletionMessageParam
import openwebui_client.client as oui

import asthralios
log = asthralios.getLogger(__name__)

def debug_event(event_name: str, **kwargs) -> None:
    log.debug(f"[DEBUG] {event_name}")
    for key, value in kwargs.items():
        log.debug(f"  - {key}: {value}")

class ChatAdapter(object):
    '''
    Base class that represents a chat adapter. Could be used for any chat interface.
    '''
    def __init__(self, config: EasyDict):
        self.config = config
        self.llm = oui.OpenWebUIClient(
            base_url=self.config.oui.base_url,
            api_key=self.config.oui.api_key,
            default_model=self.config.oui.model,
        )
        self.init()

    def get_rbac(self):
        """Return (or lazily initialise) the RBACManager for this adapter."""
        if not hasattr(self, '_rbac'):
            from asthralios.brain import BrainDB
            from asthralios.brain.rbac import RBACManager
            db = BrainDB(self.config.brain.db_path)
            self._rbac = RBACManager(db, self.config)
        return self._rbac

    async def on_message_received(
        self,
        event,
        say,
        thread_id: Optional[str] = None,
    ) -> str:
        '''
        Handler for when a message is received. Performs RBAC, then routes to
        brain inbox or normal LLM chat as appropriate.
        '''
        from asthralios.brain.db import BrainDB

        identity = self.extract_identity(event)
        channel  = self._get_channel(event)
        message  = self._get_text(event)

        rbac = self.get_rbac()
        ctx  = rbac.resolve(identity, channel, message)

        # ── Blocked users ──────────────────────────────────────────────────
        if ctx.role == 'blocked':
            rbac.log_access(ctx, 'blocked', 'denied')
            # Only reply on first contact; silent thereafter
            db = BrainDB(self.config.brain.db_path)
            prior = db.get_access_log(limit=2, platform_user_id=identity.platform_user_id)
            first_contact = len([r for r in prior if r['action'] == 'blocked']) <= 1
            if first_contact:
                blocked_msg = getattr(self.config, 'rbac', {}).get(
                    'blocked_message',
                    "This assistant is private. If you think this is an error, reach out to the owner."
                )
                await self.do_message_send(say, blocked_msg)
            return ''

        # ── Brain channel routing ───────────────────────────────────────────
        if self.is_brain_channel(channel):
            if not rbac.is_allowed(ctx, 'admin'):
                rbac.log_access(ctx, 'brain_blocked', 'denied',
                                detail='non-admin attempted brain inbox')
                await self.do_message_send(say,
                    "The brain inbox is private. General questions welcome in other channels.")
                return ''
            thread_context = await self.get_thread_history(thread_id) if thread_id else None
            await self.on_brain_message(
                message=message,
                say=say,
                source_platform=identity.platform,
                source_user=identity.platform_user_id,
                source_channel=channel,
                thread_id=thread_id,
                thread_context=thread_context,
                access_ctx=ctx,
            )
            return ''

        # ── Normal chat ─────────────────────────────────────────────────────
        rbac.log_access(ctx, 'chat', 'ok', detail=f'channel={channel}')

        # Attempt to get the system prompt.
        system_prompt = open(self.config.oui.system_prompt_file).read() or 'You are a helpful assistant.'
        # Get thread-only history (not full channel history).
        chat_history = await self.get_thread_history(thread_id) if thread_id else []

        # Build the message list based on history, context and system prompt.
        messages: Iterable[ChatCompletionMessageParam] = [{'role': 'system', 'content': system_prompt}]
        messages.extend(chat_history)
        messages.append({'role': 'user', 'content': message})
        debug_event('on_message_received', messages=messages)

        # Attempt to get a response from the LLM.
        try:
            response = self.llm.chat.completions.create(
                messages=messages,
                model=self.llm.default_model or "gpt-5",
                stream=False,
                max_tokens=1024,
            )
            reply = response.choices[0].message.content if response.choices else "Sorry, I couldn't generate a response."
        except Exception as e:
            debug_event('error:on_message_received', error=e)
            reply = 'Sorry, I had an issue getting a response...'

        return reply

    async def on_brain_message(
        self,
        message: str,
        say,
        source_platform: str,
        source_user: str,
        source_channel: str,
        thread_id: Optional[str] = None,
        thread_context: Optional[list[dict]] = None,
        access_ctx=None,
    ) -> None:
        """
        Handle a message arriving in the designated brain inbox channel.
        Classify it, file it, log it, and reply with confirmation or a clarifying question.
        access_ctx is an AccessContext from the RBAC gate (used for logging).
        """
        from asthralios.brain import BrainClassifier, BrainWriter, BrainDB, InboxLogRecord

        brain_cfg  = self.config.brain
        classifier = BrainClassifier(dict(
            model=brain_cfg.get('model', 'llama3.2:3b'),
            provider=brain_cfg.get('provider', 'ollama'),
        ))
        writer = BrainWriter(brain_cfg.vault_path)
        db     = BrainDB(brain_cfg.db_path)
        rbac   = self.get_rbac() if access_ctx is not None else None

        result = classifier.classify(message, thread_context=thread_context)

        log_record = InboxLogRecord(
            received_at=datetime.now(timezone.utc),
            source_platform=source_platform,
            source_user=source_user,
            source_channel=source_channel,
            raw_message=message,
            category=result.category if not result.needs_clarification else None,
            name=result.name if not result.needs_clarification else None,
            confidence=result.confidence,
            status='needs_review' if result.needs_clarification else 'filed',
            clarification_question=result.clarification_question,
        )

        if result.needs_clarification:
            db.log_entry(log_record)
            if rbac and access_ctx:
                rbac.log_access(access_ctx, 'clarification', 'clarification_sent',
                                detail=f'confidence={result.confidence:.2f}')
            reply = (
                f"\U0001f914 {result.clarification_question}\n"
                f"_(confidence: {result.confidence:.0%})_"
            )
            await self.do_message_send(say, reply)
            return

        filed_path = writer.write(result, source_platform, source_user)
        log_record.filed_path = filed_path
        row_id = db.log_entry(log_record)

        if rbac and access_ctx:
            rbac.log_access(access_ctx, 'brain_filed', 'ok',
                            detail=f'category={result.category} confidence={result.confidence:.2f}')

        # Confirmation reply with fix button instruction
        emoji_map = {
            'people': '\U0001f464', 'projects': '\U0001f4cb', 'ideas': '\U0001f4a1',
            'admin': '\U0001f4cc', 'musings': '\U0001f4d3',
        }
        emoji = emoji_map.get(result.category, '\U0001f5c2\ufe0f')
        reply = (
            f"{emoji} Filed as **{result.category}** \u2014 _{result.name}_ "
            f"(confidence: {result.confidence:.0%})\n"
        )
        if result.next_action:
            reply += f"Next action: {result.next_action}\n"
        reply += f"\n_Reply `fix: <category>` if I got it wrong. Entry #{row_id}_"

        await self.do_message_send(say, reply)

    def is_brain_channel(self, channel: str) -> bool:
        inbox = getattr(self.config, 'brain', {})
        if not inbox:
            return False
        inbox_channel = inbox.get('inbox_channel', None)
        if not inbox_channel:
            return False
        if isinstance(inbox_channel, list):
            return channel in inbox_channel
        return channel == inbox_channel

    async def do_message_send(self, say: Awaitable, reply: str) -> None:
        '''
        Paginated response as necessary.
        '''
        debug_event('do_message_send', reply=reply)
        msg_limit = self.mesgLimit()
        if reply:
            if len(reply) > msg_limit:
                for i in range(0, len(reply), msg_limit):
                    await say(reply[i:i+msg_limit])
            else:
                await say(reply)

    # Child/Derived classes must implement these.
    def init(self):
        raise NotImplemented(__name__)

    def start(self):
        raise NotImplemented(__name__)

    def register(self):
        raise NotImplemented(__name__)

    def extract_identity(self, event):
        """Extract a UserIdentity from a platform-specific event."""
        raise NotImplementedError

    def _get_channel(self, event) -> str:
        """Extract the channel name/ID from a platform-specific event."""
        raise NotImplementedError

    def _get_text(self, event) -> str:
        """Extract the formatted message text from a platform-specific event."""
        raise NotImplementedError

    async def get_thread_history(self, thread_id: str) -> list[dict]:
        """Return [{'role': str, 'content': str}, ...] for the given thread only."""
        raise NotImplementedError

    def mesgLimit(self):
        raise NotImplemented(__name__)
