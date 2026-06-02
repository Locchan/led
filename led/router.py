from collections import deque
import socket
import threading
import time

EVENT_CACHE = deque(maxlen=64)

# Aggregation buffer: (source_id, message) → entry dict
_agg_buffer = {}
_agg_lock = threading.Lock()

# Flush after this many seconds of inactivity for a given message
AGG_IDLE_WINDOW = 10
# Force-flush after this many seconds even if messages keep arriving
AGG_MAX_AGE = 300

_hostname = socket.gethostname()

def handle_event(source, message, targets, files=None):
    files = list(files or [])
    # Only aggregate plain-text events; pass file events through immediately
    if not files:
        source_id = getattr(source, 'id', str(source))
        key = (source_id, message)
        now = time.time()
        with _agg_lock:
            if key in _agg_buffer:
                _agg_buffer[key]['count'] += 1
                _agg_buffer[key]['last_time'] = now
            else:
                _agg_buffer[key] = {
                    'source': source,
                    'targets': list(targets),
                    'first_time': now,
                    'last_time': now,
                    'count': 1,
                }
    else:
        EVENT_CACHE.append({
            'source': source,
            'message': message,
            'targets': list(targets),
            'files': files,
            'count': 1,
            'first_time': time.time(),
        })

def _flush_agg_buffer():
    now = time.time()
    with _agg_lock:
        ready = [
            k for k, v in _agg_buffer.items()
            if (now - v['last_time'] >= AGG_IDLE_WINDOW)
            or (now - v['first_time'] >= AGG_MAX_AGE)
        ]
        for key in ready:
            entry = _agg_buffer.pop(key)
            _, message = key
            EVENT_CACHE.append({
                'source': entry['source'],
                'message': message,
                'targets': entry['targets'],
                'files': [],
                'count': entry['count'],
                'first_time': entry['first_time'],
            })

def _format_duration(seconds):
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s" if secs else f"{mins}m"
    else:
        h = int(seconds / 3600)
        m = int((seconds % 3600) / 60)
        return f"{h}h {m}m" if m else f"{h}h"

def _format_message(message, count=1, first_time=None):
    base = f"led alert from {_hostname}:\n{message}"
    if count > 1 and first_time is not None:
        elapsed = time.time() - first_time
        base += f" (x{count} over last {_format_duration(elapsed)})"
    return base

def router():
    while True:
        _flush_agg_buffer()

        if not EVENT_CACHE:
            time.sleep(0.3)
            continue

        event = EVENT_CACHE.popleft()
        source = event['source']
        message = event['message']
        targets = event['targets']
        files = event['files']
        count = event['count']
        first_time = event['first_time']

        formatted = _format_message(message, count, first_time)
        failed_targets = []

        for target in targets:
            try:
                target.send(source, formatted, files)
            except Exception as e:
                print(f"Router failed to send an event to [{target.id}] ({target.name}): {e.__class__.__name__}: {e}")
                failed_targets.append(target)

        if failed_targets:
            EVENT_CACHE.append({
                'source': source,
                'message': message,
                'targets': failed_targets,
                'files': files,
                'count': count,
                'first_time': first_time,
            })
