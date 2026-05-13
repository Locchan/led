from collections import deque
import time

EVENT_CACHE = deque(maxlen=32)

def handle_event(source, message, targets, files=None):
    EVENT_CACHE.append((source, message, list(targets), list(files or [])))

def router():
    while True:
        if not EVENT_CACHE:
            time.sleep(0.3)
            continue

        source, message, targets, files = EVENT_CACHE.popleft()
        failed_targets = []

        for target in targets:
            try:
                target.send(source, message, files)
            except Exception as e:
                print(f"Router failed to send an event to [{target.id}] ({target.name}): {e.__class__.__name__}: {e}")
                failed_targets.append(target)

        if failed_targets:
            EVENT_CACHE.append((source, message, failed_targets, files))
