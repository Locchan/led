from led import config
from led.Sources import ENABLED_SOURCES
from led.Targets import ENABLED_TARGETS


_TARGETS = {}


def _by_type(classes):
    return {cls.name: cls for cls in classes}


def get_target(instance_id):
    return _TARGETS[instance_id]


def build_targets():
    classes = _by_type(ENABLED_TARGETS)
    for instance_id, entry in (config.get('targets') or {}).items():
        cls = classes[entry['type']]
        _TARGETS[instance_id] = cls(instance_id, entry)
    return _TARGETS


def build_sources():
    classes = _by_type(ENABLED_SOURCES)
    sources = []
    for instance_id, entry in (config.get('sources') or {}).items():
        cls = classes[entry['type']]
        sources.append(cls(instance_id, entry))
    return sources


def start_listeners(sources):
    threads = []
    for source in sources:
        threads.append(source.start_listener())
    return threads
