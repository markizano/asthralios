'''
Abstract Interface to describe the main methods any derived class should implement.

Describes a common unified interface such that all the chat apps can combine
themselves into this class instance.

'''

from typing import Awaitable, Iterable

from openai.types.chat import ChatCompletionMessageParam
import asthralios.config as config
import openwebui_client.client as oui

from kizano import getLogger
log = getLogger(__name__)

def debug_event(event_name: str, **kwargs) -> None:
    log.debug(f"[DEBUG] {event_name}")
    for key, value in kwargs.items():
        log.debug(f"  - {key}: {value}")

class ChatAdapter(object):
    def __init__(self):
        self.config = config.getInstance()
        self.llm = oui.OpenWebUIClient(
            base_url=self.config.oui_base_url,
            api_key=self.config.oui_api_key,
            default_model=self.config.oui_model,
        )
        self.init()

    async def on_message_received(self, message: str) -> str:
        '''
        Handler for when a message is received.
        '''
        # Attempt to get the system prompt.
        system_prompt = open(self.config.oui_system_prompt_file).read() or 'You are a helpful Discord bot.'
        # Get the Adapter implementation chat history.
        chat_history = await self.get_message_history()

        # Build the message list based on history, context and system prompt.
        messages: Iterable[ChatCompletionMessageParam] = [ {'role': 'system', 'content': system_prompt} ]
        messages.extend(chat_history)
        messages.append({'role': 'user', 'content': message})
        debug_event(
            'on_message_received',
            messages=messages
        )

        # Attempt to get a response from the LLM.
        try:
            response = self.llm.chat.completions.create(
                messages=messages,
                model=self.llm.default_model or "gpt-5",
                stream=False
            )
            reply = response.choices[0].message.content if response.choices else "Sorry, I couldn't generate a response."
        except Exception as e:
            debug_event('error:on_message_received', error=e)
            reply = 'Sorry, I had an issue getting a response...'

        return reply

    async def do_message_send(self, say: Awaitable, reply: str) -> None:
        '''
        Paginated response as necessary.
        '''
        debug_event(
            'do_message_send',
            reply=reply
        )
        msg_limit = 4000
        if reply:
            if len(reply) > msg_limit:
                # Paginate the response.
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

    async def get_message_history(self) -> Iterable[ChatCompletionMessageParam]:
        raise NotImplemented(__name__)
