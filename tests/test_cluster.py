"""Cluster tests.

Spins up a real master and slave (HTTPS, self-signed TLS) and exercises
handshakes, authenticated pings, down alerts, version and master conflicts,
certificate setup, and connectivity skip windows.

Run with: python -m unittest discover -s tests -v

Passing tests stay quiet: stdout and stderr from a test are discarded.
They are printed only when that test fails.
"""
import http.client
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import HTTPServer
from unittest import mock

from led.cluster import (
    LED_VERSION,
    Cluster,
    _connectivity_checks_skipped,
    _ensure_certs,
    _parse_connectivity_skip,
    start_if_configured,
)

# Watcher cadence and silence threshold used by the live nodes. 0.02 minutes
# is 1.2s, long enough that one missed tick is not an outage.
PING_INTERVAL = 0.1
ALERT_REPEAT = 2.0
DOWN_MIN = 0.02
CLUSTER_ID = 'test-secret'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _buffer_passing_output():
    """Show each test and 'ok'. Keep prints only in the failure report."""
    runner = unittest.TextTestRunner
    run = runner.run
    if getattr(run, '_led_buffers', False):
        return

    def run_buffered(self, test):
        self.buffer = True
        if self.verbosity < 2:
            self.verbosity = 2
        return run(self, test)

    run_buffered._led_buffers = True
    runner.run = run_buffered

    # unittest already attaches captured output to the failure. Skip the
    # second copy it would write to the real stdout when the test ends.
    result_cls = unittest.TextTestResult
    restore = result_cls._restoreStdout

    def restore_without_echo(self):
        echo = self._mirrorOutput
        self._mirrorOutput = False
        try:
            restore(self)
        finally:
            self._mirrorOutput = echo

    result_cls._restoreStdout = restore_without_echo

    def short_description(self, test):
        parent = getattr(test, 'test_case', None)
        if parent is not None and hasattr(test, '_subDescription'):
            return f"{parent._testMethodName} {test._subDescription()}"
        return getattr(test, '_testMethodName', None) or str(test)

    result_cls.getDescription = short_description


_buffer_passing_output()


class RecordingTarget:
    def __init__(self):
        self.id = 'alerts'
        self.name = 'RecordingTarget'
        self._messages = []
        self._lock = threading.Lock()

    def send(self, source, message, files=None):
        with self._lock:
            self._messages.append(message)

    @property
    def messages(self):
        with self._lock:
            return list(self._messages)


def free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def wait_until(predicate, timeout=5, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError('condition was not met within %.1fs' % timeout)


def at_clock(hour, minute):
    now = time.localtime()
    return time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hour, minute, 30, 0, 0, -1))


class ConnectivitySkipTests(unittest.TestCase):
    def test_parse_windows(self):
        self.assertEqual(_parse_connectivity_skip({}), {})
        self.assertEqual(
            _parse_connectivity_skip({'node-b': ['02:30:90', '23:00:120']}),
            {'node-b': [(2 * 60 + 30, 90), (23 * 60, 120)]},
        )

    def test_parse_rejects_bad_entries(self):
        cases = [
            ['02:30:90'],
            {'node-b': '02:30:90'},
            {'node-b': ['2:30:90']},
            {'node-b': ['02:60:10']},
            {'node-b': ['24:00:10']},
            {'node-b': ['02:30:0']},
            {'node-b': ['02:30:']},
            {'node-b': ['02:30:90 ']},
            {'node-b': [90]},
            {'': ['02:30:90']},
        ]
        for bad in cases:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError) as caught:
                    _parse_connectivity_skip(bad)
                if isinstance(bad, dict) and next(iter(bad), None):
                    windows = next(iter(bad.values()))
                    if isinstance(windows, list) and windows and isinstance(windows[0], str):
                        self.assertIn(windows[0], str(caught.exception))

    def test_window_bounds(self):
        def windows(spec):
            return _parse_connectivity_skip({'node-b': [spec]})['node-b']

        daytime = windows('02:30:90')
        self.assertFalse(_connectivity_checks_skipped(daytime, at_clock(2, 29)))
        self.assertTrue(_connectivity_checks_skipped(daytime, at_clock(2, 30)))
        self.assertTrue(_connectivity_checks_skipped(daytime, at_clock(3, 59)))
        self.assertFalse(_connectivity_checks_skipped(daytime, at_clock(4, 0)))

        overnight = windows('23:30:90')
        self.assertFalse(_connectivity_checks_skipped(overnight, at_clock(23, 29)))
        self.assertTrue(_connectivity_checks_skipped(overnight, at_clock(23, 30)))
        self.assertTrue(_connectivity_checks_skipped(overnight, at_clock(0, 0)))
        self.assertTrue(_connectivity_checks_skipped(overnight, at_clock(0, 59)))
        self.assertFalse(_connectivity_checks_skipped(overnight, at_clock(1, 0)))

        all_day = windows('12:00:1440')
        self.assertTrue(_connectivity_checks_skipped(all_day, at_clock(0, 0)))
        self.assertTrue(_connectivity_checks_skipped(all_day, at_clock(11, 59)))

        almost = windows('12:00:1439')
        self.assertTrue(_connectivity_checks_skipped(almost, at_clock(12, 0)))
        self.assertTrue(_connectivity_checks_skipped(almost, at_clock(11, 58)))
        self.assertFalse(_connectivity_checks_skipped(almost, at_clock(11, 59)))

        self.assertFalse(_connectivity_checks_skipped([], at_clock(12, 0)))


