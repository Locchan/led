import json
import os
import shutil
import time

from led.Interfaces.EventSource import EventSource
from led.router import handle_event


DEFAULT_MAX_AGE = 24 * 60 * 60


class SourceFiles(EventSource):
    name = "SourceFiles"

    def __init__(self, instance_id, cfg):
        super().__init__(instance_id)
        from led import utils
        self.basedir = cfg.get('basedir')
        self.interval = cfg.get('interval', 5)
        self.max_age = cfg.get('max_age', DEFAULT_MAX_AGE)
        self.targets = [utils.get_target(t) for t in cfg.get('targets', [])]
        self._initialize()

    def _initialize(self):
        if not isinstance(self.basedir, str) or not self.basedir:
            raise ValueError(f"[{self.id}] {self.name}: 'basedir' must be a non-empty string")
        if not isinstance(self.interval, (int, float)) or self.interval <= 0:
            raise ValueError(f"[{self.id}] {self.name}: 'interval' must be a positive number")
        if not isinstance(self.max_age, (int, float)) or self.max_age <= 0:
            raise ValueError(f"[{self.id}] {self.name}: 'max_age' must be a positive number")
        print(f"  [{self.id}] {self.name}: basedir={self.basedir}, "
              f"interval={self.interval}s, max_age={self.max_age}s, "
              f"targets={[t.id for t in self.targets]}")

    def _listen(self):
        os.makedirs(self.basedir, exist_ok=True)
        while True:
            self._cleanup_stale()
            for entry in sorted(os.listdir(self.basedir)):
                if not entry.endswith('.json'):
                    continue
                path = os.path.join(self.basedir, entry)
                if not os.path.isfile(path):
                    continue
                self._process(path)
            time.sleep(self.interval)

    def _process(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            message = payload.get('message', '')
            rel_files = payload.get('files') or []
            files = [os.path.join(self.basedir, p) for p in rel_files]
            handle_event(self, message, self.targets, files)
            shutil.move(path, f"{path}.sent")
        except Exception as e:
            print(f"[{self.id}] {self.name}: failed to process {path}: "
                  f"{e.__class__.__name__}: {e}")
            return

    def _cleanup_stale(self):
        cutoff = time.time() - self.max_age
        for root, _dirs, names in os.walk(self.basedir):
            for n in names:
                p = os.path.join(root, n)
                try:
                    if os.path.getmtime(p) < cutoff:
                        os.remove(p)
                        print(f"[{self.id}] {self.name}: removed stale file {p}")
                except FileNotFoundError:
                    pass
                except OSError as e:
                    print(f"[{self.id}] {self.name}: could not remove stale {p}: "
                          f"{e.__class__.__name__}: {e}")
