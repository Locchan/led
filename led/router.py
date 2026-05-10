from collections import deque
import time

EVENT_CACHE = deque(maxlen=32)

def handle_event(source, message, targets):
    EVENT_CACHE.append((source, message, list(targets)))

def router():
    while True:
        if not EVENT_CACHE:
            time.sleep(0.1)
            continue

        source, message, targets = EVENT_CACHE.popleft()
        failed_targets = []

        for target in targets:
            try:
                target.send(source, message)
            except Exception as e:
                print(f"Router failed to send an event to {target}: {e.__class__.__name__}")
                failed_targets.append(target)

        if failed_targets:
            EVENT_CACHE.append((source, message, failed_targets))
