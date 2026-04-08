'''
Abstract Interface to describe the main methods any derived class should implement.

Describes a common unified interface such that all the chat apps can combine
themselves into this class instance.

'''
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Callable, Optional

from easydict import EasyDict
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from asthralios import brain

import asthralios
log = asthralios.getLogger(__name__)

SYSTEM_PROMPT = '''# Kizano's Little Helper

You're a helpful system agent of the Markizano Draconus story and for Kizano's FinTech.
Markizano Draconus is a Tanninovian from the Crux galaxy with the powers of telekinesis and telepathy.
At Kizano's FinTech, we help you from zero to master in IT and DevOps!

Your role is to help folks feel welcome and provide them with information relavant to the story and for finding
info they need to be successful in their role.

When speaking to @markizano, you can be a little more casual.
'''

def debug_event(event_name: str, **kwargs) -> None:
    log.debug(f"[DEBUG] {event_name}")
    for key, value in kwargs.items():
        log.debug(f"  - {key}: {value}")

class ChatAdapter(object):
    '''
    If I could, I would denote this an `abstract` class, but Python doesn't do that very well.
    Base "abstract" class that represents a chat adapter. Could be used for any chat interface.
    '''
    def __init__(self, config: EasyDict):
        self.config = config
        llm_cfg = config.get('llm', {})
        self._llm = init_chat_model(
            model=llm_cfg.get('model', 'gpt-oss:20b'),
            model_provider=llm_cfg.get('provider', 'ollama'),
        )
        self.init()

    def get_rbac(self) -> brain.rbac.RBACManager:
        '''
        Return (or lazily initialise) the RBACManager for this adapter.
        '''
        if not hasattr(self, '_rbac'):
            db = brain.db.BrainDB(self.config.get('brain', {}).get('db_path', '.braindb'))
            self._rbac = brain.rbac.RBACManager(db, self.config)
        return self._rbac

    def on_message_received(
        self,
        event,
        thread_id: Optional[str] = None,
    ) -> str:
        '''
        Handler for when a message is received. Performs RBAC, then routes to
        brain inbox or normal LLM chat as appropriate.
        Returns the reply string; empty string means send nothing.
        '''
        identity = self.extract_identity(event)
        channel  = self._get_channel(event)
        message  = self._get_text(event)

        rbac = self.get_rbac()
        ctx  = rbac.resolve(identity, channel, message)

        # ── Blocked users ──────────────────────────────────────────────────
        if ctx.role == 'blocked':
            rbac.log_access(ctx, 'blocked', 'denied')
            # Only reply on first contact; silent thereafter
            prior = rbac.db.get_access_log(limit=2, platform_user_id=identity.platform_user_id)
            first_contact = len([r for r in prior if r['action'] == 'blocked']) <= 1
            if first_contact:
                return getattr(self.config, 'rbac', {}).get(
                    'blocked_message',
                    "This assistant is private. If you think this is an error, reach out to the owner."
                )
            return ''

        # ── Brain channel routing ───────────────────────────────────────────
        if self.is_brain_channel(channel):
            if not rbac.is_allowed(ctx, 'admin'):
                rbac.log_access(ctx, 'brain_blocked', 'denied',
                                detail='non-admin attempted brain inbox')
                return "The brain inbox is private. General questions welcome in other channels."
            thread_context = self.get_thread_history(thread_id) if thread_id else None
            return self.on_brain_message(
                message=message,
                source_platform=identity.platform,
                source_user=identity.platform_user_id,
                source_channel=channel,
                thread_context=thread_context,
                access_ctx=ctx,
            )

        # ── Normal chat ─────────────────────────────────────────────────────
        rbac.log_access(ctx, 'chat', 'ok', detail=f'channel={channel}')

        # Get thread-only history (not full channel history).
        chat_history = self.get_thread_history(thread_id) if thread_id else []

        # Build the message list based on history, context and system prompt.
        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        for msg in chat_history:
            if msg['role'] == 'assistant':
                messages.append(AIMessage(content=msg['content']))
            else:
                messages.append(HumanMessage(content=msg['content']))
        messages.append(HumanMessage(content=message))
        debug_event('on_message_received', messages=messages)

        # Attempt to get a response from the LLM.
        try:
            response = self._llm.invoke(messages)
            return response.content if response else "Sorry, I couldn't generate a response."
        except Exception as e:
            debug_event('error:on_message_received', error=e)
            return 'Sorry, I had an issue getting a response...'

    def on_brain_message(
        self,
        message: str,
        source_platform: str,
        source_user: str,
        source_channel: str,
        thread_context: Optional[list[dict]] = None,
        access_ctx=None,
    ) -> str:
        """
        Handle a message arriving in the designated brain inbox channel.
        Classify it, file it, log it, and return the reply string.
        access_ctx is an AccessContext from the RBAC gate (used for logging).
        """
        brain_cfg  = self.config.get('brain', {})
        classifier = brain.classifier.BrainClassifier(brain_cfg)
        vault = brain.vault.BrainVault(brain_cfg.vault_path)
        rbac   = self.get_rbac() if access_ctx is not None else None

        result = classifier.classify(message, thread_context=thread_context)

        log_record = brain.schema.InboxLogRecord(
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
            rbac.db.log_entry(log_record)
            if rbac and access_ctx:
                rbac.log_access(access_ctx, 'clarification', 'clarification_sent',
                                detail=f'confidence={result.confidence:.2f}')
            return (
                f"\U0001f914 {result.clarification_question}\n"
                f"_(confidence: {result.confidence:.0%})_"
            )

        filed_path = vault.write(result, source_platform, source_user)
        log_record.filed_path = filed_path
        row_id = rbac.db.log_entry(log_record)

        if rbac and access_ctx:
            rbac.log_access(access_ctx, 'brain_filed', 'ok',
                            detail=f'category={result.category} confidence={result.confidence:.2f}')

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
        return reply

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

    def do_message_send(self, say: Callable, reply: str) -> None:
        '''
        Paginated send. Calls the sync say() callable directly.
        '''
        debug_event('do_message_send', reply=reply)
        msg_limit = self.mesgLimit()
        if reply:
            if len(reply) > msg_limit:
                for i in range(0, len(reply), msg_limit):
                    say(reply[i:i+msg_limit])
            else:
                say(reply)

    def _handle_fix_command(self, text: str, source_user: str) -> str:
        '''
        Parse 'fix: <category> [#entry_id]', move the file, update DB.
        Returns the reply string.
        '''
        match = re.match(r'^fix\s*:\s*(\w+)(?:\s+#(\d+))?', text, re.IGNORECASE)
        if not match:
            return "Couldn't parse fix command. Format: `fix: <category>` or `fix: <category> #<entry_id>`"

        new_category = match.group(1).lower()
        entry_id = int(match.group(2)) if match.group(2) else None

        if new_category not in brain.NOTE_CATEGORIES:
            return f"Unknown category `{new_category}`. Valid: {', '.join(sorted(brain.NOTE_CATEGORIES))}"

        brain_cfg = self.config.brain
        db = brain.db.BrainDB(brain_cfg.db_path)

        row = db.get_entry(entry_id) if entry_id else db.get_latest_for_user(source_user, ['filed', 'needs_review'])

        if not row:
            return "No matching entry found to fix."

        original_category = row['category']
        old_path = row['filed_path']

        if old_path and Path(old_path).exists():
            new_path = Path(brain_cfg.vault_path) / new_category / Path(old_path).name
            Path(old_path).rename(new_path)
            db.update_filed_path(row['id'], str(new_path))
            db.update_status(row['id'], 'fix_applied', fix_original_cat=original_category)
            return f"Fixed: moved entry #{row['id']} from `{original_category}` to `{new_category}`."
        else:
            db.update_status(row['id'], 'fix_applied', fix_original_cat=original_category)
            return f"Fixed category for entry #{row['id']} to `{new_category}` (no file to move)."

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

    def get_thread_history(self, thread_id: str) -> list[dict]:
        """Return [{'role': str, 'content': str}, ...] for the given thread only."""
        raise NotImplementedError

    def mesgLimit(self) -> int:
        raise NotImplemented(__name__)
