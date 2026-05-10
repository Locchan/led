from led.Interfaces.EventTarget import EventTarget


class DummyTarget(EventTarget):
    name = "DummyTarget"

    def _send(self, source, message):
        print(f"Message from {source.name}: {message}")
