from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from model_gateway.config import Settings
from model_gateway.database import list_runnable_dispatches, recover_interrupted_dispatches
from model_gateway.dispatch import dispatch_model_to_vehicle


@dataclass
class DispatchWorker:
    settings: Settings
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        recover_interrupted_dispatches(self.settings.db_path, stuck_seconds=self.settings.stuck_dispatch_seconds)
        self.thread = threading.Thread(target=self.run, name="deepracer-dispatch-worker", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=5)

    def run(self) -> None:
        while not self.stop_event.is_set():
            did_work = False
            for dispatch_id in list_runnable_dispatches(self.settings.db_path):
                did_work = True
                dispatch_model_to_vehicle(self.settings, dispatch_id)
            if not did_work:
                time.sleep(max(1, self.settings.dispatch_worker_poll_seconds))