class _ClusterTestCase(unittest.TestCase):
    def setUp(self):
        self._reuse = HTTPServer.allow_reuse_address
        HTTPServer.allow_reuse_address = True
        self.tmp = tempfile.mkdtemp(prefix='led-cluster-')
        self.tls_dir = os.path.join(self.tmp, 'tls')
        _ensure_certs(self.tls_dir)
        self.nodes = []

    def tearDown(self):
        for node in reversed(self.nodes):
            node.stop()
        HTTPServer.allow_reuse_address = self._reuse
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _cfg(self, name, port, members, master=False, down_min=DOWN_MIN, **extra):
        cfg = {
            'cluster_members': members,
            'cluster_master': master,
            'cluster_port': port,
            'cluster_id': CLUSTER_ID,
            'cluster_member_down_alert_min': down_min,
            'cluster_verify_tls': False,
            'cluster_tls_dir': self.tls_dir,
            'cluster_connectivity_skip': {},
        }
        cfg.update(extra)
        return cfg

    def _start(self, name, cfg):
        target = RecordingTarget()
        with mock.patch('led.cluster.socket.gethostname', return_value=name):
            node = Cluster(cfg, target)
        node.alerts = target
        self.nodes.append(node)
        node.start()
        return node


class ClusterConfigTests(_ClusterTestCase):
    def test_certs_are_created_and_reused(self):
        fresh = os.path.join(self.tmp, 'fresh')
        fullchain, privkey = _ensure_certs(fresh)
        with open(fullchain, 'rb') as fh:
            first = fh.read()
        self.assertTrue(first)
        self.assertTrue(os.path.exists(os.path.join(fresh, 'cert.pem')))
        self.assertEqual(os.path.getsize(os.path.join(fresh, 'chain.pem')), 0)
        self.assertEqual(os.stat(privkey).st_mode & 0o777, 0o600)

        again_fullchain, again_privkey = _ensure_certs(fresh)
        self.assertEqual(again_fullchain, fullchain)
        self.assertEqual(again_privkey, privkey)
        with open(fullchain, 'rb') as fh:
            self.assertEqual(fh.read(), first)

    def test_optional_fields_use_defaults(self):
        cfg = {
            'cluster_members': {'node-a': '127.0.0.1:9'},
            'cluster_port': 9,
            'cluster_id': CLUSTER_ID,
        }
        with mock.patch('led.cluster.socket.gethostname', return_value='node-a'):
            node = Cluster(cfg, RecordingTarget())
        self.assertFalse(node.is_master)
        self.assertEqual(node.down_min, 5)
        self.assertTrue(node.verify_tls)
        self.assertEqual(node.tls_dir, '/etc/led/tls')
        self.assertEqual(node.skip_periods, {})
        self.assertEqual(node.self_name, 'node-a')

    def test_invalid_skip_config_is_rejected_at_startup(self):
        cfg = self._cfg('node-a', 9, {'node-a': '127.0.0.1:9'}, cluster_connectivity_skip={'node-a': ['25:00:10']})
        with mock.patch('led.cluster.socket.gethostname', return_value='node-a'):
            with self.assertRaises(ValueError) as caught:
                Cluster(cfg, RecordingTarget())
        self.assertIn('25:00:10', str(caught.exception))

        cfg = self._cfg('node-a', 9, {'node-a': '127.0.0.1:9'}, cluster_connectivity_skip={'node-b': ['03:55:10']})
        with mock.patch('led.cluster.socket.gethostname', return_value='node-a'):
            with self.assertRaises(ValueError) as caught:
                Cluster(cfg, RecordingTarget())
        self.assertIn('node-b', str(caught.exception))

    def test_alert_names_the_member_or_falls_back_to_hostname(self):
        target = RecordingTarget()
        cfg = {
            'cluster_members': {'node-a': '127.0.0.1:9'},
            'cluster_port': 9,
            'cluster_id': CLUSTER_ID,
        }
        with mock.patch('led.cluster.socket.gethostname', return_value='not-a-member'):
            node = Cluster(cfg, target)
        self.assertIsNone(node.self_name)
        node._alert('hello')
        node.self_name = 'node-a'
        node._alert('again')
        self.assertEqual(target.messages, [
            'led alert from not-a-member:\nhello',
            'led alert from node-a:\nagain',
        ])

    def test_start_if_configured_requires_fields_and_a_real_target(self):
        self.assertIsNone(start_if_configured({}, lambda key: None))
        self.assertIsNone(start_if_configured({'cluster_members': {}}, lambda key: None))

        base = {
            'cluster_members': {'node-a': '127.0.0.1:9'},
            'cluster_port': 9,
            'cluster_id': CLUSTER_ID,
            'cluster_state_alert_target': 'alert_channel',
        }
        for field in ('cluster_port', 'cluster_id', 'cluster_state_alert_target'):
            cfg = dict(base)
            del cfg[field]
            with self.subTest(field=field):
                with self.assertRaises(ValueError) as caught:
                    start_if_configured(cfg, lambda key: RecordingTarget())
                self.assertIn(field, str(caught.exception))

        with self.assertRaises(ValueError) as caught:
            start_if_configured(base, lambda key: (_ for _ in ()).throw(KeyError(key)))
        self.assertIn('alert_channel', str(caught.exception))

    def test_start_if_configured_starts_the_node(self):
        port = free_port()
        target = RecordingTarget()
        cfg = self._cfg('node-a', port, {'node-a': '127.0.0.1:%d' % port}, master=True, down_min=1000)
        cfg['cluster_state_alert_target'] = 'alert_channel'
        with mock.patch('led.cluster.socket.gethostname', return_value='node-a'):
            node = start_if_configured(cfg, {'alert_channel': target}.__getitem__)
        self.nodes.append(node)
        node.alerts = target
        self.assertTrue(node.is_master)
        self.assertIs(node.alert_target, target)
        status, _body = _raw(port, 'GET', '/ping', auth=node.auth_hash)
        self.assertEqual(status, 200)


