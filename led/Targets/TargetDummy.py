from led.Interfaces.EventTarget import EventTarget


class TargetDummy(EventTarget):
    name = "TargetDummy"

    def _initialize(self):
        print(f"  {self.name}: ready (writes to stdout)")

    def _send(self, source, message):
        print(f"Message from {source.name}: {message}")
