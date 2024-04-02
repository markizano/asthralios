#!/usr/bin/python3

import sys, os
import pasimple
import numpy as np
from TTS.api import TTS
import torch
import urllib3
import kizano

log = kizano.getLogger(__name__)
local = bool(os.environ.get('LOCAL', None))
where = 'local' if local else 'remote'

def main():
    '''
    Open a connection to Pulse for playback.
    Open a connection to TTS.
    Generate a "welcome" message. Allow env var to override the text.
    Push the playback directly to the speakers.
    Assert this can be done with dynamic input.
    '''
    log.info('Welcome.')

    log.info('Opening a connection to Pulse for playback...')
    stream = pasimple.PaSimple(
        direction=pasimple.PA_STREAM_PLAYBACK,
        rate=48000,
        format=pasimple.PA_SAMPLE_S16LE,
        channels=1,
        app_name='Asthralios',
        stream_name='asthralios-test-voice',
    )
    log.info('Done connecting to Pulseaudio.')

    text = os.environ.get('WELCOME_MESG', 'Welcome to Asthralios. I am your voice assistant.')
    log.info(f'Opening a connection to {where} TTS...')
    #tts = TTS("tts_models/en/multi-dataset/tortoise-v2").to("cpu", dtype=np.float32)
    if local:
        tts = TTS("tts_models/en/jenny/jenny").to(device=torch.device('cpu'))
    else:
        request = urllib3.PoolManager()
        response = request.request('GET', 'http://secretum:5002/api/tts', fields={'text': text})
    log.info('Done connecting to TTS.')

    log.info('Generating a welcome message...')
    if local:
        wav = tts.tts(text, speed=1.0, split_sentences=True)
    else:
        # The response back will be audio/wav, so be prepared to play this directly.
        wav = np.frombuffer(response.data, dtype=np.float32)
    log.info(f'Done generating welcome message. Length: {len(wav)} samples.')

    log.info('Playing the welcome message...')
    if local:
        npwav = np.array(wav, dtype=np.float32)
        audio = np.array(npwav * (32768 / max(0.01, np.max(np.abs(npwav)))), dtype=np.int16)
    else:
        audio = wav
    log.info(f'Audio length: {len(audio)} samples.')
    # Play wav using the pasimple output module
    stream.write(audio.tobytes())
    log.info('Complete.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
