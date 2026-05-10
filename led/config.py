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


def _names(classes):
    return {cls.name for cls in classes}


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("Config root must be a JSON object")

    for key in ('sources', 'targets'):
        if key not in config:
            raise ValueError(f"Config is missing required key: '{key}'")
        if not isinstance(config[key], dict):
            raise ValueError(f"Config key '{key}' must be an object")

    available_sources = _names(ENABLED_SOURCES)
    available_targets = _names(ENABLED_TARGETS)

    for src_name in config['sources']:
        if src_name not in available_sources:
            raise ValueError(
                f"Unknown source '{src_name}'. Available sources: {sorted(available_sources)}"
            )

    for tgt_name in config['targets']:
        if tgt_name not in available_targets:
            raise ValueError(
                f"Unknown target '{tgt_name}'. Available targets: {sorted(available_targets)}"
            )
