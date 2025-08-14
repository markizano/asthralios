import asthralios.config as config
# We bootstrap configuration before anything else in the app to ensure env is loaded!
config.Configuration.getInstance()

import os, sys
import argparse
from signal import signal, SIGINT

import kizano
kizano.Config.APP_NAME = 'asthralios'
log = kizano.getLogger(__name__)

import asthralios.senses.ears as ears
import asthralios.senses.hands as hands
import asthralios.chat as chat

ACTIONS = {
    'converse': ears.conversate,
    'ingest': hands.ingest,
    'discord': chat.start_discord,
    'slack': chat.start_slack,
}

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
    while other:
        arg = other.pop(0)
        if arg in list(ACTIONS.keys()):
            action = arg
        else:
            if hasattr(opts, 'resources'):
                opts.resources.append(arg)
            else:
                opts.resources = [arg]
    if action:
        opts.action = action
    else:
        log.error('No action specified!')
        options.print_help()
        return opts.__dict__
    return opts.__dict__

def interrupt(signal, frame):
    log.error('Caught ^C interrupt, exiting...')
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
    signal(SIGINT, interrupt)
    action = config.get('action', 'converse')
    return ACTIONS[action](config)

if __name__ == "__main__":
    sys.exit( main() )
