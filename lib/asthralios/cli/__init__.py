
import os, sys
import argparse
import traceback as tb
import numpy as np
import pasimple

from signal import signal, SIGINT

from faster_whisper import WhisperModel, format_timestamp
from faster_whisper.vad import VadOptions, get_vad_model

import kizano
kizano.Config.APP_NAME = 'asthralios'

log = kizano.getLogger(__name__)

import asthralios.gpt as gpt

FORMAT = pasimple.PA_SAMPLE_S16LE
SAMPLE_WIDTH = pasimple.format2width(FORMAT)
CHANNELS = 1
SAMPLE_RATE = 16000
BYTES_PER_SEC = CHANNELS * SAMPLE_RATE * SAMPLE_WIDTH

global _running
_running = False

def getOptions() -> dict:
    '''
    Parse command line options. Just like ytffmpeg, accept a top-level command that is used if no
    recognized argument is presented.
    '''
    options = argparse.ArgumentParser(description="Asthralios - Markizano's Assistant")
    options.add_argument("--language", type=str, default="en", help="Language of the video")
    options.add_argument("--log-level", metavar='log_level', type=str, default="INFO",
                        help="Verbosity of the logger", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])

    opts, other = options.parse_known_args()
    if not 'LOG_LEVEL' in os.environ:
        os.environ['LOG_LEVEL'] = opts.log_level
        log.setLevel(opts.log_level)
    action = None
    # If any() of the above constant actions is among the unknown arguments, pop it off the list
    # and set the action accordingly.
    # If there is a subsequent resource after the action, assign the resource to the options.
    # while other:
    #     arg = other.pop(0)
    #     if arg in list(Cli.ACTIONS.keys()):
    #         action = arg
    #     else:
    #         opts.resource = arg
    # if action:
    #     opts.action = action
    # else:
    #     log.error('No action specified!')
    #     options.print_help()
    #     return opts.__dict__

    return dict(opts.__dict__)

def print_stream_attrs(stream):
    log.debug(f'  Direction: {stream.direction()}')
    log.debug(f'  Format: {stream.format()}')
    log.debug(f'  Channels: {stream.channels()}')
    log.debug(f'  Rate: {stream.rate()} Hz')
    log.debug(f'  Latency: {stream.get_latency() / 1000} ms')

def interrupt(signal, frame):
    log.error('Caught Ctrl+C, exiting...')
    global _running
    _running = False
    sys.exit(8)

class Ears:
    '''
    This class represents Asthralios' ears.
    Asthralios listens well. He listens to the world around him and tries to understand what is being said.
    
    '''
    def __init__(self, config: dict, model: WhisperModel, stream: pasimple.PaSimple):
        self.config = config
        self.model = model
        self.stream = stream
        self.listen_chunks = 5
        self.vad_options = VadOptions(
            threshold=0.5,
            min_speech_duration_ms=450,
            max_speech_duration_s=float("inf"),
            min_silence_duration_ms=2000,
            window_size_samples=1024,
            speech_pad_ms=250,
        )

    def _next_chunk(self) -> np.ndarray:
        '''
        Read the next chunk of audio from the stream.
        '''
        audio = np.frombuffer( self.stream.read(BYTES_PER_SEC * 2), dtype=np.int16 ).astype(np.float32) / 32768.0
        return audio[~np.isnan(audio) & ~np.isinf(audio)]

    def listen(self) -> np.ndarray:
        '''
        Listen to the stream until silence is detected for 3s.
        '''
        global _running
        result = np.array([]).astype(np.float32)
        audio = self._next_chunk()
        silence = 0 # concurrent number of seconds we hear relative "silence" or speech below threshold
        vad = get_vad_model()
        vad_state = vad.get_initial_state(batch_size=1)
        while silence < 2 and _running:
            speech_prob, vad_state = vad(audio, vad_state, SAMPLE_RATE)
            if speech_prob > self.vad_options.threshold:
                silence = 0 # Reset silence to 0, we heard something.
                result = np.concatenate((result, audio), dtype=np.float32)
            else:
                silence += 1
            audio = self._next_chunk()
        return result

    def toText(self, audio: np.ndarray) -> str:
        '''
        Convert the audio received to text quickly.
        '''
        segments, info = self.model.transcribe(
            audio,
            language=self.config.get('language', 'en'),
            without_timestamps=True,
            word_timestamps=False,
            vad_filter=True,
            vad_parameters=self.vad_options
        )
        log.debug(info)
        return ' '.join([ segment.text for segment in segments ])

def main():
    '''
    entrypoint.
    '''
    import kizano.logger
    log.info('Good morning.')
    kizano.log.setLevel(kizano.logger.logging.CRITICAL)
    config = kizano.getConfig()
    opts = getOptions()
    config = kizano.utils.dictmerge(opts, config)
    log.debug(config)
    log.info("Asthralios is waking up...")
    model = WhisperModel(
        os.getenv('WHISPER_MODEL', 'guillaumekln/faster-whisper-large-v2'),
        device='cuda',
        compute_type='auto',
        cpu_threads=os.cpu_count(),
    )
    stream = pasimple.PaSimple(pasimple.PA_STREAM_RECORD,
        FORMAT,
        CHANNELS,
        SAMPLE_RATE,
        app_name='asthralios',
        stream_name='asthralios-ears',
        maxlength=BYTES_PER_SEC * 2,
        fragsize=BYTES_PER_SEC // 5)
    chat = gpt.localGPT(host='secretum.home.asthralios.net')
    global _running
    _running = True
    signal(SIGINT, interrupt)
    while _running:
        log.info('Asthralios is listening...')
        hearing = Ears(config, model, stream)
        try:
            request = hearing.listen()
            message = hearing.toText(request)
            log.info(f"\x1b[34mRead\x1b[0m: {message}")
            if message:
                response = chat.talk(message)
                log.info(f"last message: {response['message']['content']}") # @FutureFeature: Speak the response.
        except KeyboardInterrupt:
            log.error('Ctrl+C detected... closing my ears ...')
            _running = False
        except RuntimeWarning as rw:
            log.error(f"Model failed: {rw}")
            log.error('Fatal.')
            _running = False
        except Exception as e:
            log.error(f"Sorry, I missed that: {e}")
            log.error(tb.format_exc())

if __name__ == "__main__":
    sys.exit( main() )
