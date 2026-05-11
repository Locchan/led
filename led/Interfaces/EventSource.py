from threading import Thread


class EventSource:
    name = None

    def __init__(self, instance_id):
        self.id = instance_id

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
                    print(f"Event source [{self.id}] {self.name} crashed: {e.__class__.__name__}: {e}")

        print(f"  starting listener: [{self.id}] {self.name}")
        thread = Thread(name=f"{self.name}:{self.id}", target=_run, daemon=True)
        thread.start()
        return thread
