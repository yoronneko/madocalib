# Copyright (C) 2026 Cabinet Office, Japan, All rights reserved.
# Copyright (C) 2026 Lighthouse Technology & Consulting Co. Ltd., All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause
"""Lightweight UI event bus used by the GUI to marshal cross-thread updates.

Design / Threading
------------------
- Single producer/consumer driven by Tk's `after()` on the main UI thread.
- Handlers must be subscribed from the UI thread and are invoked on it.
- Handler exceptions are logged at WARNING level and do not stop the pump.
"""

import logging
import queue
import tkinter as tk
from typing import Any, Callable, Dict, List, Tuple

logger = logging.getLogger(__name__)

_event_queue: "queue.Queue[Tuple[str, dict]]" = queue.Queue()
_subscribers: Dict[str, List[Callable[[dict], None]]] = {}
_root: tk.Misc | None = None
_poll_interval_ms: int = 33
_is_started: bool = False


def post(kind: str, **payload: Any) -> None:
    """Post an event from any thread.

    Args:
        kind (str): Event name.
        **payload: Arbitrary data passed to subscribers.

    Notes:
        Safe for background threads; handlers run on UI thread.

    """
    _event_queue.put((kind, payload))


def subscribe(kind: str, handler: Callable[[dict], None]) -> None:
    """Subscribe a handler to an event kind on the UI event bus.

    Args:
        kind: Event name to subscribe.
        handler: Callable invoked on the GUI thread with the event payload.

    Notes:
        Handlers are called by the periodic pump. Exceptions inside a handler
        are logged and do not stop the pump.

    """
    _subscribers.setdefault(kind, []).append(handler)


def _pump() -> None:
    """Drain queued events and dispatch them to subscribers (UI thread).

    Notes
    -----
    - Non-blocking drain using `get_nowait()` until the queue is empty.
    - Handler exceptions are logged and do not stop the pump.
    - Schedules the next pump via `after()`.

    """
    try:
        while True:
            kind, payload = _event_queue.get_nowait()
            for h in _subscribers.get(kind, []):
                try:
                    h(payload)  # keep UI thread alive even if one handler fails
                except Exception as e:
                    logger.warning(f"handler error({kind}): {e}")
    except queue.Empty:
        # Debug-only; can be very noisy in steady state.
        # logger.debug("eventbus queue empty")
        pass
    if _is_started:
        _root.after(_poll_interval_ms, _pump)


def start(root, interval_ms: int = 33) -> None:
    """Start the UI event pump.

    Args:
        root (Tk): Root window.
        interval_ms (int): Polling interval in ms.

    Notes:
        Must be called only once from the UI thread.

    """
    global _root, _poll_interval_ms, _is_started
    if _is_started:
        return
    _root = root
    _poll_interval_ms = interval_ms
    _is_started = True
    _root.after(_poll_interval_ms, _pump)
