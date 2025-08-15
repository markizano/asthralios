'''
Main configuration object.
Loads configuration from YAML and creates a giant key-value pair assignment of all configurables.
'''
import kizano
from easydict import EasyDict
kizano.Config.APP_NAME = 'asthralios'

class Configuration(object):

    _instance = None

    @staticmethod
    def getInstance():
        if not Configuration._instance:
            Configuration._instance = Configuration()
        return Configuration._instance

    def __init__(self):
        import kizano.logger
        kizano.log.setLevel(kizano.logger.logging.CRITICAL)
        self.config = EasyDict(kizano.getConfig())

    # Method to return any config.some_key as a magic return.
    def __getattr__(self, name):
        """
        Magic method to return any config value dynamically.
        Allows access like config.oui.base_url instead of config.config['oui']['base_url']
        Supports dot notation for nested configuration access using EasyDict.
        """
        if name in self.config:
            return self.config[name]
        raise AttributeError(f"Configuration has no attribute '{name}'")

def getInstance() -> Configuration:
    return Configuration.getInstance()
