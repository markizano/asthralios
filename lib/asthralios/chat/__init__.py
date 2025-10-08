import time
from asthralios.chat.agentic import start_agent
from asthralios.chat.manager import ChatManager

def start_chat(cfg: dict):
    """Start all configured chat adapters using the unified manager."""
    manager = ChatManager(cfg)
    manager.start()

    # Keep the main thread alive to handle signals
    try:
        while manager.running:
            time.sleep(1)
    except KeyboardInterrupt:
        manager.stop()

__all__ = ['start_chat', 'start_agent']
