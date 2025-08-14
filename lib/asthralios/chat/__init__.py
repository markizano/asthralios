# Imports these names into the current namespace so they are available when imported from here.
import asthralios.config as config
from .my_discord import ChatAdapterDiscord
from .my_slack import ChatAdapterSlack
# from my_msteams import ChatAdapterMSTeams # MS Teams is useless right now. They don't support Python :(

import signal
import multiprocessing
import time
import threading
from typing import List

import kizano
log = kizano.getLogger(__name__)

class ChatManager:
    """
    Manages multiple chat adapters running in separate subprocesses.
    Handles process lifecycle and signal propagation.
    """

    def __init__(self):
        self.processes: List[multiprocessing.Process] = []
        self.running = False
        self.config = config.getInstance()

    def _signal_handler(self, signum, frame):
        """Handle termination signals by stopping all subprocesses."""
        log.info(f"Received signal {signum}, shutting down chat adapters...")
        self.stop()

    def start(self):
        """Start all configured chat adapters in subprocesses."""
        if self.running:
            log.warning("Chat manager is already running")
            return

        self.running = True
        log.info("Starting chat adapters...")

        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGHUP, self._signal_handler)

        # Start Discord adapter
        discord = ChatAdapterDiscord()
        discord_process = multiprocessing.Process(target=discord.start)
        discord_process.start()
        self.processes.append(discord_process)
        log.info(f"Started Discord adapter with PID {discord_process.pid}")

        # Start Slack adapter
        slack = ChatAdapterSlack()
        slack_process = multiprocessing.Process(target=slack.start)
        slack_process.start()
        self.processes.append(slack_process)
        log.info(f"Started Slack adapter with PID {slack_process.pid}")

        # Monitor processes
        self._monitor_processes()

    def _monitor_processes(self):
        """Monitor subprocesses."""
        def monitor():
            while self.running:
                for i, process in enumerate(self.processes[:]):
                    if not process.is_alive():
                        log.info(f"Chat adapter process {process.pid} has terminated")
                        self.processes.pop(i)

                time.sleep(5)

        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()

    def stop(self):
        """Stop all chat adapters and clean up."""
        if not self.running:
            return

        self.running = False
        log.info("Stopping chat adapters...")

        for process in self.processes:
            try:
                process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()
                    process.join()
            except Exception as e:
                log.error(f"Error stopping process {process.pid}: {e}")

        self.processes.clear()
        log.info("All chat adapters stopped")

def start_chat(cfg: dict):
    """Start all configured chat adapters using the unified manager."""
    manager = ChatManager()
    manager.start()

    # Keep the main thread alive to handle signals
    try:
        while manager.running:
            time.sleep(1)
    except KeyboardInterrupt:
        manager.stop()
