from led import config
from led.Sources import ENABLED_SOURCES
from led.Targets import ENABLED_TARGETS


_TARGETS = {}


def _by_name(classes):
    return {cls.name: cls for cls in classes}


def get_target(name):
    return _TARGETS[name]


def _build_targets():
    available = _by_name(ENABLED_TARGETS)
    for tgt_name in config.get('targets') or {}:
        _TARGETS[tgt_name] = available[tgt_name]()


def start_listeners():
    _build_targets()
    available = _by_name(ENABLED_SOURCES)
    threads = []
    for src_name in config.get('sources') or {}:
        instance = available[src_name]()
        threads.append(instance.start_listener())
    return threads
