"""Shared alert helper.

Any code that wants to push a notification through a target should use
`send_alert(target, message, node_name=None)` instead of building its own
message. This guarantees a single, consistent envelope across the whole
codebase:

    led alert from <node_name>:
    <message>
"""
import socket


class _AlertSource:
    """Synthetic source so targets get a sensible label on alerts."""
    name = "alert"
    id = "alert"


_ALERT_SOURCE = _AlertSource()


def send_alert(target, message, node_name=None):
    if node_name is None:
        node_name = socket.gethostname()
    full = f"led alert from {node_name}:\n{message}"
    print(f"Sending an alert: {full!r}")
    try:
        target.send(_ALERT_SOURCE, full)
    except Exception as e:
        print(f"  failed to send alert via [{target.id}] {target.name}: "
              f"{e.__class__.__name__}: {e}")
