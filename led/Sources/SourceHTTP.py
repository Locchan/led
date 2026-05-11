import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from led.Interfaces.EventSource import EventSource
from led.router import handle_event


class SourceHTTP(EventSource):
    name = "SourceHTTP"

    def __init__(self, instance_id, cfg):
        super().__init__(instance_id)
        from led import utils
        self.port = cfg.get('port', 8080)
        self.targets = [utils.get_target(t) for t in cfg.get('targets', [])]
        self._initialize()

    def _initialize(self):
        if not isinstance(self.port, int) or not (0 < self.port < 65536):
            raise ValueError(f"[{self.id}] {self.name}: 'port' must be an integer in 1..65535")
        print(f"  [{self.id}] {self.name}: port={self.port}, targets={[t.id for t in self.targets]}")

    def _listen(self):
        source_instance = self

        class EventHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path == '/event':
                    content_length = int(self.headers.get('Content-Length', 0))
                    try:
                        data = json.loads(self.rfile.read(content_length))
                        if 'message' in data:
                            handle_event(source_instance, data['message'], source_instance.targets)
                            self.send_response(200)
                            self.end_headers()
                            return
                    except (json.JSONDecodeError, KeyError):
                        pass

                self.send_response(400)
                self.end_headers()

            def log_message(self, format, *args):
                return

        server = HTTPServer(('0.0.0.0', self.port), EventHandler)
        server.serve_forever()
