
import os, sys
import argparse
import traceback as tb
import numpy as np

from signal import signal, SIGINT

import kizano
kizano.Config.APP_NAME = 'asthralios'

log = kizano.getLogger(__name__)

import asthralios.gpt as gpt
import asthralios.senses.ears as ears

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
    chat = gpt.LocalGPT(host='secretum.home.asthralios.net')
    global _running
    _running = True
    signal(SIGINT, interrupt)
    hearing = ears.LanguageCenter(config)
    while _running:
        log.info('Asthralios is listening...')
        try:
            for query in hearing.listen():
                log.info(f"\x1b[34mRead\x1b[0m: {query}")
                if query:
                    response = chat.talk(query)
                    log.info(f"last message: {response['message']['content']}") # @FutureFeature: Speak the response.
                    chat.speak(response['message']['content'])
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
