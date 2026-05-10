class EventTarget:
    name = None

    def __init__(self):
        pass

    def _send(self, source, message):
        pass

    def send(self, source, message):
        self._send(source, message)
