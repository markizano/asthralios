'''
Main configuration object.
Loads dotenv and creates a giant key-value pair assignment of all configurables.
'''

import os
from dotenv import load_dotenv

class Configuration(object):

    _instance = None

    @staticmethod
    def getInstance():
        if not Configuration._instance:
            Configuration._instance = Configuration()
        return Configuration._instance

    def __init__(self):
        load_dotenv()
        self.config = {}
        self.loadenv()

    # Method to return any config.some_key as a magic return.
    def __getattr__(self, name):
        """
        Magic method to return any config value dynamically.
        Allows access like config.oui_base_url instead of config.config['oui_base_url']
        """
        if name in self.config:
            return self.config[name]
        raise AttributeError(f"Configuration has no attribute '{name}'")

    def loadenv(self):
        self.config = {
            # If True, must @ bot for it to respond. If False, it will respond to anything but itself.
            'chat_must_mention': os.getenv('CHAT_MUST_MENTION', ''),
            'chat_context': int(os.getenv('CHAT_CONTEXT', '5')),

            # Open WebUI Configurations
            'oui_base_url': os.getenv('OUI_BASE_URL', 'http://localhost:3000/api'),
            'oui_api_key': os.getenv('OUI_API_KEY', ''),
            'oui_model': os.getenv('OUI_MODEL', 'gpt-5'),
            'oui_system_prompt_file': os.getenv('OUI_SYSTEM_PROMPT_FILE', 'system-prompt.md'),

            # Slack Configuration
            'slack_bot_token': os.getenv('SLACK_BOT_TOKEN', ''),
            'slack_app_token': os.getenv('SLACK_APP_TOKEN', ''),

            'discord_bot_token': os.getenv('DISCORD_BOT_TOKEN', ''),
        }

def getInstance() -> Configuration:
    return Configuration.getInstance()
