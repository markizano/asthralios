import asthralios.logger as logger
getLogger = logger.getLogger
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
    entrypoint = cli.Cli()
    cmd, cfg = entrypoint.getCmd()
    return cmd(cfg)

__all__ = ['main', 'getLogger', 'logger', 'getLogger', 'cli', 'senses', 'chat', 'sentinel']
