import sys

from led import config
from led.Sources.SourceCLI import SourceCLI


def _find_cli_source():
    for instance_id, entry in (config.get('sources') or {}).items():
        if entry.get('type') == SourceCLI.name:
            return instance_id, entry
    return None, None


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ('-h', '--help'):
        print("Usage: led_send <message>", file=sys.stderr)
        sys.exit(2)
    message = sys.argv[1]

    config.load_config(config.DEFAULT_CONFIG_PATH)
    instance_id, cli_cfg = _find_cli_source()
    if cli_cfg is None:
        print(
            f"No SourceCLI instance configured in {config.DEFAULT_CONFIG_PATH}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        SourceCLI.client_send(cli_cfg, message)
    except Exception as e:
        print(f"Failed to send via [{instance_id}]: {e.__class__.__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"OK (sent via [{instance_id}])")


if __name__ == '__main__':
    main()
