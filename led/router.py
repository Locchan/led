from collections import deque
import socket
import time

EVENT_CACHE = deque(maxlen=32)

_hostname = socket.gethostname()

def handle_event(source, message, targets, files=None):
    EVENT_CACHE.append((source, message, list(targets), list(files or [])))

def _format_message(message):
    return f"led alert from {_hostname}:\n{message}"

def router():
    while True:
        if not EVENT_CACHE:
            time.sleep(0.3)
            continue

        source, message, targets, files = EVENT_CACHE.popleft()
        formatted = _format_message(message)
        failed_targets = []

        for target in targets:
            try:
                target.send(source, formatted, files)
            except Exception as e:
                print(f"Router failed to send an event to [{target.id}] ({target.name}): {e.__class__.__name__}: {e}")
                failed_targets.append(target)

        if failed_targets:
            EVENT_CACHE.append((source, message, failed_targets, files))
