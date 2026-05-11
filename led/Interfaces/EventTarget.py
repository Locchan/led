class EventTarget:
    name = None

    def __init__(self, instance_id):
        self.id = instance_id

    def _initialize(self):
        """Validate config and prepare the target. Override in subclasses."""
        pass

    def _send(self, source, message):
        pass

    def send(self, source, message):
        self._send(source, message)
