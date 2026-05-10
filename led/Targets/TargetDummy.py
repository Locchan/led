from led.Interfaces.EventTarget import EventTarget


class DummyTarget(EventTarget):
    name = "DummyTarget"

    def _initialize(self):
        print(f"  {self.name}: ready (writes to stdout)")

    def _send(self, source, message):
        print(f"Message from {source.name}: {message}")
