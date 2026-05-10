import json
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from led import config
from led.Interfaces.EventSource import EventSource
from led.router import handle_event


class SourceHTTP(EventSource):
    name = "SourceHTTP"

    def __init__(self):
        super().__init__()
        from led import utils
        cfg = config.get('sources')[self.name]
        self.port = cfg.get('port', 8080)
        self.targets = [utils.get_target(t) for t in cfg.get('targets', [])]

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

    @classmethod
    def client_send(cls, source_cfg, message):
        port = source_cfg.get('port', 8080)
        url = f"http://127.0.0.1:{port}/event"
        data = json.dumps({'message': message}).encode('utf-8')
        request = urllib.request.Request(
            url, data=data, method='POST',
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
