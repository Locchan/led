from led.Interfaces.EventTarget import EventTarget


class TargetDummy(EventTarget):
    name = "TargetDummy"

    def __init__(self, instance_id, cfg):
        super().__init__(instance_id)
        self._initialize()

    def _initialize(self):
        print(f"  [{self.id}] {self.name}: ready (writes to stdout)")

    def _send(self, source, message, files=None):
        return True

