# Imports these names into the current namespace so they are available when imported from here.
from asthralios.config import Configuration
from .my_discord import ChatAdapterDiscord
from .my_slack import ChatAdapterSlack
# from my_msteams import ChatAdapterMSTeams # MS Teams is useless right now. They don't support Python :(

def start_discord(cfg: dict):
    # Local to this namespace so it doesn't get exported.
    from openwebui_client.client import OpenWebUIClient
    config = Configuration.getInstance()
    oui_client = OpenWebUIClient(
        base_url=config.oui_base_url,
        api_key=config.oui_api_key,
        default_model=config.oui_model,
    )
    discord = ChatAdapterDiscord(oui_client)
    discord.start()

def start_slack(cfg: dict):
    # Local to this namespace so it doesn't get exported.
    from openwebui_client.client import OpenWebUIClient
    config = Configuration.getInstance()
    oui_client = OpenWebUIClient(
        base_url=config.oui_base_url,
        api_key=config.oui_api_key,
        default_model=config.oui_model,
    )
    slack = ChatAdapterSlack(oui_client)
    slack.start()

