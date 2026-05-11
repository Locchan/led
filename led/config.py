import json

from led.Sources import ENABLED_SOURCES
from led.Targets import ENABLED_TARGETS


DEFAULT_CONFIG_PATH = '/etc/led/config.json'

_CONFIG = None


def load_config(path):
    global _CONFIG
    with open(path, 'r', encoding='utf-8') as f:
        _CONFIG = json.load(f)
    return _CONFIG


def get(name, default=None):
    if _CONFIG is None:
        raise RuntimeError("Config has not been loaded. Call load_config() first.")
    return _CONFIG.get(name, default)


def _types(classes):
    return {cls.name for cls in classes}


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("Config root must be a JSON object")

    for key in ('sources', 'targets'):
        if key not in config:
            raise ValueError(f"Config is missing required key: '{key}'")
        if not isinstance(config[key], dict):
            raise ValueError(f"Config key '{key}' must be an object")

    available_sources = _types(ENABLED_SOURCES)
    available_targets = _types(ENABLED_TARGETS)

    for instance_id, entry in config['targets'].items():
        if not isinstance(entry, dict):
            raise ValueError(f"Target '{instance_id}' config must be an object")
        type_ = entry.get('type')
        if not type_:
            raise ValueError(f"Target '{instance_id}' is missing required field 'type'")
        if type_ not in available_targets:
            raise ValueError(
                f"Target '{instance_id}' has unknown type '{type_}'. "
                f"Available target types: {sorted(available_targets)}"
            )

    target_ids = set(config['targets'].keys())

    for instance_id, entry in config['sources'].items():
        if not isinstance(entry, dict):
            raise ValueError(f"Source '{instance_id}' config must be an object")
        type_ = entry.get('type')
        if not type_:
            raise ValueError(f"Source '{instance_id}' is missing required field 'type'")
        if type_ not in available_sources:
            raise ValueError(
                f"Source '{instance_id}' has unknown type '{type_}'. "
                f"Available source types: {sorted(available_sources)}"
            )
        for tref in entry.get('targets', []) or []:
            if tref not in target_ids:
                raise ValueError(
                    f"Source '{instance_id}' references unknown target '{tref}'. "
                    f"Defined targets: {sorted(target_ids)}"
                )
