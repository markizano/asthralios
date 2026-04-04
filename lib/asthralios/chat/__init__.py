import time
import asthralios.chat.adapter as adapter
import asthralios.chat.agentic as agentic
import asthralios.chat.manager as manager
import asthralios.chat.my_discord as my_discord
import asthralios.chat.my_slack as my_slack

def start_chat(cfg: dict):
    """Start all configured chat adapters using the unified manager."""
    mgr = manager.ChatManager(cfg)
    mgr.start()

    # Keep the main thread alive to handle signals
    try:
        while mgr.running:
            time.sleep(1)
    except KeyboardInterrupt:
        mgr.stop()

__all__ = [
    'agentic',
    'adapter',
    'manager',
    'my_discord',
    'my_slack',
    'start_chat',
]
