
import os, sys
import argparse
import json
import traceback as tb
import numpy as np
import pasimple

# from asthralios.asr.asr_factory import ASRFactory
# from asthralios.vad.vad_factory import VADFactory

from signal import signal, SIGINT

from faster_whisper import WhisperModel
from faster_whisper.vad import VadOptions

import kizano
kizano.Config.APP_NAME = 'asthralios'

log = kizano.getLogger(__name__)

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
    log.info('Caught Ctrl+C, exiting...')
    global _running
    _running = False
    sys.exit(8)

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
    model = WhisperModel(os.getenv('WHISPER_MODEL', 'guillaumekln/faster-whisper-large-v2'), device='cuda', compute_type='auto')
    listen_chunks = 3 # Number of seconds to record in chunks.
    stream_rec = pasimple.PaSimple(pasimple.PA_STREAM_RECORD,
        FORMAT,
        CHANNELS,
        SAMPLE_RATE,
        app_name='asthralios',
        stream_name='asthralios-ears',
        maxlength=BYTES_PER_SEC * 2,
        fragsize=BYTES_PER_SEC // 5)
    global _running
    _running = True
    signal(SIGINT, interrupt)
    while _running:
        log.info('Asthralios is listening...')
        try:
            audio = np.frombuffer( stream_rec.read(BYTES_PER_SEC * listen_chunks), dtype=np.float32 )
            clean_audio = audio[~np.isnan(audio) & ~np.isinf(audio)]
            vad_options = VadOptions(
                threshold=0.8,
                min_speech_duration_ms=450,
                max_speech_duration_s=float("inf"),
                min_silence_duration_ms=3000,
                window_size_samples=1024,
                speech_pad_ms=250,
            )
            log.debug(json.dumps({
                'audio.shape': clean_audio.shape,
                'audio.dtype': clean_audio.dtype,
                'audio.size': clean_audio.size,
                'audio.itemsize': clean_audio.itemsize,
                'audio.nbytes': clean_audio.nbytes,
                'isnan': np.any(np.isnan(clean_audio)),
                'isinf': np.any(np.isinf(clean_audio))
            }, indent=2, default=str))
            segments, info = model.transcribe(
                clean_audio,
                language=config.get('language', 'en'),
                without_timestamps=True,
                word_timestamps=False,
                vad_filter=True,
                vad_parameters=vad_options
            )
            log.debug(f"Transcription Info: {info}")
            message = ''
            for segment in segments:
                log.debug(segment)
                message += segment.text
            log.info(f"Read: {message}")
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
