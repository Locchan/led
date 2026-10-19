"""TargetTelegram media routing and API-error cleanup."""
import os
import tempfile
import unittest
from unittest import mock

import requests

from led.Targets.TargetTelegram import TargetTelegram, _upload_for


def _response(ok, description='Bad Request: file is too big'):
    resp = mock.Mock()
    resp.json.return_value = {'ok': ok, 'description': description}
    return resp


class UploadMethodTests(unittest.TestCase):
    def test_known_extensions(self):
        self.assertEqual(_upload_for('a.JPG'), ('sendPhoto', 'photo'))
        self.assertEqual(_upload_for('a.png'), ('sendPhoto', 'photo'))
        self.assertEqual(_upload_for('clip.mp4'), ('sendVideo', 'video'))
        self.assertEqual(_upload_for('clip.MKV'), ('sendVideo', 'video'))
        self.assertEqual(_upload_for('notes.txt'), ('sendDocument', 'document'))
        self.assertEqual(_upload_for('noext'), ('sendDocument', 'document'))


class SendTests(unittest.TestCase):
    def setUp(self):
        self.target = TargetTelegram('bot', {'bot_token': 'token', 'chat_id': '1'})
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _file(self, name, body=b'x'):
        path = os.path.join(self.tmp.name, name)
        with open(path, 'wb') as f:
            f.write(body)
        return path

    def test_photo_and_video_use_their_methods(self):
        photo = self._file('shot.png')
        video = self._file('clip.mp4')
        with mock.patch('led.Targets.TargetTelegram.requests.post', return_value=_response(True)) as post:
            self.target._send(None, 'hello', [photo, video])
        urls = [call.args[0] for call in post.call_args_list]
        self.assertIn('/sendPhoto', urls[0])
        self.assertIn('/sendVideo', urls[1])
        self.assertEqual(set(post.call_args_list[0].kwargs['files']), {'photo'})
        self.assertEqual(set(post.call_args_list[1].kwargs['files']), {'video'})
        self.assertEqual(post.call_args_list[1].kwargs['data']['supports_streaming'], 'true')
        self.assertTrue(os.path.isfile(photo))
        self.assertTrue(os.path.isfile(video))

    def test_api_error_alerts_and_removes_only_that_file(self):
        bad = self._file('big.jpg')
        good = self._file('ok.jpg')
        responses = [
            _response(False, 'Bad Request: file is too big'),
            _response(True),  # the alert text
            _response(True),  # the second file
        ]
        with mock.patch('led.Targets.TargetTelegram.requests.post', side_effect=responses) as post:
            self.target._send(None, 'hello', [bad, good])
        self.assertFalse(os.path.exists(bad))
        self.assertTrue(os.path.isfile(good))
        alert = post.call_args_list[1].kwargs['data']['text']
        self.assertIn('led alert from ', alert)
        self.assertIn(bad, alert)
        self.assertIn('file is too big', alert)
        self.assertIn('/sendPhoto', post.call_args_list[2].args[0])

    def test_timeout_leaves_the_file(self):
        path = self._file('clip.mp4')
        with mock.patch('led.Targets.TargetTelegram.requests.post', side_effect=requests.Timeout('slow')):
            with self.assertRaises(requests.Timeout):
                self.target._send(None, 'hello', [path])
        self.assertTrue(os.path.isfile(path))
