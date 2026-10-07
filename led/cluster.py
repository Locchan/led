"""Clustering: HTTPS ping/handshake between cluster members.

All clustering state and threads live in this module. The daemon's main code
only calls `start_if_configured(cfg, get_target)`.
"""
import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from led.alerts import send_alert

try:
    from importlib.metadata import version as _pkg_version
    LED_VERSION = _pkg_version('led')
except Exception:
    LED_VERSION = 'unknown'


PING_INTERVAL_SEC = 60
ALERT_REPEAT_SEC = 3600
CERT_DAYS = 27000  # ~74 years, well past 2100
MINUTES_PER_DAY = 24 * 60
_SKIP_PERIOD_RE = re.compile(r'^(\d{2}):(\d{2}):(\d+)$')

DEFAULTS = {
    'cluster_master': False,
    'cluster_member_down_alert_min': 5,
    'cluster_verify_tls': True,
    'cluster_tls_dir': '/etc/led/tls',
    'cluster_connectivity_skip': {},
}


def _parse_skip_windows(member, value):
    """Parse one member's `HH:MM:minutes` windows into (start, duration) pairs."""
    if not isinstance(value, list):
        raise ValueError(
            f"cluster: cluster_connectivity_skip['{member}'] must be a list of "
            f"'HH:MM:minutes' strings"
        )
    periods = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(
                f"cluster: invalid cluster_connectivity_skip entry {item!r} for '{member}'; "
                f"expected 'HH:MM:minutes'"
            )
        match = _SKIP_PERIOD_RE.match(item)
        if not match:
            raise ValueError(
                f"cluster: invalid cluster_connectivity_skip entry {item!r} for '{member}'; "
                f"expected 'HH:MM:minutes'"
            )
        hour, minute, duration = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if hour > 23 or minute > 59:
            raise ValueError(
                f"cluster: invalid cluster_connectivity_skip entry {item!r} for '{member}'; "
                f"HH must be 00-23 and MM must be 00-59"
            )
        if duration < 1:
            raise ValueError(
                f"cluster: invalid cluster_connectivity_skip entry {item!r} for '{member}'; "
                f"period minutes must be at least 1"
            )
        periods.append((hour * 60 + minute, duration))
    return periods


def _parse_connectivity_skip(value):
    """Parse `cluster_connectivity_skip` into {member: [(start_minute, duration), ...]}.

    Each member maps to `HH:MM:minutes` windows: checks against that member
    are not done from local HH:MM for `minutes` minutes. Other members are
    still checked. Windows may cross midnight.
    """
    if not isinstance(value, dict):
        raise ValueError(
            "cluster: 'cluster_connectivity_skip' must be an object mapping a member "
            "name to a list of 'HH:MM:minutes' strings"
        )
    parsed = {}
    for member, windows in value.items():
        if not isinstance(member, str) or not member:
            raise ValueError(
                "cluster: cluster_connectivity_skip member names must be non-empty strings"
            )
        parsed[member] = _parse_skip_windows(member, windows)
    return parsed


def _connectivity_checks_skipped(periods, now):
    """True when local time `now` falls inside a configured skip window."""
    if not periods:
        return False
    local = time.localtime(now)
    minute_of_day = local.tm_hour * 60 + local.tm_min
    for start, duration in periods:
        if duration >= MINUTES_PER_DAY:
            return True
        end = start + duration
        if minute_of_day >= start and minute_of_day < end:
            return True
        if end > MINUTES_PER_DAY and minute_of_day < (end - MINUTES_PER_DAY):
            return True
    return False


def _ensure_certs(tls_dir):
    """Make sure fullchain.pem + privkey.pem exist in `tls_dir`.

    File names match letsencrypt's live/<domain>/ layout so the user can
    point `cluster_tls_dir` directly at a real certbot dir if they have one.
    """
    fullchain = os.path.join(tls_dir, 'fullchain.pem')
    privkey = os.path.join(tls_dir, 'privkey.pem')
    if os.path.exists(fullchain) and os.path.exists(privkey):
        return fullchain, privkey

    os.makedirs(tls_dir, exist_ok=True)
    print(f"  cluster: no TLS certs found in {tls_dir}, generating self-signed (valid until ~2100)")
    subprocess.run(
        ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
         '-keyout', privkey, '-out', fullchain,
         '-days', str(CERT_DAYS), '-subj', '/CN=led-cluster'],
        check=True, capture_output=True,
    )
    os.chmod(privkey, 0o600)
    shutil.copy(fullchain, os.path.join(tls_dir, 'cert.pem'))
    open(os.path.join(tls_dir, 'chain.pem'), 'w').close()
    print("  cluster: WARNING TLS certs are SELF-SIGNED; peers must set cluster_verify_tls=false")
    return fullchain, privkey


