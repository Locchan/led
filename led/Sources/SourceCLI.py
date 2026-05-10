import json
import os
import socket

from led import config
from led.Interfaces.EventSource import EventSource
from led.router import handle_event


DEFAULT_SOCKET_PATH = "/run/led/cli.sock"


class SourceCLI(EventSource):
    name = "SourceCLI"

    def __init__(self):
        super().__init__()
        from led import utils
        cfg = config.get('sources')[self.name]
        self.socket_path = cfg.get('socket_path', DEFAULT_SOCKET_PATH)
        self.targets = [utils.get_target(t) for t in cfg.get('targets', [])]

    def _listen(self):
        os.makedirs(os.path.dirname(self.socket_path), exist_ok=True)
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.socket_path)
        os.chmod(self.socket_path, 0o660)
        server.listen(8)

        while True:
            conn, _ = server.accept()
            with conn:
                try:
                    data = b''
                    while not data.endswith(b'\n'):
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    payload = json.loads(data.decode('utf-8'))
                    handle_event(self, payload['message'], self.targets)
                    conn.sendall(b'OK\n')
                except Exception as e:
                    conn.sendall(f'ERR {e.__class__.__name__}\n'.encode('utf-8'))

    @classmethod
    def client_send(cls, source_cfg, message):
        path = (source_cfg or {}).get('socket_path', DEFAULT_SOCKET_PATH)
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(5)
        try:
            client.connect(path)
            client.sendall(json.dumps({'message': message}).encode('utf-8') + b'\n')
            response = b''
            while not response.endswith(b'\n'):
                chunk = client.recv(4096)
                if not chunk:
                    break
                response += chunk
            reply = response.decode('utf-8').strip()
            if not reply.startswith('OK'):
                raise RuntimeError(f"daemon replied: {reply or '(no reply)'}")
        finally:
            client.close()
