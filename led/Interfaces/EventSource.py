from threading import Thread


class EventSource:
    name = None

    def __init__(self):
        pass

    def _listen(self):
        pass

    def _initialize(self):
        """Validate config and prepare the source. Override in subclasses."""
        pass

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
