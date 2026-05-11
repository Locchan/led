import argparse
import os
import signal

from led import config, utils
from led.router import router


def _parse_args():
    parser = argparse.ArgumentParser(description="Locchan's Event Daemon")
    parser.add_argument(
        '--config',
        default=config.DEFAULT_CONFIG_PATH,
        help=f"Path to JSON config file (default: {config.DEFAULT_CONFIG_PATH})",
    )
    return parser.parse_args()


def _install_signal_handlers():
    def _kill(signum, frame):
        os._exit(128 + signum)

    handled = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, 'SIGBREAK'):
        handled.append(signal.SIGBREAK)
    if hasattr(signal, 'SIGHUP'):
        handled.append(signal.SIGHUP)
    if hasattr(signal, 'SIGQUIT'):
        handled.append(signal.SIGQUIT)
    for s in handled:
        signal.signal(s, _kill)


def main():
    args = _parse_args()
    cfg = config.load_config(args.config)
    config.validate_config(cfg)
    _install_signal_handlers()

    utils.build_targets()
    sources = utils.build_sources()

    from led import cluster
    cluster.start_if_configured(cfg, utils.get_target)

    utils.start_listeners(sources)
    router()


if __name__ == '__main__':
    main()
