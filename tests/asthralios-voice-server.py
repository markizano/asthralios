#!/usr/bin/python3

import sys, os, io
import time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib')))

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib

import pasimple
import numpy as np
import scipy.io.wavfile as wavfile

import torch
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
from TTS.utils.audio.numpy_transforms import save_wav

import kizano
kizano.Config.APP_NAME = 'asthralios'
log = kizano.getLogger(__name__)

LANG = os.environ.get('LANGUAGE', 'en')
HOME = os.environ.get('HOME', '/home/stable-diffusion')
PLAY_AUDIO = 'PLAY_AUDIO' in os.environ and os.environ['PLAY_AUDIO'].lower() not in ['', '0', 'false', 'no']

class LocalXttsContainer(object):
    _instance = None

    def __init__(self, config: kizano.Config):
        log.info('Loading TTS model...')
        log.info('> New TTSv2 Config...')
        self.config = config
        self.xconfig = XttsConfig()
        self.checkpoint_path = os.path.join(HOME, '.local', 'share', 'tts', 'tts_models--multilingual--multi-dataset--xtts_v2')
        self.xconfig.load_json(os.path.join(self.checkpoint_path, 'config.json'))
        log.info('> Config loaded.')
        # log.debug(xtts_config.__dict__)

        log.info('> Loading checkpoint...')
        default_device = 'cuda' if torch.cuda.is_available() else 'cpu'
        device = torch.device( config.get('device', default_device) )
        self.model = Xtts(self.xconfig).to(device)
        self.model.load_checkpoint(self.xconfig, checkpoint_dir=self.checkpoint_path, eval=True)
        log.info('> Checkpoint loaded.')

        log.info('Loading pulse client...')
        self.pulse: pasimple.PaSimple = pasimple.PaSimple(
            direction=pasimple.PA_STREAM_PLAYBACK,
            rate=self.xconfig.audio.output_sample_rate,
            format=pasimple.PA_SAMPLE_S16LE,
            channels=1,
            app_name='Asthralios',
            stream_name='asthralios-test-voice',
        )

    @staticmethod
    def getInstance(config: kizano.Config):
        if LocalXttsContainer._instance is None:
            LocalXttsContainer._instance = LocalXttsContainer(config)
        return LocalXttsContainer._instance

class VoiceHandler(BaseHTTPRequestHandler):
    '''
    Basic class to handle GET requests as text to synthesize and play.
    POST requests accept JSON that can be used to fiddle a few things before synthesizing and playing.
    '''

    def do_GET(self):
        '''
        Handle GET requests.
        '''
        # Get the url decoded path 
        text = urllib.parse.unquote(self.path.lstrip('/'))
        container = LocalXttsContainer.getInstance()

        log.info(f'> Synthesizing text: {text}')
        now = time.time()
        speaker_wav = os.path.join(container.checkpoint_path, 'speaker.wav')
        wav = container.model.synthesize(text, config=container.xconfig, speaker_wav=speaker_wav, language=LANG)
        log.debug(wav.keys())
        log.info(f'> Text synthesized in {time.time() - now:.2f}s.')

        npwav = wav['wav'].astype(np.float32)
        audio = np.array(npwav * (32767.0 / max(0.01, np.max(np.abs(npwav)))), dtype=np.int16)
        audiobin = audio.tobytes()

        if PLAY_AUDIO:
            log.info(f'> Playing audio for {len(audiobin)} samples...')
            container.pulse.write(audiobin)
            container.pulse.drain()
            log.info('Done playing audio.')

        buffer = io.BytesIO()
        wavfile.write(buffer, container.xconfig.audio.sample_rate, audio)
        buffer.seek(0, io.SEEK_END)
        clength = buffer.tell()
        buffer.seek(0, 0)

        self.send_response(200)
        self.send_header('Content-type', 'audio/wav')
        self.send_header('Content-length', clength)
        self.end_headers()
        self.wfile.write(buffer.read())

def main():
    '''
    Assert the speech model works by loading it up and running a test sample through it.
    '''
    log.info('Welcome.')
    config = kizano.getConfig()
    listen_host = config.get('server', {}).get('host', 'localhost')
    listen_port = config.get('server', {}).get('port', 5003)
    LocalXttsContainer.getInstance(config)
    server = HTTPServer((listen_host, listen_port), VoiceHandler)
    log.info(f'Server listening on {listen_host}:{listen_port}.')
    server.serve_forever()
    return 0

if __name__ == '__main__':
    sys.exit(main())
