import sys

from led import config
from led.Sources import ENABLED_SOURCES


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ('-h', '--help'):
        print("Usage: led_send <message>", file=sys.stderr)
        sys.exit(2)
    message = sys.argv[1]

    config.load_config(config.DEFAULT_CONFIG_PATH)
    sources_cfg = config.get('sources') or {}
    if not sources_cfg:
        print(f"No sources configured in {config.DEFAULT_CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    by_name = {cls.name: cls for cls in ENABLED_SOURCES}
    errors = []
    for src_name, src_cfg in sources_cfg.items():
        cls = by_name.get(src_name)
        if cls is None:
            errors.append(f"{src_name}: not registered in ENABLED_SOURCES")
            continue
        try:
            cls.client_send(src_cfg, message)
            print(f"Sent via {src_name}")
            return
        except Exception as e:
            errors.append(f"{src_name}: {e.__class__.__name__}: {e}")

    print("Failed to send via any configured source:", file=sys.stderr)
    for err in errors:
        print(f"  {err}", file=sys.stderr)
    sys.exit(1)


if __name__ == '__main__':
    main()
