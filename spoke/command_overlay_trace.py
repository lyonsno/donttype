"""Opt-in trace breadcrumbs for assistant overlay gesture debugging."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import threading


def record_command_overlay_trace(event: str, **details) -> None:
    path_text = os.environ.get("SPOKE_COMMAND_OVERLAY_TRACE_PATH", "").strip()
    if not path_text:
        return
    payload = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "event": event,
        "pid": os.getpid(),
        "thread": threading.current_thread().name,
    }
    payload.update({key: value for key, value in details.items() if value is not None})
    try:
        path = Path(path_text).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except Exception:
        return
