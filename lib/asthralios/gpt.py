import typing
import urllib3
import json

class Message(typing.NamedTuple):
    '''
    A message object for ollama2.
    '''
    role: str
    content: str

    def __str__(self):
        return f'{self.role}: {self.content}'

class localGPT:
    '''
    This is a client that connects to a local instance of ollama.
    '''

    def __init__(self, host: str='127.0.0.1', port: int=11434):
        self.prefix = f'http://{host}:{port}'
        self.http = urllib3.PoolManager()
        self.conversation: list[Message] = [Message('system', ("You are a helpful assistant named Asthralios. "
                "You have an aulturistic tone like Alfred is to Batman and Jarvis is to Iron Man. "
                "You are a voice assistant that can help with a variety of tasks."))]

    def talk(self, text: str) -> str:
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
        return json.loads( response.data.decode('utf-8') )
