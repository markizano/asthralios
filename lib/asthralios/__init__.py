import asthralios.logger as logger
getLogger = logger.getLogger
import asthralios.config as config
import asthralios.senses as senses
import asthralios.chat as chat
import asthralios.sentinel as sentinel
import asthralios.cli as cli

def main():
    '''
    Entrypoint: start here.
    '''
    log = logger.getLogger(__name__)
    log.info('Good morning.')
    entrypoint = cli.CliEntrypoint()
    cmd, cfg = entrypoint.getCmd()
    return cmd(cfg)

__all__ = ['main', 'logger', 'getLogger', 'config', 'cli', 'senses', 'chat', 'sentinel']
