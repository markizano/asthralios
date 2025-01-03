#!/usr/bin/python3

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib')))

import pasimple
import numpy as np
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

import kizano
log = kizano.getLogger(__name__)

LANG = os.environ.get('LANGUAGE', 'en')

def main():
    '''
    Assert the speech model works by loading it up and running a test sample through it.
    '''
    log.info('Welcome.')

    log.info('Loading TTS model...')
    log.info('> New TTSv2 Config...')
    xtts_config = XttsConfig()
    home = os.environ.get('HOME', '/home/stable-diffusion')
    text = os.environ.get('MESSAGE', 'Greetings from dallas texas')
    xtts_config.load_json(f"{home}/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2/config.json")
    log.info('> Config loaded.')
    # log.debug(xtts_config.__dict__)

    log.info('> Loading checkpoint...')
    model = Xtts(xtts_config)
    model.load_checkpoint(xtts_config, checkpoint_dir=f"{home}/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2/", eval=True)
    log.info('> Checkpoint loaded.')

    log.info('Loading pulse client...')
    pulse = pasimple.PaSimple(
        direction=pasimple.PA_STREAM_PLAYBACK,
        rate=xtts_config.audio.sample_rate,
        format=pasimple.PA_SAMPLE_S16LE,
        channels=1,
        app_name='Asthralios',
        stream_name='asthralios-test-voice',
    )

    log.info('> Synthesizing text...')
    speaker_wav = f'{home}/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2/speaker.wav'
    wav = model.synthesize(text, config=xtts_config, speaker_wav=speaker_wav, language=LANG)
    log.debug(wav.keys())
    log.info('> Text synthesized.')

    log.info('> Playing audio...')
    npwav = wav['wav'].astype(np.float32)
    audio = np.array(npwav * (32768.0 / max(0.01, np.max(np.abs(npwav)))), dtype=np.int16)
    pulse.write(audio.tobytes())
    log.info('Done.')

    return 0

if __name__ == '__main__':
    sys.exit(main())
