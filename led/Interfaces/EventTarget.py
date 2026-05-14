class EventTarget:
    name = None

    def __init__(self, instance_id):
        self.id = instance_id

    def _initialize(self):
        """Validate config and prepare the target. Override in subclasses."""
        pass

    def _send(self, source, message, files=None):
        pass

    def send(self, source, message, files=None):
        self._send(source, message, files or [])
        print(f"  [{self.id}] {self.name}:  Message sent: {message}" + (f", files: {files}" if files else ""))
