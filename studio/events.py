"""
Event emitter for Agent Studio.

Broadcasts events to external listeners (e.g. the Kitchen Visualizer).
No-op when no listeners are connected — zero overhead for CLI-only users.
"""

import json
import time
from dataclasses import dataclass, asdict

try:
    import websockets.sync.client as ws_client
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


@dataclass
class Event:
    type: str
    data: dict
    timestamp: float


class EventEmitter:
    """Optional event bus. Silent no-op if nothing is listening."""

    def __init__(self, ws_url: str = None):
        self._listeners = []
        self._ws = None

        if ws_url and HAS_WEBSOCKETS:
            try:
                self._ws = ws_client.connect(ws_url)
            except Exception:
                self._ws = None

    def on(self, callback):
        """Register an event listener."""
        self._listeners.append(callback)

    def emit(self, event_type: str, data: dict = None):
        """Emit an event. No-op if no listeners and no WebSocket."""
        if not self._listeners and not self._ws:
            return

        event = Event(type=event_type, data=data or {}, timestamp=time.time())

        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass

        if self._ws:
            try:
                self._ws.send(json.dumps(asdict(event)))
            except Exception:
                self._ws = None

    def close(self):
        """Clean up WebSocket connection."""
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None


def console_listener(event: Event):
    """Debug listener that prints events to the terminal."""
    print(f"  [EVENT] {event.type}: {json.dumps(event.data)[:100]}")
