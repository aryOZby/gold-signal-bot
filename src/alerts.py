from __future__ import annotations

import queue
from typing import Optional


class AlertBus:
    def __init__(self) -> None:
        self.q: queue.Queue[tuple[str, Optional[str]]] = queue.Queue()

    def send(self, text: str, file_path: Optional[str] = None) -> None:
        if text or file_path:
            self.q.put((text, file_path))