class Cluster:
    def __init__(self, cfg, alert_target):
        self.members = dict(cfg['cluster_members'])
        self.is_master = self._with_default(cfg, 'cluster_master')
        self.port = cfg['cluster_port']
        self.down_min = self._with_default(cfg, 'cluster_member_down_alert_min')
        self.cluster_id = cfg['cluster_id']
        self.verify_tls = self._with_default(cfg, 'cluster_verify_tls')
        self.tls_dir = self._with_default(cfg, 'cluster_tls_dir')
        skip_raw = self._with_default(cfg, 'cluster_connectivity_skip')
        self.skip_periods = _parse_connectivity_skip(skip_raw)
        unknown = sorted(name for name in self.skip_periods if name not in self.members)
        if unknown:
            raise ValueError(
                "cluster: cluster_connectivity_skip names unknown members: "
                + ', '.join(unknown)
            )
        self.alert_target = alert_target
        self.hostname = socket.gethostname()
        self.auth_hash = hashlib.sha256(self.cluster_id.encode('utf-8')).hexdigest()

        self.self_name = self.hostname if self.hostname in self.members else None
        if self.self_name is None:
            print(
                f"  cluster: WARNING our hostname '{self.hostname}' is not in cluster_members; "
                f"cannot self-identify — every member will be pinged including ourselves"
            )

        self.lock = threading.Lock()
        self.last_master_ping = time.time()
        self.last_slave_pings = {}
        self.last_alerted_at = {}
        self.master_name = None
        self.version_alerted = False
        self._stop = threading.Event()
        self._stopped = False
        self._httpd = None
        self._server_thread = None
        self._watcher_thread = None
        self._skipping_peers = set()

        if not self.verify_tls:
            print("  cluster: WARNING cluster_verify_tls=false — peer certificates are NOT verified")
        if self.skip_periods:
            shown = ', '.join(
                f"{name} ({', '.join(skip_raw[name])})" for name in self.skip_periods
            )
            print(f"  cluster: connectivity checks skipped for: {shown}")

    @staticmethod
    def _with_default(cfg, key):
        if key in cfg:
            return cfg[key]
        default = DEFAULTS[key]
        print(f"  cluster: '{key}' not set, using default: {default!r}")
        return default

    def _self_payload(self):
        return {
            'version': LED_VERSION,
            'mode': 'master' if self.is_master else 'slave',
            'hostname': self.hostname,
        }

    def _alert(self, message):
        send_alert(self.alert_target, message, node_name=self.self_name or self.hostname)

    def _ssl_client_ctx(self):
        ctx = ssl.create_default_context()
        if not self.verify_tls:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _request(self, method, addr, path, body=None):
        host, _, port_s = addr.rpartition(':')
        if not port_s:
            host, port_s = addr, str(self.port)
        port = int(port_s)
        conn = http.client.HTTPSConnection(host, port, context=self._ssl_client_ctx(), timeout=5)
        try:
            headers = {'X-Cluster-Auth': self.auth_hash}
            data = None
            if body is not None:
                headers['Content-Type'] = 'application/json'
                data = json.dumps(body)
            conn.request(method, path, body=data, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            return json.loads(raw) if raw else None
        finally:
            conn.close()

    def _do_handshakes(self):
        saw_other_master = False
        for name, addr in self.members.items():
            if name == self.self_name:
                continue
            print(f"Sending handshake to {name} ({addr}).")
            try:
                resp = self._request('POST', addr, '/handshake', self._self_payload())
            except Exception as e:
                print(f"  handshake to {name} failed: {e.__class__.__name__}: {e}")
                continue
            print(f"  handshake response from {name}: {resp}")
            if not isinstance(resp, dict):
                continue
            if resp.get('mode') == 'master':
                self.master_name = name
                if self.is_master:
                    saw_other_master = True
            if (
                self.is_master
                and resp.get('version') != LED_VERSION
                and not self.version_alerted
            ):
                self._alert(
                    f"cluster version mismatch with {name}: "
                    f"master={LED_VERSION} vs {resp.get('version')!r}"
                )
                self.version_alerted = True

        if self.is_master and saw_other_master:
            self._alert(f"Refusing to start on {self.hostname}: there's another master in the cluster.")
            os._exit(1)

    def _on_handshake_received(self, payload):
        host = payload.get('hostname', '?')
        mode = payload.get('mode', '?')
        print(f"Got a handshake from {host}: {payload}")
        if mode == 'master':
            for name, addr in self.members.items():
                if name == host or addr.rsplit(':', 1)[0] == host:
                    self.master_name = name
                    return
            self.master_name = host

    def _on_ping_received(self):
        with self.lock:
            self.last_master_ping = time.time()

    def _maybe_alert_down(self, name, last_ping, now):
        last_alert = self.last_alerted_at.get(name)
        if last_alert is not None and (now - last_alert) < ALERT_REPEAT_SEC:
            return
        when = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_ping))
        self._alert(f"Lost communication with node '{name}'. Last successful ping was at '{when}'")
        self.last_alerted_at[name] = now

    def _peer_periods(self, name):
        if not name:
            return ()
        return self.skip_periods.get(name, ())

    def _note_skip(self, name, skipping, now):
        """Track a per-peer skip window. Reset that peer's clock when it ends."""
        if skipping:
            if name not in self._skipping_peers:
                print(f"  cluster: connectivity checks paused for {name}")
                self._skipping_peers.add(name)
            return True
        if name in self._skipping_peers:
            print(f"  cluster: connectivity checks resumed for {name}")
            self._skipping_peers.discard(name)
            with self.lock:
                self.last_slave_pings[name] = now
                self.last_alerted_at.pop(name, None)
                if name == self.master_name:
                    self.last_master_ping = now
        return False

    def _watcher(self):
        threshold = self.down_min * 60
        while not self._stop.is_set():
            if self._stop.wait(PING_INTERVAL_SEC):
                return
            now = time.time()
            if self.is_master:
                for name, addr in self.members.items():
                    if name == self.self_name:
                        continue
                    skipped = _connectivity_checks_skipped(self._peer_periods(name), now)
                    if self._note_skip(name, skipped, now):
                        continue
                    try:
                        self._request('GET', addr, '/ping')
                        with self.lock:
                            self.last_slave_pings[name] = now
                            self.last_alerted_at.pop(name, None)
                    except Exception as e:
                        print(f"  cluster: ping to {name} ({addr}) failed: {e.__class__.__name__}: {e}")
                        last = self.last_slave_pings.get(name, now)
                        if now - last >= threshold:
                            self._maybe_alert_down(name, last, now)
            else:
                master = self.master_name
                skipped = _connectivity_checks_skipped(self._peer_periods(master), now)
                if master and self._note_skip(master, skipped, now):
                    continue
                with self.lock:
                    last = self.last_master_ping
                if now - last >= threshold:
                    self._maybe_alert_down(master or 'master', last, now)

    def _make_server(self):
        cluster = self

        class Handler(BaseHTTPRequestHandler):
            def _auth_ok(self):
                return self.headers.get('X-Cluster-Auth', '') == cluster.auth_hash

            def do_GET(self):
                if self.path == '/ping' and self._auth_ok():
                    cluster._on_ping_received()
                    body = b'{"ping": "pong"}'
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(403)
                self.end_headers()

            def do_POST(self):
                if self.path == '/handshake' and self._auth_ok():
                    length = int(self.headers.get('Content-Length', 0))
                    try:
                        payload = json.loads(self.rfile.read(length))
                    except Exception:
                        self.send_response(400)
                        self.end_headers()
                        return
                    cluster._on_handshake_received(payload)
                    body = json.dumps(cluster._self_payload()).encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(403)
                self.end_headers()

            def log_message(self, fmt, *args):
                return

        fullchain, privkey = _ensure_certs(self.tls_dir)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(fullchain, privkey)
        httpd = HTTPServer(('0.0.0.0', self.port), Handler)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        return httpd

    def start(self):
        mode = 'master' if self.is_master else 'slave'
        print(f"  cluster: starting on port {self.port}, mode={mode}, members={list(self.members)}")
        httpd = self._make_server()
        self._httpd = httpd
        self._server_thread = threading.Thread(
            target=httpd.serve_forever, name="cluster-server", daemon=True,
        )
        self._server_thread.start()
        # Give the server a beat to actually be listening before we handshake peers.
        time.sleep(0.2)
        self._do_handshakes()
        self._watcher_thread = threading.Thread(
            target=self._watcher, name="cluster-watcher", daemon=True,
        )
        self._watcher_thread.start()

    def stop(self):
        """Stop the HTTPS server and the connectivity watcher."""
        if self._stopped:
            return
        self._stopped = True
        self._stop.set()
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
            try:
                self._httpd.server_close()
            except Exception:
                pass
        if self._server_thread is not None:
            self._server_thread.join(timeout=2)
        if self._watcher_thread is not None:
            self._watcher_thread.join(timeout=2)


def start_if_configured(cfg, get_target):
    """If cluster_members is present in `cfg`, build and start a Cluster.

    `get_target(instance_id)` resolves a target id to its instance. Raises
    ValueError on missing required cluster fields or a bad alert target id.
    """
    members = cfg.get('cluster_members')
    if not members:
        return None
    for required in ('cluster_port', 'cluster_id', 'cluster_state_alert_target'):
        if required not in cfg:
            raise ValueError(f"cluster: missing required field '{required}'")
    alert_target_id = cfg['cluster_state_alert_target']
    try:
        alert_target = get_target(alert_target_id)
    except KeyError:
        raise ValueError(
            f"cluster: cluster_state_alert_target '{alert_target_id}' "
            f"does not match any configured target"
        )
    cluster = Cluster(cfg, alert_target)
    cluster.start()
    return cluster
