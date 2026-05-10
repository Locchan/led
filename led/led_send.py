import sys

from led import config
from led.Sources.SourceCLI import SourceCLI


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ('-h', '--help'):
        print("Usage: led_send <message>", file=sys.stderr)
        sys.exit(2)
    message = sys.argv[1]

    config.load_config(config.DEFAULT_CONFIG_PATH)
    cli_cfg = (config.get('sources') or {}).get(SourceCLI.name, {})
    try:
        SourceCLI.client_send(cli_cfg, message)
    except Exception as e:
        print(f"Failed to send: {e.__class__.__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    print("OK")


if __name__ == '__main__':
    main()
