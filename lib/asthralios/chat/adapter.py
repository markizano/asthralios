'''
Abstract Interface to describe the main methods any derived class should implement.

Describes a common unified interface such that all the chat apps can combine
themselves into this class instance.

'''

import openwebui_client.client as oui


class ChatAdapter(object):
    def __init__(self, oui_client: oui.OpenWebUIClient):
        self.oui_client = oui_client
        self.init()

    def init(self):
        raise NotImplemented(__name__)

    def onMessageReceived(self, message):
        raise NotImplemented(__name__)

    def onMessageSent(self, message):
        raise NotImplemented(__name__)
