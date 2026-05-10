from threading import Thread


class EventSource:
    name = None

    def __init__(self):
        pass

    def _listen(self):
        pass

    @classmethod
    def client_send(cls, source_cfg, message):
        """Deliver `message` to a running instance of this source.

        Implementations must raise on failure so the CLI can fall back to the
        next configured source.
        """
        raise NotImplementedError(f"{cls.__name__} has no CLI sender")

    def start_listener(self):
        def _run():
            while True:
                try:
                    self._listen()
                except BaseException as e:
                    print(f"Event source {self.__class__.__name__} crashed: {e.__class__.__name__}")

        print(f"Starting listener: {self.__class__.__name__}...")
        thread = Thread(name=self.__class__.__name__, target=_run, daemon=True)
        thread.start()
        return thread