class ClusterPairTests(_ClusterTestCase):
    def setUp(self):
        super().setUp()
        self._interval = mock.patch('led.cluster.PING_INTERVAL_SEC', PING_INTERVAL)
        self._repeat = mock.patch('led.cluster.ALERT_REPEAT_SEC', ALERT_REPEAT)
        self._interval.start()
        self._repeat.start()

    def tearDown(self):
        self._interval.stop()
        self._repeat.stop()
        super().tearDown()

    def _pair(self, master=True, slave=True, master_extra=None, slave_extra=None, down_min=DOWN_MIN):
        port_a = free_port()
        port_b = free_port()
        members = {
            'node-a': '127.0.0.1:%d' % port_a,
            'node-b': '127.0.0.1:%d' % port_b,
        }
        nodes = {}
        if slave:
            cfg = self._cfg('node-b', port_b, members, master=False, down_min=down_min, **(slave_extra or {}))
            nodes['slave'] = self._start('node-b', cfg)
        if master:
            cfg = self._cfg('node-a', port_a, members, master=master, down_min=down_min, **(master_extra or {}))
            nodes['master'] = self._start('node-a', cfg)
        nodes['members'] = members
        nodes['ports'] = {'node-a': port_a, 'node-b': port_b}
        return nodes

    def test_handshake_ping_and_no_false_down_alert(self):
        pair = self._pair()
        master, slave = pair['master'], pair['slave']
        slave_addr = pair['members']['node-b']

        self.assertEqual(slave.master_name, 'node-a')
        self.assertIsNone(master.master_name)

        resp = master._request('POST', slave_addr, '/handshake', master._self_payload())
        self.assertEqual(resp['mode'], 'slave')
        self.assertEqual(resp['hostname'], 'node-b')
        self.assertEqual(resp['version'], LED_VERSION)

        before = slave.last_master_ping
        pong = master._request('GET', slave_addr, '/ping')
        self.assertEqual(pong, {'ping': 'pong'})
        self.assertGreaterEqual(slave.last_master_ping, before)

        wait_until(lambda: 'node-b' in master.last_slave_pings)
        self.assertNotIn('node-a', master.last_slave_pings)

        # Stay up longer than the down threshold. Healthy pings must not alert.
        time.sleep(1.5)
        self.assertEqual(master.alerts.messages, [])
        self.assertEqual(slave.alerts.messages, [])

    def test_endpoints_require_auth_and_reject_bad_handshake_json(self):
        port = free_port()
        members = {'node-a': '127.0.0.1:%d' % port}
        node = self._start('node-a', self._cfg('node-a', port, members, down_min=1000))

        status, _body = _raw(port, 'GET', '/ping')
        self.assertEqual(status, 403)
        status, _body = _raw(port, 'GET', '/ping', auth='nope')
        self.assertEqual(status, 403)
        status, _body = _raw(port, 'POST', '/handshake', body='{}')
        self.assertEqual(status, 403)
        status, _body = _raw(port, 'GET', '/other', auth=node.auth_hash)
        self.assertEqual(status, 403)

        status, _body = _raw(port, 'POST', '/handshake', body='not-json', auth=node.auth_hash)
        self.assertEqual(status, 400)

        status, body = _raw(port, 'GET', '/ping', auth=node.auth_hash)
        self.assertEqual(status, 200)
        self.assertEqual(body, b'{"ping": "pong"}')

        status, body = _raw(
            port, 'POST', '/handshake',
            body='{"version": "x", "mode": "master", "hostname": "node-a"}',
            auth=node.auth_hash,
        )
        self.assertEqual(status, 200)
        self.assertIn(b'"mode": "slave"', body)
        self.assertEqual(node.master_name, 'node-a')

    def test_startup_survives_an_unreachable_peer(self):
        port_a = free_port()
        port_b = free_port()
        members = {
            'node-a': '127.0.0.1:%d' % port_a,
            'node-b': '127.0.0.1:%d' % port_b,
        }
        master = self._start(
            'node-a',
            self._cfg('node-a', port_a, members, master=True, down_min=1000),
        )
        self.assertIsNone(master.master_name)
        self.assertEqual(master.alerts.messages, [])
        self.assertFalse(master.version_alerted)

    def test_slave_down_alerts_repeats_then_clears_on_recovery(self):
        pair = self._pair()
        master = pair['master']
        slave = pair['slave']
        wait_until(lambda: 'node-b' in master.last_slave_pings)

        slave.stop()
        wait_until(lambda: master.alerts.messages)
        self.assertEqual(len(master.alerts.messages), 1)
        self.assertRegex(
            master.alerts.messages[0],
            r"led alert from node-a:\nLost communication with node 'node-b'\. "
            r"Last successful ping was at '\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'",
        )

        time.sleep(PING_INTERVAL * 3)
        self.assertEqual(len(master.alerts.messages), 1, 'alert repeated inside the suppression window')

        with master.lock:
            master.last_alerted_at['node-b'] = time.time() - (ALERT_REPEAT + 1)
        wait_until(lambda: len(master.alerts.messages) >= 2)
        self.assertIn("Lost communication with node 'node-b'", master.alerts.messages[1])

        restarted_at = time.time()
        recovered = self._start('node-b', self._cfg(
            'node-b', pair['ports']['node-b'], pair['members'], master=False,
        ))
        self.assertIs(recovered.alert_target, recovered.alerts)

        def healthy():
            with master.lock:
                last = master.last_slave_pings.get('node-b', 0)
                still_down = 'node-b' in master.last_alerted_at
            return last >= restarted_at and not still_down

        wait_until(healthy, timeout=10)
        settled = len(master.alerts.messages)
        time.sleep(PING_INTERVAL * 5)
        self.assertEqual(len(master.alerts.messages), settled)
        with master.lock:
            self.assertNotIn('node-b', master.last_alerted_at)

    def test_master_silence_alerts_the_slave(self):
        pair = self._pair()
        master, slave = pair['master'], pair['slave']
        wait_until(lambda: 'node-b' in master.last_slave_pings)
        self.assertEqual(slave.master_name, 'node-a')

        master.stop()
        wait_until(lambda: slave.alerts.messages)
        self.assertEqual(len(slave.alerts.messages), 1)
        self.assertTrue(slave.alerts.messages[0].startswith('led alert from node-b:\n'))
        self.assertIn("Lost communication with node 'node-a'", slave.alerts.messages[0])

    def test_version_mismatch_alerts_once(self):
        port_a, port_b, port_c = free_port(), free_port(), free_port()
        members = {
            'node-a': '127.0.0.1:%d' % port_a,
            'node-b': '127.0.0.1:%d' % port_b,
            'node-c': '127.0.0.1:%d' % port_c,
        }
        slave_b = self._start('node-b', self._cfg('node-b', port_b, members, down_min=1000))
        slave_c = self._start('node-c', self._cfg('node-c', port_c, members, down_min=1000))
        _force_version(slave_b, '9.9.9')
        _force_version(slave_c, '8.8.8')

        master = self._start('node-a', self._cfg('node-a', port_a, members, master=True, down_min=1000))
        mismatches = [m for m in master.alerts.messages if 'version mismatch' in m]
        self.assertEqual(mismatches, [
            "led alert from node-a:\n"
            "cluster version mismatch with node-b: master=%s vs '9.9.9'" % LED_VERSION
        ])
        self.assertTrue(master.version_alerted)

    def test_second_master_exits(self):
        port_a = free_port()
        port_b = free_port()
        members = {
            'node-a': '127.0.0.1:%d' % port_a,
            'node-b': '127.0.0.1:%d' % port_b,
        }
        self._start('node-a', self._cfg('node-a', port_a, members, master=True, down_min=1000))

        script = """
import sys
from unittest import mock
from led.cluster import Cluster

class Target:
    id = 'alerts'
    name = 'Target'
    def send(self, source, message, files=None):
        sys.stdout.write('ALERT ' + message + '\\n')
        sys.stdout.flush()

cfg = {
    'cluster_members': {
        'node-a': '127.0.0.1:%(port_a)d',
        'node-b': '127.0.0.1:%(port_b)d',
    },
    'cluster_master': True,
    'cluster_port': %(port_b)d,
    'cluster_id': %(cluster_id)r,
    'cluster_member_down_alert_min': 1000,
    'cluster_verify_tls': False,
    'cluster_tls_dir': %(tls_dir)r,
    'cluster_connectivity_skip': {},
}
with mock.patch('led.cluster.socket.gethostname', return_value='node-b'):
    node = Cluster(cfg, Target())
node.start()
sys.stdout.write('STILL_RUNNING\\n')
sys.stdout.flush()
""" % {
            'port_a': port_a,
            'port_b': port_b,
            'cluster_id': CLUSTER_ID,
            'tls_dir': self.tls_dir,
        }
        env = os.environ.copy()
        env['PYTHONPATH'] = ROOT + os.pathsep + env.get('PYTHONPATH', '')
        proc = subprocess.run(
            [sys.executable, '-c', script],
            capture_output=True, text=True, timeout=30, env=env, cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("there's another master in the cluster", proc.stdout)
        self.assertIn('led alert from node-b:', proc.stdout)
        self.assertNotIn('STILL_RUNNING', proc.stdout)

    def test_verified_tls_rejects_self_signed_peers(self):
        pair = self._pair(
            master_extra={'cluster_verify_tls': True},
            down_min=1000,
        )
        master = pair['master']
        self.assertFalse(master.version_alerted)
        self.assertIsNone(master.master_name)
        self.assertEqual(master.alerts.messages, [])

    def test_unknown_hostname_pings_every_member(self):
        # This node's listen port is not one of the member addresses, and its
        # hostname is not a member name, so it cannot skip itself.
        port_a, port_b, port_c = free_port(), free_port(), free_port()
        members = {
            'node-b': '127.0.0.1:%d' % port_b,
            'node-c': '127.0.0.1:%d' % port_c,
        }
        self._start('node-b', self._cfg('node-b', port_b, members, down_min=1000))
        self._start('node-c', self._cfg('node-c', port_c, members, down_min=1000))
        with mock.patch('led.cluster.socket.gethostname', return_value='not-a-member'):
            stranger = Cluster(self._cfg('node-a', port_a, members, master=True, down_min=1000), RecordingTarget())
        stranger.alerts = stranger.alert_target
        self.nodes.append(stranger)
        self.assertIsNone(stranger.self_name)
        stranger.start()
        wait_until(lambda: set(stranger.last_slave_pings) == {'node-b', 'node-c'})
        self.assertEqual(stranger.alerts.messages, [])

    def test_skip_period_suppresses_pings_and_down_alerts(self):
        port_a, port_b, port_c = free_port(), free_port(), free_port()
        members = {
            'node-a': '127.0.0.1:%d' % port_a,
            'node-b': '127.0.0.1:%d' % port_b,
            'node-c': '127.0.0.1:%d' % port_c,
        }
        self._start('node-c', self._cfg('node-c', port_c, members))
        master = self._start('node-a', self._cfg(
            'node-a', port_a, members, master=True,
            cluster_connectivity_skip={'node-b': ['00:00:1440']},
        ))
        slave_b = self._start('node-b', self._cfg(
            'node-b', port_b, members,
            cluster_connectivity_skip={'node-a': ['00:00:1440']},
        ))
        wait_until(lambda: 'node-c' in master.last_slave_pings)
        time.sleep(1.5)
        self.assertNotIn('node-b', master.last_slave_pings)
        self.assertEqual(master.alerts.messages, [])
        self.assertEqual(slave_b.alerts.messages, [])

    def test_leaving_skip_period_resets_the_down_clock(self):
        port_a, port_b, port_c = free_port(), free_port(), free_port()
        members = {
            'node-a': '127.0.0.1:%d' % port_a,
            'node-b': '127.0.0.1:%d' % port_b,
            'node-c': '127.0.0.1:%d' % port_c,
        }
        state = {'skip': True}

        def skipped(periods, _now):
            return bool(periods) and state['skip']

        with mock.patch('led.cluster._connectivity_checks_skipped', side_effect=skipped):
            self._start('node-c', self._cfg('node-c', port_c, members, down_min=1000))
            master = self._start('node-a', self._cfg(
                'node-a', port_a, members, master=True,
                cluster_connectivity_skip={'node-b': ['00:00:10']},
            ))
            wait_until(lambda: 'node-c' in master.last_slave_pings)
            self.assertNotIn('node-b', master.last_slave_pings)
            self.assertEqual(master.alerts.messages, [])

            with master.lock:
                master.last_slave_pings['node-b'] = time.time() - 100000
                master.last_alerted_at['node-b'] = time.time()
            state['skip'] = False

            def resumed():
                with master.lock:
                    last = master.last_slave_pings.get('node-b', 0)
                    still_marked = 'node-b' in master.last_alerted_at
                return time.time() - last < 2 and not still_marked

            wait_until(resumed, timeout=3)
            self.assertEqual(master.alerts.messages, [])
            wait_until(
                lambda: any("Lost communication with node 'node-b'" in m for m in master.alerts.messages),
                timeout=5,
            )


def _force_version(node, version):
    original = node._self_payload

    def payload():
        data = original()
        data['version'] = version
        return data

    node._self_payload = payload


def _raw(port, method, path, body=None, auth=None):
    ctx = ssl._create_unverified_context()
    conn = http.client.HTTPSConnection('127.0.0.1', port, context=ctx, timeout=5)
    try:
        headers = {}
        data = None
        if auth is not None:
            headers['X-Cluster-Auth'] = auth
        if body is not None:
            headers['Content-Type'] = 'application/json'
            data = body
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        # 403/400 responses have no body. Reading one after the server has
        # already closed the socket raises BrokenPipeError on some versions.
        try:
            raw = resp.read()
        except (BrokenPipeError, ConnectionResetError):
            raw = b''
        return resp.status, raw
    finally:
        conn.close()


if __name__ == '__main__':
    unittest.main()
