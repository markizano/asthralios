'''
Command line interface for Asthralios.
This is the main entrypoint for the application.
'''

from dotenv import load_dotenv
load_dotenv()

import asthralios.config as config
# We bootstrap configuration before anything else in the app to ensure env is loaded!
config.Configuration.getInstance()

import os, sys
import argparse
from signal import signal, SIGINT

import kizano
kizano.Config.APP_NAME = 'asthralios'
log = kizano.getLogger(__name__)

import asthralios

ACTIONS = {
    'converse': asthralios.senses.conversate,
    'ingest': asthralios.senses.ingest,
    'chat': asthralios.chat.start_chat,
    'agent': asthralios.chat.start_agent,
    'sentinel': asthralios.sentinel.check_code_quality,
}

def getOptions() -> dict:
    '''
    Parse command line options. Just like ytffmpeg, accept a top-level command that is used if no
    recognized argument is presented.
    '''
    options = argparse.ArgumentParser(description="Asthralios - Markizano's Assistant")
    options.add_argument("--language", type=str, default="en", help="Language to send to the model.")
    options.add_argument("--log-level", metavar='log_level', type=str, default="INFO",
                        help="Verbosity of the logger", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
    options.add_argument('--model', type=str, default="gpt-oss:20b", help="Model to use for the chat")
    options.add_argument('--model-provider', type=str, default="ollama", help="Model provider to use for the chat")
    options.add_argument('--path', type=str, default=".", help="Path to the codebase to check")
    options.add_argument('--output', '-o', type=str, default='-', help="If there's output, where to write.")

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
        log.error(f'Available actions: {list(ACTIONS.keys())}')
        options.print_help()
        raise SystemExit(8)
    return opts.__dict__

def interrupt(signal, frame):
    log.error('Caught ^C interrupt, exiting...')
    sys.exit(signal)

def main():
    '''
    Entrypoint: start here.
    '''
    log.info('Good morning.')
    cfg = asthralios.config.getInstance()
    opts = getOptions()
    # Command line takes precedence over config.
    for name, value in opts.items():
        cfg.config[name] = value
    log.info("Asthralios is waking up...")
    signal(SIGINT, interrupt)
    action = cfg.config.get('action', 'converse')
    return ACTIONS[action](cfg.config)

if __name__ == "__main__":
    sys.exit( main() )
