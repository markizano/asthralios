import typing
import urllib3
import json

import kizano
log = kizano.getLogger(__name__)
class Message(typing.NamedTuple):
    '''
    A message object for ollama2.
    '''
    role: str
    content: str

    def __str__(self):
        return f'{self.role}: {self.content}'

class LocalGPT:
    '''
    This is a client that connects to a local instance of ollama.
    '''

    def __init__(self, host: str='127.0.0.1', port: int=11434):
        self.prefix = f'http://{host}:{port}'
        self.http = urllib3.PoolManager()
        self.conversation: list[Message] = [Message('system', ("You are a helpful assistant named Asthralios and you serve me, Markizano. "
                "You have an aulturistic tone like Alfred is to Batman and Jarvis is to Iron Man. "
                "You are a voice assistant that can help with a variety of tasks. You are careful not to be too wordy."))]

    def converse(self, text: str) -> str:
        '''
        Query the local ollama instance with the text.
        '''
        url = f'{self.prefix}/api/chat'
        self.conversation.append(Message('user', text))
        payload = {
            'model': 'llama2',
            'messages': [x._asdict() for x in self.conversation],
            'stream': False,
        }
        response = self.http.request('POST', url,
            body=json.dumps(payload, default=str).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        result = json.loads( response.data.decode('utf-8') )
        log.debug(result)
        msg = result['message']['content']
        self.conversation.append(Message('assistant', msg))
        return msg

    def __del__(self):
        '''
        Close the connection to the local ollama instance.
        '''
        self.http.clear()
        log.debug('LocalGPT closed.')
